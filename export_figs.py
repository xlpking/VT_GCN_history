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
    d = obs_dt.strftime('%Y-%m-%d')
    if src.startswith('SVOM'): svom_x.append(d); svom_y.append(ident)
    else: oth_x.append(d); oth_y.append(ident)

fig, ax = plt.subplots(figsize=(10, 3.8))
ax.scatter(oth_x, oth_y, c='#3b82f6', s=30, alpha=0.6, label='外部卫星', edgecolors='none')
ax.scatter(svom_x, svom_y, c='#ef4444', s=30, alpha=0.6, label='SVOM/ECLAIRs', edgecolors='none')
ax.axhline(y=0, color='#94a3b8', linestyle='--', linewidth=1, label='证认时间=0')
ax.set_ylabel('证认时间消耗 (h)', fontsize=11)
ax.set_title('证认时间消耗趋势（≤24h内发布）', fontsize=13)
ax.legend(fontsize=9, loc='upper right')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
# 稀疏x轴标签
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=8)
# 转换日期字符串为日期对象
import matplotlib.dates as mdates2
for collection, xs in [(ax.collections[0], oth_x), (ax.collections[1], svom_x)]:
    pass  # scatter已经用字符串，matplotlib自动处理
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
