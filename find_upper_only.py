"""Find all events where VT only has upper limits (no detections)"""
import sys
sys.path.insert(0, ".")
from vt_store import get_store
from collections import defaultdict

store = get_store()
recs = store.all_records()
vt = [r for r in recs if r.get("is_vt")]

# Group by event_name
events = defaultdict(lambda: {"detections": [], "limits": [], "gcn_ids": [], "src": ""})

for r in vt:
    rtype = r.get("report_type", "")
    if rtype in ("stellar_flare", "clarification", "other"):
        continue
    event = r.get("event_name", "") or ""
    if not event:
        continue
    ev = events[event]
    ev["src"] = r.get("trigger_source", "") or ""
    ev["gcn_ids"].append(r.get("circularId"))
    for m in r.get("magnitudes", []):
        if m.get("band") == "VT_R":
            if m.get("is_limit"):
                ev["limits"].append((r["circularId"], m.get("value"), m.get("t_mid_hr")))
            else:
                ev["detections"].append((r["circularId"], m.get("value"), m.get("t_mid_hr")))

# Events with only upper limits (no VT_R detections)
only_limits = {}
for event, data in events.items():
    if not data["detections"] and data["limits"]:
        only_limits[event] = data

# Also check events with only VT_B detection but no VT_R
print(f"=== {len(only_limits)} events with VT_R upper limits only (no VT_R detection) ===\n")
print(f"{'Event':<25} {'Source':<15} {'GCN IDs':<25} {'VT_R limits (mag @ hr)':<40}")
print("-" * 110)
for event in sorted(only_limits.keys(), key=lambda e: only_limits[e]["gcn_ids"][0]):
    d = only_limits[event]
    gcns = ",".join(str(g) for g in sorted(set(d["gcn_ids"])))
    lims = "; ".join(f"{v:.1f}@{t:.1f}h" if t else f"{v:.1f}" for _, v, t in d["limits"])
    print(f"{event:<25} {d['src']:<15} {gcns:<25} {lims}")
