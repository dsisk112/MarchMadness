import requests
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

class MBBAPIClient:
    """
    Client for RapidAPI Men's College Basketball endpoints.
    Handles API calls, caching, and data parsing.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('RAPIDAPI_KEY')
        if not self.api_key:
            raise ValueError("RAPIDAPI_KEY environment variable not set")

        # Use the men's college basketball endpoint
        self.base_url = "https://mens-college-basketball-mbb.p.rapidapi.com"
        self.headers = {
            'X-RapidAPI-Key': self.api_key,
            'X-RapidAPI-Host': 'mens-college-basketball-mbb.p.rapidapi.com'
        }

        # Caching setup
        self.cache_dir = os.path.join(os.path.dirname(__file__), '..', 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.force_refresh = False

    def _get_cache_path(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate cache file path based on endpoint and params."""
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        filename = f"{endpoint}_{param_str}.json"
        return os.path.join(self.cache_dir, filename)

    def _load_cache(self, cache_path: str) -> Optional[Dict]:
        """Load data from cache if exists."""
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                    return cached_data['data']
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Cache corrupted ({os.path.basename(cache_path)}): {e} — deleting and re-fetching")
                os.remove(cache_path)
        return None

    def _save_cache(self, cache_path: str, data: Dict):
        """Save data to cache."""
        cache_data = {
            'timestamp': datetime.now().timestamp(),
            'data': data
        }
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f)

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict:
        """Make API request with caching. Skips cache when force_refresh is set."""
        cache_path = self._get_cache_path(endpoint, params)
        if not self.force_refresh:
            cached = self._load_cache(cache_path)
            if cached:
                return cached

        import time
        url = f"{self.base_url}/{endpoint}"
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        self._save_cache(cache_path, data)
        time.sleep(0.3)  # Rate-limit between API calls
        return data

    # Specific endpoint methods

    def get_schedule(self, year: int, month: int, day: int, seasontype: int = 3, group: int = 50) -> Dict:
        """Get schedule for a specific date.

        - seasontype: 1 Pre, 2 Regular, 3 Postseason, 4 Offseason
        - group: 50 DI, 51 DII, 52 DIII
        """
        params = {
            'year': year,
            'month': month,
            'day': day,
            'seasontype': seasontype,
            'group': group
        }
        return self._make_request('schedule', params)

    def get_scoreboard(self, year: int, month: int, day: int) -> Dict:
        """Alias for schedule (legacy method)."""
        return self.get_schedule(year, month, day)

    def get_standings(self, year: int) -> Dict:
        """Get standings for a season."""
        params = {'year': year}
        return self._make_request('standings', params)

    def get_team_info(self, team_id: str) -> Dict:
        """Get info for a specific team."""
        params = {'teamId': team_id}
        return self._make_request('team', params)

    def get_team_roster(self, team_id: str, season: int) -> Dict:
        """Get roster for a team and season."""
        params = {'teamId': team_id, 'season': season}
        return self._make_request('team-roster', params)

    def get_player_stats(self, player_id: str, season: int = None) -> Dict:
        """Get stats for a specific player."""
        params = {'playerId': player_id}
        return self._make_request('player-statistic', params)

    # Helper methods for data extraction

    def get_tournament_games(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get all tournament games within date range with rate limiting.

        The RapidAPI schedule response is structured as:
          {"data": {"YYYYMMDD": {"games": [ ... ]}}}

        We extract games from each date and filter for postseason/tournament games.
        """
        games = []
        current_date = start_date

        while current_date <= end_date:
            try:
                scoreboard = self.get_scoreboard(
                    current_date.year,
                    current_date.month,
                    current_date.day
                )

                date_key = current_date.strftime('%Y%m%d')
                # Handle both raw API shape {"data":{"YYYYMMDD":...}}
                # and cached shape {"YYYYMMDD":...}
                day_data = scoreboard.get('data', scoreboard).get(date_key, {})

                for game in day_data.get('games', []):
                    # Post-season (type=3) or tournament-type games
                    season_type = game.get('season', {}).get('type')
                    comp_type = game.get('competitions', [{}])[0].get('type', {}).get('abbreviation')
                    if season_type == 3 or comp_type == 'TRNMNT':
                        games.append(game)
            except Exception as e:
                print(f"Error fetching games for {current_date}: {e}")

            current_date += timedelta(days=1)

            # Add delay to avoid rate limits
            import time
            time.sleep(0.5)

        return games

    def get_team_stats(self, team_id: str, year: int) -> Dict:
        """Get comprehensive team stats."""
        standings = self.get_standings(year)
        for entry in standings.get('standings', {}).get('entries', []):
            if entry['team']['id'] == team_id:
                return entry
        return {}

    def get_roster_with_stats(self, team_id: str, season: int) -> List[Dict]:
        """Get full roster with player stats."""
        roster = self.get_team_roster(team_id, season)
        players = []
        for player in roster.get('athletes', roster.get('players', [])):
            try:
                stats = self.get_player_stats(player['id'], season)
                player['stats'] = stats
                players.append(player)
            except Exception as e:
                print(f"Error fetching stats for player {player['id']}: {e}")
                # Cache a "no data" marker so we don't retry failed players
                cache_path = self._get_cache_path('player-statistic', {'playerId': player['id']})
                self._save_cache(cache_path, {"_error": True})
                players.append(player)
        return players