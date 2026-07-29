"""
VT GCN History —— Flask Web 应用 + 后台 10 分钟定时更新

启动方式：
    python3 app.py

首次启动会下载完整 GCN 归档做初始化（约 30MB 下载 + 解析），
之后每 10 分钟自动增量拉取最新 circulars。
"""
from __future__ import annotations

import html
import logging
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template_string, request

import config
from gcn_fetcher import created_on_to_iso
from vt_store import get_store
import visualizations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("app")

app = Flask(__name__)
store = get_store()


# ---------- 后台调度 ----------
class UpdateScheduler:
    def __init__(self, interval: int = config.UPDATE_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            # 启动时立即尝试一次
            while not self._stop.is_set():
                try:
                    if not store.meta().get("max_circular_id"):
                        store.initialize_from_full_archive()
                    else:
                        store.update_incremental()
                except Exception as exc:  # pragma: no cover
                    log.error("Scheduled update failed: %s", exc)
                # 等待 interval 或停止
                self._stop.wait(self.interval)

        self._thread = threading.Thread(target=_run, name="vt-updater", daemon=True)
        self._thread.start()
        log.info("Scheduler started (interval=%ds)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


scheduler = UpdateScheduler()


# ---------- 页面模板 ----------
INDEX_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>SVOM/VT GCN Circulars 历史 & 分析</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root { --bg:#0b1016; --card:#161d27; --card2:#1d2733; --fg:#f0f4f8; --muted:#b8c4d2; --muted2:#8896a8; --accent:#5aa9ff; --green:#4ade80; --red:#f87171; --orange:#fbbf24; --purple:#c4a8e8; --border:#2a3644; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif; line-height:1.5; }
    header { position:sticky; top:0; z-index:10; background:linear-gradient(135deg,#161d27,#222e3c); border-bottom:1px solid var(--border); padding:18px 28px; }
    header h1 { margin:0; font-size:20px; color:#fff; }
    header .sub { color:var(--muted); font-size:13px; margin-top:4px; }
    a { color:var(--accent); text-decoration:none; }
    a:hover { text-decoration:underline; }
    .wrap { max-width:1280px; margin:0 auto; padding:24px 20px 60px; }
    .grid-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:18px 0; }
    .stat { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
    .stat .num { font-size:26px; font-weight:700; color:var(--accent); }
    .stat .lbl { color:var(--muted2); font-size:12px; margin-top:4px; }
    .stat.green .num { color:var(--green); }
    .stat.red .num { color:var(--red); }
    .meta-bar { display:flex; flex-wrap:wrap; gap:14px; align-items:center; color:var(--muted); font-size:13px; margin-bottom:10px; }
    .meta-bar .badge { background:var(--card); border:1px solid var(--border); border-radius:999px; padding:4px 12px; }
    .meta-bar b { color:#fff; }
    .controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:14px 0; }
    input, select, button { background:var(--card2); color:var(--fg); border:1px solid var(--border); border-radius:8px; padding:8px 12px; font-size:13px; }
    button { cursor:pointer; font-weight:600; }
    button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
    button:hover { filter:brightness(1.15); }
    .charts { display:grid; grid-template-columns:repeat(auto-fit,minmax(480px,1fr)); gap:16px; margin:18px 0; }
    .chart-card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px; overflow:hidden; min-height:200px; contain:layout style; }
    .chart-card.full { grid-column:1/-1; }
    /* Plotly 内部容器强制 100% 宽度，确保每个图表撑满其 grid cell */
    .chart-card > div, .chart-card > div > div { width:100% !important; max-width:100% !important; }
    .chart-card svg { max-width:100% !important; }
    .empty { color:var(--muted); padding:30px; text-align:center; }
    table { width:100%; border-collapse:collapse; font-size:13px; background:var(--card); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
    th, td { padding:9px 10px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; color:var(--fg); }
    th { background:var(--card2); color:var(--muted); font-weight:600; position:sticky; top:0; }
    tr:hover td { background:var(--card2); }
    .tag { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }
    .tag.det { background:rgba(74,222,128,.18); color:#86efac; }
    .tag.ul { background:rgba(248,113,113,.18); color:#fca5a5; }
    .tag.other { background:rgba(148,163,184,.18); color:#cbd5e1; }
    .small { color:var(--muted); font-size:12px; }
    .pill { display:inline-block; background:var(--card2); color:var(--fg); padding:1px 8px; border-radius:6px; margin:1px; font-size:11px; border:1px solid var(--border); }
    footer { text-align:center; color:var(--muted2); font-size:12px; padding:20px; border-top:1px solid var(--border); margin-top:30px; }
    .live-dot { display:inline-block; width:8px; height:8px; background:var(--green); border-radius:50%; animation:pulse 1.8s infinite; margin-right:6px; vertical-align:middle; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
    h3 { color:#fff; }
  </style>
</head>
<body>
<header>
  <h1>SVOM / VT · GCN Circulars 历史与分析</h1>
  <div class="sub">自动从 <a href="https://gcn.nasa.gov/circulars" target="_blank">GCN</a> 识别标题/正文含 VT 的报告，分类（探测 / 上限）并可视化；每 {{ interval_min }} 分钟自动刷新。</div>
</header>
<div class="wrap">
  <div class="meta-bar">
    <span class="badge"><span class="live-dot"></span>自动更新中</span>
    <span>最大 GCN ID: <b>{{ meta.max_circular_id }}</b></span>
    <span>VT 记录数: <b>{{ stats.total }}</b></span>
    <span>最近全量更新: <b>{{ meta.last_full_update or '—' }}</b></span>
    <span>最近增量更新: <b>{{ meta.last_incremental_update or '—' }}</b></span>
    <span>扫描总数: <b>{{ meta.total_scanned }}</b></span>
  </div>

  <div class="grid-stats">
    <div class="stat"><div class="num">{{ stats.total }}</div><div class="lbl">VT 报告总数 Total</div></div>
    <div class="stat green"><div class="num">{{ stats.detection_count }}</div><div class="lbl">探测 Detections</div></div>
    <div class="stat red"><div class="num">{{ stats.upper_limit_count }}</div><div class="lbl">上限 Upper Limits</div></div>
    <div class="stat"><div class="num">{{ stats.stellar_flare_count }}</div><div class="lbl">恒星耀斑 Flares</div></div>
    <div class="stat"><div class="num">{{ stats.clarification_count }}</div><div class="lbl">澄清/否定 Clarif.</div></div>
    <div class="stat"><div class="num">{{ stats.events_count }}</div><div class="lbl">涉及事件数 Events</div></div>
    <div class="stat"><div class="num">{{ '%.2f'|format(stats.median_delay_hr) if stats.median_delay_hr is not none else '—' }}</div><div class="lbl">首光中位延时 P50 (hr)</div></div>
    <div class="stat green"><div class="num">{{ '%.0f'|format((stats.frac_within_2h or 0)*100) }}%</div><div class="lbl">≤2h 早期响应占比</div></div>
    <div class="stat"><div class="num">{{ '%.0f'|format((stats.frac_within_6h or 0)*100) }}%</div><div class="lbl">≤6h 响应占比</div></div>
  </div>

  <div class="controls">
    <button onclick="triggerUpdate()">立即更新</button>
  </div>

  <div class="charts">
    <div class="chart-card full">{{ charts.type_pie|safe }}</div>
    <div class="chart-card">{{ charts.trigger_bar|safe }}</div>
    <div class="chart-card">{{ charts.band_bar|safe }}</div>
    {{ charts.delay_hist|safe }}
    {{ charts.mag_vs_delay|safe }}
    <div class="chart-card full">{{ charts.monthly_bar|safe }}</div>
    <div class="chart-card full">{{ charts.timeline|safe }}</div>
  </div>

  <h3 style="margin-top:30px;margin-bottom:10px">VT 报告列表（共 {{ total }} 条，显示 {{ records|length }} 条）</h3>
  <div class="controls" style="margin-top:0;margin-bottom:10px">
    <input id="q" type="text" placeholder="搜索 Subject / 事件 / 正文..." value="{{ q }}" style="flex:1;min-width:220px"/>
    <select id="ftype">
      <option value="">全部类型</option>
      <option value="detection" {{ 'selected' if ftype=='detection' else '' }}>探测 Detection</option>
      <option value="upper_limit" {{ 'selected' if ftype=='upper_limit' else '' }}>上限 Upper Limit</option>
      <option value="stellar_flare" {{ 'selected' if ftype=='stellar_flare' else '' }}>恒星耀斑 Stellar Flare</option>
      <option value="clarification" {{ 'selected' if ftype=='clarification' else '' }}>澄清/否定 Clarification</option>
      <option value="other" {{ 'selected' if ftype=='other' else '' }}>其他 Other</option>
    </select>
    <select id="ps">
      {% for n in [20,50,100,200] %}<option value="{{ n }}" {{ 'selected' if n==pagesize else '' }}>{{ n }} 条/页</option>{% endfor %}
    </select>
    <button class="primary" onclick="applyFilter()">应用</button>
    <button onclick="clearFilter()">清除</button>
  </div>
  <table>
    <thead><tr>
      <th>GCN ID</th><th>时间 (UTC)</th><th>事件</th><th>类型</th><th>触发卫星</th><th>Subject</th><th>波段</th><th>延时 (hr)</th><th>观测起始</th>
    </tr></thead>
    <tbody>
    {% for r in records %}
      <tr>
        <td><a href="https://gcn.nasa.gov/circulars/{{ r.circularId }}" target="_blank">{{ r.circularId }}</a></td>
        <td class="small">{{ r.created_on_iso }}</td>
        <td>{{ r.event_name }}</td>
        <td>
          {% if r.report_type=='detection' %}<span class="tag det">探测</span>
          {% elif r.report_type=='upper_limit' %}<span class="tag ul">上限</span>
          {% elif r.report_type=='stellar_flare' %}<span class="tag" style="background:rgba(251,191,36,.18);color:#fcd34d">耀斑</span>
          {% elif r.report_type=='clarification' %}<span class="tag" style="background:rgba(196,168,232,.18);color:#d8b4fe">澄清</span>
          {% else %}<span class="tag other">其他</span>{% endif %}
        </td>
        <td><span class="pill">{{ r.trigger_source }}</span></td>
        <td>{{ r.subject }}</td>
        <td>{% for b in r.bands %}<span class="pill">{{ b }}</span>{% endfor %}</td>
        <td>{{ '%.2f'|format(r.trigger_to_obs_hr) if r.trigger_to_obs_hr is not none else '—' }}</td>
        <td class="small">{{ r.obs_start_utc or '—' }}</td>
      </tr>
    {% else %}
      <tr><td colspan="9" class="empty">暂无符合条件的记录</td></tr>
    {% endfor %}
    </tbody>
  </table>

  <div class="controls" style="justify-content:space-between;margin-top:14px">
    <div>
      {% if page>1 %}<button onclick="goPage({{ page-1 }})">上一页</button>{% endif %}
      <span class="small">第 {{ page }} / {{ total_pages }} 页</span>
      {% if page<total_pages %}<button onclick="goPage({{ page+1 }})">下一页</button>{% endif %}
    </div>
    <div class="small">触发/观测时间从正文中自动解析；延时=触发到首光时间</div>
  </div>

  <footer>
    数据来源：NASA GCN &middot; SVOM/VT team &middot; 本工具仅用于研究展示，自动分类可能存在误差。
  </footer>
</div>
<script>
function applyFilter(){const q=encodeURIComponent(document.getElementById('q').value);const f=document.getElementById('ftype').value;const ps=document.getElementById('ps').value;window.location=`/?q=${q}&ftype=${f}&ps=${ps}&page=1`;}
function clearFilter(){window.location='/';}
function goPage(p){const q=encodeURIComponent(document.getElementById('q').value);const f=document.getElementById('ftype').value;const ps=document.getElementById('ps').value;window.location=`/?q=${q}&ftype=${f}&ps=${ps}&page=${p}`;}
function triggerUpdate(){fetch('/api/update',{method:'POST'}).then(r=>r.json()).then(d=>{alert(d.message||JSON.stringify(d));setTimeout(()=>location.reload(),1500);}).catch(e=>alert('更新失败: '+e));}
setInterval(()=>location.reload(),{{ interval_min }}*60*1000);
</script>
</body>
</html>
"""


def _filter_records(records, q: str, ftype: str):
    q_lower = (q or "").lower().strip()
    out = []
    for r in records:
        if ftype and r.get("report_type") != ftype:
            continue
        if q_lower:
            blob = f"{r.get('subject','')} {r.get('event_name','')} {r.get('body','')}".lower()
            if q_lower not in blob:
                continue
        out.append(r)
    return out


def _paginate(items, page, pagesize):
    total = len(items)
    total_pages = max(1, (total + pagesize - 1) // pagesize)
    page = max(1, min(page, total_pages))
    start = (page - 1) * pagesize
    return items[start:start + pagesize], page, total_pages


@app.route("/")
def index():
    q = request.args.get("q", "")
    ftype = request.args.get("ftype", "")
    pagesize = int(request.args.get("ps", 50))
    page = int(request.args.get("page", 1))

    all_recs = store.all_records()
    filtered = _filter_records(all_recs, q, ftype)
    page_items, page, total_pages = _paginate(filtered, page, pagesize)

    # 给每条加 ISO 时间字符串
    for r in page_items:
        r["created_on_iso"] = created_on_to_iso(r.get("createdOn", 0))

    stats = store.stats()
    charts = visualizations.build_all_charts(filtered, stats)

    return render_template_string(
        INDEX_TEMPLATE,
        meta=store.meta(),
        stats=stats,
        charts=charts,
        records=page_items,
        total=len(filtered),
        q=q, ftype=ftype, pagesize=pagesize, page=page, total_pages=total_pages,
        interval_min=config.UPDATE_INTERVAL_SECONDS // 60,
    )


@app.route("/api/records")
def api_records():
    q = request.args.get("q", "")
    ftype = request.args.get("ftype", "")
    all_recs = store.all_records()
    filtered = _filter_records(all_recs, q, ftype)
    return jsonify({"total": len(filtered), "records": filtered[:200]})


@app.route("/api/stats")
def api_stats():
    return jsonify(store.stats())


@app.route("/api/meta")
def api_meta():
    return jsonify(store.meta())


@app.route("/api/update", methods=["POST"])
def api_update():
    """手动触发一次增量更新。"""
    try:
        added = store.update_incremental()
        return jsonify({"ok": True, "added": added, "message": f"更新完成，新增 VT 报告 {added} 条"})
    except Exception as exc:
        return jsonify({"ok": False, "message": f"更新失败: {exc}"}), 500


# ---------- 触发卫星详情页 ----------
TRIGGER_DETAIL_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>触发卫星: {{ trigger }} - VT GCN 列表</title>
<style>
:root { --bg:#0b1016; --card:#161d27; --card2:#1d2733; --fg:#f0f4f8; --muted:#b8c4d2; --muted2:#8896a8; --accent:#5aa9ff; --border:#2a3644; --green:#4ade80; --red:#f87171; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC",sans-serif; line-height:1.5; }
header { background:linear-gradient(135deg,#161d27,#222e3c); border-bottom:1px solid var(--border); padding:18px 28px; }
header h1 { margin:0; font-size:20px; color:#fff; }
header .sub { color:var(--muted); font-size:13px; margin-top:4px; }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
.wrap { max-width:1300px; margin:0 auto; padding:24px 20px 60px; }
table { width:100%; border-collapse:collapse; font-size:13px; background:var(--card); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
th, td { padding:9px 10px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; color:var(--fg); }
th { background:var(--card2); color:var(--muted); font-weight:600; position:sticky; top:0; }
tr:hover td { background:var(--card2); }
.tag { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }
.tag.det { background:rgba(74,222,128,.18); color:#86efac; }
.tag.ul { background:rgba(248,113,113,.18); color:#fca5a5; }
.tag.other { background:rgba(148,163,184,.18); color:#cbd5e1; }
.pill { display:inline-block; background:var(--card2); color:var(--fg); padding:1px 8px; border-radius:6px; margin:1px; font-size:11px; border:1px solid var(--border); }
.small { color:var(--muted); font-size:12px; }
.summary { display:flex; gap:20px; flex-wrap:wrap; margin:16px 0; }
.summary .box { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px 18px; }
.summary .box .num { font-size:22px; font-weight:700; color:var(--accent); }
.summary .box .lbl { color:var(--muted2); font-size:12px; }
/* 人工分类控件 */
.mo-sel { background:var(--card2); color:var(--fg); border:1px solid var(--border); border-radius:5px; padding:3px 6px; font-size:12px; max-width:140px; }
.mo-btn { background:var(--accent); color:#0b1016; border:none; border-radius:5px; padding:3px 10px; font-size:12px; font-weight:700; cursor:pointer; }
.mo-btn:hover { opacity:.85; }
.mo-btn:disabled { opacity:.4; cursor:default; }
.mo-manual { color:#fbbf24; font-size:11px; }
.mo-saved { color:var(--green); font-size:11px; display:none; }
.mo-link { font-size:12px; color:var(--accent); }
</style></head><body>
<header>
  <h1>触发卫星: {{ trigger }}</h1>
  <div class="sub"><a href="/">&larr; 返回主页</a> &nbsp;|&nbsp; 以下为该触发/主探测卫星对应的全部 VT GCN 报告，可用于交叉检查分类是否正确{% if is_unknown %}。修改下方"人工分类"下拉并保存即可纠正触发卫星{% endif %}</div>
</header>
<div class="wrap">
  <div class="summary">
    <div class="box"><div class="num">{{ records|length }}</div><div class="lbl">VT 报告数</div></div>
    <div class="box"><div class="num">{{ detections }}</div><div class="lbl">探测 Detection</div></div>
    <div class="box"><div class="num">{{ upper_limits }}</div><div class="lbl">上限 Upper Limit</div></div>
  </div>
  <table>
    <thead><tr><th>GCN ID</th><th>时间 (UTC)</th><th>事件</th><th>类型</th><th>Subject</th><th>延时 (hr)</th><th>人工分类</th></tr></thead>
    <tbody>
    {% for r in records %}
      <tr>
        <td><a href="https://gcn.nasa.gov/circulars/{{ r.circularId }}" target="_blank">{{ r.circularId }}</a></td>
        <td class="small">{{ r.created_on_iso }}</td>
        <td>{{ r.event_name }}</td>
        <td>{% if r.report_type=='detection' %}<span class="tag det">探测</span>
          {% elif r.report_type=='upper_limit' %}<span class="tag ul">上限</span>
          {% else %}<span class="tag other">{{ r.report_type }}</span>{% endif %}</td>
        <td>{{ r.subject }}</td>
        <td>{{ '%.2f'|format(r.trigger_to_obs_hr) if r.trigger_to_obs_hr is not none else '—' }}</td>
        <td>
          {% if r.manual_override %}<span class="mo-manual">已覆盖: {{ r.trigger_source }}</span>
            &nbsp;<a class="mo-link" href="/trigger/{{ r.trigger_source | urlencode }}" target="_blank">查看</a>
          {% else %}
          <select class="mo-sel" id="sel_{{ r.circularId }}" onchange="document.getElementById('btn_{{ r.circularId }}').disabled=false;">
            <option value="">（无需修改）</option>
            {% for t in valid_triggers %}
            <option value="{{ t }}">{{ t }}</option>
            {% endfor %}
          </select>
          <button class="mo-btn" id="btn_{{ r.circularId }}" disabled onclick="saveOverride({{ r.circularId }})">保存</button>
          <span class="mo-saved" id="ok_{{ r.circularId }}">已保存</span>
          {% endif %}
        </td>
      </tr>
    {% else %}
      <tr><td colspan="7" style="color:var(--muted);padding:30px;text-align:center">该触发卫星暂无 VT 报告</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
<script>
function saveOverride(cid){
  var sel=document.getElementById('sel_'+cid);
  var val=sel.value;
  if(!val) return;
  fetch('/api/manual_override',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({circularId:cid,trigger_source:val})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){
      document.getElementById('btn_'+cid).disabled=true;
      sel.style.display='none';
      document.getElementById('btn_'+cid).style.display='none';
      var ok=document.getElementById('ok_'+cid);
      ok.style.display='inline';
      ok.textContent='已保存为 '+val;
    } else { alert(d.message||'保存失败'); }
  }).catch(e=>alert('网络错误: '+e));
}
</script>
</body></html>"""


DELAY_DETAIL_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{{ title }} - VT GCN 延时交叉检验</title>
<style>
:root { --bg:#0b1016; --card:#161d27; --card2:#1d2733; --fg:#f0f4f8; --muted:#b8c4d2; --muted2:#8896a8; --accent:#5aa9ff; --border:#2a3644; --green:#4ade80; --yellow:#fbbf24; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC",sans-serif; line-height:1.5; }
header { background:linear-gradient(135deg,#161d27,#222e3c); border-bottom:1px solid var(--border); padding:18px 28px; }
header h1 { margin:0; font-size:20px; color:#fff; }
header .sub { color:var(--muted); font-size:13px; margin-top:4px; }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
.wrap { max-width:1300px; margin:0 auto; padding:24px 20px 60px; }
table { width:100%; border-collapse:collapse; font-size:13px; background:var(--card); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
th, td { padding:9px 10px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; color:var(--fg); }
th { background:var(--card2); color:var(--muted); font-weight:600; position:sticky; top:0; }
tr:hover td { background:var(--card2); }
.small { color:var(--muted); font-size:12px; }
.delay { font-weight:700; color:var(--yellow); font-size:14px; }
.snippet { color:var(--green); font-style:italic; font-size:12px; background:rgba(74,222,128,.06); padding:2px 6px; border-radius:4px; display:inline-block; max-width:400px; }
.pill { display:inline-block; background:var(--card2); color:var(--fg); padding:1px 8px; border-radius:6px; margin:1px; font-size:11px; border:1px solid var(--border); }
.summary { display:flex; gap:20px; flex-wrap:wrap; margin:16px 0; }
.summary .box { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px 18px; }
.summary .box .num { font-size:22px; font-weight:700; color:var(--accent); }
.summary .box .lbl { color:var(--muted2); font-size:12px; }
</style></head><body>
<header>
  <h1>{{ title }}</h1>
  <div class="sub"><a href="/">&larr; 返回主页</a> &nbsp;|&nbsp; 按延时升序排列，"延时原文"列展示正文中的匹配片段，可用于检验提取是否正确</div>
</header>
<div class="wrap">
  <div class="summary">
    <div class="box"><div class="num">{{ records|length }}</div><div class="lbl">有延时数据的报告数</div></div>
  </div>
  <table>
    <thead><tr><th>GCN ID</th><th>时间 (UTC)</th><th>事件</th><th>触发卫星</th><th>延时 (hr)</th><th>Subject</th><th>延时提取原文片段</th></tr></thead>
    <tbody>
    {% for r in records %}
      <tr>
        <td><a href="https://gcn.nasa.gov/circulars/{{ r.circularId }}" target="_blank">{{ r.circularId }}</a></td>
        <td class="small">{{ r.created_on_iso }}</td>
        <td>{{ r.event_name }}</td>
        <td><span class="pill">{{ r.trigger_source }}</span></td>
        <td class="delay">{{ '%.3f'|format(r.trigger_to_obs_hr) }}</td>
        <td class="small">{{ r.subject }}</td>
        <td>{% if r.snippet %}<span class="snippet">…{{ r.snippet }}…</span>{% else %}<span class="small">（未匹配）</span>{% endif %}</td>
      </tr>
    {% else %}
      <tr><td colspan="7" style="color:var(--muted);padding:30px;text-align:center">该分组暂无延时数据</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
</body></html>"""


@app.route("/trigger/<path:name>")
def trigger_detail(name: str):
    """显示某个触发卫星的全部 VT GCN 列表，用于交叉检查。"""
    name = name.replace("%2F", "/")  # URL 解码后的斜杠
    all_recs = store.all_records()
    records = [r for r in all_recs if r.get("trigger_source") == name]
    records.sort(key=lambda r: r.get("circularId", 0), reverse=True)
    detections = sum(1 for r in records if r.get("report_type") == "detection")
    upper_limits = sum(1 for r in records if r.get("report_type") == "upper_limit")
    from manual_override import VALID_TRIGGERS
    return render_template_string(
        TRIGGER_DETAIL_TEMPLATE,
        trigger=name, records=records,
        detections=detections, upper_limits=upper_limits,
        is_unknown=(name == "Unknown"),
        valid_triggers=VALID_TRIGGERS,
    )


@app.route("/api/manual_override", methods=["POST"])
def api_manual_override():
    """保存人工分类覆盖。"""
    from manual_override import set_override
    data = request.get_json(force=True)
    cid = data.get("circularId")
    ts = data.get("trigger_source", "")
    if not cid:
        return jsonify({"ok": False, "message": "缺少 circularId"}), 400
    try:
        set_override(cid, ts)
        # 即时应用到内存中的记录
        recs = store.all_records()
        for r in recs:
            if r.get("circularId") == int(cid):
                r["trigger_source"] = ts
                r["manual_override"] = True
                break
        store._save()
        return jsonify({"ok": True, "message": f"已保存: GCN {cid} → {ts}"})
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "message": f"保存失败: {exc}"}), 500


@app.route("/delay/<group>")
def delay_detail(group: str):
    """显示延时分布详情：每个有延时的 GCN 及其延时提取原文片段，用于交叉检验。"""
    group = group.lower()
    if group == "svom":
        title = "SVOM/ECLAIRs 自触发延时详情"
        filter_fn = lambda r: r.get("trigger_source", "").startswith("SVOM")
    elif group == "others":
        title = "外部卫星触发延时详情"
        filter_fn = lambda r: not r.get("trigger_source", "").startswith("SVOM")
    else:
        return "无效分组", 404

    from vt_parser import RE_POST_TRIGGER, RE_POST_TRIGGER_RANGE
    all_recs = store.all_records()
    records = []
    for r in all_recs:
        d = r.get("trigger_to_obs_hr")
        if not isinstance(d, (int, float)) or d < 0 or d > 1000:
            continue
        if not filter_fn(r):
            continue
        body = r.get("body", "") or ""
        # 提取延时匹配的原文片段
        snippet = ""
        m = RE_POST_TRIGGER_RANGE.search(body)
        if m:
            start = max(0, m.start() - 30)
            end = min(len(body), m.end() + 30)
            snippet = body[start:end].replace("\n", " ").strip()
        else:
            m = RE_POST_TRIGGER.search(body)
            if m:
                start = max(0, m.start() - 30)
                end = min(len(body), m.end() + 30)
                snippet = body[start:end].replace("\n", " ").strip()
        records.append({
            "circularId": r.get("circularId"),
            "created_on_iso": r.get("created_on_iso", ""),
            "event_name": r.get("event_name", ""),
            "subject": r.get("subject", ""),
            "trigger_source": r.get("trigger_source", ""),
            "trigger_to_obs_hr": d,
            "snippet": snippet,
        })
    records.sort(key=lambda r: r["trigger_to_obs_hr"])

    return render_template_string(
        DELAY_DETAIL_TEMPLATE,
        title=title, records=records,
    )


@app.route("/health")
def health():
    return jsonify({"ok": True, "records": len(store.all_records()), "meta": store.meta()})


def main() -> None:
    scheduler.start()
    try:
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, use_reloader=False)
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
