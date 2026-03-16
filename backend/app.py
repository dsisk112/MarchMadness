from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime
from elo import EloRating
from bracket_simulator import BracketSimulator
from data_fetcher import DataFetcher
from mbb_api import MBBAPIClient
from bracket_builder import BracketBuilder
from matchup_predictor import MatchupPredictor

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

# Initialize components
elo_system = EloRating()
simulator = BracketSimulator(elo_system)
fetcher = DataFetcher()

# New MBB API components
api_client = MBBAPIClient()
bracket_builder = BracketBuilder(api_client)
predictor = MatchupPredictor(api_client)

@app.route('/')
def home():
    return jsonify({"message": "March Madness Simulator API"})

@app.route('/api/teams')
def get_teams():
    # Fetch and return team data
    try:
        teams_df = fetcher.load_cached_data('teams_2023.csv')
        if teams_df is None:
            teams_df = fetcher.fetch_sports_reference_teams(2023)
        if teams_df is not None:
            teams = teams_df.to_dict('records')
            return jsonify({"teams": teams[:10]})  # Limit for demo
        return jsonify({"teams": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate_tournament():
    # Simulate tournament
    data = request.get_json()
    bracket_teams = data.get('teams', [])
    num_sims = data.get('simulations', 100)

    if not bracket_teams:
        return jsonify({"error": "No teams provided"}), 400

    try:
        probabilities = simulator.run_multiple_simulations(bracket_teams, num_sims)
        return jsonify({"probabilities": probabilities})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bracket')
def get_bracket():
    season = int(request.args.get('season', 2026))
    start_date_str = request.args.get('start')
    end_date_str = request.args.get('end')

    start_date = None
    end_date = None
    if start_date_str:
        start_date = datetime.fromisoformat(start_date_str)
    if end_date_str:
        end_date = datetime.fromisoformat(end_date_str)

    try:
        bracket = bracket_builder.get_tournament_bracket(season, start_date, end_date)
        return jsonify(bracket)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/matchup')
def get_matchup():
    team_a = request.args.get('teamA')
    team_b = request.args.get('teamB')
    season = int(request.args.get('season', 2026))

    if not team_a or not team_b:
        return jsonify({"error": "teamA and teamB parameters required"}), 400

    try:
        prediction = predictor.predict_matchup(team_a, team_b, season)
        return jsonify(prediction)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/schedule')
def get_schedule():
    season = int(request.args.get('season', 2026))
    start_date_str = request.args.get('start')
    end_date_str = request.args.get('end')

    start_date = datetime.fromisoformat(start_date_str) if start_date_str else datetime(season, 3, 16)
    end_date = datetime.fromisoformat(end_date_str) if end_date_str else datetime(season, 3, 20)

    try:
        games = api_client.get_tournament_games(start_date, end_date)
        return jsonify({"season": season, "games": games})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
