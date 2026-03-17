from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import os
import re

from mbb_api import MBBAPIClient
from injury_analyzer import InjuryAnalyzer


class BracketBuilder:
    """Builds tournament bracket from the official 2026 bracket JSON.

    Always loads the real bracket_2026.json. Optionally enriches with RapidAPI
    data for better predictions, but never falls back to mock data.
    When API data is unavailable, uses seed-based predictions.
    """

    # Bracket name → API name aliases for teams whose short names don't prefix-match
    NAME_ALIASES = {
        "cal baptist": "california baptist",
        "liu": "long island university",
    }

    # Historical upset probabilities — probability that the BETTER seed wins
    SEED_WIN_PROB = {
        (1, 16): 0.99, (1, 8): 0.80, (1, 9): 0.85, (1, 5): 0.65, (1, 4): 0.55,
        (2, 15): 0.94, (2, 7): 0.60, (2, 10): 0.75, (2, 6): 0.65, (2, 3): 0.55,
        (3, 14): 0.85, (3, 6): 0.60, (3, 11): 0.70, (3, 7): 0.55,
        (4, 13): 0.79, (4, 5): 0.55, (4, 12): 0.65, (4, 8): 0.60,
        (5, 12): 0.65, (5, 4): 0.45, (5, 13): 0.75,
        (6, 11): 0.62, (6, 3): 0.40, (6, 14): 0.80,
        (7, 10): 0.61, (7, 2): 0.40, (7, 15): 0.85,
        (8, 9): 0.51, (8, 1): 0.20,
        (9, 8): 0.49, (9, 1): 0.15,
        (10, 7): 0.39, (10, 2): 0.25,
        (11, 6): 0.38, (11, 3): 0.30,
        (12, 5): 0.35, (12, 4): 0.35,
        (13, 4): 0.21,
        (14, 3): 0.15,
        (15, 2): 0.06,
        (16, 1): 0.01,
    }

    def __init__(self, api_client: MBBAPIClient):
        self.api = api_client
        self.injury_analyzer: Optional[InjuryAnalyzer] = None
        self._predictor = None  # Lazy-loaded MatchupPredictor (shared across matchups)

    def get_tournament_bracket(
        self,
        season: int = 2026,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        """Build full bracket from bracket_2026.json with predictions."""
        start_date = start_date or datetime(season, 3, 16)
        end_date = end_date or datetime(season, 3, 20)

        # Always load real bracket — no mock fallback
        bracket_structure = self._load_bracket_structure(season)

        # Initialize injury analyzer
        try:
            self.injury_analyzer = InjuryAnalyzer(self.api, season)
        except Exception as e:
            print(f"BracketBuilder: Injury analysis unavailable: {e}")
            self.injury_analyzer = None

        # Try to enrich with API data (optional — failures are non-fatal)
        name_to_info: Dict[str, Dict] = {}
        try:
            games = self.api.get_tournament_games(start_date, end_date)
            standings = self.api.get_standings(season)
            name_to_info = self._build_name_to_team_info_map(games, standings)
            print(f"BracketBuilder: mapped {len(name_to_info)} teams from API")
        except Exception as e:
            print(f"BracketBuilder: API enrichment skipped (non-fatal): {e}")

        # Enrich bracket teams with IDs/ranks where possible
        for round_obj in bracket_structure.get("rounds", []):
            for matchup in round_obj.get("matchups", []):
                self._enrich_team(matchup.get("teamA", {}), name_to_info)
                self._enrich_team(matchup.get("teamB", {}), name_to_info)

        # Predict First Four matchups
        ff_winners = {}  # maps placeholder name -> predicted winner team dict
        for round_obj in bracket_structure.get("rounds", []):
            if round_obj.get("name") == "First Four":
                for matchup in round_obj["matchups"]:
                    self._predict_matchup(matchup, season)
                    a_name = matchup.get("teamA", {}).get("name", "")
                    b_name = matchup.get("teamB", {}).get("name", "")
                    placeholder = f"{a_name} / {b_name}"
                    winner = matchup.get("predictedWinner", matchup.get("teamA", {}))
                    ff_winners[placeholder] = dict(winner)

        # Substitute First Four winners into First Round matchups
        for round_obj in bracket_structure.get("rounds", []):
            if round_obj.get("name") == "First Round":
                for matchup in round_obj.get("matchups", []):
                    for slot in ("teamA", "teamB"):
                        team = matchup.get(slot, {})
                        name = team.get("name", "")
                        if name in ff_winners:
                            matchup[slot] = ff_winners[name]

        # Extract first round and predict
        first_round = self._get_first_round(bracket_structure)
        for matchup in first_round:
            self._predict_matchup(matchup, season)

        # Simulate remaining rounds
        subsequent_rounds = self._simulate_remaining_rounds(first_round, season)

        # Assemble final output: First Four (if present) + simulated rounds
        rounds = []
        for round_obj in bracket_structure.get("rounds", []):
            if round_obj.get("name") == "First Four":
                rounds.append(round_obj)
        rounds.extend(subsequent_rounds)

        return {"season": season, "rounds": rounds}

    # ------------------------------------------------------------------
    # Round simulation
    # ------------------------------------------------------------------

    def _simulate_remaining_rounds(self, first_round: List[Dict], season: int) -> List[Dict]:
        """Build every round from first round through Championship."""
        rounds = []
        current_matchups = first_round
        round_index = 1

        while current_matchups:
            round_name = self._round_name(round_index)
            rounds.append({"name": round_name, "matchups": current_matchups})

            if len(current_matchups) == 1:
                break

            # Collect winners and pair them into next-round matchups
            winners = [self._winner_of(m, season) for m in current_matchups]
            next_matchups = []
            for i in range(0, len(winners), 2):
                a = winners[i]
                b = winners[i + 1] if i + 1 < len(winners) else None
                if not b:
                    next_matchups.append({
                        "gameId": f"bye_{a.get('name', 'TBD')}",
                        "teamA": a,
                        "teamB": {"name": "BYE", "seed": 99},
                        "predictedWinner": a,
                        "metrics": {"keyDrivers": ["Auto-advanced (bye)"]},
                    })
                    continue
                m = {
                    "gameId": f"{a.get('name','A')}_vs_{b.get('name','B')}",
                    "teamA": a,
                    "teamB": b,
                }
                self._predict_matchup(m, season)
                next_matchups.append(m)

            current_matchups = next_matchups
            round_index += 1

        return rounds

    # ------------------------------------------------------------------
    # Prediction logic
    # ------------------------------------------------------------------

    def _predict_matchup(self, matchup: Dict, season: int):
        """Predict using API stats when available, otherwise seed-based."""
        team_a = matchup.get("teamA", {})
        team_b = matchup.get("teamB", {})
        if not team_a or not team_b:
            return

        # Try API-powered prediction when both teams have IDs
        if team_a.get("id") and team_b.get("id"):
            try:
                from matchup_predictor import MatchupPredictor
                predictor = MatchupPredictor(self.api)
                prediction = predictor.predict_matchup(
                    team_a["id"], team_b["id"], season
                )
                self._normalize_api_prediction_names(prediction, team_a, team_b)
                self._calibrate_api_prediction(prediction, team_a, team_b)
                pw = prediction.get("predictedWinner") or prediction.get("winner")
                if pw:
                    # Carry seed info from bracket data onto the winner
                    if str(pw.get("id")) == str(team_a.get("id")):
                        pw = {**{k: v for k, v in pw.items() if v}, **team_a}
                    else:
                        pw = {**{k: v for k, v in pw.items() if v}, **team_b}
                    matchup["predictedWinner"] = pw
                    matchup["metrics"] = prediction.get("metrics", {})
                    # Apply injury adjustment on top of API prediction
                    self._apply_injury_adjustment(matchup)
                    return
            except Exception as e:
                print(f"  API prediction failed for "
                      f"{team_a.get('name')} vs {team_b.get('name')}: {e}")

        # Seed-based prediction (always works)
        self._predict_by_seed(matchup)

    def _predict_by_seed(self, matchup: Dict):
        """Predict winner based on historical seed win probabilities."""
        team_a = matchup["teamA"]
        team_b = matchup["teamB"]
        seed_a = team_a.get("seed", 8)
        seed_b = team_b.get("seed", 8)

        if seed_a <= seed_b:
            better, worse = team_a, team_b
            better_seed, worse_seed = seed_a, seed_b
        else:
            better, worse = team_b, team_a
            better_seed, worse_seed = seed_b, seed_a

        win_prob = self.SEED_WIN_PROB.get(
            (better_seed, worse_seed),
            max(0.50, min(0.99, 0.50 + 0.03 * (worse_seed - better_seed))),
        )

        winner = better if win_prob >= 0.50 else worse
        final_prob = win_prob if winner is better else (1 - win_prob)
        seed_diff = abs(seed_a - seed_b)

        drivers = self._seed_drivers(better, worse, better_seed, worse_seed,
                                     win_prob, seed_diff)

        matchup["predictedWinner"] = dict(winner)
        matchup["metrics"] = {
            "winProbability": round(final_prob, 3),
            "seedDifferential": seed_diff,
            "method": "seed-based (historical)",
            "keyDrivers": drivers[:3],
        }

        # Apply injury adjustment on top of seed prediction
        self._apply_injury_adjustment(matchup)

    def _apply_injury_adjustment(self, matchup: Dict):
        """Adjust prediction based on injury impact differential."""
        if not self.injury_analyzer:
            return

        team_a = matchup.get("teamA", {})
        team_b = matchup.get("teamB", {})
        a_name = team_a.get("name", "")
        b_name = team_b.get("name", "")
        if not a_name or not b_name:
            return

        try:
            delta, info = self.injury_analyzer.get_injury_adjustment(a_name, b_name)
        except Exception as e:
            print(f"  Injury adjustment failed for {a_name} vs {b_name}: {e}")
            return

        if abs(delta) < 0.001:
            return  # No meaningful injury differential

        metrics = matchup.get("metrics", {})

        # Convert stored winner-based probability to team-A probability.
        # metrics.winProbability is winner confidence, not always team-A confidence.
        base_winner = matchup.get("predictedWinner", {})
        base_win_prob = float(metrics.get("winProbability", 0.5) or 0.5)
        base_winner_id = str(base_winner.get("id") or "")
        team_a_id = str(team_a.get("id") or "")
        team_b_id = str(team_b.get("id") or "")

        base_winner_is_a = False
        if base_winner_id and team_a_id and base_winner_id == team_a_id:
            base_winner_is_a = True
        elif base_winner_id and team_b_id and base_winner_id == team_b_id:
            base_winner_is_a = False
        else:
            base_winner_name = base_winner.get("name", "")
            if base_winner_name == a_name:
                base_winner_is_a = True
            elif base_winner_name == b_name:
                base_winner_is_a = False
            else:
                base_winner_is_a = True

        base_prob_a = base_win_prob if base_winner_is_a else (1 - base_win_prob)

        # delta > 0 means team A is healthier → increase team A win probability
        adjusted_prob_a = max(0.01, min(0.99, base_prob_a + delta))
        adjusted_winner_is_a = adjusted_prob_a >= 0.5
        adjusted_winner_prob = adjusted_prob_a if adjusted_winner_is_a else (1 - adjusted_prob_a)

        matchup["predictedWinner"] = dict(team_a if adjusted_winner_is_a else team_b)
        metrics["winProbability"] = round(adjusted_winner_prob, 3)
        metrics["injuryAdjustment"] = round(delta, 4)

        # Add injury details to metrics
        if info["teamA"]["players"]:
            metrics["injuriesTeamA"] = info["teamA"]
        if info["teamB"]["players"]:
            metrics["injuriesTeamB"] = info["teamB"]

        # Add injury driver to key drivers
        drivers = metrics.get("keyDrivers", [])
        a_impact = info["teamA"]["total_impact"]
        b_impact = info["teamB"]["total_impact"]
        if a_impact > 0 or b_impact > 0:
            healthier = a_name if a_impact < b_impact else b_name
            hurt_team = b_name if a_impact < b_impact else a_name
            hurt_impact = max(a_impact, b_impact)
            top_player = ""
            hurt_info = info["teamB"] if a_impact < b_impact else info["teamA"]
            if hurt_info["players"]:
                top = hurt_info["players"][0]
                top_player = f" ({top['player']} {top['status']}, {top['ppg']} PPG/{top['rpg']} RPG/{top['apg']} APG)"
            drivers.append(
                f"Injury edge: {healthier} healthier — {hurt_team} "
                f"losing ~{hurt_impact:.1f} composite impact{top_player}"
            )

        # Keep displayed pick reason aligned with the final winner after injury adjustment
        final_winner_name = matchup.get("predictedWinner", {}).get("name", "")
        if final_winner_name:
            pick_text = f"Pick: {final_winner_name} projects at {metrics['winProbability']:.1%}"
            if drivers:
                if isinstance(drivers[0], str) and drivers[0].startswith("Pick: "):
                    drivers[0] = pick_text
                else:
                    drivers.insert(0, pick_text)
            else:
                drivers = [pick_text]
            metrics["keyDrivers"] = drivers

        matchup["metrics"] = metrics

    @staticmethod
    def _seed_drivers(better, worse, b_seed, w_seed, prob, diff):
        drivers = []
        if diff == 0:
            drivers.append(f"Even matchup — both {b_seed}-seeds")
            drivers.append(f"{better.get('name')} slight edge ({prob:.0%})")
        elif diff <= 3:
            drivers.append(f"Competitive: #{b_seed} vs #{w_seed} seed")
            drivers.append(f"{better.get('name')} favored at {prob:.0%}")
        else:
            drivers.append(f"#{b_seed} seed {better.get('name')} heavily favored")
            drivers.append(
                f"Historical: {b_seed}-seeds beat {w_seed}-seeds {prob:.0%} of the time"
            )
        if diff >= 8:
            drivers.append("Major upset unlikely based on history")
        elif diff >= 4:
            drivers.append(f"Upset chance: {1-prob:.0%}")
        return drivers

    @staticmethod
    def _normalize_api_prediction_names(prediction: Dict, team_a: Dict, team_b: Dict):
        """Ensure API prediction text uses bracket's canonical short team names."""
        if not prediction:
            return

        api_a = prediction.get("teamA", {}).get("name")
        api_b = prediction.get("teamB", {}).get("name")
        short_a = team_a.get("name")
        short_b = team_b.get("name")

        replacements = []
        if api_a and short_a and api_a != short_a:
            replacements.append((api_a, short_a))
            replacements.append((f"{api_a}'s", f"{short_a}'s"))
            replacements.append((f"{api_a}'", f"{short_a}'"))
        if api_b and short_b and api_b != short_b:
            replacements.append((api_b, short_b))
            replacements.append((f"{api_b}'s", f"{short_b}'s"))
            replacements.append((f"{api_b}'", f"{short_b}'"))

        if not replacements:
            return

        metrics = prediction.get("metrics", {})
        drivers = metrics.get("keyDrivers", [])
        normalized = []
        for driver in drivers:
            text = driver
            for old, new in replacements:
                text = text.replace(old, new)
            normalized.append(text)
        metrics["keyDrivers"] = normalized

        # Keep response names aligned with canonical bracket names too.
        if prediction.get("teamA"):
            prediction["teamA"]["name"] = short_a or prediction["teamA"].get("name")
        if prediction.get("teamB"):
            prediction["teamB"]["name"] = short_b or prediction["teamB"].get("name")
        winner = prediction.get("predictedWinner") or prediction.get("winner")
        if winner and str(winner.get("id")) == str(team_a.get("id")):
            winner["name"] = short_a or winner.get("name")
        elif winner and str(winner.get("id")) == str(team_b.get("id")):
            winner["name"] = short_b or winner.get("name")

    def _calibrate_api_prediction(self, prediction: Dict, team_a: Dict, team_b: Dict):
        """Blend API output with a tournament seed prior to avoid cross-conference overreach."""
        if not prediction:
            return

        metrics = prediction.get("metrics", {})
        predicted_winner = prediction.get("predictedWinner") or prediction.get("winner") or {}
        api_winner_prob = float(metrics.get("winProbability", 0.5) or 0.5)
        api_prob_a = self._winner_prob_to_team_a_prob(api_winner_prob, predicted_winner, team_a, team_b)
        seed_prob_a = self._seed_probability_for_team_a(team_a, team_b)

        seed_a = int(team_a.get("seed", 8) or 8)
        seed_b = int(team_b.get("seed", 8) or 8)
        seed_diff = abs(seed_a - seed_b)
        api_weight = 0.65
        if seed_diff >= 7:
            api_weight = 0.2
        elif seed_diff >= 5:
            api_weight = 0.3
        elif seed_diff >= 3:
            api_weight = 0.4
        elif seed_diff >= 2:
            api_weight = 0.5

        calibrated_prob_a = max(0.01, min(0.99, (api_prob_a * api_weight) + (seed_prob_a * (1 - api_weight))))

        close_threshold = 0.08
        distance_from_coinflip = abs(calibrated_prob_a - 0.5)
        if distance_from_coinflip <= close_threshold:
            close_factor = 1.0 - (distance_from_coinflip / close_threshold)
            historical_weight = 0.15 + (0.20 * close_factor)
            if self._is_classic_upset_band(seed_a, seed_b):
                historical_weight = max(0.05, historical_weight - 0.10)
            calibrated_prob_a = max(
                0.01,
                min(
                    0.99,
                    (calibrated_prob_a * (1 - historical_weight)) + (seed_prob_a * historical_weight),
                ),
            )
            metrics["closeGameHistoricalWeight"] = round(historical_weight, 3)

        if self._is_classic_upset_band(seed_a, seed_b):
            max_distance = 0.20
            calibrated_prob_a = max(
                seed_prob_a - max_distance,
                min(seed_prob_a + max_distance, calibrated_prob_a),
            )

        calibrated_winner_is_a = calibrated_prob_a >= 0.5
        calibrated_winner_prob = calibrated_prob_a if calibrated_winner_is_a else (1 - calibrated_prob_a)

        metrics["apiWinProbability"] = round(api_winner_prob, 3)
        metrics["seedPriorProbability"] = round(seed_prob_a if seed_prob_a >= 0.5 else (1 - seed_prob_a), 3)
        metrics["winProbability"] = round(calibrated_winner_prob, 3)
        metrics["method"] = "api-analysis + seed calibration"

        calibrated_winner = team_a if calibrated_winner_is_a else team_b
        prediction["predictedWinner"] = {
            "id": calibrated_winner.get("id"),
            "name": calibrated_winner.get("name"),
            "winProbability": round(calibrated_winner_prob, 3),
        }

        drivers = list(metrics.get("keyDrivers", []))
        pick_text = f"Pick: {calibrated_winner.get('name')} projects at {calibrated_winner_prob:.1%}"
        if drivers:
            if isinstance(drivers[0], str) and drivers[0].startswith("Pick: "):
                drivers[0] = pick_text
            else:
                drivers.insert(0, pick_text)
        else:
            drivers = [pick_text]

        if seed_diff >= 3:
            drivers.append(
                f"Tournament prior: #{seed_a} vs #{seed_b} seed tempers raw regular-season stats"
            )
        if metrics.get("closeGameHistoricalWeight") is not None:
            if self._is_classic_upset_band(seed_a, seed_b):
                drivers.append(
                    "Close-game anchor: blended with historical upset profile for this seed band"
                )
            else:
                drivers.append(
                    "Close-game anchor: leaned toward historical seed outcomes in near coin-flip matchup"
                )
        metrics["keyDrivers"] = drivers[:4]

    @staticmethod
    def _is_classic_upset_band(seed_a: int, seed_b: int) -> bool:
        pair = tuple(sorted((seed_a, seed_b)))
        return pair in {(5, 12), (6, 11), (7, 10)}

    def _seed_probability_for_team_a(self, team_a: Dict, team_b: Dict) -> float:
        """Return the seed-based prior probability that team A wins."""
        seed_a = int(team_a.get("seed", 8) or 8)
        seed_b = int(team_b.get("seed", 8) or 8)

        if seed_a <= seed_b:
            better_seed, worse_seed = seed_a, seed_b
            better_is_a = True
        else:
            better_seed, worse_seed = seed_b, seed_a
            better_is_a = False

        better_win_prob = self.SEED_WIN_PROB.get(
            (better_seed, worse_seed),
            max(0.50, min(0.99, 0.50 + 0.03 * (worse_seed - better_seed))),
        )
        return better_win_prob if better_is_a else (1 - better_win_prob)

    @staticmethod
    def _winner_prob_to_team_a_prob(winner_prob: float, predicted_winner: Dict, team_a: Dict, team_b: Dict) -> float:
        """Convert winner-centric confidence into team A win probability."""
        winner_id = str(predicted_winner.get("id") or "")
        team_a_id = str(team_a.get("id") or "")
        team_b_id = str(team_b.get("id") or "")
        winner_name = predicted_winner.get("name", "")

        winner_is_a = False
        if winner_id and team_a_id and winner_id == team_a_id:
            winner_is_a = True
        elif winner_id and team_b_id and winner_id == team_b_id:
            winner_is_a = False
        elif winner_name == team_a.get("name"):
            winner_is_a = True
        elif winner_name == team_b.get("name"):
            winner_is_a = False
        else:
            winner_is_a = True

        return winner_prob if winner_is_a else (1 - winner_prob)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _winner_of(self, matchup: Dict, season: int) -> Dict:
        if matchup.get("predictedWinner"):
            return matchup["predictedWinner"]
        self._predict_matchup(matchup, season)
        return matchup.get("predictedWinner", matchup.get("teamA", {}))

    @staticmethod
    def _round_name(idx: int) -> str:
        return {
            1: "First Round", 2: "Second Round", 3: "Sweet 16",
            4: "Elite Eight", 5: "Final Four", 6: "Championship",
        }.get(idx, f"Round {idx}")

    def _load_bracket_structure(self, season: int) -> Dict:
        path = os.path.join(os.path.dirname(__file__), "data",
                            f"bracket_{season}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_name_to_team_info_map(
        self, games: List[Dict], standings: Dict
    ) -> Dict[str, Dict]:
        mapping: Dict[str, Dict] = {}
        for game in games:
            comp = game.get("competitions", [{}])[0]
            for c in comp.get("competitors", []):
                team = c.get("team", {})
                name = team.get("displayName") or team.get("name")
                if not name:
                    continue
                mapping[self._norm(name)] = {
                    "id": team.get("id"),
                    "name": name,
                    "rank": c.get("curatedRank", {}).get("current"),
                }
        for entry in standings.get("standings", {}).get("entries", []):
            team = entry.get("team", {})
            name = team.get("displayName") or team.get("name")
            if not name:
                continue
            n = self._norm(name)
            if n not in mapping:
                mapping[n] = {"id": team.get("id"), "name": name, "rank": None}
        return mapping

    @staticmethod
    def _norm(name: str) -> str:
        n = name.strip().lower()
        n = n.replace("&", " and ")
        n = n.replace("'", "")
        n = re.sub(r"[\.\-/(),]", " ", n)
        return re.sub(r"\s+", " ", n).strip()

    def _enrich_team(self, team: Dict, name_to_info: Dict[str, Dict]):
        if not team or "name" not in team or not name_to_info:
            return
        norm = self._norm(team["name"])
        # Check alias map
        norm = self.NAME_ALIASES.get(norm, norm)
        # Exact match first
        info = name_to_info.get(norm)
        # Prefix match: "duke" matches "duke blue devils"
        # Pick the shortest matching key to avoid "texas" → "texas tech" instead of "texas longhorns"
        if not info:
            best_key = None
            for key, val in name_to_info.items():
                if key.startswith(norm + " "):
                    if best_key is None or len(key) < len(best_key):
                        best_key = key
                        info = val
        if info:
            team["id"] = info["id"]
            if info.get("rank") is not None:
                team["rank"] = info["rank"]

    @staticmethod
    def _get_first_round(bracket: Dict) -> List[Dict]:
        for r in bracket.get("rounds", []):
            if r.get("name") == "First Round":
                return r.get("matchups", [])
        return []
