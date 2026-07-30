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


def build_band_bar(stats: dict, records: List[dict] | None = None) -> str:
    by_band: Dict[str, int] = stats.get("by_band", {})
    if not by_band:
        return "<div class='empty'>暂无波段数据</div>"
    # 固定显示顺序：VT_B / VT_R / VT_white / VHF / 其他
    order = ["VT_B", "VT_R", "VT_white", "VHF", "VT_clear", "unknown"]
    keys = [k for k in order if k in by_band] + [k for k in by_band if k not in order]
    vals = [by_band[k] for k in keys]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b", "#aaaaaa"][:len(keys)]
    # 为每个波段生成 GCN 链接列表（点击跳转）
    band_gcn_map: Dict[str, list] = {}
    if records:
        for r in records:
            for b in (r.get("bands") or []):
                band_gcn_map.setdefault(b, []).append(r.get("circularId"))
    custom_data = []
    for k in keys:
        gcns = band_gcn_map.get(k, [])
        custom_data.append(gcns)
    fig = go.Figure([go.Bar(x=keys, y=vals, marker_color=colors, text=vals, textposition="outside",
                            textfont=dict(color="#e2e8f0", size=13),
                            customdata=[",".join(str(g) for g in gcns[:20]) for gcns in custom_data],
                            hovertemplate="<b>%{x}</b>: %{y} 条<br>GCN: %{customdata}<extra></extra>")])
    max_v = max(vals) if vals else 1
    fig.update_layout(
        title_text="波段分布 Band Distribution（点击柱子查看 GCN 详情）",
        xaxis_title="波段 Band", yaxis_title="报告数 Count",
        yaxis=dict(range=[0, max_v * 1.22]),
    )
    # 构建每个波段的 GCN 链接 HTML 弹窗
    link_parts = []
    for k, gcns in zip(keys, custom_data):
        if gcns:
            links = " ".join(f'<a href="https://gcn.nasa.gov/circulars/{g}" target="_blank" style="color:#5aa9ff;margin-right:8px;">{g}</a>' for g in sorted(gcns))
            link_parts.append(f'<div id="band-links-{k}" style="display:none;margin-top:6px;font-size:11px;line-height:1.6;"><b>{k}</b> ({len(gcns)}): {links}</div>')
    html = _fig_to_html(fig, height=420)
    # 添加点击交互脚本
    onclick_js = """
    <script>
    (function() {
        var idx = setInterval(function() {
            var plot = document.querySelectorAll('.js-plotly-plot');
            if (!plot.length) return;
            clearInterval(idx);
            plot.forEach(function(p) {
                p.on('plotly_click', function(data) {
                    var band = data.points[0].x;
                    var el = document.getElementById('band-links-' + band);
                    if (el) { el.style.display = el.style.display === 'none' ? 'block' : 'none'; }
                });
            });
        }, 500);
    })();
    </script>
    """
    return html + "".join(link_parts) + onclick_js


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
    max_v = max(vals) if vals else 1
    fig.update_layout(
        title_text="月度 VT 报告数量 Monthly VT Reports",
        xaxis_title="年月", yaxis_title="报告数",
        yaxis=dict(range=[0, max_v * 1.2]),
    )
    return _fig_to_html(fig, height=420, margin=dict(l=40, r=20, t=50, b=60))


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
        xaxis_title="后随延时区间", yaxis_title="数量",
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
    """后随延时时间线：横坐标=观测延时(T-T0)，纵坐标=事件(最近在上)。"""
    if not records:
        return "<div class='empty'>暂无数据</div>"
    # 有有效延时的记录
    valid = [r for r in records if isinstance(r.get("trigger_to_obs_hr"), (int, float)) and r["trigger_to_obs_hr"] > 0]
    if not valid:
        return "<div class='empty'>暂无延时数据</div>"
    # 按事件最近报告时间倒序（最近在上）排序事件
    latest_by_ev = {}
    for r in valid:
        ev = r.get("event_name", "UNKNOWN")
        ts = r.get("createdOn", 0)
        if ev not in latest_by_ev or ts > latest_by_ev[ev]:
            latest_by_ev[ev] = ts
    # 事件按最近时间倒序（最近的排第一=最上）
    sorted_events = sorted(latest_by_ev.keys(), key=lambda e: latest_by_ev[e], reverse=True)
    top_events = sorted_events[:45]
    ev_to_y = {e: i for i, e in enumerate(top_events)}

    # 触发源颜色
    SRC_COLOR = {
        "SVOM": "#ef4444",       # 红
        "EP": "#3b82f6",          # 蓝
        "Swift": "#f59e0b",       # 橙
        "Fermi": "#a855f7",       # 紫
    }

    # 按触发源分组
    by_src = {}
    for r in valid:
        ev = r.get("event_name", "UNKNOWN")
        if ev not in ev_to_y:
            continue
        d = r["trigger_to_obs_hr"]
        y = ev_to_y[ev]
        src = r.get("trigger_source", "Unknown") or "Unknown"
        # 归类
        if src.startswith("SVOM"):
            src_key = "SVOM"
        elif src.startswith("EP"):
            src_key = "EP"
        elif src.startswith("Swift"):
            src_key = "Swift"
        elif src.startswith("Fermi"):
            src_key = "Fermi"
        else:
            src_key = "Other"
        by_src.setdefault(src_key, {"x": [], "y": [], "text": [], "color": SRC_COLOR.get(src_key, "#94a3b8")})
        by_src[src_key]["x"].append(d)
        by_src[src_key]["y"].append(y)
        by_src[src_key]["text"].append(
            f"GCN {r.get('circularId')}<br>{r.get('subject','')[:80]}<br>"
            f"事件: {ev}<br>触发: {src}<br>延时: {d:.3f}h ({d*3600:.0f}s)"
        )

    fig = go.Figure()
    for src_key, data in by_src.items():
        fig.add_trace(go.Scatter(
            x=data["x"], y=data["y"], mode="markers",
            name=src_key, showlegend=True,
            marker=dict(color=data["color"], size=11, line=dict(width=1, color="DarkSlateGrey"), opacity=0.85),
            text=data["text"], hoverinfo="text",
        ))

    fig.update_layout(
        title_text=f"VT 后随延时时间线 Follow-up Delay Timeline（{len(top_events)} 个事件 / {sum(len(d['x']) for d in by_src.values())} 条报告）",
        xaxis_title="观测延时 T-T₀ (小时, 对数)", yaxis_title="事件 (↑最近 → 最老)",
        height=max(560, 26 * len(top_events)),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(r=100),
    )
    # x 轴对数
    fig.update_xaxes(type="log")
    # y 轴：用事件名作为刻度标签
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(top_events))),
        ticktext=top_events,
        autorange="reversed",  # 第一个（最近）在最上方
    )
    return _fig_to_html(fig, height=max(560, 26 * len(top_events)))


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
                             title_text="后随延时 T-T₀ (s)" if row == 3 else "",
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
        showlegend=False,
        margin=dict(t=60, b=55, l=65, r=25),
        height=780,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return '<div class="chart-card full" style="background:white;">' + _fig_to_html(fig, height=780, dark=False) + '</div>'


def build_obs_vs_publish(records: List[dict]) -> str:
    """后随观测延时 vs GCN 发布延时散点图，SVOM(红) vs 其他卫星(蓝)。
    delay = 后随开始时间 - T0；gcn_publish_delay = GCN发布时间 - T0。
    """
    from datetime import datetime, timezone
    svom_x, svom_y, svom_text = [], [], []
    oth_x, oth_y, oth_text = [], [], []
    for r in records:
        d_obs = r.get("trigger_to_obs_hr")
        if not isinstance(d_obs, (int, float)) or d_obs <= 0:
            continue
        obs_str = r.get("obs_start_utc")
        if not obs_str:
            continue
        try:
            obs_dt = datetime.fromisoformat(obs_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if obs_dt.tzinfo is None:
            obs_dt = obs_dt.replace(tzinfo=timezone.utc)
        try:
            pub_dt = datetime.fromtimestamp(r["createdOn"] / 1000.0, tz=timezone.utc)
        except Exception:
            continue
        # T0 = obs_start - delay; 发布延时 = pub - T0 = (pub - obs_start) + delay
        d_pub = (pub_dt - obs_dt).total_seconds() / 3600.0 + d_obs  # 发布 - T0
        if d_pub <= 0 or d_pub > 2000:
            continue
        src = r.get("trigger_source", "Unknown") or "Unknown"
        is_svom = src.startswith("SVOM")
        label = f"GCN {r.get('circularId')}<br>{r.get('event_name','')}<br>触发: {src}<br>后随延时: {d_obs:.2f}h<br>发布延时: {d_pub:.2f}h"
        if is_svom:
            svom_x.append(d_obs); svom_y.append(d_pub); svom_text.append(label)
        else:
            oth_x.append(d_obs); oth_y.append(d_pub); oth_text.append(label)

    fig = go.Figure()
    if oth_x:
        fig.add_trace(go.Scatter(
            x=oth_x, y=oth_y, mode="markers", name="外部卫星 (EP/Swift/Fermi)",
            marker=dict(color="#3b82f6", size=10, line=dict(width=0.5, color="#1e293b"), opacity=0.75),
            text=oth_text, hoverinfo="text",
        ))
    if svom_x:
        fig.add_trace(go.Scatter(
            x=svom_x, y=svom_y, mode="markers", name="SVOM/ECLAIRs",
            marker=dict(color="#ef4444", size=10, line=dict(width=0.5, color="#1e293b"), opacity=0.75),
            text=svom_text, hoverinfo="text",
        ))
    # 对角参考线 y=x
    all_vals = svom_x + svom_y + oth_x + oth_y
    if all_vals:
        lo, hi = min(all_vals) * 0.5, max(all_vals) * 2
        fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines",
                                 name="y = x", line=dict(color="#94a3b8", dash="dash", width=1.5),
                                 showlegend=True, hoverinfo="none"))
    fig.update_layout(
        title_text="后随观测延时 vs GCN 发布延时 Obs Delay vs Publish Delay",
        xaxis_title="后随延时 (后随开始−T₀, h, 对数)", yaxis_title="GCN 发布延时 (发布−T₀, h, 对数)",
        height=440, legend=dict(orientation="v", yanchor="bottom", y=0.05, xanchor="right", x=0.98,
                                bgcolor="rgba(255,255,255,0.85)", bordercolor="#94a3b8", borderwidth=1,
                                font=dict(size=11)),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=60, b=50, l=60, r=30),
    )
    fig.update_xaxes(type="log", gridcolor="rgba(0,0,0,0.12)", tickfont=dict(color="black"))
    fig.update_yaxes(type="log", gridcolor="rgba(0,0,0,0.12)", tickfont=dict(color="black"))

    # 后随延时 ≤2h 统计总结（独立于 obs_start_utc，直接用 trigger_to_obs_hr）
    def _stats_le2h(dels):
        d = sorted([x for x in dels if 0 < x <= 2])
        if not d:
            return None
        med = d[len(d) // 2]
        return len(d), d[0], med, d[-1]

    # 从全部记录直接统计（不依赖散点图的 obs_start 过滤）
    svom_dels, ep_dels, swift_dels, fermi_dels, oth_dels = [], [], [], [], []
    # GCN 发布延时统计（需要 obs_start）
    svom_pub, ep_pub, swift_pub, oth_pub = [], [], [], []
    for r in records:
        d_obs = r.get("trigger_to_obs_hr")
        if not isinstance(d_obs, (int, float)) or d_obs <= 0:
            continue
        src = (r.get("trigger_source") or "")
        is_svom = src.startswith("SVOM")
        if is_svom:
            svom_dels.append(d_obs)
        elif src.startswith("EP"):
            ep_dels.append(d_obs)
        elif src.startswith("Swift"):
            swift_dels.append(d_obs)
        elif src.startswith("Fermi"):
            fermi_dels.append(d_obs)
        if not is_svom:
            oth_dels.append(d_obs)
        # 发布延时
        obs_str = r.get("obs_start_utc")
        if obs_str:
            try:
                obs_dt = datetime.fromisoformat(obs_str.replace("Z", "+00:00"))
                if obs_dt.tzinfo is None:
                    obs_dt = obs_dt.replace(tzinfo=timezone.utc)
                pub_dt = datetime.fromtimestamp(r["createdOn"] / 1000.0, tz=timezone.utc)
                d_pub = (pub_dt - obs_dt).total_seconds() / 3600.0 + d_obs
                if d_pub > 0:
                    if is_svom:
                        svom_pub.append(d_pub)
                    elif src.startswith("EP"):
                        ep_pub.append(d_pub)
                    elif src.startswith("Swift"):
                        swift_pub.append(d_pub)
                    else:
                        oth_pub.append(d_pub)
            except Exception:
                pass
    all_dels = svom_dels + oth_dels
    s_svom = _stats_le2h(svom_dels)
    s_ep = _stats_le2h(ep_dels)
    s_swift = _stats_le2h(swift_dels)
    s_fermi = _stats_le2h(fermi_dels)
    s_oth = _stats_le2h(oth_dels)
    s_all = _stats_le2h(all_dels)
    # 发布延时统计
    def _pub_stats(dels):
        d = sorted([x for x in dels if x > 0])
        if not d:
            return None
        return len(d), d[0], d[len(d)//2], d[-1]
    p_svom = _pub_stats(svom_pub)
    p_oth = _pub_stats(ep_pub + swift_pub + oth_pub)

    summary = '<div class="chart-card full" style="background:white;border:1px solid #cbd5e1;padding:14px 18px;margin-top:-8px;">'
    summary += '<div style="font-size:14px;font-weight:bold;color:#1e293b;margin-bottom:8px;">后随延时 ≤2h 统计总结（剔除 >2h 长延时点）</div>'
    summary += '<table style="width:100%;border-collapse:collapse;font-size:12px;color:#334155;">'
    summary += '<tr style="border-bottom:2px solid #e2e8f0;"><th style="text-align:left;padding:4px 8px;">触发源</th><th style="text-align:right;padding:4px 8px;">样本数</th><th style="text-align:right;padding:4px 8px;">最小值</th><th style="text-align:right;padding:4px 8px;">中位数</th><th style="text-align:right;padding:4px 8px;">最大值</th></tr>'
    for name, s in [("SVOM/ECLAIRs", s_svom), ("EP", s_ep), ("Swift", s_swift), ("Fermi", s_fermi), ("外部卫星合计", s_oth), ("全部", s_all)]:
        if s:
            n, mn, md, mx = s
            summary += f'<tr style="border-bottom:1px solid #f1f5f9;"><td style="padding:4px 8px;font-weight:600;">{name}</td><td style="text-align:right;padding:4px 8px;">{n}</td><td style="text-align:right;padding:4px 8px;">{mn:.4f}h ({mn*3600:.0f}s)</td><td style="text-align:right;padding:4px 8px;">{md:.4f}h ({md*3600:.0f}s)</td><td style="text-align:right;padding:4px 8px;">{mx:.2f}h</td></tr>'
    summary += '</table>'
    # GCN 发布延时统计表
    if p_svom or p_oth:
        summary += '<div style="font-size:14px;font-weight:bold;color:#1e293b;margin:14px 0 8px;">GCN 发布延时统计（发布时间 − T₀）</div>'
        summary += '<table style="width:100%;border-collapse:collapse;font-size:12px;color:#334155;">'
        summary += '<tr style="border-bottom:2px solid #e2e8f0;"><th style="text-align:left;padding:4px 8px;">触发源</th><th style="text-align:right;padding:4px 8px;">样本数</th><th style="text-align:right;padding:4px 8px;">最小值</th><th style="text-align:right;padding:4px 8px;">中位数</th><th style="text-align:right;padding:4px 8px;">最大值</th></tr>'
        for name, p in [("SVOM/ECLAIRs", p_svom), ("外部卫星合计", p_oth)]:
            if p:
                n, mn, md, mx = p
                summary += f'<tr style="border-bottom:1px solid #f1f5f9;"><td style="padding:4px 8px;font-weight:600;">{name}</td><td style="text-align:right;padding:4px 8px;">{n}</td><td style="text-align:right;padding:4px 8px;">{mn:.2f}h</td><td style="text-align:right;padding:4px 8px;">{md:.2f}h</td><td style="text-align:right;padding:4px 8px;">{mx:.1f}h</td></tr>'
        summary += '</table>'
    summary += '<div style="margin-top:10px;font-size:12px;color:#475569;line-height:1.7;">'
    if s_svom:
        summary += f'<b>后随延时：</b>SVOM/ECLAIRs 自触发最快响应仅 <b>{s_svom[1]*3600:.0f} 秒</b>（{s_svom[1]:.2f} min），中位数 <b>{s_svom[2]*60:.0f} 分钟</b>，'
    if s_oth:
        summary += f'外部卫星 ToO 中位数约 <b>{s_oth[2]:.1f} 小时</b>。'
    summary += 'SVOM 在轨自动 slew 具有显著的分钟级快速响应优势。'
    if p_svom:
        summary += f'<br><b>GCN 发布延时：</b>SVOM 触发后中位 <b>{p_svom[2]:.1f} 小时</b>完成 GCN 发布'
    if p_oth:
        summary += f'，外部卫星约 <b>{p_oth[2]:.1f} 小时</b>。'
    summary += '</div></div>'

    return '<div class="chart-card full" style="background:white;">' + _fig_to_html(fig, height=440, dark=False) + '</div>' + summary


def build_ident_time_trend(records: List[dict]) -> str:
    """证认时间消耗累积增长图：GCN发布 - 后随延时 - 6h(X-band平均下行)。
    仅统计24h内发布的样本。横坐标=触发时间(累积)，纵坐标=证认时间消耗(h)。
    """
    from datetime import datetime, timezone
    X_BAND_DOWNLINK = 6.0  # X-band 平均下行时间 (h)
    PUBLISH_LIMIT = 24.0   # 仅统计24h内发布
    PERSON_PER_BURST = 2   # 每个暴按2人参与量计算工作量

    import re as _re
    from datetime import timedelta as _td
    RE_GRB_DATE = _re.compile(r"(?:GRB|EP)\s*(\d{2})(\d{2})(\d{2})")

    svom_x, svom_y, svom_text = [], [], []
    oth_x, oth_y, oth_text = [], [], []
    n_exact, n_est = 0, 0  # 精确/估算 计数
    # 收集所有月份的数据（含超24h样本，后续用均值替代）
    month_data: "dict[str, list]" = {}  # month -> [(ident_time, is_overlimit), ...]
    within_24h_vals = []  # ≤24h 样本的证认时间（用于算均值）

    for r in records:
        pub_dt = datetime.fromtimestamp(r["createdOn"] / 1000.0, tz=timezone.utc)
        obs_str = r.get("obs_start_utc")
        d_obs = r.get("trigger_to_obs_hr")
        has_delay = isinstance(d_obs, (int, float)) and d_obs > 0

        if obs_str:
            # 方式1：有观测开始绝对时间，精确计算
            try:
                obs_dt = datetime.fromisoformat(obs_str.replace("Z", "+00:00"))
                if obs_dt.tzinfo is None:
                    obs_dt = obs_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            diff_h = (pub_dt - obs_dt).total_seconds() / 3600.0
            is_est = False
            n_exact += 1
        elif has_delay:
            # 方式2：无绝对时间，从事件名日期 + 后随延时估算观测开始时间
            ev = r.get("event_name", "") or ""
            m = RE_GRB_DATE.search(ev)
            if not m:
                continue
            try:
                yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
                t0_dt = datetime(2000 + yy, mm, dd, tzinfo=timezone.utc)
            except ValueError:
                continue
            obs_dt = t0_dt + _td(hours=d_obs)
            diff_h = (pub_dt - obs_dt).total_seconds() / 3600.0
            is_est = True
            n_est += 1
        else:
            continue

        if diff_h <= 0:
            continue
        ident_time = diff_h - X_BAND_DOWNLINK
        if ident_time < -6:
            continue
        is_overlimit = diff_h > PUBLISH_LIMIT

        src = (r.get("trigger_source") or "Unknown")
        is_svom = src.startswith("SVOM")
        d_obs_str = f"{d_obs:.2f}h" if has_delay else "N/A"
        method = "精确" if not is_est else "估算(事件名+延时)"
        label = (f"GCN {r.get('circularId')}<br>{r.get('event_name','')}<br>触发: {src}"
                 f"<br>发布−观测: {diff_h:.1f}h<br>后随延时: {d_obs_str}"
                 f"<br>X-band下行: {X_BAND_DOWNLINK:.0f}h"
                 f"<br>证认时间: {ident_time:.1f}h ({method})")
        trig_date = obs_dt.strftime("%Y-%m-%d")
        month_key = trig_date[:7]

        # 收集月度数据（所有样本）
        month_data.setdefault(month_key, []).append((ident_time, is_overlimit))
        if not is_overlimit:
            within_24h_vals.append(ident_time)

        # 散点图只显示 ≤24h 的样本
        if is_overlimit:
            continue
        if is_svom:
            svom_x.append(trig_date); svom_y.append(ident_time); svom_text.append(label)
        else:
            oth_x.append(trig_date); oth_y.append(ident_time); oth_text.append(label)

    if not svom_x and not oth_x:
        return ""

    fig = go.Figure()
    if oth_x:
        fig.add_trace(go.Scatter(
            x=oth_x, y=oth_y, mode="markers", name="外部卫星 (EP/Swift/Fermi)",
            marker=dict(color="#3b82f6", size=9, line=dict(width=0.5, color="#1e293b"), opacity=0.7),
            text=oth_text, hoverinfo="text",
        ))
    if svom_x:
        fig.add_trace(go.Scatter(
            x=svom_x, y=svom_y, mode="markers", name="SVOM/ECLAIRs",
            marker=dict(color="#ef4444", size=9, line=dict(width=0.5, color="#1e293b"), opacity=0.7),
            text=svom_text, hoverinfo="text",
        ))
    # y=0 参考线
    fig.add_hline(y=0, line_dash="dash", line_color="#94a3b8", line_width=1,
                  annotation_text="证认时间=0（发布即下行完成）", annotation_position="top left",
                  annotation_font_size=10, annotation_font_color="#64748b")

    fig.update_layout(
        title_text="证认时间消耗趋势（≤24h 内发布）",
        xaxis_title="观测日期", yaxis_title="证认时间消耗 (h)",
        height=420,
        legend=dict(orientation="v", yanchor="top", y=0.98, xanchor="right", x=0.98,
                    bgcolor="rgba(255,255,255,0.85)", bordercolor="#94a3b8", borderwidth=1, font=dict(size=11)),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=60, b=50, l=60, r=30),
    )
    fig.update_xaxes(gridcolor="rgba(0,0,0,0.1)", tickfont=dict(color="black"))
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.1)", tickfont=dict(color="black"), zeroline=True, zerolinecolor="rgba(0,0,0,0.3)")

    # 统计说明
    all_idents = svom_y + oth_y
    n_total = len(all_idents)
    n_positive = len([v for v in all_idents if v > 0])
    med = sorted(all_idents)[len(all_idents) // 2] if all_idents else 0
    summary = ('<div style="font-size:12px;color:#475569;margin-top:8px;line-height:1.7;">'
               f'<b>统计说明：</b>共 {n_total} 个样本（≤{PUBLISH_LIMIT:.0f}h 内发布），其中 {n_exact} 个精确计算、{n_est} 个估算（事件名+延时）。'
               f'中位证认时间 <b>{med:.1f}h</b>。'
               f'其中 {n_positive} 个样本证认时间 >0（即数据下行后仍需额外分析时间），'
               f'{n_total - n_positive} 个 ≤0（下行完成前即已发布）。'
               '负值表示 GCN 报告在 X-band 数据下行预计完成前就已提交，可能基于 VHF 快速预警数据。</div>')

    # ===== 累积增长图（按月 bin，单位：人时 = 证认时间 × 2人/暴） =====
    from collections import OrderedDict as OD
    # ≤24h 样本的平均证认时间（用于替代超24h样本）
    avg_ident = sum(within_24h_vals) / len(within_24h_vals) if within_24h_vals else 0.0
    # 按月聚合（超24h样本用均值替代）
    month_totals: "OD[str, float]" = OD()
    n_over = 0
    for m in sorted(month_data.keys()):
        total = 0.0
        for val, over in month_data[m]:
            if over:
                total += avg_ident  # 用≤24h样本均值替代
                n_over += 1
            else:
                total += val
        month_totals[m] = total * PERSON_PER_BURST
    # 累积
    months = sorted(month_totals.keys())
    cumul = []
    running = 0.0
    for m in months:
        running += month_totals[m]
        cumul.append(running)

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=months, y=[month_totals[m] for m in months],
        name="月度工作量", marker_color="#93c5fd",
        text=[f"{month_totals[m]:.0f}" for m in months],
        textposition="inside", textfont=dict(size=10, color="#1e3a5f"),
    ))
    fig2.add_trace(go.Scatter(
        x=months, y=cumul, name="累积工作量", mode="lines+markers",
        line=dict(color="#ef4444", width=2.5), marker=dict(size=7, color="#ef4444"),
        text=[f"累积: {c:.0f}人时" for c in cumul], hoverinfo="x+text",
        yaxis="y2",
    ))
    total_h = cumul[-1] if cumul else 0
    total_days = total_h / 24.0
    fig2.update_layout(
        title=f"<b>证认工作量累积增长</b><br><span style='font-size:11px;color:#64748b;'>按 {PERSON_PER_BURST} 人/暴 | 总工作量 {total_h:.0f} 人时（{total_days:.0f} 人天）| 超24h样本按均值 {avg_ident:.1f}h 替代，共 {n_over} 个</span>",
        title_font_size=14,
        xaxis_title="月份", yaxis=dict(title="月度工作量 (人时)", gridcolor="rgba(0,0,0,0.1)"),
        yaxis2=dict(title="累积工作量 (人时)", overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"),
        height=460,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0, font=dict(size=11)),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=90, b=50, l=60, r=70),
    )
    fig2.update_xaxes(tickfont=dict(color="black"))
    fig2.update_yaxes(tickfont=dict(color="black"))

    return ('<div class="chart-card full" style="background:white;">' + _fig_to_html(fig, height=420, dark=False) + summary + '</div>'
            + '<div class="chart-card full" style="background:white;">' + _fig_to_html(fig2, height=460, dark=False) + '</div>')


def build_all_charts(records: List[dict], stats: dict) -> "OrderedDict[str, str]":
    charts: "OrderedDict[str, str]" = OrderedDict()
    charts["type_pie"] = build_type_pie(stats)
    charts["trigger_bar"] = build_trigger_bar(stats)
    charts["band_bar"] = build_band_bar(stats, records)
    charts["delay_hist"] = build_delay_hist(stats)
    charts["mag_vs_delay"] = build_mag_vs_delay(records)
    charts["obs_vs_publish"] = build_obs_vs_publish(records)
    charts["ident_time"] = build_ident_time_trend(records)
    charts["monthly_bar"] = build_monthly_bar(stats)
    charts["timeline"] = build_timeline(records)
    return charts
