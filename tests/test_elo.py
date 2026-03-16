import unittest
from backend.elo import EloRating

class TestEloRating(unittest.TestCase):
    def setUp(self):
        self.elo = EloRating()

    def test_initial_rating(self):
        self.assertEqual(self.elo.get_rating('team1'), 1500)

    def test_update_rating(self):
        self.elo.update_rating('team1', 'team2')
        self.assertGreater(self.elo.get_rating('team1'), 1500)
        self.assertLess(self.elo.get_rating('team2'), 1500)

    def test_predict_probability(self):
        prob = self.elo.predict_win_probability('team1', 'team2')
        self.assertGreater(prob, 0)
        self.assertLess(prob, 1)

if __name__ == '__main__':
    unittest.main()