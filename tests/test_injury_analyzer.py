import os
import sys
import unittest


BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from injury_analyzer import InjuryAnalyzer


class DummyApi:
    def __init__(self):
        self._standings = {
            "standings": {
                "entries": [
                    {
                        "team": {"id": "vandy-id", "displayName": "Vanderbilt Commodores"},
                        "stats": [
                            {"name": "wins", "value": 10},
                            {"name": "losses", "value": 6},
                        ],
                    },
                    {
                        "team": {"id": "duke-id", "displayName": "Duke Blue Devils"},
                        "stats": [
                            {"name": "wins", "value": 14},
                            {"name": "losses", "value": 2},
                        ],
                    },
                ]
            }
        }
        self._rosters = {
            "vandy-id": {
                "athletes": [
                    {
                        "id": "kimble-id",
                        "shortName": "G. Kimble III",
                        "displayName": "George Kimble III",
                    }
                ]
            },
            "duke-id": {"athletes": []},
        }
        self._player_stats = {
            "kimble-id": {
                "categories": [
                    {
                        "stats": [
                            {"name": "avgPoints", "value": 0},
                            {"name": "avgRebounds", "value": 0},
                            {"name": "avgAssists", "value": 0},
                            {"name": "gamesPlayed", "value": 0},
                        ]
                    }
                ]
            }
        }

    def get_standings(self, _season):
        return self._standings

    def get_team_roster(self, team_id, _season):
        return self._rosters.get(team_id, {"athletes": []})

    def get_player_stats(self, player_id):
        return self._player_stats.get(player_id, {})


class TestInjuryAnalyzer(unittest.TestCase):
    def test_preseason_carryover_no_current_stats_is_ignored(self):
        analyzer = InjuryAnalyzer(DummyApi(), season=2026)
        analyzer._injuries = {
            "Vanderbilt": {
                "injuries": [
                    {
                        "player": "G. Kimble III",
                        "position": "G",
                        "status": "Out",
                        "injury": "Knee",
                        "updated": "2025-02-14",
                    }
                ]
            }
        }

        impact = analyzer._team_injury_impact("Vanderbilt")
        self.assertEqual(impact["total_impact"], 0.0)
        self.assertEqual(impact["players"], [])

    def test_preseason_carryover_with_historical_stats_is_ignored(self):
        api = DummyApi()
        api._player_stats["kimble-id"] = {
            "categories": [
                {
                    "stats": [
                        {"name": "avgPoints", "value": 18.04},
                        {"name": "avgRebounds", "value": 3.68},
                        {"name": "avgAssists", "value": 3.24},
                        {"name": "gamesPlayed", "value": 25},
                    ]
                }
            ]
        }
        analyzer = InjuryAnalyzer(api, season=2026)
        analyzer._injuries = {
            "Vanderbilt": {
                "injuries": [
                    {
                        "player": "G. Kimble III",
                        "position": "G",
                        "status": "Out",
                        "injury": "Knee",
                        "updated": "2024-06-04",
                    }
                ]
            }
        }

        impact = analyzer._team_injury_impact("Vanderbilt")
        self.assertEqual(impact["total_impact"], 0.0)
        self.assertEqual(impact["players"], [])

    def test_current_season_injury_without_stats_uses_fallback(self):
        analyzer = InjuryAnalyzer(DummyApi(), season=2026)
        analyzer._injuries = {
            "Duke": {
                "injuries": [
                    {
                        "player": "Unknown Player",
                        "position": "G",
                        "status": "Out",
                        "injury": "Ankle",
                        "updated": "2026-01-15",
                    }
                ]
            }
        }

        impact = analyzer._team_injury_impact("Duke")
        self.assertGreater(impact["total_impact"], 0.0)
        self.assertEqual(len(impact["players"]), 1)

    def test_recent_preseason_out_is_retained(self):
        api = DummyApi()
        api._rosters["duke-id"] = {
            "athletes": [
                {
                    "id": "foster-id",
                    "shortName": "C. Foster",
                    "displayName": "Caleb Foster",
                }
            ]
        }
        api._player_stats["foster-id"] = {
            "categories": [
                {
                    "stats": [
                        {"name": "avgPoints", "value": 6.8},
                        {"name": "avgRebounds", "value": 2.5},
                        {"name": "avgAssists", "value": 2.1},
                        {"name": "gamesPlayed", "value": 96},
                    ]
                }
            ]
        }

        analyzer = InjuryAnalyzer(api, season=2026)
        analyzer._injuries = {
            "Duke": {
                "injuries": [
                    {
                        "player": "C. Foster",
                        "position": "G",
                        "status": "Out",
                        "injury": "Foot",
                        "updated": "2025-03-09",
                    }
                ]
            }
        }

        impact = analyzer._team_injury_impact("Duke")
        self.assertGreater(impact["total_impact"], 0.0)
        self.assertEqual(len(impact["players"]), 1)


if __name__ == "__main__":
    unittest.main()