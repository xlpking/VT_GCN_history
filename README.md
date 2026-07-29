# SVOM/VT GCN Circulars 历史与自动分析平台

自动从 [NASA GCN Circulars](https://gcn.nasa.gov/circulars) 识别 **SVOM/VT** 相关报告，
完成**自动分类（探测 / 上限 upper limit）**、**结构化解析**（事件、波段、星等、曝光、触发/观测时间、首光延时）、
**统计分析与可视化**，并通过网页展示；同时实现 **每 10 分钟自动增量更新**。

---

## 1. 功能概览

| 能力 | 说明 |
| --- | --- |
| 自动识别 VT 报告 | 通过 subject（标题）+ body（正文）双重判据，命中 `SVOM/VT`、`SVOM VT`、`VT team` 等关键字 |
| 自动分类 | `detection`（探测）/ `upper_limit`（上限）/ `other`（其他），基于 subject 与正文关键词打分 |
| 结构化字段 | 事件名（GRB/EP/IceCube/sb...）、波段（VT_B / VT_R / VT_white / VHF）、星等与是否上限、曝光时间、观测起始 UTC、触发时间、**触发→首光延时（小时）** |
| 统计可视化 | 6 张 Plotly 交互图表：类型饼图、波段柱状图、延时直方图、月度趋势、Top 事件、按事件时间线 |
| 列表与检索 | 关键词搜索、类型筛选、分页，每行链接到 GCN 原文 |
| 自动更新 | 后台线程每 10 分钟增量拉取最新 circulars（基于 circularId 单调递增 + 二分探测最新 ID） |
| API | `/api/records`、`/api/stats`、`/api/meta`、`/api/update`（手动触发）、`/health` |

---

## 2. 数据来源与抓取策略

GCN 官方全文搜索 REST 接口（`/api/circulars`）不稳定（实测返回 400），因此采用以下**不依赖搜索接口**的稳健策略：

1. **首次全量初始化**：下载官方完整归档 `https://gcn.nasa.gov/circulars/archive.json.tar.gz`
   - 实际是一个 `tar.gz`，包内每个文件 `{circularId}.json` 对应一条 circular（约 4.5 万条，压缩后 ~30MB）
   - 用 `tarfile` 流式解析，逐条过滤 VT 相关条目并结构化，写入本地缓存 `data/cache/archive_all.json`
2. **增量更新（每 10 分钟）**：基于已知的最大 `circularId`，
   - 通过指数扩张 + 二分查找快速定位**当前最新 circularId**（`discover_latest_id`）
   - 顺序抓取 `https://gcn.nasa.gov/circulars/{id}.json` 进行增量入库
   - 单次扫描数量受限（`hard_cap`），并对每次请求做礼貌限速与重试

> 数据落地：`data/vt_circulars.json`（含 `records` 与 `meta`，原子写入：先写 `.tmp` 再 `os.replace`）。

---

## 3. 分类与解析规则

### 3.1 VT 相关性（精确口径：只保留 SVOM/VT 团队自己的报告）
判据（满足任一）：
- **subject 明确含 VT**：`SVOM/VT`、`SVOM VT`、或独立的 `VT` 词（如 "SVOM/VT optical upper limits"、"Second VT observation"）
- **body 作者署名段含 VT 团队署名**（仅在 subject 未提 VT 时兜底）：
  - `on behalf of ... SVOM/VT team`（team 在 "on behalf of" 句式 120 字符以内）
  - `SVOM/VT commissioning team`（早期 in-flight commissioning 阶段）
  - **仅检测作者署名段**（第一个 "We observed/performed..." 观测动词之前），避免命中引用列表

**会排除的情况**（经过多轮验证）：
- `svomgroup@bao.ac.cn` 是 SVOM **任务总邮箱**，会发 ECLAIRs/GRM/MXT/LCO 等其他仪器的报告 → body 只有 "SVOM team"/"SVOM/GRM team"，**不含 VT**，被排除
- 其他团队（Fermi GBM Team、GIT team、IKI-GRB-FuN、Liverpool Telescope、ATCA、JWST、VLT/FORS2、Mondy/AbAO 等）仅在正文"引用 SVOM/VT"的报告 → body 署名段是自己的团队（IKI-GRB-FuN 等），被排除
- EP Team（`ep_ta@bao.ac.cn`）虽然同属 BAO，但属于 Einstein Probe 卫星团队 → 单独排除
- 引用列表里的 "SVOM/VT commissioning team, GCN xxxxx" → 通过"仅检测作者署名段"排除

这一口径将初版的 477 条（含 ~200 条误检）修正为 **264 条真实的 SVOM/VT 团队报告**。

### 3.2 报告类型 `report_type`（5 类）
| 类型 | 含义 | 触发条件 |
| --- | --- | --- |
| `detection` | 探测到光学对应体 | subject 含 detection/counterpart/afterglow；或正文探测关键词计数 ≥ 上限关键词 |
| `upper_limit` | 未探测，给出上限 | subject 含 upper limit/non-detection；或正文上限关键词占优 |
| `stellar_flare` | 恒星耀斑（非真实暂现源） | subject 含 stellar flare / flare / star |
| `clarification` | 澄清/否定（如"之前的候选体不是真实源"） | subject/body 含 "is not an astrophysical source" / "not a real source" / "not a GRB" 等 |
| `other` | 其他（综述/计划/改正等） | 上述均不显著 |

### 3.3 触发卫星 `trigger_source`（VT 后随了谁）
从 subject（优先）/body 识别 VT 跟随观测的触发或主探测卫星。SVOM 只有出现具体仪器标记（`sb...` / ECLAIRs / GRM / MXT）时才计为 SVOM 自触发，否则继续匹配其他卫星：

| 触发卫星 | 说明 |
| --- | --- |
| SVOM/ECLAIRs / SVOM/GRM / SVOM/MXT / SVOM (sb trigger) | SVOM 自家触发，VT 自动后随 |
| EP | Einstein Probe（EP-WXT/EP-FXT） |
| Swift | Swift/BAT、XRT、UVOT |
| Fermi | Fermi/GBM、LAT |
| GECAM / AstroSat / Insight-HXMT / MAXI / Konus-Wind / IceCube / LIGO/Virgo | 其他高能/多信使触发 |
| Unknown | subject/body 都未明确标注触发器 |

### 3.4 结构化字段（正则提取）
- **事件名** `event_name`：`GRB YYMMDDx` / `EPyymmmd` / `IceCube-YYMMDDx` / `sb yymmdd…`
- **波段** `bands`：**只从"实际测光/上限数据行"中提取**（同一行同时含 VT_x 与数字+mag），避免被"VT_B (400-650 nm) and VT_R (650-1000 nm)"这种仪器描述模板污染。区分 `VT_B` / `VT_R` / `VT_white` / `VHF` / `VT_clear`
- **星等** `magnitudes`：形如 `VT_B > 23.2 mag`、`> 23.2 mag`、`22.5 +/- 0.3 mag`，并标记 `is_limit`
- **曝光** `exposure_times`：`42*50 s`、`38*50 s` 等
- **观测起始** `obs_start_utc`：`observations started at YYYY-MM-DDTHH:MM UTC`
- **触发时间** `trigger_time_utc`：`trigger(ed) at …` / `T0 = …`
- **首光延时** `trigger_to_obs_hr`：`about 44.08 minutes post trigger` 等归一化为小时

> 提示：自由文本解析存在误差，所有自动结果仅供研究与筛选，关键结论请回看 GCN 原文（列表每行带链接）。

---

## 4. 项目结构

```
VT_GCN_history/
├── app.py              # Flask Web 应用 + 后台 10 分钟调度（入口）
├── config.py           # 全局配置（URL、间隔、关键字等）
├── gcn_fetcher.py      # GCN 抓取：全量归档 + 单条/区间 + 最新 ID 探测
├── vt_parser.py        # VT 过滤 / 分类 / 结构化解析（纯正则，无外部依赖）
├── vt_store.py         # 本地存储 + 增量更新 + 统计聚合（线程安全单例）
├── visualizations.py   # Plotly 图表生成（HTML 片段）
├── requirements.txt    # Flask / requests / plotly / pandas
├── data/
│   ├── vt_circulars.json      # 主数据（records + meta）
│   └── cache/archive_all.json # 全量归档缓存
└── README.md
```

---

## 5. 安装与运行

```bash
cd VT_GCN_history
pip3 install -r requirements.txt
python3 app.py
```

- 首次启动会自动下载 ~30MB 全量归档完成初始化（约 5–10 秒），随后开启 Web 服务。
- 浏览器访问：`http://127.0.0.1:5000/`
- 后台线程每 **10 分钟** 自动增量更新一次（间隔可在 `config.UPDATE_INTERVAL_SECONDS` 调整）。
- 页面右上角「立即更新」按钮可手动触发一次增量更新。

> 依赖：Python 3.9+（已在 macOS / Python 3.9.6 验证）。

---

## 6. HTTP 接口

| 方法 & 路径 | 说明 |
| --- | --- |
| `GET /` | 主界面（支持 `q=`、`ftype=`、`ps=`、`page=` 查询参数） |
| `GET /api/records?q=&ftype=` | 结构化记录（默认前 200 条） |
| `GET /api/stats` | 聚合统计（类型/波段/事件/月度/延时分布等） |
| `GET /api/meta` | 更新元信息（最新 ID、扫描总数、更新历史） |
| `POST /api/update` | 手动触发一次增量更新 |
| `GET /health` | 健康检查 |

---

## 7. 示例数据（最新重建后）

```
total             : 264   （初版 477 含 ~200 条误检，已修正）
detection         : 190
upper_limit       : 62
stellar_flare     : 5     （恒星耀斑，非真实暂现源）
clarification     : 2     （澄清/否定）
other             : 5
events_count      : 210
median_delay_hr   : 3.3   （n≈240，仅统计正文显式写出 post trigger 的报告）

触发卫星 trigger_source：
  SVOM 自触发合计  : 110   （ECLAIRs 89 + sb 13 + GRM 6 + MXT 2）
  EP              : 87
  Swift           : 26
  Fermi           : 18
  LIGO/Virgo      : 2
  Unknown         : 21

波段 by_band（基于实际测光行，非仪器模板）：
  VT_R : 121   VT_B : 116   VHF : 3   VT_white : 1   unknown : 4
max_circular_id   : 45237+
```

---

## 8. 注意事项

- 自动分类基于关键词与正则，对边界情况可能误判；**上限/探测**的判定优先看 subject，再参考正文计数。
- `trigger_to_obs_hr` 仅当正文显式写出 "post trigger / after trigger …" 时才能提取；缺失很常见。
- GCN 全量归档由官方每日生成一次，**最新一天内**的 circular 主要通过增量接口（`/circulars/{id}.json`）补齐。
- 本工具仅用于研究展示，数据版权归原作者（SVOM/VT 团队及各 submitter）。
