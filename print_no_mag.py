"""Print full body of 21 records without magnitudes for LLM review"""
import sys, json
sys.path.insert(0, ".")
from vt_store import get_store

store = get_store()
recs = store.all_records()
vt = [r for r in recs if r.get("is_vt")]
no_mag = [r for r in vt if not r.get("magnitudes")]

for r in no_mag:
    cid = r.get("circularId")
    body = r.get("body", "") or ""
    print(f"\n{'='*70}")
    print(f"GCN{cid} | event={r.get('event_name','')} | type={r.get('report_type')} | src={r.get('trigger_source','')}")
    print(f"subject: {r.get('subject','')}")
    print(f"{'='*70}")
    print(body[:1500])
