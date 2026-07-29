"""收集统计数据"""
from vt_store import get_store
from collections import Counter
from datetime import datetime, timezone

store = get_store()
recs = store.all_records()
print(f"总 VT GCN 数: {len(recs)}")

ts = Counter(r.get('trigger_source','Unknown') for r in recs)
for k,v in sorted(ts.items(), key=lambda x:-x[1]):
    print(f"  {k}: {v}")

svom = [r for r in recs if (r.get('trigger_source') or '').startswith('SVOM')]
dels = [r['trigger_to_obs_hr'] for r in svom if isinstance(r.get('trigger_to_obs_hr'),(int,float))]
print(f"\nSVOM/ECLAIRs 自触发: {len(svom)} 条, 有延时: {len(dels)}")
le1 = len([d for d in dels if d<=1])
le2 = len([d for d in dels if d<=2])
le6 = len([d for d in dels if d<=6])
print(f"  <=1h: {le1}, <=2h: {le2}, <=6h: {le6}")
if dels:
    dels_s = sorted(dels)
    med = dels_s[len(dels_s)//2]
    print(f"  中位数: {med:.3f}h, 最小: {min(dels):.4f}h, 最大: {max(dels):.3f}h")

ep = [r for r in recs if r.get('trigger_source')=='EP']
ep_dels = [r['trigger_to_obs_hr'] for r in ep if isinstance(r.get('trigger_to_obs_hr'),(int,float))]
print(f"\nEP ToO: {len(ep)} 条, 有延时: {len(ep_dels)}")
if ep_dels:
    ed_s = sorted(ep_dels)
    print(f"  中位数: {ed_s[len(ed_s)//2]:.3f}h, 最小: {min(ep_dels):.3f}h")

swift = [r for r in recs if r.get('trigger_source')=='Swift']
sw_dels = [r['trigger_to_obs_hr'] for r in swift if isinstance(r.get('trigger_to_obs_hr'),(int,float))]
print(f"\nSwift ToO: {len(swift)} 条, 有延时: {len(sw_dels)}")
if sw_dels:
    sd_s = sorted(sw_dels)
    print(f"  中位数: {sd_s[len(sd_s)//2]:.3f}h, 最小: {min(sw_dels):.3f}h")

for grp_name, grp in [('SVOM', svom), ('EP', ep), ('Swift', swift)]:
    for band in ['VT_B','VT_R']:
        det = [m for r in grp for m in (r.get('magnitudes') or []) if m.get('band')==band and not m.get('is_limit')]
        ul = [m for r in grp for m in (r.get('magnitudes') or []) if m.get('band')==band and m.get('is_limit')]
        if det:
            vals = sorted(m['value'] for m in det)
            med = vals[len(vals)//2]
            print(f"\n{grp_name}/{band}: det {len(det)} (med {med:.1f}, {vals[0]:.1f}~{vals[-1]:.1f}), ul {len(ul)}")

bands = Counter()
for r in recs:
    for b in (r.get('bands') or []):
        bands[b] += 1
print(f"\n波段统计:")
for k,v in sorted(bands.items(), key=lambda x:-x[1]):
    print(f"  {k}: {v}")

dates = sorted([r.get('createdOn',0) for r in recs if r.get('createdOn')])
if dates:
    d0 = datetime.fromtimestamp(dates[0]/1000, tz=timezone.utc).strftime('%Y-%m-%d')
    d1 = datetime.fromtimestamp(dates[-1]/1000, tz=timezone.utc).strftime('%Y-%m-%d')
    print(f"\n时间跨度: {d0} ~ {d1}")
