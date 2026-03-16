from elo import EloRating
import random

class BracketSimulator:
    def __init__(self, elo_system):
        self.elo = elo_system

    def simulate_game(self, team_a, team_b, team_a_home=False):
        """Simulate a single game between two teams"""
        prob_a_wins = self.elo.predict_win_probability(team_a, team_b, team_a_home)
        return team_a if random.random() < prob_a_wins else team_b

    def simulate_round(self, teams):
        """Simulate a round of games"""
        winners = []
        for i in range(0, len(teams), 2):
            winner = self.simulate_game(teams[i], teams[i+1])
            winners.append(winner)
        return winners

    def simulate_tournament(self, bracket_teams):
        """Simulate full tournament"""
        current_round = bracket_teams
        round_num = 1
        results = {}

        while len(current_round) > 1:
            results[f'round_{round_num}'] = current_round.copy()
            current_round = self.simulate_round(current_round)
            round_num += 1

        results['champion'] = current_round[0]
        return results

    def run_multiple_simulations(self, bracket_teams, num_sims=1000):
        """Run multiple simulations and return win probabilities"""
        champions = {}
        for _ in range(num_sims):
            result = self.simulate_tournament(bracket_teams)
            champ = result['champion']
            champions[champ] = champions.get(champ, 0) + 1

        # Convert to probabilities
        total = sum(champions.values())
        probabilities = {team: count / total for team, count in champions.items()}
        return probabilities