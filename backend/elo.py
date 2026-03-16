import math

class EloRating:
    def __init__(self, k_factor=32, home_advantage=100):
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.ratings = {}  # team_id: rating

    def get_rating(self, team_id):
        return self.ratings.get(team_id, 1500)  # Default Elo rating

    def update_rating(self, winner_id, loser_id, winner_home=False):
        winner_rating = self.get_rating(winner_id)
        loser_rating = self.get_rating(loser_id)

        if winner_home:
            winner_rating += self.home_advantage

        expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
        expected_loser = 1 - expected_winner

        self.ratings[winner_id] = winner_rating + self.k_factor * (1 - expected_winner)
        self.ratings[loser_id] = loser_rating + self.k_factor * (0 - expected_loser)

    def predict_win_probability(self, team_a_id, team_b_id, team_a_home=False):
        rating_a = self.get_rating(team_a_id)
        rating_b = self.get_rating(team_b_id)

        if team_a_home:
            rating_a += self.home_advantage

        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))