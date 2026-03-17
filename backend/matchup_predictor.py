from typing import Dict, List, Any, Tuple
from mbb_api import MBBAPIClient
import math

class MatchupPredictor:
    """
    Predicts winners of basketball matchups using team stats and player matchups.
    """

    def __init__(self, api_client: MBBAPIClient):
        self.api = api_client

    def predict_matchup(self, team_a_id: str, team_b_id: str, season: int) -> Dict:
        """
        Predict winner between two teams with detailed analysis.
        """
        # Get team stats
        team_a_stats = self.api.get_team_stats(team_a_id, season)
        team_b_stats = self.api.get_team_stats(team_b_id, season)

        # If team stats unavailable, signal caller to fall back
        if not team_a_stats or not team_b_stats:
            return {}

        # Get rosters with stats
        team_a_roster = self.api.get_roster_with_stats(team_a_id, season)
        team_b_roster = self.api.get_roster_with_stats(team_b_id, season)

        # Calculate win probability
        win_prob_a, metrics = self._calculate_win_probability(
            team_a_stats, team_b_stats, team_a_roster, team_b_roster
        )

        predicted_winner = team_a_id if win_prob_a > 0.5 else team_b_id
        win_probability = win_prob_a if win_prob_a > 0.5 else 1 - win_prob_a

        return {
            'teamA': self._format_team_data(team_a_stats),
            'teamB': self._format_team_data(team_b_stats),
            'predictedWinner': {
                'id': predicted_winner,
                'name': team_a_stats['team']['displayName'] if predicted_winner == team_a_id else team_b_stats['team']['displayName'],
                'winProbability': round(win_probability, 3)
            },
            'metrics': metrics
        }

    def _calculate_win_probability(self, team_a: Dict, team_b: Dict,
                                 roster_a: List[Dict], roster_b: List[Dict]) -> Tuple[float, Dict]:
        """
        Calculate win probability using multiple factors.
        """
        metrics = {}

        # Team-level stats comparison
        team_score = self._compare_team_stats(team_a, team_b)
        metrics['teamComparison'] = team_score

        # Player matchup analysis
        player_score = self._analyze_player_matchups(roster_a, roster_b)
        metrics['playerMatchups'] = player_score

        # Ranking factor
        ranking_score = self._compare_rankings(team_a, team_b)
        metrics['ranking'] = ranking_score

        # Combine scores (weighted average)
        total_score = (team_score * 0.5) + (player_score * 0.3) + (ranking_score * 0.2)

        # Upset risk context (derived only from available team + roster stats)
        favorite_is_a = total_score >= 0
        if favorite_is_a:
            upset_context = self._calculate_upset_risk(team_a, team_b, roster_a, roster_b)
            total_score -= upset_context['pressure']
        else:
            upset_context = self._calculate_upset_risk(team_b, team_a, roster_b, roster_a)
            total_score += upset_context['pressure']
        metrics['upsetRisk'] = upset_context

        # Convert to probability using sigmoid
        win_prob = 1 / (1 + math.exp(-total_score))

        metrics['winProbability'] = round(win_prob if win_prob > 0.5 else 1 - win_prob, 3)
        metrics['method'] = 'api-analysis (team stats + player matchups + rankings)'

        # Key drivers (winner-first, with explicit close-game context)
        metrics['keyDrivers'] = self._generate_key_drivers(
            team_a, team_b, roster_a, roster_b, win_prob, upset_context
        )

        return win_prob, metrics

    def _compare_team_stats(self, team_a: Dict, team_b: Dict) -> float:
        """
        Compare team-level statistics.
        Returns positive score if team_a is stronger.
        """
        stats_a = team_a.get('stats', [])
        stats_b = team_b.get('stats', [])

        # Extract key stats
        def get_stat_value(stats: List[Dict], name: str) -> float:
            for stat in stats:
                if stat['name'] == name:
                    return stat.get('value', 0)
            return 0

        # Key metrics (higher is better for team_a)
        win_percent_a = get_stat_value(stats_a, 'winPercent')
        win_percent_b = get_stat_value(stats_b, 'winPercent')
        win_percent_diff = win_percent_a - win_percent_b

        points_for_a = get_stat_value(stats_a, 'avgPointsFor')
        points_for_b = get_stat_value(stats_b, 'avgPointsFor')
        points_diff = points_for_a - points_for_b

        point_diff_a = get_stat_value(stats_a, 'pointDifferential')
        point_diff_b = get_stat_value(stats_b, 'pointDifferential')
        diff_diff = point_diff_a - point_diff_b

        # Normalize and combine
        score = (win_percent_diff * 2) + (points_diff * 0.1) + (diff_diff * 0.01)
        return score

    @staticmethod
    def _get_position_abbr(player: Dict) -> str:
        """Extract position abbreviation from player dict."""
        pos = player.get('position', '')
        if isinstance(pos, dict):
            return pos.get('abbreviation', '')
        return str(pos)

    def _analyze_player_matchups(self, roster_a: List[Dict], roster_b: List[Dict]) -> float:
        """
        Analyze player matchups by position group (G, F, C).
        """
        positions = ['G', 'F', 'C']

        score = 0
        for pos in positions:
            players_a = [p for p in roster_a if self._get_position_abbr(p) == pos]
            players_b = [p for p in roster_b if self._get_position_abbr(p) == pos]

            if players_a and players_b:
                # Compare top players at position
                top_a = max(players_a, key=lambda p: self._get_player_score(p))
                top_b = max(players_b, key=lambda p: self._get_player_score(p))

                score += self._get_player_score(top_a) - self._get_player_score(top_b)

        return score * 0.1  # Scale down

    def _get_player_score(self, player: Dict) -> float:
        """Calculate player strength score from nested categories structure."""
        stats_data = player.get('stats', {})
        ppg = self._extract_stat(stats_data, 'avgPoints')
        rpg = self._extract_stat(stats_data, 'avgRebounds')
        apg = self._extract_stat(stats_data, 'avgAssists')
        return ppg + rpg + apg

    @staticmethod
    def _extract_stat(stats_data: Dict, stat_name: str) -> float:
        """Extract a named stat from the nested categories structure."""
        if not stats_data:
            return 0.0
        for cat in stats_data.get('categories', []):
            for stat in cat.get('stats', []):
                if stat.get('name') == stat_name:
                    return float(stat.get('value', 0))
        return 0.0

    def _compare_rankings(self, team_a: Dict, team_b: Dict) -> float:
        """Compare team rankings."""
        rank_a = team_a.get('curatedRank', {}).get('current', 100)
        rank_b = team_b.get('curatedRank', {}).get('current', 100)

        # Lower rank number is better
        if rank_a < rank_b:
            return 1.0
        elif rank_b < rank_a:
            return -1.0
        return 0

    def _generate_key_drivers(self, team_a: Dict, team_b: Dict,
                            roster_a: List[Dict], roster_b: List[Dict], win_prob_a: float,
                            upset_context: Dict = None) -> List[str]:
        """Generate winner-first reasons and call out what keeps games close."""
        team_a_name = team_a['team']['displayName']
        team_b_name = team_b['team']['displayName']

        winner_is_a = win_prob_a >= 0.5
        winner_name = team_a_name if winner_is_a else team_b_name
        loser_name = team_b_name if winner_is_a else team_a_name
        winner_prob = win_prob_a if winner_is_a else (1 - win_prob_a)

        reasons_for_a: List[str] = []
        reasons_for_b: List[str] = []

        win_pct_a = self._get_stat_value(team_a, 'winPercent')
        win_pct_b = self._get_stat_value(team_b, 'winPercent')
        if win_pct_a > win_pct_b:
            reasons_for_a.append(
                f"{team_a_name} has higher win percentage ({win_pct_a:.3f} vs {win_pct_b:.3f})"
            )
        elif win_pct_b > win_pct_a:
            reasons_for_b.append(
                f"{team_b_name} has higher win percentage ({win_pct_b:.3f} vs {win_pct_a:.3f})"
            )

        rank_a = team_a.get('curatedRank', {}).get('current')
        rank_b = team_b.get('curatedRank', {}).get('current')
        if rank_a and rank_b:
            if rank_a < rank_b:
                reasons_for_a.append(f"{team_a_name} is ranked higher (#{rank_a} vs #{rank_b})")
            elif rank_b < rank_a:
                reasons_for_b.append(f"{team_b_name} is ranked higher (#{rank_b} vs #{rank_a})")

        for pos in ['G', 'F', 'C']:
            top_a = self._get_top_player_at_pos(roster_a, pos)
            top_b = self._get_top_player_at_pos(roster_b, pos)
            if top_a and top_b:
                score_a = self._get_player_score(top_a)
                score_b = self._get_player_score(top_b)
                if score_a > score_b:
                    reasons_for_a.append(
                        f"{self._possessive(team_a_name)} {pos} ({top_a.get('displayName','?')}) outperforms {self._possessive(team_b_name)} {pos}"
                    )
                elif score_b > score_a:
                    reasons_for_b.append(
                        f"{self._possessive(team_b_name)} {pos} ({top_b.get('displayName','?')}) outperforms {self._possessive(team_a_name)} {pos}"
                    )

        winner_reasons = reasons_for_a if winner_is_a else reasons_for_b
        loser_reasons = reasons_for_b if winner_is_a else reasons_for_a

        closeness = abs(win_prob_a - 0.5)
        drivers = [
            f"Pick: {winner_name} projects at {winner_prob:.1%}"
        ]

        if winner_reasons:
            drivers.append(winner_reasons[0])

        if closeness <= 0.08:
            if loser_reasons:
                drivers.append(f"Close factor: {loser_reasons[0]}")
            else:
                drivers.append(f"Close factor: {winner_name} has only a slim model edge over {loser_name}")
        else:
            drivers.append(f"Model edge: {winner_name} has a clear profile advantage")

        if upset_context and upset_context.get('score', 0) >= 60:
            drivers.append(
                f"Upset risk: {upset_context.get('underdog')} profile pressure is elevated ({upset_context.get('score')}/100)"
            )

        return drivers[:3]

    def _calculate_upset_risk(self, favorite: Dict, underdog: Dict,
                            roster_fav: List[Dict], roster_dog: List[Dict]) -> Dict:
        """Calculate upset pressure against the current favorite using available and derived stats."""
        signals: List[str] = []
        risk_points = 0.0

        favorite_name = favorite['team']['displayName']
        underdog_name = underdog['team']['displayName']

        # 1) Road/neutral form proxy
        fav_away = self._get_away_win_pct(favorite)
        dog_away = self._get_away_win_pct(underdog)
        if fav_away is not None and dog_away is not None and dog_away > fav_away:
            delta = dog_away - fav_away
            risk_points += min(14.0, delta * 28.0)
            signals.append(f"{underdog_name} travels better ({dog_away:.3f} vs {fav_away:.3f})")

        # 2) Favorite fragility in per-game margin
        fav_ppg = self._get_stat_value_any(favorite, ['avgPointsFor'])
        fav_ppga = self._get_stat_value_any(favorite, ['avgPointsAgainst'])
        if fav_ppg is not None and fav_ppga is not None:
            fav_margin = fav_ppg - fav_ppga
            if fav_margin < 6:
                risk_points += 12.0
                signals.append(f"{favorite_name} has a thin per-game margin ({fav_margin:.1f} pts)")
            elif fav_margin < 10:
                risk_points += 6.0

        # 3) Top-heavy scoring risk (few big scorers)
        fav_top_share = self._top_scorer_share(roster_fav)
        dog_top_share = self._top_scorer_share(roster_dog)
        if fav_top_share is not None and dog_top_share is not None:
            if fav_top_share - dog_top_share > 0.10:
                risk_points += 12.0
                signals.append(f"{favorite_name} offense is more top-heavy")

        # 4) Underdog three-point path
        dog_3pa = self._get_stat_value_any(underdog, ['avgThreePointFieldGoalsAttempted', 'threePointFieldGoalsAttempted'])
        dog_3p_pct = self._get_stat_value_any(underdog, ['threePointFieldGoalPct', 'avgThreePointFieldGoalPct'])
        if dog_3pa is not None and dog_3p_pct is not None:
            if dog_3pa >= 22 and dog_3p_pct >= 0.34:
                risk_points += 8.0
                signals.append(f"{underdog_name} has a live 3PT upset profile")

        # 5) Turnover edge proxy
        fav_to = self._get_stat_value_any(favorite, ['avgTurnovers'])
        dog_to = self._get_stat_value_any(underdog, ['avgTurnovers'])
        if fav_to is not None and dog_to is not None and fav_to - dog_to >= 1.5:
            risk_points += 6.0
            signals.append(f"{favorite_name} is sloppier with the ball")

        score = int(max(5, min(95, round(20 + risk_points))))
        pressure = max(0.0, min(0.45, (score - 35) / 100.0))

        return {
            'favorite': favorite_name,
            'underdog': underdog_name,
            'score': score,
            'pressure': round(pressure, 3),
            'signals': signals[:3],
        }

    def _get_away_win_pct(self, team: Dict) -> float:
        # Try direct stat names first
        away_pct = self._get_stat_value_any(team, ['awayWinPercent', 'roadWinPercent'])
        if away_pct is not None:
            return away_pct

        # Parse the 'Road' stat's summary string (e.g. '2-8' -> 0.20)
        for stat in team.get('stats', []):
            if stat.get('name') == 'Road' and stat.get('summary'):
                try:
                    w, l = [int(x) for x in str(stat['summary']).split('-')[:2]]
                    if w + l > 0:
                        return w / (w + l)
                except (ValueError, AttributeError):
                    pass

        # Fallback: separate wins/losses fields
        away_wins = self._get_stat_value_any(team, ['awayWins', 'roadWins'])
        away_losses = self._get_stat_value_any(team, ['awayLosses', 'roadLosses'])
        if away_wins is not None and away_losses is not None and (away_wins + away_losses) > 0:
            return away_wins / (away_wins + away_losses)

        return None

    def _top_scorer_share(self, roster: List[Dict]) -> float:
        points = []
        for player in roster:
            ppg = self._extract_stat(player.get('stats', {}), 'avgPoints')
            if ppg > 0:
                points.append(ppg)
        if len(points) < 4:
            return None
        total = sum(points)
        if total <= 0:
            return None
        return max(points) / total

    def _get_stat_value_any(self, team: Dict, stat_names: List[str]) -> float:
        stats = team.get('stats', [])
        for name in stat_names:
            for stat in stats:
                if stat.get('name') == name:
                    try:
                        return float(stat.get('value', 0))
                    except (TypeError, ValueError):
                        return None
        return None

    def _get_stat_value(self, team: Dict, stat_name: str) -> float:
        """Helper to get stat value."""
        stats = team.get('stats', [])
        for stat in stats:
            if stat['name'] == stat_name:
                return stat.get('value', 0)
        return 0

    def _get_top_player_at_pos(self, roster: List[Dict], position: str) -> Dict:
        """Get top player at position."""
        pos_players = [p for p in roster if self._get_position_abbr(p) == position]
        return max(pos_players, key=self._get_player_score) if pos_players else None

    @staticmethod
    def _possessive(name: str) -> str:
        """Format possessive team names for readable text."""
        return f"{name}'" if name.endswith('s') else f"{name}'s"

    def _format_team_data(self, team: Dict) -> Dict:
        """Format team data for API response."""
        return {
            'id': team['team']['id'],
            'name': team['team']['displayName'],
            'stats': {
                stat['name']: stat.get('value', 0)
                for stat in team.get('stats', [])
            }
        }