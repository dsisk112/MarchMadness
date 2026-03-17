"""Quick diagnostic: dump upset risk metrics for East Round 1 matchups."""
import urllib.request, json

resp = urllib.request.urlopen(
    'http://127.0.0.1:5000/api/bracket?season=2026&start=2026-03-16&end=2026-03-20'
)
data = json.loads(resp.read())

for rnd in data.get('rounds', []):
    name = rnd.get('name', '')
    if 'First' not in name and '1' not in name:
        continue
    for m in rnd.get('matchups', []):
        region = m.get('region', '')
        if region != 'East':
            continue
        ta = m.get('teamA', {})
        tb = m.get('teamB', {})
        w  = m.get('predictedWinner', {})
        mx = m.get('metrics', {})
        ur = mx.get('upsetRisk', {})
        if not isinstance(ur, dict):
            ur = {}

        seed_a = ta.get('seed', '?')
        seed_b = tb.get('seed', '?')
        print(f"--- {seed_a} {ta.get('name','?')} vs {seed_b} {tb.get('name','?')} ---")
        print(f"  Winner: {w.get('name','?')} at {mx.get('winProbability','?')}")
        print(f"  upsetRisk score={ur.get('score','MISSING')}  pressure={ur.get('pressure','MISSING')}")
        print(f"  signals: {ur.get('signals', [])}")
        print(f"  upsetRiskAdjustment: {mx.get('upsetRiskAdjustment', 'NONE')}")
        print(f"  classicBandPush: {mx.get('classicBandPush', 'NONE')}")
        print(f"  closeGameHistoricalWeight: {mx.get('closeGameHistoricalWeight', 'NONE')}")
        print(f"  apiWinProbability: {mx.get('apiWinProbability', '?')}")
        print(f"  seedPriorProbability: {mx.get('seedPriorProbability', '?')}")
        print()
    break
