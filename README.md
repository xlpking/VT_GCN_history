# SVOM/VT GCN Circulars 历史与自动分析平台

自动从 [NASA GCN Circulars](https://gcn.nasa.gov/circulars) 识别 **SVOM/VT** 相关报告，
完成**自动分类（探测 / 上限 upper limit / 恒星耀发 / 澄清）**、**结构化解析**（事件、波段、星等、曝光、触发/观测时间、首光延时）、
**统计分析与可视化**，并通过网页展示；同时实现 **每 10 分钟自动增量更新**。

---

## 1. 功能概览

| 能力 | 说明 |
| --- | --- |
| 自动识别 VT 报告 | 通过 subject（标题）+ body（正文）双重判据，命中 `SVOM/VT`、`SVOM VT`、`VT team` 等关键字 |
| 自动分类 | `detection`（探测）/ `upper_limit`（上限）/ `stellar_flare`（恒星耀斑）/ `clarification`（澄清）/ `other`，基于 subject 与正文关键词打分 |
| 多格式表格解析 | 支持 8 种 GCN 常见表格格式：Markdown 管道表格、空格分隔、管道分隔、band-前置/后置、数值+曝光+band+星等、纯文本描述 |
| 结构化字段 | 事件名、波段（VT_B / VT_R / VT_white / VHF）、星等与 `is_limit` 标记、曝光时间、观测起始 UTC、触发时间、**触发→首光延时（小时）**、`is_auto_followup`（自动后随标记）|
| 统计可视化 | Plotly 交互图表 + matplotlib 静态光变图：类型饼图、波段柱状图、延时直方图、月度趋势、Top 事件、触发卫星分布、VT 光变图（VT_R / VT_i+VT_z）|
| 上限事件交叉检验表 | 网页上分三类横向展示仅含上限的事件：SVOM 自动后随（≤1h）/ SVOM ToO / 外部卫星触发；每行支持在线修改类型和备注 |
| 人工覆盖 | `data/manual_overrides.json` 持久化人工修正（report_type / magnitudes / trigger_source / delay / is_auto_followup / ul_comment），网页支持在线编辑 |
| 列表与检索 | 关键词搜索、类型筛选、分页，每行链接到 GCN 原文 |
| 自动更新 | 后台线程每 10 分钟增量拉取最新 circulars（基于 circularId 单调递增 + 二分探测最新 ID） |
| API | `/api/records`、`/api/stats`、`/api/meta`、`/api/update`（手动触发）、`/health`、`/api/ul_override`（上限在线修改） |

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

### 3.4 多格式表格解析（`vt_parser.py`）

GCN Circulars 中 SVOM/VT 报告使用了多种不同的表格格式，解析器支持以下 8 种：

| 解析器 | 格式特征 | 示例 |
| --- | --- | --- |
| `_parse_markdown_table` | Markdown 管道表格 | `\| VT_B mag \| 16.16 ± 0.01 \|` |
| `_parse_space_table` | 空格分隔，mid-time 在首列 | `4.36 hour VT_R 68*70 sec 22.98+/-0.25` |
| `_parse_space_table` | 管道分隔，band 在末列 | `48.133 \| 28x60 \| 20.388 \| 0.08 \| VT_R` |
| `_parse_space_table` | 数值+曝光+band+星等 | `2.2 2.85 VT_R 23.3` |
| `_parse_space_table` | band 前置 | `VT_B 13.25 149x100s 23.5 +/-0.2` |
| `_parse_space_table` | 纯文本描述 | `VT_R~20.61 mag ... mid time of 443 seconds` |
| 正则提取 | `VT_B > 23.2 mag` | 标准不等式格式 |
| 正则提取 | `22.5 +/- 0.3 mag` | 标准误差格式 |

**`is_limit` 自动判定**：当 body 包含 "3 sigma limit"、"upper limit"、"no credible candidate"、"non-detection" 等关键词时，提取的星等自动标记为 `is_limit=True`。

**时间单位转换**：支持 seconds / minutes / hours / days → 统一归一化为小时（`t_mid_hr`）。

### 3.5 结构化字段
- **事件名** `event_name`：`GRB YYMMDDx` / `EPyymmmd` / `IceCube-YYMMDDx` / `sb yymmmd…`
- **波段** `bands`：只从"实际测光/上限数据行"中提取（同一行同时含 VT_x 与数字+mag），避免被仪器描述模板污染。区分 `VT_B` / `VT_R` / `VT_white` / `VHF` / `VT_clear`
- **星等** `magnitudes`：每条含 `band`、`value`、`unit`、`is_limit`、`t_mid_hr`
- **曝光** `exposure_times`：`42*50 s`、`38*50 s` 等
- **观测起始** `obs_start_utc`：`observations started at YYYY-MM-DDTHH:MM UTC`
- **触发时间** `trigger_time_utc`：`trigger(ed) at …` / `T0 = …`
- **首光延时** `trigger_to_obs_hr`：`about 44.08 minutes post trigger` 等归一化为小时
- **自动后随** `is_auto_followup`：基于 delay ≤ 1h（SVOM）/ ≤ 2h（EP/Swift）或正文含 "automatic slew"

> 提示：自由文本解析存在误差，所有自动结果仅供研究与筛选，关键结论请回看 GCN 原文（列表每行带链接）。

---

## 4. 人工覆盖系统（Manual Override）

### 4.1 设计目的
GCN 发布后，后续分析可能修正原始结论（如探测实为恒星耀发、上限实为探测等）。人工覆盖系统确保这些修正持久化，不受自动重新解析影响。

### 4.2 文件格式
持久化文件：`data/manual_overrides.json`
```json
{
  "38852": {
    "report_type": "detection",
    "magnitudes": [{"band": "VT_R", "value": 19.0, "is_limit": false, "t_mid_hr": 1.516}],
    "note": "actual optical candidate detection, not upper limit",
    "updated_at": "2026-07-31T08:00:00+00:00"
  },
  "42712": {
    "is_auto_followup": true,
    "trigger_to_obs_hr": 1.1,
    "note": "automatic slew confirmed from body text"
  }
}
```

### 4.3 支持的覆盖字段
| 字段 | 说明 |
| --- | --- |
| `report_type` | 覆盖自动分类（detection / upper_limit / stellar_flare / clarification / other） |
| `magnitudes` | 覆盖星等数据（含 is_limit 标记） |
| `trigger_source` | 覆盖触发卫星 |
| `trigger_to_obs_hr` | 覆盖首光延时 |
| `is_auto_followup` | 覆盖自动后随标记 |
| `event_name` | 覆盖事件名 |
| `bands` | 覆盖波段列表 |
| `ul_comment` | 上限表格中的备注（网页在线编辑） |

### 4.4 网页在线编辑
上限事件表格每行支持：
- **类型下拉框**：将事件在 detection / upper_limit / stellar_flare 等类型间切换
- **备注输入框**：添加物理含义注释（如"高红移 z=7.3"、"重消光"、"地球杂散光"）

修改通过 `POST /api/ul_override` 提交，自动保存到 `manual_overrides.json`。

---

## 5. 上限事件交叉检验表

网页上将**VT 仅提供定位误差（全部波段无探测）**的事件分三类横向展示：

| 类别 | 判定条件 | 颜色 |
| --- | --- | --- |
| SVOM/ECLAIRs 自动后随（≤1h） | `trigger_source` 以 SVOM 开头 + `is_auto_followup=True` | 绿色 |
| SVOM/ECLAIRs 触发（ToO） | `trigger_source` 以 SVOM 开头 + 非自动后随 | 蓝色 |
| 外部卫星触发（EP/Swift/Fermi 等） | 非 SVOM 触发 | 紫色 |

每个事件一行（多波段上限合并显示），方便交叉检验哪些 GRB VT 未探测到光学对应体。

---

## 6. 项目结构

```
VT_GCN_history/
├── app.py                    # Flask Web 应用 + 后台 10 分钟调度（入口）
├── config.py                 # 全局配置（URL、间隔、关键字等）
├── gcn_fetcher.py            # GCN 抓取：全量归档 + 单条/区间 + 最新 ID 探测
├── vt_parser.py              # VT 过滤 / 分类 / 结构化解析（8 种表格格式）
├── vt_store.py               # 本地存储 + 增量更新 + 统计聚合（线程安全单例）
├── manual_override.py        # 人工覆盖：加载/保存/应用到 records
├── visualizations.py         # Plotly 图表生成（HTML 片段）
├── lc_density_plot.py        # VT 光变图（matplotlib 静态图）
├── llm_review.py             # LLM 辅助审核脚本（批量检查星等数据）
├── audit_stats.py            # 统计数据交叉检验脚本
├── requirements.txt          # Flask / requests / plotly / pandas
├── data/
│   ├── vt_circulars.json          # 主数据（records + meta）
│   ├── manual_overrides.json      # 人工覆盖（report_type / magnitudes / delay 等）
│   └── cache/archive_all.json     # 全量归档缓存
├── doc_figures/              # 静态图表输出（PNG）
└── README.md
```

---

## 7. 安装与运行

```bash
cd VT_GCN_history
pip3 install -r requirements.txt
python3 app.py
```

- 首次启动会自动下载 ~30MB 全量归档完成初始化（约 5–10 秒），随后开启 Web 服务。
- 浏览器访问：`http://127.0.0.1:5050/`
- 后台线程每 **10 分钟** 自动增量更新一次（间隔可在 `config.UPDATE_INTERVAL_SECONDS` 调整）。
- 页面右上角「立即更新」按钮可手动触发一次增量更新。

> 依赖：Python 3.9+（已在 macOS / Python 3.9.6 验证）。

---

## 8. HTTP 接口

| 方法 & 路径 | 说明 |
| --- | --- |
| `GET /` | 主界面（支持 `q=`、`ftype=`、`ps=`、`page=` 查询参数） |
| `GET /api/records?q=&ftype=` | 结构化记录（默认前 200 条） |
| `GET /api/stats` | 聚合统计（类型/波段/事件/月度/延时分布/自动后随率等） |
| `GET /api/meta` | 更新元信息（最新 ID、扫描总数、更新历史） |
| `POST /api/update` | 手动触发一次增量更新 |
| `POST /api/ul_override` | 在线修改上限事件的 report_type 和 comment |
| `GET /health` | 健康检查 |

---

## 9. 统计数据（2026-07-31 审核后）

经全面交叉检验（`audit_stats.py`）后的准确统计：

```
total             : 260
detection         : 175   (探测率 71.1%)
upper_limit       : 71
stellar_flare     : 8     （恒星耀发，已排除出统计）
clarification     : 1     （澄清/否定）
other             : 5
events_count      : 209
median_delay_hr   : 1.85
auto_followup_rate: 69.2% （含 is_auto_followup override）

触发卫星 trigger_source：
  SVOM/ECLAIRs    : 125
  EP              : 76
  Swift           : 29
  Fermi           : 24
  SVOM/MXT        : 2
  Unknown         : 2
  LIGO/Virgo      : 1
  INTEGRAL        : 1

波段 by_band（基于实际测光行）：
  VT_R : 213   VT_B : 194

人工覆盖         : 65 条（report_type / magnitudes / delay / is_auto_followup 等）
max_circular_id   : 45260
```

### 上限事件分类

| 类别 | 事件数 |
| --- | --- |
| SVOM 自动后随（≤1h） | 14 |
| SVOM ToO（>1h） | 11 |
| 外部卫星触发 | 30 |
| **合计** | **55** |

---

## 10. 审核工具

| 脚本 | 用途 |
| --- | --- |
| `audit_stats.py` | 全面交叉检验：探测/上限计数一致性、is_limit 正确性、触发源匹配、事件名一致性、缺失 delay 等 |
| `llm_review.py` | LLM 辅助逐条阅读 GCN 正文，提取遗漏的星等数据 |
| `find_upper_only.py` | 找出所有 VT 仅提供上限（无探测）的事件 |
| `check_svom_too.py` | 检查 SVOM ToO 事件的 delay 和自动后随状态 |

---

## 11. 注意事项

- 自动分类基于关键词与正则，对边界情况可能误判；**上限/探测**的判定优先看 subject，再参考正文计数。
- `is_limit` 自动判定：当正文含 "upper limit"/"3 sigma limit"/"non-detection" 等关键词时，所有星等标记为上限；人工覆盖可逐条修正。
- `trigger_to_obs_hr` 仅当正文显式写出 "post trigger / after trigger …" 时才能提取；约 50 条记录缺失此数据。
- `is_auto_followup`：优先看正文是否含 "automatic slew"，而非仅依赖 delay 阈值（有些自动后随因观测约束 delay >1h）。
- GCN 全量归档由官方每日生成一次，**最新一天内**的 circular 主要通过增量接口（`/circulars/{id}.json`）补齐。
- 本工具仅用于研究展示，数据版权归原作者（SVOM/VT 团队及各 submitter）。
