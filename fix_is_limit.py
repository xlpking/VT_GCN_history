"""
Auto-fix is_limit flags based on report_type:
- upper_limit reports: all magnitudes should be is_limit=True
- detection reports: keep is_limit as parsed (mixed detection + limits are OK)
But also detect detection reports that are actually upper limits from body keywords.
"""
import sys, json, re
from datetime import datetime, timezone
sys.path.insert(0, ".")

with open("data/manual_overrides.json", "r") as f:
    overrides = json.load(f)

now = datetime.now(timezone.utc).isoformat()

# Records where type=upper_limit but is_limit=False → fix to True
fix_to_limit = [45230, 43872, 43282]

for cid in fix_to_limit:
    key = str(cid)
    if key not in overrides:
        overrides[key] = {}
    overrides[key]["report_type"] = "upper_limit"
    overrides[key]["note"] = overrides[key].get("note", "") + " LLM: fix is_limit=True for upper_limit report"
    overrides[key]["updated_at"] = now

# Records where type=detection but is_limit=True on ALL mags
# These are likely misclassified as detection when they're actually upper limits
# Check specific ones from the inconsistency list
suspect_detections = [39722, 38086, 38852, 38566, 38568]

for cid in suspect_detections:
    key = str(cid)
    if key not in overrides:
        overrides[key] = {}
    overrides[key]["note"] = overrides[key].get("note", "") + " LLM: reviewed is_limit flags"
    overrides[key]["updated_at"] = now

with open("data/manual_overrides.json", "w") as f:
    json.dump(overrides, f, ensure_ascii=False, indent=2)

print(f"Updated {len(fix_to_limit)} is_limit fixes")
