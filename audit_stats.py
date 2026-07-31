"""Comprehensive audit of all stats and chart data"""
import sys, json
sys.path.insert(0, ".")
from vt_store import get_store
from collections import defaultdict

store = get_store()
recs = store.all_records()
vt = [r for r in recs if r.get("is_vt")]
stats = store.stats()

with open("audit_report.txt", "w") as f:
    f.write("=" * 70 + "\n")
    f.write("COMPREHENSIVE AUDIT REPORT\n")
    f.write("=" * 70 + "\n\n")

    # 1. Basic counts
    f.write("=== 1. BASIC COUNTS ===\n")
    by_type = defaultdict(int)
    for r in vt:
        by_type[r.get("report_type", "other")] += 1
    f.write(f"Total VT records: {len(vt)}\n")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        f.write(f"  {t}: {c}\n")
    
    det = by_type.get("detection", 0)
    ul = by_type.get("upper_limit", 0)
    f.write(f"\nDetection rate: {det}/{det+ul} = {det/(det+ul)*100:.1f}%\n")
    f.write(f"Stats says: detection_rate={stats['detection_rate']:.3f}\n")
    f.write(f"Stats says: detection_count={stats['detection_count']}, upper_limit_count={stats['upper_limit_count']}\n")
    f.write(f"MATCH: {det == stats['detection_count'] and ul == stats['upper_limit_count']}\n\n")

    # 2. Magnitude data check
    f.write("=== 2. MAGNITUDE DATA ===\n")
    has_mag = sum(1 for r in vt if r.get("magnitudes"))
    no_mag = sum(1 for r in vt if not r.get("magnitudes"))
    f.write(f"Has magnitudes: {has_mag}, No magnitudes: {no_mag}\n")
    
    # Check is_limit consistency
    det_with_limit = 0
    ul_with_det = 0
    for r in vt:
        rtype = r.get("report_type", "")
        mags = r.get("magnitudes", [])
        if not mags:
            continue
        has_det = any(not m.get("is_limit") for m in mags)
        has_limit = any(m.get("is_limit") for m in mags)
        if rtype == "detection" and not has_det and has_limit:
            det_with_limit += 1
        if rtype == "upper_limit" and has_det:
            ul_with_det += 1
    f.write(f"detection records with ONLY limits (no actual detection): {det_with_limit}\n")
    f.write(f"upper_limit records with some detections: {ul_with_det}\n\n")
    
    # List the problematic detection records
    if det_with_limit > 0:
        f.write("Problematic 'detection' records with only limits:\n")
        for r in vt:
            rtype = r.get("report_type", "")
            mags = r.get("magnitudes", [])
            if rtype == "detection" and mags and all(m.get("is_limit") for m in mags):
                f.write(f"  GCN{r['circularId']} {r.get('event_name','')} : {[m for m in mags]}\n")
        f.write("\n")

    # 3. Upper limit events check
    f.write("=== 3. UPPER LIMIT EVENTS ===\n")
    events = store.upper_limit_events()
    af = [e for e in events if e["is_auto_followup"]]
    svom = [e for e in events if e["is_svom"] and not e["is_auto_followup"]]
    other = [e for e in events if not e["is_svom"]]
    f.write(f"Total UL-only events: {len(events)}\n")
    f.write(f"  SVOM auto followup: {len(af)}\n")
    f.write(f"  SVOM ToO: {len(svom)}\n")
    f.write(f"  External: {len(other)}\n\n")

    # 4. Trigger source check
    f.write("=== 4. TRIGGER SOURCES ===\n")
    by_src = defaultdict(int)
    for r in vt:
        by_src[r.get("trigger_source", "Unknown")] += 1
    for s, c in sorted(by_src.items(), key=lambda x: -x[1]):
        f.write(f"  {s}: {c}\n")
    f.write(f"Stats says: {stats['by_trigger']}\n")
    f.write(f"MATCH: {dict(by_src) == stats['by_trigger']}\n\n")

    # 5. Auto followup rate check
    f.write("=== 5. AUTO FOLLOWUP RATE ===\n")
    f.write(f"Stats auto_followup_rate: {stats['auto_followup_rate']:.3f}\n")
    af_det = 0
    af_ul = 0
    for r in vt:
        d = r.get("trigger_to_obs_hr")
        rtype = r.get("report_type", "")
        if rtype not in ("detection", "upper_limit"):
            continue
        src = r.get("trigger_source", "") or ""
        if not src.startswith("SVOM"):
            continue
        if not isinstance(d, (int, float)) or d <= 0:
            continue
        thr = 1.0
        is_af = d <= thr or r.get("is_auto_followup")
        if is_af:
            if rtype == "detection":
                af_det += 1
            else:
                af_ul += 1
    f.write(f"Manual count (with is_auto_followup override): det={af_det}, ul={af_ul}\n")
    f.write(f"Rate: {af_det}/{af_det+af_ul} = {af_det/(af_det+af_ul)*100:.1f}%\n")
    f.write(f"NOTE: stats may not account for is_auto_followup override\n\n")

    # 6. Events with duplicate GCNs or name mismatch
    f.write("=== 6. EVENT NAME MISMATCH ===\n")
    name_variants = defaultdict(set)
    for r in vt:
        evt = r.get("event_name", "") or ""
        if evt:
            # Normalize: remove spaces
            norm = evt.replace(" ", "").upper()
            name_variants[norm].add(evt)
    for norm, variants in name_variants.items():
        if len(variants) > 1:
            f.write(f"  {norm}: {variants}\n")
    f.write("\n")

    # 7. Delay check - records with None delay
    f.write("=== 7. MISSING DELAY DATA ===\n")
    no_delay = [r for r in vt if r.get("report_type") in ("detection", "upper_limit") and not isinstance(r.get("trigger_to_obs_hr"), (int, float))]
    f.write(f"Detection/UL records with missing delay: {len(no_delay)}\n")
    for r in no_delay[:15]:
        f.write(f"  GCN{r['circularId']} {r.get('event_name','')} type={r.get('report_type')}\n")
    if len(no_delay) > 15:
        f.write(f"  ... and {len(no_delay)-15} more\n")
    f.write("\n")

    # 8. Stellar flare check - make sure none have magnitudes
    f.write("=== 8. STELLAR FLARE WITH MAGNITUDES ===\n")
    sf_with_mag = [r for r in vt if r.get("report_type") == "stellar_flare" and r.get("magnitudes")]
    f.write(f"Stellar flares still with magnitudes: {len(sf_with_mag)}\n")
    for r in sf_with_mag:
        f.write(f"  GCN{r['circularId']} {r.get('event_name','')}: {r.get('magnitudes')}\n")
    f.write("\n")

    # 9. LC plot data check
    f.write("=== 9. LC PLOT DATA ===\n")
    vt_r_det = 0
    vt_r_ul = 0
    for r in vt:
        rtype = r.get("report_type", "")
        if rtype in ("stellar_flare", "clarification", "other"):
            continue
        for m in r.get("magnitudes", []):
            if m.get("band") == "VT_R":
                if m.get("is_limit"):
                    vt_r_ul += 1
                else:
                    vt_r_det += 1
    f.write(f"VT_R detections (for LC plot): {vt_r_det}\n")
    f.write(f"VT_R upper limits (for LC plot): {vt_r_ul}\n")

print("Audit written to audit_report.txt")
