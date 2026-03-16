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

        # Convert to probability using sigmoid
        win_prob = 1 / (1 + math.exp(-total_score))

        metrics['winProbability'] = round(win_prob if win_prob > 0.5 else 1 - win_prob, 3)
        metrics['method'] = 'api-analysis (team stats + player matchups + rankings)'

        # Key drivers (winner-first, with explicit close-game context)
        metrics['keyDrivers'] = self._generate_key_drivers(
            team_a, team_b, roster_a, roster_b, win_prob
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
                            roster_a: List[Dict], roster_b: List[Dict], win_prob_a: float) -> List[str]:
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

        return drivers[:3]

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