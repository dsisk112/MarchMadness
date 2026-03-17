import os
import sys
import unittest


BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from matchup_predictor import MatchupPredictor


class DummyApi:
    pass


class TestMatchupPredictorUpsetRisk(unittest.TestCase):
    def setUp(self):
        self.predictor = MatchupPredictor(DummyApi())

    @staticmethod
    def _team(name, stats):
        return {
            'team': {'displayName': name, 'id': name.lower().replace(' ', '-')},
            'stats': [{'name': k, 'value': v} for k, v in stats.items()],
            'curatedRank': {'current': 20},
        }

    @staticmethod
    def _roster(points):
        roster = []
        for idx, p in enumerate(points):
            roster.append({
                'displayName': f'P{idx}',
                'position': {'abbreviation': 'G' if idx < 2 else ('F' if idx < 4 else 'C')},
                'stats': {
                    'categories': [
                        {'stats': [
                            {'name': 'avgPoints', 'value': p},
                            {'name': 'avgRebounds', 'value': 3},
                            {'name': 'avgAssists', 'value': 2},
                        ]}
                    ]
                }
            })
        return roster

    def test_upset_risk_score_rises_with_fragility_signals(self):
        favorite = self._team('Favorite', {
            'awayWinPercent': 0.42,
            'avgPointsFor': 75.0,
            'avgPointsAgainst': 71.0,   # per-game margin = 4.0 (<6 → fragility signal)
            'avgTurnovers': 13.8,
            'winPercent': 0.76,
        })
        underdog = self._team('Underdog', {
            'awayWinPercent': 0.61,
            'avgThreePointFieldGoalsAttempted': 24.0,
            'threePointFieldGoalPct': 0.36,
            'avgTurnovers': 11.9,
            'winPercent': 0.68,
            'avgPointsFor': 73,
        })

        roster_fav = self._roster([24, 10, 8, 7, 6, 5])
        roster_dog = self._roster([15, 12, 10, 9, 8, 7])

        upset = self.predictor._calculate_upset_risk(favorite, underdog, roster_fav, roster_dog)

        self.assertGreaterEqual(upset['score'], 60)
        self.assertGreater(upset['pressure'], 0)
        self.assertTrue(len(upset['signals']) >= 1)

    def test_upset_risk_present_in_prediction_metrics(self):
        team_a = self._team('Team A', {
            'awayWinPercent': 0.48,
            'pointDifferential': 7.0,
            'avgTurnovers': 13.0,
            'winPercent': 0.74,
            'avgPointsFor': 76,
        })
        team_b = self._team('Team B', {
            'awayWinPercent': 0.55,
            'avgThreePointFieldGoalsAttempted': 23.0,
            'threePointFieldGoalPct': 0.35,
            'avgTurnovers': 12.1,
            'winPercent': 0.70,
            'avgPointsFor': 74,
        })

        roster_a = self._roster([20, 12, 9, 8, 6, 5])
        roster_b = self._roster([16, 12, 10, 9, 8, 7])

        _, metrics = self.predictor._calculate_win_probability(team_a, team_b, roster_a, roster_b)

        self.assertIn('upsetRisk', metrics)
        self.assertIn('score', metrics['upsetRisk'])
        self.assertIn('pressure', metrics['upsetRisk'])


if __name__ == '__main__':
    unittest.main()
