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
        self.assertIn('Tournament prior:', prediction['metrics']['keyDrivers'][-1])


if __name__ == '__main__':
    unittest.main()