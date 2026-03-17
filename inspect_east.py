"""Read bracket_dump.json and show upset risk details for East Round 1."""
import json, sys

with open('bracket_dump.json') as f:
    data = json.load(f)

for rnd in data.get('rounds', []):
    name = rnd.get('name', '')
    if name != 'First Round':
        continue
    for m in rnd.get('matchups', []):
        region = m.get('region', '')
        if region != 'East':
            continue
        ta = m.get('teamA', {})
        tb = m.get('teamB', {})
        w  = m.get('predictedWinner', {})
        mx = m.get('metrics', {})
        ur = mx.get('upsetRisk', {}) if isinstance(mx.get('upsetRisk'), dict) else {}

        sa = ta.get('seed', '?')
        sb = tb.get('seed', '?')
        print(f"--- {sa} {ta.get('name','?')} vs {sb} {tb.get('name','?')} ---")
        print(f"  Winner: {w.get('name','?')} at {mx.get('winProbability','?')}")
        print(f"  API raw prob: {mx.get('apiWinProbability','?')}")
        print(f"  Seed prior:   {mx.get('seedPriorProbability','?')}")
        print(f"  upsetRisk:    score={ur.get('score','MISSING')} pressure={ur.get('pressure','MISSING')}")
        print(f"  signals:      {ur.get('signals', [])}")
        print(f"  riskAdjust:   {mx.get('upsetRiskAdjustment', 'NONE')}")
        print(f"  bandPush:     {mx.get('classicBandPush', 'NONE')}")
        print(f"  closeWeight:  {mx.get('closeGameHistoricalWeight', 'NONE')}")
        print()
    break
