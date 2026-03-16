"""Injury impact analysis for NCAA tournament predictions.

Loads injury data from injuries_2026.json, fetches real player stats from
the RapidAPI, and computes a team-level injury penalty based on how much
production the injured players represent.
"""

import json
import os
import re
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from mbb_api import MBBAPIClient


# Status weights: how much of the player's production to subtract
STATUS_WEIGHT = {
    "Out": 1.0,
    "Questionable": 0.5,
    "Probable": 0.15,
    "Day-to-Day": 0.35,
}

# Positional fallback PPG estimates when API stats aren't available
POSITION_FALLBACK_PPG = {"G": 8.0, "F": 7.0, "C": 6.5, "F-C": 6.5, "G-F": 7.5}


class InjuryAnalyzer:
    """Computes injury-based win probability adjustments."""

    def __init__(self, api_client: MBBAPIClient, season: int = 2026):
        self.api = api_client
        self.season = season
        self._injuries: Dict[str, Dict] = {}
        self._roster_cache: Dict[str, List[Dict]] = {}  # team_name -> roster
        self._team_games_cache: Dict[str, Optional[float]] = {}  # team_name -> current season games
        self._player_stats_cache: Dict[str, Dict] = {}  # player_id -> stats
        self._load_injuries()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_injury_adjustment(
        self, team_a_name: str, team_b_name: str
    ) -> Tuple[float, Dict]:
        """Return a probability adjustment and explanation dict.

        Returns (delta, info) where:
          - delta > 0 means team A is relatively healthier (boost A's prob)
          - delta < 0 means team B is relatively healthier (boost B's prob)
          - info contains per-team details for the frontend / key drivers
        """
        impact_a = self._team_injury_impact(team_a_name)
        impact_b = self._team_injury_impact(team_b_name)

        # Difference: positive ⇒ team B is more hurt ⇒ boost team A
        raw_diff = impact_b["total_impact"] - impact_a["total_impact"]

        # Scale: a 10-PPG differential maps to roughly ±0.05 probability shift
        # Cap at ±0.12 so injuries can swing but not dominate predictions
        adjustment = max(-0.12, min(0.12, raw_diff * 0.005))

        info = {
            "teamA": impact_a,
            "teamB": impact_b,
            "adjustment": round(adjustment, 4),
        }
        return adjustment, info

    # ------------------------------------------------------------------
    # Impact calculation
    # ------------------------------------------------------------------

    def _team_injury_impact(self, team_name: str) -> Dict:
        """Compute aggregate injury impact for a team.

        Returns dict with total_impact (lost PPG-equivalent), player details.
        """
        injury_team_name = self._resolve_injury_team_name(team_name)
        team_data = self._injuries.get(injury_team_name) if injury_team_name else None

        if not team_data or not team_data.get("injuries"):
            return {"total_impact": 0.0, "players": [], "team": team_name}

        injuries = team_data["injuries"]

        # Filter out redshirt injuries (those players wouldn't play anyway)
        active_injuries = [
            inj for inj in injuries if inj.get("injury", "").lower() != "redshirt"
        ]

        if not active_injuries:
            return {"total_impact": 0.0, "players": [], "team": team_name}

        # Try to fetch real stats for injured players via roster lookup
        roster = self._get_roster(team_name, team_data)
        team_games_played = self._get_team_games_played(team_name)

        total_impact = 0.0
        player_details = []

        for inj in active_injuries:
            status_w = STATUS_WEIGHT.get(inj["status"], 0.5)
            player_name = inj["player"]
            position = inj.get("position", "G")
            is_preseason_carryover = self._is_preseason_carryover_injury(inj)
            updated_year = self._injury_updated_year(inj)

            # Preseason "Out" entries are usually stale carryover data for the
            # next tournament season (or redshirt-like cases), so exclude older
            # years while keeping recent preseason injuries (e.g., players who
            # were active this season and are now ruled out).
            if (
                is_preseason_carryover
                and inj.get("status") == "Out"
                and (updated_year is None or updated_year < (self.season - 1))
            ):
                continue

            # Try to find this player in the roster and get their stats
            ppg, rpg, apg, has_current_production, games_played = self._get_player_stats(
                player_name, position, roster
            )

            if is_preseason_carryover:
                # Ignore clearly stale cases:
                # - no current-season production, or
                # - older-year entries with ambiguous historical production
                if not has_current_production:
                    continue
                if updated_year is not None and updated_year < (self.season - 1):
                    continue
                # Keep non-Out preseason injuries but damp them and cap to
                # fallback-level production so old seasons don't dominate.
                fallback_ppg = POSITION_FALLBACK_PPG.get(position, 6.0)
                fallback_rpg = 3.0 if position in ("F", "C", "F-C") else 2.0
                fallback_apg = 3.0 if position in ("G", "G-F") else 1.5
                ppg = min(ppg, fallback_ppg)
                rpg = min(rpg, fallback_rpg)
                apg = min(apg, fallback_apg)
                if inj.get("status") != "Out":
                    status_w *= 0.35

            # Composite impact score weighted toward scoring
            impact = (ppg * 1.0 + rpg * 0.4 + apg * 0.6) * status_w

            total_impact += impact
            player_details.append({
                "player": player_name,
                "position": position,
                "status": inj["status"],
                "injury": inj.get("injury", "Unknown"),
                "ppg": round(ppg, 1),
                "rpg": round(rpg, 1),
                "apg": round(apg, 1),
                "impact": round(impact, 2),
            })

        # Sort by impact descending
        player_details.sort(key=lambda p: p["impact"], reverse=True)

        return {
            "total_impact": round(total_impact, 2),
            "players": player_details,
            "team": team_name,
        }

    def _resolve_injury_team_name(self, team_name: str) -> Optional[str]:
        """Resolve API/bracket team names to keys in injuries_2026.json.

        Examples:
          - "Duke Blue Devils" -> "Duke"
          - "NC State Wolfpack" -> "NC State"
          - "St. John's Red Storm" -> "St. John's"
        """
        if not team_name or not self._injuries:
            return None

        norm = self._norm(team_name)

        # 1) Exact normalized key match
        for name in self._injuries.keys():
            if self._norm(name) == norm:
                return name

        # 2) Prefix match in either direction, choose shortest matching injury key
        best_match = None
        best_len = None
        for name in self._injuries.keys():
            injury_norm = self._norm(name)
            if norm.startswith(injury_norm + " ") or injury_norm.startswith(norm + " "):
                if best_len is None or len(injury_norm) < best_len:
                    best_match = name
                    best_len = len(injury_norm)

        return best_match

    # ------------------------------------------------------------------
    # Roster + player stats lookup
    # ------------------------------------------------------------------

    def _get_roster(self, team_name: str, team_data: Dict) -> List[Dict]:
        """Fetch and cache roster for a team."""
        norm = self._norm(team_name)
        if norm in self._roster_cache:
            return self._roster_cache[norm]

        roster = []
        try:
            standings = self.api.get_standings(self.season)
            team_id = None
            best_len = None
            for entry in standings.get("standings", {}).get("entries", []):
                t = entry.get("team", {})
                t_name = t.get("displayName") or t.get("name", "")
                t_norm = self._norm(t_name)
                # Exact match wins immediately
                if t_norm == norm:
                    team_id = t.get("id")
                    break
                # Prefix match — prefer shortest to avoid "texas" → "texas tech"
                if t_norm.startswith(norm + " "):
                    if best_len is None or len(t_norm) < best_len:
                        best_len = len(t_norm)
                        team_id = t.get("id")

            if team_id:
                roster_data = self.api.get_team_roster(team_id, self.season)
                roster = roster_data.get("athletes", [])
        except Exception as e:
            print(f"  InjuryAnalyzer: Could not fetch roster for {team_name}: {e}")

        self._roster_cache[norm] = roster
        return roster

    def _get_player_stats(
        self, player_name: str, position: str, roster: List[Dict]
    ) -> Tuple[float, float, float, bool, float]:
        """Get (PPG, RPG, APG, has_current_production, games_played)."""
        # Try to match player in roster by short name (e.g. "C. Foster")
        matched = self._match_player(player_name, roster)

        if matched:
            player_id = matched.get("id")
            if player_id:
                stats = self._fetch_player_stats(player_id)
                if stats:
                    ppg = self._extract_stat(stats, "avgPoints")
                    rpg = self._extract_stat(stats, "avgRebounds")
                    apg = self._extract_stat(stats, "avgAssists")
                    games_played = self._extract_stat(stats, "gamesPlayed")
                    has_current_production = (
                        games_played > 0 or ppg > 0 or rpg > 0 or apg > 0
                    )
                    if has_current_production:
                        return ppg, rpg, apg, True, games_played
                    # Explicitly return zero production if the player is on
                    # roster but has not played this season.
                    return 0.0, 0.0, 0.0, False, games_played

        # Fallback: position-based estimate
        fallback_ppg = POSITION_FALLBACK_PPG.get(position, 6.0)
        fallback_rpg = 3.0 if position in ("F", "C", "F-C") else 2.0
        fallback_apg = 3.0 if position in ("G", "G-F") else 1.5
        return fallback_ppg, fallback_rpg, fallback_apg, True, 0.0

    def _get_team_games_played(self, team_name: str) -> Optional[float]:
        """Get current-season team games played from standings (wins + losses)."""
        norm = self._norm(team_name)
        if norm in self._team_games_cache:
            return self._team_games_cache[norm]

        games_played = None
        try:
            standings = self.api.get_standings(self.season)
            best_len = None
            for entry in standings.get("standings", {}).get("entries", []):
                t = entry.get("team", {})
                t_name = t.get("displayName") or t.get("name", "")
                t_norm = self._norm(t_name)
                if t_norm == norm:
                    wins = float(self._entry_stat(entry, "wins"))
                    losses = float(self._entry_stat(entry, "losses"))
                    games_played = wins + losses
                    break
                if t_norm.startswith(norm + " "):
                    if best_len is None or len(t_norm) < best_len:
                        best_len = len(t_norm)
                        wins = float(self._entry_stat(entry, "wins"))
                        losses = float(self._entry_stat(entry, "losses"))
                        games_played = wins + losses
        except Exception as e:
            print(f"  InjuryAnalyzer: Could not fetch team games for {team_name}: {e}")

        self._team_games_cache[norm] = games_played
        return games_played

    @staticmethod
    def _entry_stat(entry: Dict, stat_name: str) -> float:
        for stat in entry.get("stats", []):
            if stat.get("name") == stat_name:
                return float(stat.get("value", 0) or 0)
        return 0.0

    def _is_preseason_carryover_injury(self, injury: Dict) -> bool:
        """True when injury update predates the current season's start window."""
        updated = injury.get("updated")
        if not updated:
            return False
        try:
            updated_date = datetime.strptime(updated, "%Y-%m-%d").date()
        except ValueError:
            return False
        return updated_date < self._season_start_date()

    @staticmethod
    def _injury_updated_year(injury: Dict) -> Optional[int]:
        updated = injury.get("updated")
        if not updated:
            return None
        try:
            return datetime.strptime(updated, "%Y-%m-%d").year
        except ValueError:
            return None

    def _season_start_date(self) -> date:
        """Approximate season start date for a given tournament year."""
        # 2026 tournament corresponds to the 2025-26 season.
        return date(self.season - 1, 11, 1)

    def _match_player(self, short_name: str, roster: List[Dict]) -> Optional[Dict]:
        """Match abbreviated name (e.g. 'C. Foster') to a roster entry.

        Roster entries have displayName ('Cameron Foster') and
        shortName ('C. Foster'), so we try direct shortName match first,
        then fall back to initial + last name parsing of displayName.
        """
        if not roster or not short_name:
            return None

        inj_norm = short_name.strip().lower()

        # Direct shortName match (most reliable)
        for player in roster:
            sn = (player.get("shortName") or "").strip().lower()
            if sn and sn == inj_norm:
                return player

        # Parse "C. Foster" → first_initial="C", last="foster"
        parts = short_name.split(". ", 1)
        if len(parts) == 2:
            first_initial = parts[0].strip().upper()
            last_name = parts[1].strip().lower()
        else:
            first_initial = None
            last_name = short_name.strip().lower()

        for player in roster:
            display = player.get("displayName", "")
            d_parts = display.rsplit(" ", 1)
            if len(d_parts) == 2:
                d_first, d_last = d_parts[0], d_parts[1]
            else:
                d_first, d_last = "", display

            if d_last.lower() == last_name:
                if first_initial is None:
                    return player
                if d_first and d_first[0].upper() == first_initial:
                    return player

        return None

    def _fetch_player_stats(self, player_id: str) -> Optional[Dict]:
        """Fetch player season stats, with caching."""
        if player_id in self._player_stats_cache:
            return self._player_stats_cache[player_id]

        try:
            stats = self.api.get_player_stats(player_id)
            self._player_stats_cache[player_id] = stats
            return stats
        except Exception as e:
            print(f"  InjuryAnalyzer: Could not fetch stats for player {player_id}: {e}")
            self._player_stats_cache[player_id] = None
            return None

    @staticmethod
    def _extract_stat(stats_data: Dict, stat_name: str) -> float:
        """Extract a named stat from the nested categories structure."""
        if not stats_data:
            return 0.0
        for cat in stats_data.get("categories", []):
            for stat in cat.get("stats", []):
                if stat.get("name") == stat_name:
                    return float(stat.get("value", 0))
        return 0.0

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_injuries(self):
        """Load injuries JSON from backend/data/."""
        path = os.path.join(
            os.path.dirname(__file__), "data", f"injuries_{self.season}.json"
        )
        if not os.path.exists(path):
            print(f"InjuryAnalyzer: No injury file at {path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._injuries = data.get("teams", {})
        count = sum(
            len(t.get("injuries", [])) for t in self._injuries.values()
        )
        print(f"InjuryAnalyzer: Loaded {count} injuries across "
              f"{len(self._injuries)} teams")

    @staticmethod
    def _norm(name: str) -> str:
        n = name.strip().lower()
        n = re.sub(r"[\.\-'/&]", " ", n)
        return re.sub(r"\s+", " ", n)
