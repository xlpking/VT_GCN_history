"""Fix audit issues"""
import json
from datetime import datetime, timezone

with open('data/manual_overrides.json', 'r') as f:
    overrides = json.load(f)
now = datetime.now(timezone.utc).isoformat()

# Fix 1: detection records with only upper limit magnitudes -> upper_limit
fix_ids = [43623, 43551, 43337, 40412, 39917, 38566, 38378, 38086, 42819]
for cid in fix_ids:
    key = str(cid)
    if key not in overrides:
        overrides[key] = {}
    existing = overrides.get(key, {})
    if existing.get('report_type') != 'detection':
        existing['report_type'] = 'upper_limit'
        existing['note'] = (existing.get('note', '') + ' LLM audit: all mags are limits, fix to upper_limit').strip()
        existing['updated_at'] = now
        overrides[key] = existing
        print(f'Fixed GCN{cid} -> upper_limit')
    else:
        print(f'SKIP GCN{cid} - explicitly set to detection')

with open('data/manual_overrides.json', 'w') as f:
    json.dump(overrides, f, ensure_ascii=False, indent=2)
print('Done')
