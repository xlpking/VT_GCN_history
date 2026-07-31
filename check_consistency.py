"""Check for is_limit / report_type inconsistencies"""
import sys
sys.path.insert(0, ".")
from vt_store import get_store

store = get_store()
recs = store.all_records()
vt = [r for r in recs if r.get("is_vt")]

issues = []
for r in vt:
    rtype = r.get("report_type", "")
    mags = r.get("magnitudes", [])
    if not mags:
        continue
    for m in mags:
        is_limit = m.get("is_limit", False)
        # detection type should not have is_limit=True
        # upper_limit type should not have is_limit=False
        if rtype == "detection" and is_limit:
            issues.append(f"GCN{r['circularId']} type=detection but mag is_limit=True: {m}")
        elif rtype == "upper_limit" and not is_limit:
            issues.append(f"GCN{r['circularId']} type=upper_limit but mag is_limit=False: {m}")

print(f"=== {len(issues)} inconsistencies ===")
for s in issues:
    print(s)
