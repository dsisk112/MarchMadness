# Prediction Rules

This document describes the prediction logic used by the March Madness bracket simulator.

---

## Overview

The system uses a **two-tier prediction model**:

1. **API-powered prediction** — When both teams have RapidAPI team IDs, the system attempts a data-driven prediction using real team stats, player matchups, and rankings.
2. **Seed-based prediction** — When API data is unavailable (the common case for pre-tournament brackets), the system falls back to historical seed-matchup probabilities.

The system **always uses the real bracket** from `bracket_2026.json` and never falls back to mock data.

---

## Tier 1: API-Powered Prediction (`MatchupPredictor`)

Used when both teams have been enriched with a RapidAPI team ID (via schedule or standings lookup).

### Data Sources
- **Team stats** from RapidAPI standings (win %, avg points for, point differential)
- **Player rosters** with individual stats (points, rebounds, assists)
- **Team rankings** (curated AP/coaches poll rank)

### Scoring Formula

The final win probability is calculated as a **weighted composite score** converted to a probability via the sigmoid function:

```
total_score = (team_score × 0.5) + (player_score × 0.3) + (ranking_score × 0.2)
win_probability = 1 / (1 + e^(-total_score))
```

#### Component Weights

| Factor | Weight | Description |
|---|---|---|
| Team Stats | **50%** | Comparison of win percentage, average points scored, and point differential |
| Player Matchups | **30%** | Position-by-position comparison of top players (PG, SG, SF, PF, C) |
| Rankings | **20%** | AP/coaches poll ranking comparison |

#### Team Stats Score

```
score = (win_pct_diff × 2) + (avg_points_diff × 0.1) + (point_differential_diff × 0.01)
```

- `win_pct_diff` = Team A win % − Team B win %
- `avg_points_diff` = Team A avg points for − Team B avg points for
- `point_differential_diff` = Team A point differential − Team B point differential

#### Player Matchup Score

For each of the 5 positions (PG, SG, SF, PF, C):
1. Find the top player at that position for each team
2. Calculate each player's strength: `points + rebounds + assists`
3. Sum the per-position differences and scale by `0.1`

#### Ranking Score

| Condition | Score |
|---|---|
| Team A ranked higher (lower number) | +1.0 |
| Team B ranked higher | −1.0 |
| Same rank or both unranked | 0.0 |

### Key Drivers (API mode)

The system generates up to 3 human-readable explanations:
- Win percentage comparison (e.g., "Duke has higher win percentage (0.900 vs 0.750)")
- Ranking comparison (e.g., "Duke is ranked higher (#1 vs #8)")
- Positional player advantages (e.g., "Duke's PG (Player Name) outperforms Siena's PG")

---

## Tier 2: Seed-Based Prediction (Fallback)

Used when API team IDs are not available. This is the primary prediction method since the bracket is loaded before tournament games are played.

### Historical Seed Win Probabilities

The probability that the **better-seeded team wins**, based on aggregate NCAA tournament history:

| Matchup | Better Seed Wins |
|---|---|
| 1 vs 16 | **99%** |
| 1 vs 9 | 85% |
| 1 vs 8 | 80% |
| 1 vs 5 | 65% |
| 1 vs 4 | 55% |
| 2 vs 15 | **94%** |
| 2 vs 10 | 75% |
| 2 vs 7 | 60% |
| 2 vs 6 | 65% |
| 2 vs 3 | 55% |
| 3 vs 14 | **85%** |
| 3 vs 11 | 70% |
| 3 vs 7 | 55% |
| 3 vs 6 | 60% |
| 4 vs 13 | **79%** |
| 4 vs 12 | 65% |
| 4 vs 8 | 60% |
| 4 vs 5 | 55% |
| 5 vs 12 | 65% |
| 5 vs 13 | 75% |
| 6 vs 11 | 62% |
| 6 vs 14 | 80% |
| 7 vs 10 | 61% |
| 7 vs 15 | 85% |
| 8 vs 9 | **51%** |
| 9 vs 8 | 49% |

#### Fallback Linear Model

For seed matchups not in the table above:

```
win_probability = 0.50 + 0.03 × (worse_seed − better_seed)
```

Clamped to the range [0.50, 0.99].

### Winner Selection

The better-seeded team (lower seed number) is always selected as the winner when their win probability ≥ 50%. Since all entries in the table favor the better seed, this means the **higher seed always wins** in seed-based mode.

### Key Drivers (Seed mode)

The system generates up to 3 context-aware explanations based on the seed differential:

| Seed Differential | Driver Examples |
|---|---|
| **0** (same seed) | "Even matchup — both 1-seeds", "Duke slight edge (50%)" |
| **1–3** (competitive) | "Competitive: #4 vs #5 seed", "Kansas favored at 55%" |
| **4+** (lopsided) | "#1 seed Duke heavily favored", "Historical: 1-seeds beat 16-seeds 99% of the time" |
| **4–7** | "Upset chance: 21%" |
| **8+** | "Major upset unlikely based on history" |

---

## Tier 3: Injury Impact Adjustment

Applied **after** both Tier 1 (API) and Tier 2 (seed-based) predictions. Adjusts win probability based on each team's injured players and how much production they represent.

### Data Sources
- **injuries_2026.json** — scraped injury reports for all 68 tournament teams (player, position, status, injury type)
- **RapidAPI Player Statistics** — per-game averages (PPG, RPG, APG) for each injured player
- **RapidAPI Team Roster** — used to match injured player names to their player IDs

### How It Works

1. For each team in a matchup, look up their injury list
2. For each injured player, fetch their season stats via the API (cached)
3. Compute a **player impact score**: `(PPG × 1.0) + (RPG × 0.4) + (APG × 0.6)`
4. Weight by injury status:

| Status | Weight | Meaning |
|---|---|---|
| **Out** | 1.0 | Full impact subtracted |
| **Questionable** | 0.5 | Half impact subtracted |
| **Day-to-Day** | 0.35 | Partial impact |
| **Probable** | 0.15 | Minimal impact |

5. Sum all weighted impacts for each team → **team injury impact score**
6. Compute the **differential**: `team_B_impact − team_A_impact`
7. Convert to probability adjustment: `delta = differential × 0.005`, capped at ±0.12

### Positional Fallback

When a player's API stats aren't available, position-based estimates are used:

| Position | Est. PPG | Est. RPG | Est. APG |
|---|---|---|---|
| G (Guard) | 8.0 | 2.0 | 3.0 |
| F (Forward) | 7.0 | 3.0 | 1.5 |
| C (Center) | 6.5 | 3.0 | 1.5 |

### Winner Flipping

If the injury adjustment changes the win probability across the 50% threshold, the predicted winner flips. For example, if a 6-seed was favored at 52% but their star player (20 PPG) is Out, the probability may drop below 50% and the opponent becomes the predicted winner.

### Key Drivers (Injury mode)

An injury driver is appended to the matchup's key drivers when injuries affect the prediction:

> "Injury edge: Florida healthier — Duke missing ~12.5 impact pts (C. Foster Out, 14.2 PPG)"

### Metrics Output

When injuries affect a matchup, the metrics object includes:

```json
{
  "injuryAdjustment": 0.035,
  "injuriesTeamA": {
    "total_impact": 12.5,
    "team": "Duke",
    "players": [
      { "player": "C. Foster", "position": "G", "status": "Out",
        "injury": "Foot", "ppg": 14.2, "rpg": 3.1, "apg": 2.8, "impact": 16.78 }
    ]
  }
}
```

---

## Bracket Simulation Flow

1. **Load** `bracket_2026.json` — the official 68-team bracket with seeds and regions
2. **Enrich** (optional) — attempt to map team names to RapidAPI IDs via schedule/standings
3. **Predict First Four** — 4 play-in matchups
4. **Predict First Round** — 32 matchups across East, South, West, Midwest regions
5. **Simulate forward** — winners are paired into the next round and predicted:
   - Second Round (16 matchups)
   - Sweet 16 (8 matchups)
   - Elite Eight (4 matchups)
   - Final Four (2 matchups)
   - Championship (1 matchup)
6. **Return** all rounds with predictions, win probabilities, and key drivers

---

## Output Format

Each matchup in the API response includes:

```json
{
  "gameId": "east_1",
  "region": "East",
  "teamA": { "name": "Duke", "seed": 1 },
  "teamB": { "name": "Siena", "seed": 16 },
  "predictedWinner": { "name": "Duke", "seed": 1 },
  "metrics": {
    "winProbability": 0.99,
    "seedDifferential": 15,
    "method": "seed-based (historical)",
    "keyDrivers": [
      "#1 seed Duke heavily favored",
      "Historical: 1-seeds beat 16-seeds 99% of the time",
      "Major upset unlikely based on history"
    ]
  }
}
```
