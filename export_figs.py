"""用matplotlib导出图表为PNG"""
import os
from vt_store import get_store
from datetime import datetime, timezone, timedelta
from collections import Counter, OrderedDict
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# 中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'PingFang SC', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

OUT_DIR = os.path.join(os.path.dirname(__file__), "doc_figures")
os.makedirs(OUT_DIR, exist_ok=True)

store = get_store()
recs = store.all_records()

X_BAND = 6.0
PUBLISH_LIMIT = 24.0
RE_GRB_DATE = re.compile(r"(?:GRB|EP)\s*(\d{2})(\d{2})(\d{2})")

# ===== 图1: 月度报告柱状图 =====
month_counts = Counter()
for r in recs:
    pub = datetime.fromtimestamp(r['createdOn']/1000, tz=timezone.utc)
    month_counts[pub.strftime('%Y-%m')] += 1
months = sorted(month_counts.keys())
vals = [month_counts[m] for m in months]

fig, ax = plt.subplots(figsize=(10, 3.8))
x = np.arange(len(months))
bars = ax.bar(x, vals, color='#3b82f6', width=0.7)
ax.bar_label(bars, padding=3, fontsize=8)
ax.set_xticks(x)
ax.set_xticklabels(months, rotation=45, ha='right', fontsize=8)
ax.set_ylabel('报告数量', fontsize=11)
ax.set_title('SVOM/VT GCN 月度报告数量', fontsize=13)
ax.set_ylim(0, max(vals)*1.2)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "monthly_bar.png"), dpi=150)
plt.close()
print("Saved monthly_bar.png")

# ===== 图2: 触发源分布 =====
src_counts = Counter(r.get('trigger_source','Unknown') for r in recs)
src_order = ['SVOM/ECLAIRs', 'EP', 'Swift', 'Fermi', 'INTEGRAL', 'LIGO/Virgo']
labels = [s for s in src_order if s in src_counts]
values = [src_counts[s] for s in labels]

fig, ax = plt.subplots(figsize=(7, 3.8))
colors2 = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#6b7280']
bars = ax.bar(labels, values, color=colors2[:len(labels)], width=0.6)
ax.bar_label(bars, padding=3, fontsize=10)
ax.set_ylabel('报告数量', fontsize=11)
ax.set_title('触发源分布', fontsize=13)
ax.set_ylim(0, max(values)*1.15)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "trigger_bar.png"), dpi=150)
plt.close()
print("Saved trigger_bar.png")

# ===== 图2b: 报告类型分布饼图 =====
type_map = {'detection': '光学证认', 'upper_limit': '上限', 'stellar_flare': '恒星耀发', 'clarification': '澄清', 'other': '其他'}
type_counts = Counter(r.get('report_type','other') for r in recs)
tl = [type_map.get(k,k) for k in type_counts if type_counts[k]>0]
tv = [type_counts[k] for k in type_counts if type_counts[k]>0]
tc = ['#4ade80','#f87171','#f59e0b','#60a5fa','#94a3b8'][:len(tv)]

fig, ax = plt.subplots(figsize=(6, 4))
wedges, texts, autotexts = ax.pie(tv, labels=tl, colors=tc, autopct='%1.1f%%',
    startangle=90, pctdistance=0.75, wedgeprops=dict(width=0.45))
for at in autotexts: at.set_fontsize(9)
ax.set_title('报告类型分布', fontsize=13)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "type_pie.png"), dpi=150)
plt.close()
print("Saved type_pie.png")

# ===== 图2c: 波段分布 =====
band_counts = Counter()
for r in recs:
    for b in (r.get('bands') or []):
        band_counts[b] += 1
bl = list(band_counts.keys())
bv = list(band_counts.values())

fig, ax = plt.subplots(figsize=(6, 3.8))
bars = ax.bar(bl, bv, color=['#f59e0b','#3b82f6'][:len(bl)], width=0.5)
ax.bar_label(bars, padding=3, fontsize=10)
ax.set_ylabel('报告数量', fontsize=11)
ax.set_title('观测波段分布', fontsize=13)
ax.set_ylim(0, max(bv)*1.15)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "band_bar.png"), dpi=150)
plt.close()
print("Saved band_bar.png")

# ===== 图3: 后随延时直方图 =====
delays_svom = [r['trigger_to_obs_hr'] for r in recs
               if isinstance(r.get('trigger_to_obs_hr'),(int,float)) and r['trigger_to_obs_hr']>0
               and (r.get('trigger_source') or '').startswith('SVOM')]
delays_oth = [r['trigger_to_obs_hr'] for r in recs
              if isinstance(r.get('trigger_to_obs_hr'),(int,float)) and r['trigger_to_obs_hr']>0
              and not (r.get('trigger_source') or '').startswith('SVOM')]

fig, ax = plt.subplots(figsize=(8, 3.8))
bins = np.linspace(0, 30, 31)
ax.hist(delays_svom, bins=bins, alpha=0.7, label=f'SVOM/ECLAIRs (n={len(delays_svom)})', color='#ef4444')
ax.hist(delays_oth, bins=bins, alpha=0.7, label=f'外部卫星 (n={len(delays_oth)})', color='#3b82f6')
ax.set_xlabel('后随延时 (h)', fontsize=11)
ax.set_ylabel('样本数', fontsize=11)
ax.set_title('后随观测延时分布', fontsize=13)
ax.legend(fontsize=10)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "delay_hist.png"), dpi=150)
plt.close()
print("Saved delay_hist.png")

# ===== 图3b: 星等 vs 后随延时散点图 (3×2 子图) =====
group_names = ["SVOM", "EP", "Swift"]
group_fns = {
    "SVOM": lambda ts: ts.startswith("SVOM"),
    "EP": lambda ts: ts == "EP",
    "Swift": lambda ts: ts == "Swift",
}
band_names = ["VT_B", "VT_R"]
det_color = "#4ade80"
ul_color = "#f87171"

# 收集所有子图数据
all_data = {}
all_y_vals = []
for gname in group_names:
    gfn = group_fns[gname]
    for band in band_names:
        det_x, det_y = [], []
        ul_x, ul_y = [], []
        for r in recs:
            ts = r.get("trigger_source", "")
            if not gfn(ts):
                continue
            d = r.get("trigger_to_obs_hr")
            for m in (r.get("magnitudes") or []):
                if m.get("band") != band:
                    continue
                val = m.get("value")
                if not isinstance(val, (int, float)):
                    continue
                t_eff = m.get("t_mid_hr")
                if isinstance(t_eff, (int, float)) and t_eff >= 0:
                    d_eff = t_eff
                elif isinstance(d, (int, float)) and d >= 0:
                    d_eff = d
                else:
                    continue
                d_sec = d_eff * 3600.0
                if d_sec > 3.6e6:
                    continue
                if m.get("is_limit"):
                    ul_x.append(d_sec); ul_y.append(val)
                else:
                    det_x.append(d_sec); det_y.append(val)
        all_data[(gname, band)] = (det_x, det_y, ul_x, ul_y)
        all_y_vals.extend(det_y + ul_y)

ymin, ymax = (min(all_y_vals) - 0.5, max(all_y_vals) + 0.5) if all_y_vals else (14, 25)

fig, axes = plt.subplots(3, 2, figsize=(9, 9), sharex=True)
for row, gname in enumerate(group_names):
    for col, band in enumerate(band_names):
        ax = axes[row][col]
        det_x, det_y, ul_x, ul_y = all_data[(gname, band)]
        if det_x:
            ax.scatter(det_x, det_y, c=det_color, s=15, alpha=0.7, edgecolors='none', label=f'探测 (n={len(det_x)})')
        if ul_x:
            ax.scatter(ul_x, ul_y, c=ul_color, s=15, alpha=0.7, marker='v', edgecolors='none', label=f'上限 (n={len(ul_x)})')
        ax.set_xscale('log')
        ax.set_ylim(ymax, ymin)  # 反转y轴
        ax.set_title(f'{gname} / {band}', fontsize=11)
        if col == 0:
            ax.set_ylabel('星等 (mag)', fontsize=10)
        if row == 2:
            ax.set_xlabel('后随延时 T-T$_0$ (s)', fontsize=10)
        ax.legend(fontsize=7, loc='lower right')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
fig.suptitle('星等 vs 后随延时（按触发源和波段）', fontsize=13, y=0.98)
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(os.path.join(OUT_DIR, "mag_vs_delay.png"), dpi=150)
plt.close()
print("Saved mag_vs_delay.png")

# ===== 图3c: 后随延时 vs GCN发布延时散点图 =====
from datetime import datetime, timezone as tz2
svom_x2, svom_y2 = [], []
oth_x2, oth_y2 = [], []
for r in recs:
    d_obs = r.get("trigger_to_obs_hr")
    if not isinstance(d_obs, (int, float)) or d_obs <= 0:
        continue
    obs_str = r.get("obs_start_utc")
    if not obs_str:
        continue
    try:
        obs_dt = datetime.fromisoformat(obs_str.replace("Z", "+00:00"))
        if obs_dt.tzinfo is None: obs_dt = obs_dt.replace(tzinfo=tz2.utc)
        pub_dt = datetime.fromtimestamp(r["createdOn"]/1000.0, tz=tz2.utc)
    except: continue
    d_pub = (pub_dt - obs_dt).total_seconds()/3600.0 + d_obs
    if d_pub <= 0 or d_pub > 2000: continue
    src = r.get("trigger_source","") or ""
    if src.startswith("SVOM"): svom_x2.append(d_obs); svom_y2.append(d_pub)
    else: oth_x2.append(d_obs); oth_y2.append(d_pub)

fig, ax = plt.subplots(figsize=(7, 4.5))
if oth_x2:
    ax.scatter(oth_x2, oth_y2, c='#3b82f6', s=20, alpha=0.6, edgecolors='none', label='外部卫星')
if svom_x2:
    ax.scatter(svom_x2, svom_y2, c='#ef4444', s=20, alpha=0.6, edgecolors='none', label='SVOM/ECLAIRs')
allv = svom_x2 + svom_y2 + oth_x2 + oth_y2
if allv:
    lo, hi = min(allv)*0.5, max(allv)*2
    ax.plot([lo,hi],[lo,hi], '--', color='#94a3b8', linewidth=1, label='y = x')
ax.set_xscale('log'); ax.set_yscale('log')
ax.set_xlabel('后随延时 (后随开始−T$_0$, h)', fontsize=11)
ax.set_ylabel('GCN 发布延时 (发布−T$_0$, h)', fontsize=11)
ax.set_title('后随观测延时 vs GCN 发布延时', fontsize=13)
ax.legend(fontsize=9, loc='lower right')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "obs_vs_publish.png"), dpi=150)
plt.close()
print("Saved obs_vs_publish.png")

# ===== 图4: 证认时间散点图 =====
svom_x, svom_y = [], []
oth_x, oth_y = [], []
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
    else: continue
    if diff_h <= 0 or diff_h > PUBLISH_LIMIT: continue
    ident = diff_h - X_BAND
    if ident < -6: continue
    src = r.get('trigger_source','')
    # 用 datetime 对象，不能用字符串
    if src.startswith('SVOM'): svom_x.append(obs_dt); svom_y.append(ident)
    else: oth_x.append(obs_dt); oth_y.append(ident)

fig, ax = plt.subplots(figsize=(10, 3.8))
ax.scatter(oth_x, oth_y, c='#3b82f6', s=30, alpha=0.6, label='外部卫星', edgecolors='none')
ax.scatter(svom_x, svom_y, c='#ef4444', s=30, alpha=0.6, label='SVOM/ECLAIRs', edgecolors='none')
ax.axhline(y=0, color='#94a3b8', linestyle='--', linewidth=1, label='证认时间=0')
ax.set_ylabel('证认时间消耗 (h)', fontsize=11)
ax.set_title('证认时间消耗趋势（≤24h内发布）', fontsize=13)
ax.legend(fontsize=9, loc='upper right')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
# datetime 对象 + mdates 格式化
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "ident_scatter.png"), dpi=150)
plt.close()
print("Saved ident_scatter.png")

# ===== 图5: 工作量累积图 =====
PERSON = 2
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
    else: continue
    if diff_h <= 0: continue
    ident = diff_h - X_BAND
    if ident < -6: continue
    over = diff_h > PUBLISH_LIMIT
    mk = obs_dt.strftime('%Y-%m')
    month_data.setdefault(mk, []).append((ident, over))
    if not over: within_24h.append(ident)

avg_ident = sum(within_24h)/len(within_24h) if within_24h else 0
month_totals = OrderedDict()
for m in sorted(month_data.keys()):
    total = sum((avg_ident if over else val) for val, over in month_data[m]) * PERSON
    month_totals[m] = total
months5 = list(month_totals.keys())
vals5 = list(month_totals.values())
cumul5 = np.cumsum(vals5)

fig, ax1 = plt.subplots(figsize=(10, 4))
x5 = np.arange(len(months5))
bars = ax1.bar(x5, vals5, color='#93c5fd', width=0.7, label='月度工作量')
ax1.bar_label(bars, fmt='%.0f', padding=2, fontsize=7)
ax1.set_xticks(x5)
ax1.set_xticklabels(months5, rotation=45, ha='right', fontsize=8)
ax1.set_ylabel('月度工作量 (人时)', fontsize=11)
ax1.set_title(f'证认工作量累积增长（按{PERSON}人/暴，总工作量{cumul5[-1]:.0f}人时，{cumul5[-1]/24:.0f}人天）', fontsize=12)
ax1.spines['top'].set_visible(False)

ax2 = ax1.twinx()
ax2.plot(x5, cumul5, 'o-', color='#ef4444', linewidth=2, markersize=4, label='累积工作量')
ax2.set_ylabel('累积工作量 (人时)', fontsize=11, color='#ef4444')
ax2.tick_params(axis='y', labelcolor='#ef4444')
ax2.spines['top'].set_visible(False)

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1+lines2, labels1+labels2, fontsize=9, loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "workload_cumul.png"), dpi=150)
plt.close()
print("Saved workload_cumul.png")

print(f"\nAll figures saved to {OUT_DIR}")
