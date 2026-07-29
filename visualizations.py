"""统计分析与 Plotly 可视化生成（v2）"""
from __future__ import annotations

from collections import Counter, OrderedDict
from datetime import datetime, timezone
from typing import Dict, List

import plotly.graph_objects as go
from plotly.subplots import make_subplots

COLORS_TYPE = {
    "detection": "#4ade80",
    "upper_limit": "#f87171",
    "stellar_flare": "#fbbf24",
    "clarification": "#c4a8e8",
    "other": "#94a3b8",
}
TYPE_LABEL_CN = {
    "detection": "探测 Detection",
    "upper_limit": "上限 Upper Limit",
    "stellar_flare": "恒星耀斑 Stellar Flare",
    "clarification": "澄清/否定 Clarification",
    "other": "其他 Other",
}


def _fig_to_html(fig: go.Figure, height: int = 360, margin: dict | None = None, dark: bool = True) -> str:
    if dark:
        fig.update_layout(
            template="plotly_dark",
            height=height,
            width=None,
            margin=margin if margin else dict(l=40, r=20, t=50, b=40),
            font=dict(size=12, color="#e2e8f0"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#cbd5e1"))
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#cbd5e1"))
    else:
        fig.update_layout(
            template="plotly_white",
            height=height,
            width=None,
            margin=margin if margin else dict(l=40, r=20, t=50, b=40),
        )
    # responsive=true 让图表自适应容器宽度；翻页错位由 CSS .chart-card { contain:layout } 隔离
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True, "displayModeBar": False})


def build_type_pie(stats: dict) -> str:
    by_type: Dict[str, int] = stats.get("by_type", {})
    labels, values, colors = [], [], []
    for k in ("detection", "upper_limit", "stellar_flare", "clarification", "other"):
        v = by_type.get(k, 0)
        if v:
            labels.append(TYPE_LABEL_CN.get(k, k))
            values.append(v)
            colors.append(COLORS_TYPE.get(k, "#888"))
    if not values:
        return "<div class='empty'>暂无数据</div>"
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.42,
        marker=dict(colors=colors),
        textinfo="label+percent",
        textposition="outside",
        domain=dict(x=[0.30, 0.70], y=[0.15, 0.95]),
    )])
    fig.update_layout(
        title_text="报告类型分布 Report Type Distribution",
        title_x=0.5,
        title_xanchor="center",
        showlegend=False,
    )
    return _fig_to_html(fig, height=340, margin=dict(l=20, r=20, t=45, b=20))


def build_band_bar(stats: dict) -> str:
    by_band: Dict[str, int] = stats.get("by_band", {})
    if not by_band:
        return "<div class='empty'>暂无波段数据</div>"
    # 固定显示顺序：VT_B / VT_R / VT_white / VHF / 其他
    order = ["VT_B", "VT_R", "VT_white", "VHF", "VT_clear", "unknown"]
    keys = [k for k in order if k in by_band] + [k for k in by_band if k not in order]
    vals = [by_band[k] for k in keys]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b", "#aaaaaa"][:len(keys)]
    fig = go.Figure([go.Bar(x=keys, y=vals, marker_color=colors, text=vals, textposition="outside",
                            textfont=dict(color="#e2e8f0", size=13))])
    max_v = max(vals) if vals else 1
    fig.update_layout(
        title_text="波段分布 Band Distribution（基于实际测光/上限行）",
        xaxis_title="波段 Band", yaxis_title="报告数 Count",
        yaxis=dict(range=[0, max_v * 1.22]),
    )
    return _fig_to_html(fig, height=420)


def build_trigger_bar(stats: dict) -> str:
    by_trigger: Dict[str, int] = stats.get("by_trigger", {})
    if not by_trigger:
        return "<div class='empty'>暂无触发卫星数据</div>"
    # SVOM 系列合并展示但分开计数
    items = list(by_trigger.items())
    items.sort(key=lambda kv: kv[1], reverse=True)
    keys = [k for k, _ in items]
    vals = [v for _, v in items]
    colors = []
    for k in keys:
        if k.startswith("SVOM"):
            colors.append("#1f77b4")
        elif k == "EP":
            colors.append("#ff7f0e")
        elif k == "Swift":
            colors.append("#2ca02c")
        elif k == "Fermi":
            colors.append("#d62728")
        elif k == "IceCube":
            colors.append("#17becf")
        else:
            colors.append("#9467bd")
    # customdata 存 trigger name，用于点击跳转
    fig = go.Figure([go.Bar(
        x=keys, y=vals, marker_color=colors, text=vals, textposition="outside",
        textfont=dict(size=13, color="#e2e8f0"),
        customdata=keys,
        hovertemplate="<b>%{customdata}</b><br>VT 报告数: %{y}<br><i>点击查看 GCN 列表</i><extra></extra>",
    )])
    fig.update_layout(
        title_text="VT 后随的触发卫星分布（点击柱子查看 GCN 列表）",
        xaxis_title="触发/主探测卫星", yaxis_title="VT 报告数 Count",
        yaxis=dict(range=[0, max(vals) * 1.18]),
    )
    html = _fig_to_html(fig, height=420, margin=dict(l=40, r=20, t=50, b=70))
    # 注入点击事件跳转
    click_js = """<script>
    (function(){
        var tries=0;
        function attach(){
            tries++;
            document.querySelectorAll('.chart-card .plotly-graph-div').forEach(function(div){
                if(div._plotly_click_attached) return;
                if(div.data && div.data[0] && div.data[0].customdata){
                    div._plotly_click_attached=true;
                    div.on('plotly_click', function(evt){
                        var pn=evt.points[0], name=pn.data.customdata[pn.pointNumber];
                        if(name) window.location.href='/trigger/'+encodeURIComponent(name);
                    });
                    div.style.cursor='pointer';
                }
            });
            if(tries<10) setTimeout(attach,300);
        }
        setTimeout(attach,300);
    })();
    </script>"""
    return html + click_js


def build_monthly_bar(stats: dict) -> str:
    """按月堆叠的报告数（按 report_type 分层）。"""
    monthly: Dict[str, int] = stats.get("monthly", {})
    if not monthly:
        return "<div class='empty'>暂无时间数据</div>"
    # 只画总体柱状（保持简单清晰）
    keys = list(monthly.keys())
    vals = [monthly[k] for k in keys]
    fig = go.Figure([go.Bar(x=keys, y=vals, marker_color="#ff7f0e", text=vals, textposition="outside")])
    fig.update_layout(
        title_text="月度 VT 报告数量 Monthly VT Reports",
        xaxis_title="年月", yaxis_title="报告数",
    )
    return _fig_to_html(fig, height=340)


def build_event_bar(stats: dict, top_n: int = 25) -> str:
    by_event: Dict[str, int] = stats.get("by_event", {})
    if not by_event:
        return "<div class='empty'>暂无事件数据</div>"
    items = list(by_event.items())[:top_n]
    items = list(reversed(items))
    keys = [k for k, _ in items]
    vals = [v for _, v in items]
    fig = go.Figure([go.Bar(y=keys, x=vals, orientation="h", marker_color="#17becf", text=vals, textposition="outside")])
    fig.update_layout(
        title_text=f"Top {top_n} 事件 VT 报告数 VT Reports per Event",
        yaxis_title="", xaxis_title="VT 报告数",
        height=max(420, 26 * len(keys)),
    )
    return _fig_to_html(fig, height=max(420, 26 * len(keys)))


def _delay_barchart(delays: List[float], title: str, color: str) -> go.Figure:
    """构建单个延时分箱柱状图（线性坐标，等宽类别轴）。"""
    # 只统计 <= 1000h 的延时
    delays = [d for d in delays if d <= 1000]
    bin_edges = [0, 0.5, 1, 2, 4, 6, 12, 24, 48, 100, 240, 1000]
    bin_labels = ["0-0.5h", "0.5-1h", "1-2h", "2-4h", "4-6h", "6-12h", "12-24h", "24-48h", "48-100h", "100-240h", "240h+"]
    counts = [0] * len(bin_labels)
    for d in delays:
        placed = False
        for i in range(len(bin_edges) - 1):
            if bin_edges[i] <= d < bin_edges[i + 1]:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1

    n = len(delays)
    frac1 = sum(1 for d in delays if d <= 1) / n if n else 0
    frac2 = sum(1 for d in delays if d <= 2) / n if n else 0
    frac6 = sum(1 for d in delays if d <= 6) / n if n else 0
    ds = sorted(delays)
    p50 = ds[len(ds) // 2] if ds else 0

    fig = go.Figure(data=[go.Bar(
        x=bin_labels, y=counts,
        marker_color=color,
        hovertemplate="%{x}<br>数量: %{y}<extra></extra>",
        text=[f"{c}" for c in counts],
        textposition="outside",
        textfont=dict(color="#e2e8f0", size=11),
    )])
    # 阈值线标注（用 add_annotation 在顶部显示百分比）
    annotations = []
    for thr, frac, clr in [(1.0, frac1, "#4ade80"), (2.0, frac2, "#5aa9ff"), (6.0, frac6, "#fbbf24")]:
        annotations.append(dict(
            text=f"≤{int(thr)}h: {frac*100:.0f}%", showarrow=False,
            xref="paper", yref="paper", x=0.98, y=1.08 - annotations.__len__() * 0.05,
            font=dict(color=clr, size=10), bgcolor="rgba(0,0,0,0.4)",
        ))
    max_c = max(counts) if counts else 1
    fig.update_layout(
        title_text=f"{title} (n={n}, P50={p50:.1f}h)",
        xaxis_title="延时区间", yaxis_title="数量",
        bargap=0.2, yaxis=dict(range=[0, max_c * 1.25]),
        annotations=annotations,
    )
    fig.update_xaxes(tickangle=-30)
    return fig


def build_delay_hist(stats: dict) -> str:
    """延时分布：SVOM/ECLAIRs 和外部卫星分开画两幅独立图，左右并排。标题可点击查看详情。"""
    delays_svom = stats.get("delay_svom", [])
    delays_others = stats.get("delay_others", [])
    if not delays_svom and not delays_others:
        return "<div class='empty'>暂无延时数据</div>"

    parts = []
    if delays_svom:
        fig1 = _delay_barchart(delays_svom, "SVOM/ECLAIRs 自触发", "#5aa9ff")
        parts.append('<div class="chart-card"><a href="/delay/svom" target="_blank" style="position:absolute;top:10px;right:14px;z-index:10;font-size:11px;color:#5aa9ff;text-decoration:none;">查看详情 &rarr;</a>' + _fig_to_html(fig1, height=340) + '</div>')
    if delays_others:
        fig2 = _delay_barchart(delays_others, "外部卫星触发 (EP/Swift/Fermi/…)", "#fbbf24")
        parts.append('<div class="chart-card"><a href="/delay/others" target="_blank" style="position:absolute;top:10px;right:14px;z-index:10;font-size:11px;color:#fbbf24;text-decoration:none;">查看详情 &rarr;</a>' + _fig_to_html(fig2, height=340) + '</div>')

    n_all = len(delays_svom) + len(delays_others)
    parts.append(f'<div class="chart-card full" style="text-align:center;color:#94a3b8;font-size:11px;padding:8px;">'
                 f'总量 n={n_all}（仅正文显式写出 post trigger / after T0 的报告）</div>')
    return "\n".join(parts)


def build_timeline(records: List[dict]) -> str:
    """报告时间线（按事件分组）。显示全部事件（最多 40 个）以保证有足够样本。"""
    if not records:
        return "<div class='empty'>暂无数据</div>"
    cnt = Counter(r.get("event_name", "UNKNOWN") for r in records)
    # 显示报告数 >=1 的事件，按报告数倒序，最多 40 个
    top_events = [e for e, _ in cnt.most_common(40)]
    pts_x, pts_y, colors, text = [], [], [], []
    for r in records:
        ev = r.get("event_name", "UNKNOWN")
        if ev not in top_events:
            continue
        try:
            dt = datetime.fromtimestamp(r["createdOn"] / 1000.0, tz=timezone.utc)
        except Exception:
            continue
        pts_x.append(dt)
        pts_y.append(ev)
        t = r.get("report_type", "other")
        colors.append(COLORS_TYPE.get(t, "#888"))
        text.append(
            f"GCN {r.get('circularId')}<br>{r.get('subject','')[:80]}<br>"
            f"类型: {TYPE_LABEL_CN.get(t, t)}<br>触发: {r.get('trigger_source','?')}"
        )
    fig = go.Figure(data=go.Scatter(
        x=pts_x, y=pts_y, mode="markers",
        marker=dict(color=colors, size=12, line=dict(width=1, color="DarkSlateGrey")),
        text=text, hoverinfo="text",
    ))
    fig.update_layout(
        title_text=f"VT 报告时间线 Reports Timeline（{len(top_events)} 个事件 / {len(pts_x)} 条报告）",
        xaxis_title="报告时间", yaxis_title="事件",
        height=max(500, 28 * len(top_events)),
    )
    return _fig_to_html(fig, height=max(500, 28 * len(top_events)))


def build_mag_vs_delay(records: List[dict]) -> str:
    """星等 vs 延时散点图：3×2 子图，行=SVOM/EP/Swift，列=VT_B/VT_R。"""
    from plotly.subplots import make_subplots
    group_names = ["SVOM", "EP", "Swift"]
    group_fns = {
        "SVOM": lambda ts: ts.startswith("SVOM"),
        "EP": lambda ts: ts == "EP",
        "Swift": lambda ts: ts == "Swift",
    }
    band_names = ["VT_B", "VT_R"]
    det_color = "#4ade80"
    ul_color = "#f87171"

    # 先收集所有子图数据
    all_data = {}  # (gname, band) -> (det_x, det_y, det_text, ul_x, ul_y, ul_text)
    all_y_vals = []
    for gname in group_names:
        gfn = group_fns[gname]
        for band in band_names:
            det_x, det_y, det_text = [], [], []
            ul_x, ul_y, ul_text = [], [], []
            for r in records:
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
                    label = f"GCN {r.get('circularId')} | {r.get('event_name','')} | t={d_eff:.3f}h"
                    if m.get("is_limit"):
                        ul_x.append(d_sec); ul_y.append(val); ul_text.append(label)
                    else:
                        det_x.append(d_sec); det_y.append(val); det_text.append(label)
            all_data[(gname, band)] = (det_x, det_y, det_text, ul_x, ul_y, ul_text)
            all_y_vals.extend(det_y + ul_y)

    # 共享 y 轴范围
    if all_y_vals:
        ymin, ymax = min(all_y_vals) - 0.5, max(all_y_vals) + 0.5
    else:
        ymin, ymax = 14, 25

    # 构建 3×2 子图
    subplot_titles = []
    for gname in group_names:
        for band in band_names:
            det_x, det_y, _, ul_x, ul_y, _ = all_data[(gname, band)]
            n_det, n_ul = len(det_x), len(ul_x)
            if n_det:
                sy = sorted(det_y)
                med = sy[n_det // 2]
                stat = f"中位数 {med:.1f} | {sy[0]:.1f}~{sy[-1]:.1f} | N={n_det}+{n_ul}"
            else:
                stat = f"无探测 | N={n_det}+{n_ul}"
            subplot_titles.append(f"<b>{gname} / {band}</b><br><span style='font-size:11px;color:#475569;'>{stat}</span>")

    fig = make_subplots(rows=3, cols=2, shared_xaxes=True, shared_yaxes=False,
                        horizontal_spacing=0.16, vertical_spacing=0.08,
                        subplot_titles=subplot_titles)

    show_legend = True
    for row, gname in enumerate(group_names, 1):
        for col, band in enumerate(band_names, 1):
            det_x, det_y, det_text, ul_x, ul_y, ul_text = all_data[(gname, band)]
            if det_x:
                fig.add_trace(go.Scatter(
                    x=det_x, y=det_y, mode="markers", name="探测 (detection)",
                    showlegend=show_legend, legendgroup="det",
                    marker=dict(color=det_color, size=8, symbol="circle",
                                line=dict(width=0.5, color="#1e293b"), opacity=0.85),
                    text=det_text, hovertemplate="%{text}<br>T-T0=%{x:.0f}s mag=%{y}<extra></extra>",
                ), row=row, col=col)
            if ul_x:
                fig.add_trace(go.Scatter(
                    x=ul_x, y=ul_y, mode="markers", name="上限 (upper limit)",
                    showlegend=show_legend, legendgroup="ul",
                    marker=dict(color=ul_color, size=9, symbol="triangle-down",
                                line=dict(width=0.5, color="#1e293b"), opacity=0.85),
                    text=ul_text, hovertemplate="%{text}<br>T-T0=%{x:.0f}s mag=%{y}<extra></extra>",
                ), row=row, col=col)
            show_legend = False  # 只第一个子图显示图例

    # x 轴：对数，10^x 刻度；仅底行显示标题
    log_range = [2, 7]
    tick_vals = [10**i for i in range(2, 8)]
    tick_text = ["10<sup>%d</sup>" % i for i in range(2, 8)]
    for row in range(1, 4):
        for col in range(1, 3):
            fig.update_xaxes(type="log", range=log_range,
                             gridcolor="rgba(0,0,0,0.12)", zerolinecolor="rgba(0,0,0,0.2)",
                             tickfont=dict(color="black", size=13),
                             tickvals=tick_vals, ticktext=tick_text,
                             row=row, col=col,
                             title_text="T-T0 (s)" if row == 3 else "",
                             title_font=dict(size=15, color="black"),
                             title_standoff=8,
                             showticklabels=(row == 3),
                             tickcolor="black", ticklen=7, tickwidth=2,
                             showline=True, linewidth=2.5, linecolor="black",
                             mirror=True)
    # y 轴：反转，左右列都显示标题和刻度
    for row in range(1, 4):
        for col in range(1, 3):
            fig.update_yaxes(autorange="reversed", range=[ymin, ymax],
                             gridcolor="rgba(0,0,0,0.12)", zerolinecolor="rgba(0,0,0,0.2)",
                             tickfont=dict(color="black", size=13),
                             title_text="星等 (mag)" if col == 1 else "",
                             row=row, col=col,
                             title_font=dict(size=15, color="black"),
                             title_standoff=8,
                             showticklabels=True,
                             tickcolor="black", ticklen=7, tickwidth=2,
                             showline=True, linewidth=2.5, linecolor="black",
                             mirror=True)

    # 子图标题样式
    for i, ann in enumerate(fig.layout.annotations):
        ann.update(font=dict(size=14, color="#0f172a"))

    fig.update_layout(
        legend=dict(font=dict(size=12, color="black"), orientation="h", y=1.02, x=0.32,
                    bgcolor="white", bordercolor="black", borderwidth=1),
        margin=dict(t=70, b=55, l=65, r=25),
        height=780,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return '<div class="chart-card full" style="background:white;">' + _fig_to_html(fig, height=780, dark=False) + '</div>'


def build_all_charts(records: List[dict], stats: dict) -> "OrderedDict[str, str]":
    charts: "OrderedDict[str, str]" = OrderedDict()
    charts["type_pie"] = build_type_pie(stats)
    charts["trigger_bar"] = build_trigger_bar(stats)
    charts["band_bar"] = build_band_bar(stats)
    charts["delay_hist"] = build_delay_hist(stats)
    charts["mag_vs_delay"] = build_mag_vs_delay(records)
    charts["monthly_bar"] = build_monthly_bar(stats)
    charts["timeline"] = build_timeline(records)
    return charts
