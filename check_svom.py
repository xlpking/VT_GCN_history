"""Check all SVOM records without magnitudes"""
import sys
sys.path.insert(0, ".")
from vt_store import get_store

store = get_store()
recs = store.all_records()
svom = [r for r in recs if (r.get("trigger_source", "") or "").startswith("SVOM")]

print("=== SVOM records WITHOUT magnitudes ===")
no_mag = [r for r in svom if not r.get("magnitudes")]
print(f"Total: {len(no_mag)}\n")

for r in no_mag:
    cid = r.get("circularId")
    evt = r.get("event_name") or r.get("eventId") or ""
    rtype = r.get("report_type")
    body = r.get("body", "") or ""
    # Check if body mentions magnitude values
    import re
    has_mag_keyword = bool(re.search(r"mag", body, re.IGNORECASE))
    has_limit_keyword = bool(re.search(r"upper\s*limit|limit", body, re.IGNORECASE))
    # Look for any number that looks like magnitude
    mag_like = re.findall(r"(?:>~?|~)\s*(2[0-3]\.\d)\s*(?:mag)?", body, re.IGNORECASE)
    meas_like = re.findall(r"([12][0-9]\.\d+)\s*(?:\+/?-|±)\s*[\d.]+", body)
    print(f"GCN{cid} {evt} type={rtype}")
    print(f"  mag_keyword={has_mag_keyword} limit_keyword={has_limit_keyword}")
    print(f"  limit_values={mag_like[:5]} meas_values={meas_like[:5]}")
    # Print relevant lines
    for line in body.splitlines():
        ln = line.strip()
        if re.search(r"(?:mag|limit|VT[_\s]?[BR])", ln, re.IGNORECASE) and len(ln) < 200:
            print(f"  >> {ln}")
    print()
