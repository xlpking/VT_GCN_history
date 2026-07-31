"""Export all VT records for LLM review - structured JSON"""
import sys, json
sys.path.insert(0, ".")
from vt_store import get_store

store = get_store()
recs = store.all_records()
vt = [r for r in recs if r.get("is_vt")]

output = []
for r in vt:
    output.append({
        "cid": r.get("circularId"),
        "event": r.get("event_name") or r.get("eventId") or "",
        "report_type": r.get("report_type"),
        "trigger_source": r.get("trigger_source", "") or "",
        "bands": r.get("bands", []),
        "magnitudes": r.get("magnitudes", []),
        "body_excerpt": (r.get("body", "") or "")[:2000],
    })

# Save full export
with open("llm_review_export.json", "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# Also print summary of problematic records
no_mag = [r for r in vt if not r.get("magnitudes")]
print(f"=== {len(no_mag)} records WITHOUT magnitudes ===")
for r in no_mag:
    print(f"GCN{r.get('circularId')} | {r.get('event_name','')} | type={r.get('report_type')} | src={r.get('trigger_source','')[:25]}")

print(f"\n=== Total: {len(vt)} VT records exported to llm_review_export.json ===")
