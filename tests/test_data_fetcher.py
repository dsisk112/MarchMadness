from data_fetcher import DataFetcher
DataFetcher().fetch_sports_reference_teams()
DataFetcher().fetch_rapidapi_games()
import os
print('Teams file exists:', os.path.exists('../data/teams_2023.csv'))
print('Games file exists:', os.path.exists('../data/games_2023.csv'))