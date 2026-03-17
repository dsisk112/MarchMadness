import argparse
import json
from datetime import datetime

from bracket_builder import BracketBuilder
from injury_analyzer import InjuryAnalyzer
from mbb_api import MBBAPIClient


def _collect_bracket_teams(bracket):
    names = set()
    for round_obj in bracket.get("rounds", []):
        for matchup in round_obj.get("matchups", []):
            for team in (matchup.get("teamA", {}), matchup.get("teamB", {})):
                name = team.get("name")
                if name and " / " not in name:
                    names.add(name)
    return sorted(names)


def run_validation(season: int):
    api = MBBAPIClient()
    builder = BracketBuilder(api)
    injury = InjuryAnalyzer(api, season)

    start = datetime(season, 3, 16)
    end = datetime(season, 3, 20)

    bracket = builder._load_bracket_structure(season)
    teams = _collect_bracket_teams(bracket)

    games = api.get_tournament_games(start, end)
    standings = api.get_standings(season)
    mapping = builder._build_name_to_team_info_map(games, standings)

    unresolved = []
    ambiguous_prefix = []
    resolved = []

    for team_name in teams:
        norm = builder.NAME_ALIASES.get(builder._norm(team_name), builder._norm(team_name))
        exact = mapping.get(norm)
        prefixes = [k for k in mapping.keys() if k.startswith(norm + " ")]

        probe = {"name": team_name}
        builder._enrich_team(probe, mapping)
        chosen_id = probe.get("id")

        if not chosen_id:
            unresolved.append(team_name)
        else:
            resolved.append(team_name)

        if not exact and len(prefixes) > 1:
            ambiguous_prefix.append(
                {
                    "team": team_name,
                    "normalized": norm,
                    "candidates": sorted(prefixes)[:5],
                    "chosenId": chosen_id,
                }
            )

    injury_unresolved = []
    for team_name in teams:
        if not injury._resolve_injury_team_name(team_name):
            injury_unresolved.append(team_name)

    report = {
        "season": season,
        "totalBracketTeams": len(teams),
        "resolvedApiTeamIds": len(resolved),
        "unresolvedApiTeamIds": unresolved,
        "ambiguousPrefixMatches": ambiguous_prefix,
        "unresolvedInjuryNames": injury_unresolved,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Validate team name mapping integrity")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    report = run_validation(args.season)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
