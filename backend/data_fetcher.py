import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import datetime

class DataFetcher:
    def __init__(self, rapidapi_key=None):
        self.rapidapi_key = rapidapi_key or os.getenv('RAPIDAPI_KEY')
        self.data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        os.makedirs(self.data_dir, exist_ok=True)

    def fetch_sports_reference_teams(self, year=2023):
        """Scrape team data from Sports-Reference.com"""
        url = f"https://www.sports-reference.com/cbb/seasons/{year}-school-stats.html"
        try:
            df = pd.read_html(url)[0]
            print("Parsed df shape:", df.shape)
            file_path = os.path.join(self.data_dir, f'teams_{year}.csv')
            df.to_csv(file_path, index=False)
            print(f"Saved to {file_path}")
            return df
        except Exception as e:
            print(f"Error fetching or parsing: {e}")
            return None

    def fetch_rapidapi_games(self, season=2022):
        """Fetch games data from Sports-Reference.com"""
        url = f"https://www.sports-reference.com/cbb/seasons/{season}-schedule.html"
        try:
            df = pd.read_html(url)[0]
            print("Parsed games df shape:", df.shape)
            file_path = os.path.join(self.data_dir, f'games_{season}.csv')
            df.to_csv(file_path, index=False)
            print(f"Saved games to {file_path}")
            return df
        except Exception as e:
            print(f"Error fetching games: {e}")
            return None
            data = response.json()
            df = pd.DataFrame(data.get('response', []))
            df.to_csv(os.path.join(self.data_dir, f'games_{season}.csv'), index=False)
            return df
        return None

    def load_cached_data(self, filename):
        """Load data from cache"""
        path = os.path.join(self.data_dir, filename)
        if os.path.exists(path):
            return pd.read_csv(path)
        return None