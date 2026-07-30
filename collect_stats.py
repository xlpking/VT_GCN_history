"""收集所有统计数据用于LaTeX文档"""
import json, config
from vt_parser import enrich
from vt_store import get_store
from datetime import datetime, timezone, timedelta
from collections import Counter
import re

store = get_store()
recs = store.all_records()

RE_GRB_DATE = re.compile(r"(?:GRB|EP)\s*(\d{2})(\d{2})(\d{2})")
X_BAND = 6.0
PUBLISH_LIMIT = 24.0

stats = {}

# 1. 基础统计
stats['total'] = len(recs)
dets = [r for r in recs if r.get('report_type') == 'detection']
lims = [r for r in recs if r.get('report_type') == 'upper_limit']
stats['n_det'] = len(dets)
stats['n_lim'] = len(lims)

# 2. 触发源
src_counter = Counter(r.get('trigger_source','Unknown') for r in recs)
stats['sources'] = dict(src_counter)

# 3. 波段
band_counter = Counter()
for r in recs:
    for b in (r.get('bands') or []):
        band_counter[b] += 1
stats['bands'] = dict(band_counter)

# 4. 后随延时统计 (≤2h)
svom_delays = []
ep_delays = []
swift_delays = []
fermi_delays = []
for r in recs:
    d = r.get('trigger_to_obs_hr')
    if not isinstance(d, (int,float)) or d <= 0 or d > 2:
        continue
    src = r.get('trigger_source','')
    if src.startswith('SVOM'): svom_delays.append(d)
    elif 'EP' in src or 'Einstein' in src: ep_delays.append(d)
    elif 'Swift' in src: swift_delays.append(d)
    elif 'Fermi' in src: fermi_delays.append(d)

def stat_summary(lst):
    if not lst: return None
    s = sorted(lst)
    return {'n': len(lst), 'min': min(lst), 'med': s[len(s)//2], 'max': max(lst)}

stats['delay_svom'] = stat_summary(svom_delays)
stats['delay_ep'] = stat_summary(ep_delays)
stats['delay_swift'] = stat_summary(swift_delays)
stats['delay_fermi'] = stat_summary(fermi_delays)

# 5. 证认时间统计
ident_exact = []
ident_est = []
ident_over24 = 0
within_24h = []
month_data = {}
for r in recs:
    pub_dt = datetime.fromtimestamp(r['createdOn']/1000, tz=timezone.utc)
    obs_str = r.get('obs_start_utc')
    d_obs = r.get('trigger_to_obs_hr')
    has_delay = isinstance(d_obs, (int,float)) and d_obs > 0
    if obs_str:
        try:
            obs_dt = datetime.fromisoformat(obs_str.replace('Z','+00:00'))
            if obs_dt.tzinfo is None: obs_dt = obs_dt.replace(tzinfo=timezone.utc)
        except: continue
        diff_h = (pub_dt - obs_dt).total_seconds()/3600
        is_est = False
    elif has_delay:
        ev = r.get('event_name','') or ''
        m = RE_GRB_DATE.search(ev)
        if not m: continue
        try:
            yy,mm,dd = int(m.group(1)),int(m.group(2)),int(m.group(3))
            t0 = datetime(2000+yy,mm,dd,tzinfo=timezone.utc)
        except: continue
        obs_dt = t0 + timedelta(hours=d_obs)
        diff_h = (pub_dt - obs_dt).total_seconds()/3600
        is_est = True
    else:
        continue
    if diff_h <= 0: continue
    ident = diff_h - X_BAND
    if ident < -6: continue
    over = diff_h > PUBLISH_LIMIT
    mk = obs_dt.strftime('%Y-%m')
    month_data.setdefault(mk, []).append((ident, over))
    if not over:
        within_24h.append(ident)
        if is_est: ident_est.append(ident)
        else: ident_exact.append(ident)
    else:
        ident_over24 += 1

avg_ident = sum(within_24h)/len(within_24h) if within_24h else 0
s24 = sorted(within_24h)
stats['ident'] = {
    'n_exact': len(ident_exact), 'n_est': len(ident_est),
    'n_within24': len(within_24h), 'n_over24': ident_over24,
    'avg_within24': avg_ident,
    'med_within24': s24[len(s24)//2] if s24 else 0,
    'min_within24': min(within_24h) if within_24h else 0,
    'max_within24': max(within_24h) if within_24h else 0,
}

# 工作量
PERSON = 2
total_person_hours = 0
for mk in month_data:
    for val, over in month_data[mk]:
        total_person_hours += (avg_ident if over else val) * PERSON
stats['ident']['total_person_hours'] = total_person_hours
stats['ident']['total_person_days'] = total_person_hours / 24.0

# 6. 月度统计
month_counts = Counter()
for r in recs:
    pub = datetime.fromtimestamp(r['createdOn']/1000, tz=timezone.utc)
    month_counts[pub.strftime('%Y-%m')] += 1
stats['monthly'] = dict(sorted(month_counts.items()))

# 7. 时间跨度
dates = [datetime.fromtimestamp(r['createdOn']/1000, tz=timezone.utc) for r in recs]
stats['date_start'] = min(dates).strftime('%Y-%m-%d')
stats['date_end'] = max(dates).strftime('%Y-%m-%d')

import json as jj
print(jj.dumps(stats, ensure_ascii=False, indent=2, default=str))
