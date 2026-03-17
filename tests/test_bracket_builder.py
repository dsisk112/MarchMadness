import os
import sys
import unittest


BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from bracket_builder import BracketBuilder


class DummyApiClient:
    pass


class TestBracketBuilderCalibration(unittest.TestCase):
    def setUp(self):
        self.builder = BracketBuilder(DummyApiClient())

    def test_large_seed_gap_calibrates_api_overreach(self):
        prediction = {
            'predictedWinner': {
                'id': 'high-point-id',
                'name': 'High Point',
                'winProbability': 0.962,
            },
            'metrics': {
                'winProbability': 0.962,
                'method': 'api-analysis (team stats + player matchups + rankings)',
                'keyDrivers': [
                    'Pick: High Point projects at 96.2%',
                    'High Point has higher win percentage (0.882 vs 0.706)',
                ],
            },
        }
        team_a = {'id': 'wisconsin-id', 'name': 'Wisconsin', 'seed': 5}
        team_b = {'id': 'high-point-id', 'name': 'High Point', 'seed': 12}

        self.builder._calibrate_api_prediction(prediction, team_a, team_b)

        self.assertEqual(prediction['predictedWinner']['name'], 'Wisconsin')
        self.assertLess(prediction['metrics']['winProbability'], 0.70)
        self.assertEqual(
            prediction['metrics']['method'],
            'api-analysis + seed calibration',
        )
        self.assertTrue(
            any('Tournament prior:' in d for d in prediction['metrics']['keyDrivers'])
        )

    def test_close_game_gets_historical_anchor(self):
        prediction = {
            'predictedWinner': {
                'id': 'team-b-id',
                'name': 'Team B',
                'winProbability': 0.53,
            },
            'metrics': {
                'winProbability': 0.53,
                'method': 'api-analysis (team stats + player matchups + rankings)',
                'keyDrivers': ['Pick: Team B projects at 53.0%'],
            },
        }
        team_a = {'id': 'team-a-id', 'name': 'Team A', 'seed': 8}
        team_b = {'id': 'team-b-id', 'name': 'Team B', 'seed': 9}

        self.builder._calibrate_api_prediction(prediction, team_a, team_b)

        self.assertIn('closeGameHistoricalWeight', prediction['metrics'])
        self.assertTrue(
            any('Close-game anchor:' in d for d in prediction['metrics']['keyDrivers'])
        )

    def test_classic_upset_band_uses_lighter_anchor_weight(self):
        prediction = {
            'predictedWinner': {
                'id': 'seed11-id',
                'name': 'Seed 11',
                'winProbability': 0.53,
            },
            'metrics': {
                'winProbability': 0.53,
                'method': 'api-analysis (team stats + player matchups + rankings)',
                'keyDrivers': ['Pick: Seed 11 projects at 53.0%'],
            },
        }
        team_a = {'id': 'seed6-id', 'name': 'Seed 6', 'seed': 6}
        team_b = {'id': 'seed11-id', 'name': 'Seed 11', 'seed': 11}

        self.builder._calibrate_api_prediction(prediction, team_a, team_b)

        self.assertLess(prediction['metrics']['closeGameHistoricalWeight'], 0.60)
        self.assertTrue(self.builder._is_classic_upset_band(6, 11))

    def test_classic_upset_band_probability_is_capped(self):
        prediction = {
            'predictedWinner': {
                'id': 'seed6-id',
                'name': 'Seed 6',
                'winProbability': 0.95,
            },
            'metrics': {
                'winProbability': 0.95,
                'method': 'api-analysis (team stats + player matchups + rankings)',
                'keyDrivers': ['Pick: Seed 6 projects at 95.0%'],
            },
        }
        team_a = {'id': 'seed6-id', 'name': 'Seed 6', 'seed': 6}
        team_b = {'id': 'seed11-id', 'name': 'Seed 11', 'seed': 11}

        self.builder._calibrate_api_prediction(prediction, team_a, team_b)

        self.assertLessEqual(prediction['metrics']['winProbability'], 0.82)

    def test_high_upset_risk_can_flip_close_favorite(self):
        prediction = {
            'predictedWinner': {
                'id': 'seed6-id',
                'name': 'Seed 6',
                'winProbability': 0.56,
            },
            'metrics': {
                'winProbability': 0.56,
                'method': 'api-analysis (team stats + player matchups + rankings)',
                'keyDrivers': ['Pick: Seed 6 projects at 56.0%'],
                'upsetRisk': {
                    'favorite': 'Seed 6',
                    'underdog': 'Seed 11',
                    'score': 78,
                    'pressure': 0.43,
                    'signals': ['Seed 11 travels better'],
                },
            },
        }
        team_a = {'id': 'seed6-id', 'name': 'Seed 6', 'seed': 6}
        team_b = {'id': 'seed11-id', 'name': 'Seed 11', 'seed': 11}

        self.builder._calibrate_api_prediction(prediction, team_a, team_b)

        self.assertEqual(prediction['predictedWinner']['name'], 'Seed 11')
        self.assertIn('upsetRiskAdjustment', prediction['metrics'])

    def test_norm_strips_parentheses_and_punctuation(self):
        self.assertEqual(self.builder._norm('Miami (OH)'), 'miami oh')
        self.assertEqual(self.builder._norm("St. John's"), 'st johns')

    def test_enrich_team_prefers_exact_match(self):
        mapping = {
            self.builder._norm('Miami'): {'id': 'miami-id', 'name': 'Miami Hurricanes', 'rank': 18},
            self.builder._norm('Miami (OH) RedHawks'): {'id': 'miami-oh-id', 'name': 'Miami (OH) RedHawks', 'rank': None},
        }
        team = {'name': 'Miami'}

        self.builder._enrich_team(team, mapping)

        self.assertEqual(team.get('id'), 'miami-id')
        self.assertEqual(team.get('rank'), 18)

    def test_enrich_team_uses_shortest_prefix_when_no_exact_match(self):
        mapping = {
            self.builder._norm('Texas Longhorns'): {'id': 'texas-id', 'name': 'Texas Longhorns', 'rank': 9},
            self.builder._norm('Texas Tech Red Raiders'): {'id': 'ttu-id', 'name': 'Texas Tech Red Raiders', 'rank': 14},
        }
        team = {'name': 'Texas'}

        self.builder._enrich_team(team, mapping)

        self.assertEqual(team.get('id'), 'texas-id')
        self.assertEqual(team.get('rank'), 9)


if __name__ == '__main__':
    unittest.main()