"""
SVOM/VT Circulars 过滤、分类与结构化解析（v2 收紧版）

关键修正：
1. VT 相关性判定收紧为「作者署名」口径：
   - subject 显式含 SVOM/VT（"SVOM/VT ..."）
   - 或正文含 "on behalf of the SVOM/VT team" / "SVOM/VT team report" / "VT team report"
   仅在正文"引用" SVOM/ECLAIRs 触发的其他团队报告不再算作 VT 报告。
2. 波段统计基于「实际测光/上限出现的波段」，避免被"VT_B (400-650 nm) and VT_R (650-1000 nm)"模板污染。
3. report_type 细分：detection / upper_limit / stellar_flare / clarification / other。
4. 新增 trigger_source：从 subject/body 识别触发或主探测卫星（SVOM/EP/Swift/Fermi/GECAM/IceCube/...）。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

import config


# ---------- 正则 ----------
RE_EVENT = re.compile(
    r"\b(GRB\s?\d{6}[A-Z]|EP\d{6}[a-z]|IceCube-\d{6}[A-Z]|svom\s?sb\d+|\bsb\d{6,}\d?)\b",
    re.IGNORECASE,
)
RE_POST_TRIGGER = re.compile(
    r"(about\s+)?([\d.]+)\s*(min|minutes|hr|hour|hours|s|sec|seconds|days|day)\s*"
    r"(?:post[- ]trigger|post[- ]burst|"
    r"after\s+(?:the\s+)?(?:SVOM\s+)?trigger(?:\s+time)?|"   # after (the) (SVOM) trigger
    r"after\s+(?:the\s+)?(?:trigger|burst|GBM|detection|alert)|"
    r"after\s+(?:the\s+)?T0|after\s+(?:the\s+)?Tb)",
    re.IGNORECASE,
)
# "from 2.467 hours to 7.573 hours after the burst" → 取第一个值（观测开始）
RE_POST_TRIGGER_RANGE = re.compile(
    r"from\s+([\d.]+)\s*(min|minutes|hr|hour|hours|s|sec|seconds|days|day)\s+to\s+[\d.]+\s*"
    r"(?:min|minutes|hr|hour|hours|s|sec|seconds|days|day)\s*"
    r"(?:post|after)",
    re.IGNORECASE,
)
RE_OBS_START = re.compile(
    r"(?:began\s+observ\w+|start(?:ed|ing)?\s+observ\w+|observ\w+\s+(?:started|began|start(?:ed)?)|"
    r"(?:vhf\s+)?data\s+start(?:ed)?\s+at|start(?:ed|ing)?\s+at|since|from)"
    r"[\w\s,()\d.#/+;-]{0,40}?\s*"
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s*UT",
    re.IGNORECASE,
)
RE_TRIGGER_TIME = re.compile(
    r"(trigger\s+(?:time\s+)?(?:at\s+)?|triggered\s+(?:at\s+)?|trigger\s+by\s+[\w/\s]+?\s+at\s+|burst\s+(?:time\s+)?(?:at\s+)?|T0\s*[:=]\s*)"
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s*UT",
    re.IGNORECASE,
)

# 上限 / 探测 关键词
UPPER_LIMIT_TOKENS = (
    "upper limit", "upper-limit", "non-detection", "no credible",
    "no optical counterpart", "not detected", "no source",
)
DETECTION_TOKENS = (
    "detection", "detected", "counterpart candidate", "afterglow",
    "counterpart", "discovery", "identified",
)
STELLAR_FLARE_TOKENS = ("stellar flare", "flare", "star")
CLARIFICATION_TOKENS = (
    "is not an astrophysical source", "not a real source", "not a grb",
    "is not a grb", "is not real", "not real",
)

# 触发/主探测卫星识别（顺序重要：先匹配更具体的）
# 注意：因为所有 VT 报告都含 "SVOM"，必须用具体的仪器标记（sb/ECLAIRs/GRM/MXT）才能判定为 SVOM 自触发；
# 否则继续找其他卫星（EP/Swift/Fermi 等）—— VT 是后随观测者。
# SVOM 所有警报都通过 sb trigger 发布，sb trigger 即代表 SVOM/ECLAIRs 触发。
TRIGGER_PATTERNS = [
    # SVOM 自触发：ECLAIRs 或 sb trigger（SVOM 警报统一用 sb 开头）
    ("SVOM/ECLAIRs", re.compile(r"\bECLAIRs\b|SVOM/ECLAIRs|SVOM\s+trigger\s+sb|\bsb\d{6,}\d?\b", re.IGNORECASE)),
    ("SVOM/GRM", re.compile(r"\bSVOM/GRM\b|\bGRM\b.*SVOM|SVOM.*\bGRM\b", re.IGNORECASE)),
    ("SVOM/MXT", re.compile(r"\bSVOM/MXT\b|\bMXT\b", re.IGNORECASE)),
    # 其他卫星（VT 后随）
    ("EP", re.compile(r"\bEP[- ]?WXT\b|\bEP[- ]?FXT\b|Einstein\s+Probe|\bEP\d{6}", re.IGNORECASE)),
    ("Swift", re.compile(r"\bSwift\b|\bBAT\b|\bXRT\b|\bUVOT\b", re.IGNORECASE)),
    ("Fermi", re.compile(r"\bFermi\b|\bGBM\b|\bLAT\b", re.IGNORECASE)),
    ("INTEGRAL", re.compile(r"\bINTEGRAL\b|\bIBAS\b|\bSPI-ACS\b|ISGRI", re.IGNORECASE)),
    ("GECAM", re.compile(r"\bGECAM\b", re.IGNORECASE)),
    ("IceCube", re.compile(r"\bIceCube\b", re.IGNORECASE)),
    ("AstroSat", re.compile(r"\bAstroSat\b|\bCZTI\b", re.IGNORECASE)),
    ("Insight-HXMT", re.compile(r"Insight-HXMT|\bHXMT\b", re.IGNORECASE)),
    ("MAXI", re.compile(r"\bMAXI\b|\bGSC\b", re.IGNORECASE)),
    ("Konus-Wind", re.compile(r"\bKonus\b", re.IGNORECASE)),
    ("LIGO/Virgo", re.compile(r"\bLIGO\b|\bVirgo\b|\bKAGRA\b|S\d{6}[a-z]{1,3}", re.IGNORECASE)),
]


def _norm_band(token: str) -> str:
    """归一化波段名（对外显示）。"""
    t = token.lower().replace("_", "").replace("-", "").replace(" ", "")
    if t in ("vtb",):
        return "VT_B"
    if t in ("vtr",):
        return "VT_R"
    if t in ("vtw", "vtwhite"):
        return "VT_white"
    if "vhf" in t:
        return "VHF"
    if "clear" in t:
        return "VT_clear"
    return token.strip()


# 已知 SVOM/VT 团队 submitter 邮箱/机构标识（用于 body 兜底验证）
# 通过对历史 SVOM/VT 报告 submitter 字段的归纳得到
SVOM_TEAM_EMAIL_DOMAINS = (
    "@nao.cas.cn", "@nao.ac.cn", "@bao.ac.cn", "@pmo.ac.cn",
    "@xao.ac.cn", "@niaot.ac.cn", "@ustc.edu.cn",
)
SVOM_TEAM_EMAIL_LOCAL = (
    "svomgroup", "xlp@", "lhl@", "yuxin@", "caihb@", "weijy@",
)
# submitter 字段里出现的 SVOM 机构标识
SVOM_TEAM_SUBMITTER_TOKENS = (
    "SVOM", "NAOC", "NAOC, SVOM", "at NAOC", "at BAO",
)


def _submitter_is_svom(submitter: str) -> bool:
    """判断 submitter 字段是否属于 SVOM/VT 团队。

    判据（满足任一）：
    - submitter 文本明确含 "SVOM"
    - 邮箱属于 SVOM 团队已知邮箱（svomgroup / xlp@ / lhl@ 等）
    - 邮箱域名 @nao.cas.cn / @bao.ac.cn 且 submitter 含 NAOC 与 SVOM/VT 标识
    但排除 EP Team（ep_ta@bao.ac.cn）—— 同属 BAO 但是 EP 卫星团队。
    """
    s = (submitter or "")
    sl = s.lower()
    # 排除：EP Team（明确是 Einstein Probe 团队，不是 VT）
    if "ep team" in sl or "ep_ta@" in sl or "einstein probe" in sl:
        return False
    # 1) submitter 文本含 "SVOM"（最可靠）
    if "svom" in sl:
        return True
    # 2) 已知 SVOM 团队个人邮箱
    for loc in SVOM_TEAM_EMAIL_LOCAL:
        if loc in sl:
            return True
    # 3) 域名 + NAOC 标识（兜底）
    for dom in SVOM_TEAM_EMAIL_DOMAINS:
        if dom in sl and ("naoc" in sl or "vt" in sl):
            return True
    return False


# ---------- VT 相关性判定（收紧版） ----------
def _subject_is_vt(subject: str) -> bool:
    """subject 是否明确提到 VT（SVOM/VT 或独立 VT 词）。

    覆盖：
    - "GRB xxxx: SVOM/VT optical upper limits"
    - "SVOM J195836+32283: Second VT observation"（SVOM 多仪器联合，但主题是 VT）
    """
    return _subject_mentions_vt(subject)


# VT 团队署名识别（精确版）
# pat1: "report on behalf of ... SVOM/VT team" 或 "VT team"
#   注意：不要匹配 "SVOM team"（过宽）—— SVOM/GRM、SVOM/ECLAIRs 等团队都写 "SVOM team"，
#   会把 GRM/ECLAIRs 的报告误纳入。只认明确带 "VT" 的署名。
RE_VT_ONBEHALF = re.compile(
    r"on behalf of[^.\n]{0,120}?(svom/vt\s+team|\bvt\s+team)",
    re.IGNORECASE,
)
# pat2: "SVOM/VT commissioning team" 作为作者署名（早期 commissioning 阶段）
#   排除引用形式 "SVOM/VT commissioning team, GCN xxxxx"（后面紧跟 GCN 编号）
RE_VT_COMM = re.compile(
    r"svom/vt\s+commissioning\s+team(?!\s*[,，]\s*(?:GCN|gcn)\s*\d)",
    re.IGNORECASE,
)


def _body_is_vt_team(body: str, submitter: str) -> bool:
    """正文是否为 SVOM/VT 团队作者署名（精确版）。

    判据：正文前 600 字符（作者署名段）满足以下之一：
      1) 出现 `on behalf of ... SVOM/VT team`（或 VT team）—— team 在
         "on behalf of" 句式 120 字符以内
      2) 出现 `SVOM/VT commissioning team`（且不是引用形式 "team, GCN xxxxx"）

    重要：
    - `svomgroup@bao.ac.cn` 是 SVOM 任务总邮箱，会发 ECLAIRs/GRM/MXT/LCO 等
      其他仪器的报告——这些 body 里只有 "SVOM team" / "SVOM/GRM team" 等，**不含** VT，
      因此不会命中上述模式。
    - 不能用 "SVOM team" 作为判据（会误纳 GRM/ECLAIRs 团队报告）。
    - 其他团队（IKI/JWST 等）在引用列表里写 "SVOM/VT commissioning team, GCN xxxxx"
      会被 pat2 的负向断言排除。
    """
    # 仅取"作者署名段"：第一个空行或"We observed/report"等观测描述之前的部分
    # 引用列表（含 "SVOM/VT commissioning team, GCN xxxxx"）都在观测描述之后
    body_text = (body or "")
    # 截到第一个观测动词前（这些动词开启引用/观测描述段）
    cut_match = re.search(r"\n\s*(?:We\s+(?:observed|obtained|report|detected|started|performed|conducted|re-?observed)|Observations?\s+(?:started|began|were)|Based\s+on|In\s+summary|Further\s+analysis)", body_text, re.IGNORECASE)
    head = body_text[:cut_match.start()] if cut_match else body_text[:350]
    if RE_VT_ONBEHALF.search(head):
        return True
    if RE_VT_COMM.search(head):
        return True
    return False


def _subject_mentions_vt(subject: str) -> bool:
    """subject 是否明确提到 VT 望远镜观测（如 'VT observation', 'SVOM/VT optical'）。

    用于兜底少数 SVOM 多仪器联合署名（on behalf of SVOM team）但实质是 VT 报告的情况。
    要求 "VT" 作为独立词出现，且不是 "EVT"/"SVOM/ECLAIRs" 这种误匹配。
    """
    s = subject or ""
    # SVOM/VT 或 SVOM VT
    if "SVOM/VT" in s or "SVOM VT" in s:
        return True
    # 独立的 VT 词（前后是非字母）
    if re.search(r"(?<![A-Za-z])VT(?![A-Za-z])", s):
        return True
    return False


# ---------- 报告类型分类 ----------
def classify_report(subject: str, body: str) -> str:
    text = f"{subject}\n{body}".lower()
    subj_lower = (subject or "").lower()

    # 1) 澄清/否定（最高优先级）
    for token in CLARIFICATION_TOKENS:
        if token in subj_lower or token in text:
            return "clarification"

    # 2) 恒星耀斑
    for token in STELLAR_FLARE_TOKENS:
        if token in subj_lower:
            return "stellar_flare"

    # 3) 上限
    if "upper limit" in subj_lower or "upper-limit" in subj_lower or "non-detection" in subj_lower:
        return "upper_limit"
    ul_hits = sum(1 for k in UPPER_LIMIT_TOKENS if k in text)
    det_hits = sum(1 for k in DETECTION_TOKENS if k in text)

    # 4) 探测
    if "detection" in subj_lower or "counterpart" in subj_lower or "afterglow" in subj_lower:
        return "detection"
    if det_hits > 0 and det_hits >= ul_hits:
        return "detection"
    if ul_hits > 0:
        return "upper_limit"
    return "other"


# ---------- 触发/主探测卫星识别 ----------
def identify_trigger_source(subject: str, body: str) -> str:
    """
    识别触发/主探测卫星。
    策略：优先匹配 "detected by X" / "triggered by X" 等真触发表述，
    避免 "within the error box of Swift/XRT"（引用定位）造成的误分类。
    """
    # 0) SVOM 自触发强信号："automatic slew" = VT 自动响应 ECLAIRs 触发
    #    优先级最高：联合触发时（SVOM/ECLAIRs + EP 同时探测），只要 VT 做了 automatic slew，
    #    说明 SVOM 自己探测到了，应归类为 SVOM/ECLAIRs
    head = (body or "")[:1200]
    if re.search(r"automatic\s+slew(?!\s+for)", head, re.IGNORECASE):
        return "SVOM/ECLAIRs"

    # 0b) body 明确写 "triggered by SVOM/ECLAIRs" + sb 触发号 = SVOM 自触发
    #     （后续观测报告无 automatic slew，但引用了原始 SVOM 触发）
    if re.search(r"sb\d{6,}", head) and re.search(r"SVOM\s*/?\s*ECLAIRs", head, re.IGNORECASE):
        # 确认是 "triggered by SVOM/ECLAIRs" 而非 "also detected by SVOM/ECLAIRs"
        if re.search(r"(?:triggered|detected)\s+by\s+SVOM\s*/?\s*ECLAIRs", head, re.IGNORECASE):
            return "SVOM/ECLAIRs"

    # 1) subject 里明确写了触发卫星名（如 "EP250610a:" / "GRB XXXXX detected by Fermi"）
    for name, pat in TRIGGER_PATTERNS:
        if pat.search(subject or ""):
            return name

    # 2) body 里找 "detected by" / "triggered by" / "in response to" 后跟的卫星
    #    （只匹配 GRB 事件名附近的，排除 "source #2 detected by Swift/XRT" 这种引用）
    #    也匹配 "INTEGRAL-detected GRB" / "Swift-triggered GRB" 这种前置修饰
    trigger_phrase = re.compile(
        r"(?:detected\s+by|triggered\s+by|in\s+response\s+to|alert\s+from)\s+"
        r"(SVOM(?:/ECLAIRs)?|SVOM/GRM|Einstein\s+Probe|\bEP\b|Swift|\bBAT\b|Fermi|\bGBM\b|\bLAT\b|"
        r"INTEGRAL|\bIBAS\b|\bSPI-ACS\b|GECAM|IceCube|AstroSat|Insight-HXMT|\bHXMT\b|MAXI|Konus|LIGO|Virgo)"
        r"|"  # 或前置修饰
        r"((?:SVOM(?:/ECLAIRs)?|Swift|\bBAT\b|Fermi|\bGBM\b|\bLAT\b|INTEGRAL|\bIBAS\b|EP|GECAM)"
        r"[- ](?:detected|triggered))",
        re.IGNORECASE,
    )
    m = trigger_phrase.search(head)
    if m:
        # 取匹配到的卫星名（后置或前置）
        sat_raw = m.group(1) or m.group(2)
        if sat_raw:
            sat = sat_raw.lower()
            # 排除 "source detected by" / "candidate detected by" 这种引用（仅后置模式需要检查）
            if m.group(1):
                ctx = head[max(0, m.start()-30):m.start()]
                if re.search(r"source|candidate|afterglow|counterpart|host", ctx, re.IGNORECASE):
                    sat = None
            if sat:
                if "eclair" in sat or sat == "svom":
                    return "SVOM/ECLAIRs"
                if "grm" in sat:
                    return "SVOM/GRM"
                if sat in ("ep",) or "einstein" in sat:
                    return "EP"
                if "swift" in sat or sat == "bat":
                    return "Swift"
                if "fermi" in sat or sat in ("gbm", "lat"):
                    return "Fermi"
                if "integral" in sat or "ibas" in sat or "spi-acs" in sat:
                    return "INTEGRAL"
                if "gecam" in sat:
                    return "GECAM"
                if "icecube" in sat:
                    return "IceCube"
                if "ligo" in sat or "virgo" in sat:
                    return "LIGO/Virgo"

    # 4) 回退：body 前段找 SVOM 自触发标识（ECLAIRs / sb trigger）
    for name, pat in TRIGGER_PATTERNS[:3]:  # 只查 SVOM 系列模式
        if pat.search(head):
            return name

    # 5) 最后回退：body 前 400 字符找其他卫星名（但排除纯引用）
    # 检查 "within the error box of Swift/XRT" / "consistent with" 这种引用
    head_short = head[:400]
    has_ref_only = bool(re.search(r"error.?\s*box\s+of|consistent\s+with|Swift.?\s*XRT.?\s*position|Swift.?\s*XRT.?\s*localiz", head_short, re.IGNORECASE))
    if not has_ref_only:
        for name, pat in TRIGGER_PATTERNS[3:]:  # 其他卫星模式
            if pat.search(head_short):
                return name

    return "Unknown"


# ---------- 波段 & 星等提取（基于实际测光行） ----------
def extract_bands_and_mags(subject: str, body: str) -> tuple[List[str], List[dict]]:
    """
    只从「看起来是测光数据」的行中提取波段，避免被 "VT_B (400-650 nm) and VT_R (650-1000 nm)" 模板污染。
    测光行特征：同一行内同时含 VT_x 与数字 + mag/> /limit 关键字。
    同时提取行首的 mid-time（有效观测中点时间，post trigger）。
    """
    text = f"{subject}\n{body}"
    lines = text.splitlines()
    bands: List[str] = []
    mags: List[dict] = []

    # mid-time 行首正则：如 "1.07 hour", "2.27 h", "1.05 hr"
    mid_time_re = re.compile(
        r"^\s*(?:mid[_\s-]?time\s*)?([\d.]+)\s*(hour|hr|h)\s+(?:VT|mid|band)",
        re.IGNORECASE,
    )
    # 表格行首数字+单位（管道分隔），如 "20.7 min | ... | VT_B | ..." 或 "1.934 | ..."
    table_time_re = re.compile(r"^\s*([\d.]+)\s*(min|sec|s|hour|hr|h)?\s*\|", re.IGNORECASE)
    # 表头含时间列单位提示
    header_hour_re = re.compile(r"mid[_\s-]?time.*\(h|mid[_\s-]?time.*hour", re.IGNORECASE)
    header_sec_re = re.compile(r"mid[_\s-]?time.*\(s|mid[_\s-]?time.*sec", re.IGNORECASE)
    header_min_re = re.compile(r"mid[_\s-]?time.*\(min|mid[_\s-]?time.*minute", re.IGNORECASE)

    # 行级正则：这一行像是测光/上限数据
    # 支持 "VT_B = 20.5 mag", "VT_B: 20.5 mag", "VT_B | 20.5 | 0.1" 等格式
    photometric_line = re.compile(
        r"(vt[_\s-]?(?:b|r|white|clear))"
        r"\s*(?:[=:|]\s*)+"
        r"(>?~?\s*([\d.]+)"
        r"(?:\s*(?:\+/?-|±)\s*[\d.]+)?"
        r"\s*mag)?"
        , re.IGNORECASE,
    )
    limit_line = re.compile(r"(?:>\s*|limit(?:ed)?\s+to\s+|upper\s+limit(?:s)?\s*(?:of|[:=])?\s*(?:are\s+)?(?:about\s+|~\s*)?)([\d.]+)\s*mag", re.IGNORECASE)
    vhf_line = re.compile(r"VHF.*?([\d.]+)\s*mag", re.IGNORECASE)
    measure_line = re.compile(r"(?<![<>=\d.])([\d]{1,2}(?:\.[\d]{1,3})?)\s*(?:\+/?-|±)\s*[\d.]+\s*mag\b", re.IGNORECASE)

    # 跟踪表格时间列单位（"hour"/"sec"/None）和是否上限表
    table_time_unit = None
    table_is_limit = False

    for line in lines:
        ln = line.strip()
        if not ln:
            # 空行重置表格上下文
            table_time_unit = None
            table_is_limit = False
            continue
        # 跳过色指数行（VT_B-VT_R ~ 0.30 mag）—— 不是星等
        if re.search(r"vt[_\s-]?[br]\s*[-–—]\s*vt[_\s-]?[br]", ln, re.IGNORECASE):
            continue
        # 检测表头，确定时间列单位和是否上限表
        if "mid" in ln.lower() and "time" in ln.lower() and "|" in ln:
            if header_hour_re.search(ln):
                table_time_unit = "hour"
            elif header_sec_re.search(ln):
                table_time_unit = "sec"
            elif header_min_re.search(ln):
                table_time_unit = "min"
            else:
                # 表头有 (h) 或 (hour) 提示
                if re.search(r"\bh\b", ln) or "hour" in ln.lower():
                    table_time_unit = "hour"
                elif re.search(r"\bmin\b", ln) or "minute" in ln.lower():
                    table_time_unit = "min"
                elif re.search(r"\bs\b", ln) or "sec" in ln.lower():
                    table_time_unit = "sec"
            # 检测是否上限表
            if "upper limit" in ln.lower() or "upper_limit" in ln.lower():
                table_is_limit = True

        # 解析行首 mid-time
        t_mid_hr = None
        mt = mid_time_re.match(ln)
        if mt:
            try:
                t_mid_hr = float(mt.group(1))
            except ValueError:
                pass
        # 尝试表格行首数字（管道分隔），优先用行内单位，否则用表头单位
        if t_mid_hr is None:
            tt = table_time_re.match(ln)
            if tt and (tt.group(2) or table_time_unit):
                try:
                    raw = float(tt.group(1))
                    unit = (tt.group(2) or "").lower() or table_time_unit
                    if unit in ("sec", "s"):
                        t_mid_hr = raw / 3600.0
                    elif unit in ("min",):
                        t_mid_hr = raw / 60.0
                    else:
                        t_mid_hr = raw
                except ValueError:
                    pass

        # 1) 行内 VT_x ... mag 或 VT_x | 数字 |（表格格式）
        m = photometric_line.search(ln)
        if m:
            # 确认不是色指数：VT_B 后面不能紧跟 - VT_R
            after = ln[m.start():m.end()+10]
            if not re.search(r"vt[_\s-]?[br]\s*[-–—]\s*vt", after, re.IGNORECASE):
                band = _norm_band(m.group(1))
                if band not in bands:
                    bands.append(band)
                is_limit = ">" in ln or "limit" in ln.lower() or table_is_limit
                val = None
                # 如果完整匹配了 mag（group 3 有值），直接用
                if m.group(3):
                    try:
                        val = float(m.group(3))
                    except ValueError:
                        pass
                else:
                    # 表格格式：VT_B | <数字> | <误差>，在匹配位置之后找第一个数值
                    rest = ln[m.end():]
                    # 按管道/空格分割找数值
                    parts = re.split(r"[|]", rest)
                    for part in parts:
                        part = part.strip()
                        # 跳过曝光时间格式（如 50x60, 37*70）
                        if re.match(r"^[\d.]+\s*[x*]\s*\d", part):
                            continue
                        mv = re.match(r"^(>?~?\s*)([\d.]+)", part)
                        if mv:
                            try:
                                v = float(mv.group(2))
                                # 跳过曝光时间（整数且 >100，如 3000, 2940, 70）
                                if v >= 30 and v == int(v):
                                    continue
                                val = v
                                break
                            except ValueError:
                                pass
                if val is not None and 14 <= val <= 26:
                    entry = {"band": band, "value": val, "unit": "mag", "is_limit": is_limit}
                    if t_mid_hr is not None:
                        entry["t_mid_hr"] = t_mid_hr
                    mags.append(entry)
                continue
        # 1.5) 范围格式: "from X mag to Y mag for VT_B" (取首值作为星等)
        range_line = re.compile(r"from\s+([\d.]+)\s*mag\s+to\s+([\d.]+)\s*mag\s+for\s+VT[_\s-]?([BR])", re.IGNORECASE)
        rms = list(range_line.finditer(ln))
        if rms:
            for rm in rms:
                band = f"VT_{rm.group(3).upper()}"
                if band not in bands:
                    bands.append(band)
                try:
                    entry = {"band": band, "value": float(rm.group(1)), "unit": "mag", "is_limit": False}
                    if t_mid_hr is not None:
                        entry["t_mid_hr"] = t_mid_hr
                    mags.append(entry)
                except ValueError:
                    pass
            continue
        # 2) VHF 只是数据下传方式，不是独立波段；不跳过行，继续解析 VT_B/VT_R
        # 3) 纯上限行（不含 VT 前缀）
        if any(k in ln.lower() for k in ("upper limit", "limit", ">")):
            ml = limit_line.search(ln)
            if ml:
                bv = re.search(r"vt[_\s-]?(?:b|r|white|clear)", ln, re.IGNORECASE)
                # "in both channels" → 同时属于 VT_B 和 VT_R
                if not bv and re.search(r"both\s+channels?", ln, re.IGNORECASE):
                    for band in ("VT_B", "VT_R"):
                        if band not in bands:
                            bands.append(band)
                        try:
                            entry = {"band": band, "value": float(ml.group(1)), "unit": "mag", "is_limit": True}
                            if t_mid_hr is not None:
                                entry["t_mid_hr"] = t_mid_hr
                            mags.append(entry)
                        except ValueError:
                            pass
                    continue
                band = _norm_band(bv.group(0)) if bv else "unknown"
                if band not in bands:
                    bands.append(band)
                try:
                    entry = {"band": band, "value": float(ml.group(1)), "unit": "mag", "is_limit": True}
                    if t_mid_hr is not None:
                        entry["t_mid_hr"] = t_mid_hr
                    mags.append(entry)
                except ValueError:
                    pass
            continue
        # 跳过变化量描述（fading/brightening/decayed by ... mag）
        if re.search(r"(?:fad|brighten|decay|change|increas|decreas)[a-z]*\s+(?:by\s+)?about\s+[\d.]+\s*(?:\+/?-|±)", ln, re.IGNORECASE):
            continue
        # 4) 测量值
        mm = measure_line.search(ln)
        if mm:
            bv = re.search(r"vt[_\s-]?(?:b|r|white|clear)", ln, re.IGNORECASE)
            # "in both channels" → 同时属于 VT_B 和 VT_R
            if not bv and re.search(r"both\s+channels?", ln, re.IGNORECASE):
                for band in ("VT_B", "VT_R"):
                    if band not in bands:
                        bands.append(band)
                    try:
                        entry = {"band": band, "value": float(mm.group(1)), "unit": "mag", "is_limit": False}
                        if t_mid_hr is not None:
                            entry["t_mid_hr"] = t_mid_hr
                        mags.append(entry)
                    except ValueError:
                        pass
                continue
            band = _norm_band(bv.group(0)) if bv else "unknown"
            if band not in bands:
                bands.append(band)
            try:
                entry = {"band": band, "value": float(mm.group(1)), "unit": "mag", "is_limit": False}
                if t_mid_hr is not None:
                    entry["t_mid_hr"] = t_mid_hr
                mags.append(entry)
            except ValueError:
                pass

    # Fallback 1: try Markdown table format if nothing found
    if not mags:
        md_bands, md_mags = _parse_markdown_table(body)
        if md_bands:
            bands = md_bands
            mags = md_mags

    # Fallback 2: try space-separated table format
    # e.g. "4.36 hour  VT_R  68*70 sec  22.98+/-0.25"
    if not mags:
        sp_bands, sp_mags = _parse_space_table(body)
        if sp_bands:
            bands = sp_bands
            mags = sp_mags

    return bands, mags


def _parse_markdown_table(body: str) -> tuple[List[str], List[dict]]:
    """
    Parse Markdown-style photometry tables like:

    | date-obs (utc)      | mid-time   | exposure  | VT_B mag(AB) | VT_R mag(AB) |
    | 2026-05-15T19:12:34 | 5.08 min   | 2*50 sec  | 16.16 ± 0.01 | 15.78 ± 0.01 |

    Returns (bands, mags) with t_mid_hr extracted from the mid-time column.
    """
    bands: List[str] = []
    mags: List[dict] = []
    lines = body.splitlines()

    # Find table blocks (consecutive lines starting with |)
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if not ln.startswith("|"):
            i += 1
            continue
        # Collect table block
        block = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            block.append(lines[i].strip())
            i += 1

        if len(block) < 2:
            continue

        # Parse header (same splitting as data rows for index alignment)
        header = [c.strip() for c in block[0].split("|")]
        if header and header[0] == "":
            header.pop(0)
        if header and header[-1] == "":
            header.pop()

        # Find VT_B / VT_R column indices
        vt_b_col = vt_r_col = None
        mid_col = exp_col = None
        for ci, col_name in enumerate(header):
            cn = col_name.lower()
            if "vt_b" in cn or "vtb" in cn:
                vt_b_col = ci
            if "vt_r" in cn or "vtr" in cn:
                vt_r_col = ci
            if "mid" in cn and "time" in cn:
                mid_col = ci
            if "exp" in cn:
                exp_col = ci

        if vt_b_col is None and vt_r_col is None:
            continue

        # Parse data rows (skip separator rows like |---|---|)
        for row in block[1:]:
            cells = [c.strip() for c in row.split("|")]
            # Remove leading/trailing empty from | delimiters
            if cells and cells[0] == "":
                cells.pop(0)
            if cells and cells[-1] == "":
                cells.pop()
            # Filter separator
            if all(re.match(r"^[-:\s]*$", c) for c in cells if c):
                continue

            # Extract mid-time
            t_mid_hr = None
            if mid_col is not None and mid_col < len(cells):
                mt = cells[mid_col]
                # formats: "5.08 min", "1.07 h", "0.965 hour", "123 sec"
                mtm = re.match(r"([\d.]+)\s*(min|sec|s|hour|hr|h)?", mt, re.IGNORECASE)
                if mtm:
                    try:
                        raw = float(mtm.group(1))
                        unit = (mtm.group(2) or "").lower()
                        if unit in ("sec", "s"):
                            t_mid_hr = raw / 3600.0
                        elif unit.startswith("min"):
                            t_mid_hr = raw / 60.0
                        else:
                            t_mid_hr = raw
                    except ValueError:
                        pass

            # Extract VT_B
            for band, col in [("VT_B", vt_b_col), ("VT_R", vt_r_col)]:
                if col is None or col >= len(cells):
                    continue
                val_str = cells[col]
                # Parse magnitude: "16.16 ± 0.01" or ">21.5" or "21.5"
                is_limit = val_str.startswith(">")
                mv = re.search(r"([\d.]+)", val_str.replace(">", ""))
                if mv:
                    try:
                        val = float(mv.group(1))
                        if 10 <= val <= 27:
                            if band not in bands:
                                bands.append(band)
                            entry = {"band": band, "value": val, "unit": "mag",
                                     "is_limit": is_limit}
                            if t_mid_hr is not None:
                                entry["t_mid_hr"] = t_mid_hr
                            mags.append(entry)
                    except ValueError:
                        pass

    return bands, mags


def _parse_space_table(body: str) -> tuple[List[str], List[dict]]:
    """
    Parse various space-separated photometry table formats found in GCNs.

    Supported formats:
    1. "4.36 hour  VT_R  68*70 sec  22.98+/-0.25" (mid-time unit band exp mag)
    2. "48.133 | 28x60 | 20.388 | 0.08 | VT_R" (pipe-separated, band last)
    3. "2.2  2.85  VT_R  23.3" (mid-time exp band mag)
    4. "377  300  VT_R  21.5" (mid-time(sec) exp band limit)
    5. "VT_B  13.25  149x100s  23.5 +/-0.2" (band mid-time exp mag)
    6. "VT_B~21.53 mag(AB) ... mid time of 443 seconds" (text)
    """
    bands: List[str] = []
    mags: List[dict] = []

    def _add(band, val, t_mid_hr, is_limit):
        if band and val is not None and 10 <= val <= 27:
            if band not in bands:
                bands.append(band)
            entry = {"band": band, "value": val, "unit": "mag", "is_limit": is_limit}
            entry["t_mid_hr"] = t_mid_hr
            mags.append(entry)

    def _to_hr(raw, unit=""):
        u = (unit or "").lower()
        if u.startswith("sec") or u == "s":
            return raw / 3600.0
        if u.startswith("min"):
            return raw / 60.0
        return raw  # default hours

    lines = body.splitlines()

    # Detect if this is an upper-limit table (context-based)
    body_lower = body.lower()
    is_limit_context = bool(re.search(
        r"(?:3\s*sigma\s*limit|upper\s*limit|upperlim|non[- ]detection|no\s+(?:credible\s+)?candidate)",
        body_lower
    ))

    for line in lines:
        ln = line.strip()
        if not ln:
            continue

        # Skip color index lines
        if re.search(r"vt[_\s-]?[br]\s*[-–—]\s*vt", ln, re.IGNORECASE):
            continue

        # --- Format 2: pipe-separated, band at end ---
        # "48.133 | 28x60 | 20.388 | 0.08 | VT_R"
        if "|" in ln and re.search(r"VT[_\s-]?[BR]", ln, re.IGNORECASE):
            cells = [c.strip() for c in ln.split("|")]
            # band is usually last cell
            band_match = re.search(r"(VT[_\s-]?[BR])", ln, re.IGNORECASE)
            if band_match:
                band = _norm_band(band_match.group(1))
                # find magnitude: a float in range 14-25, not exposure
                val = None
                is_limit = ">" in ln or is_limit_context
                t_mid = None
                for ci, cell in enumerate(cells):
                    # exposure like 28x60
                    if re.match(r"^[\d.]+\s*[x*]", cell):
                        continue
                    # band cell
                    if re.search(r"VT[_\s-]?[BR]", cell, re.IGNORECASE):
                        continue
                    # time: first numeric cell
                    mv = re.match(r"^([\d.]+)\s*(hour|hr|h|min|sec|s)?", cell, re.IGNORECASE)
                    if mv and t_mid is None:
                        try:
                            raw = float(mv.group(1))
                            unit = mv.group(2) or ""
                            # guess: if >100 and no unit, likely seconds; if header says hours use hours
                            if not unit:
                                if raw > 100:
                                    unit = "sec"
                                else:
                                    unit = "hour"
                            t_mid = _to_hr(raw, unit)
                        except ValueError:
                            pass
                        continue
                    # magnitude value
                    mv2 = re.match(r"^(>?~?\s*)([\d.]+)", cell)
                    if mv2 and val is None:
                        try:
                            v = float(mv2.group(2))
                            if 10 <= v <= 26:
                                val = v
                                if ">" in mv2.group(1):
                                    is_limit = True
                        except ValueError:
                            pass
                if val is not None:
                    _add(band, val, t_mid, is_limit)
                continue

        # --- Format 5: band first ---
        # "VT_B  13.25  149x100s  23.5 +/-0.2" or "VT_R 13.26 142x100s 22.4 +/-0.1"
        m5 = re.match(
            r"\s*(VT[_\s-]?[BR])\s+"
            r"([\d.]+)\s*(hour|hr|h|min|sec|s|minutes?)?\s+"  # mid-time
            r"(?:[\d.]+\s*[x*+\s]*\d+\s*(?:sec|s)?\s+)?"       # exposure
            r"(>?~?\s*)([\d.]+)"                                # magnitude
            r"(?:\s*(?:\+/?-|±)\s*[\d.]+)?",
            ln, re.IGNORECASE,
        )
        if m5:
            band = _norm_band(m5.group(1))
            t_raw = float(m5.group(2))
            t_unit = m5.group(3) or ""
            is_limit = ">" in m5.group(4) or is_limit_context
            val = float(m5.group(5))
            _add(band, val, _to_hr(t_raw, t_unit), is_limit)
            continue

        # --- Format 1/3/4: mid-time first, then band ---
        # "4.36 hour VT_R 68*70 sec 22.98"
        # "2.2 2.85 VT_R 23.3"
        # "377 300 VT_R 21.5"
        m1 = re.match(
            r"\s*([\d.]+)\s*(hour|hr|h|min|sec|s|minutes?)?\s+"  # mid-time (+optional unit)
            r"(?:[\d.]+\s*[x*+\s]*\d+\s*(?:sec|s)?\s+)?"         # optional exposure
            r"(VT[_\s-]?[BR])\s+"                                 # band
            r"(?:[\d.]+\s*[x*+\s]*\d+\s*(?:sec|s)?\s+)?"         # optional exposure after band
            r"(>?~?\s*)([\d.]+)"                                  # magnitude
            r"(?:\s*(?:\+/?-|±)\s*[\d.]+)?",
            ln, re.IGNORECASE,
        )
        if m1:
            band = _norm_band(m1.group(3))
            t_raw = float(m1.group(1))
            t_unit = m1.group(2) or ""
            if not t_unit:
                if t_raw > 100:
                    t_unit = "sec"
                else:
                    t_unit = "hour"
            is_limit = ">" in m1.group(4) or is_limit_context
            val = float(m1.group(5))
            _add(band, val, _to_hr(t_raw, t_unit), is_limit)
            continue

    # --- Format 6: text descriptions ---
    # "VT_R ~20.61 mag(AB) ... mid time of 443 seconds"
    # "VT_B~15.8 mag(AB) and VT_R~14.2 mag(AB) ... mid time of 461 seconds"
    if not mags:
        # find all "VT_x ~val" or "VT_x val" patterns
        text_mags = list(re.finditer(
            r"(VT[_\s-]?[BR])\s*~?\s*([\d.]+)\s*(?:mag)?",
            body, re.IGNORECASE,
        ))
        if text_mags:
            # extract global mid-time
            t_global = None
            tm = re.search(r"(?:mid(?:dle)?\s*time(?:\s+of)?|at)\s+([\d.]+)\s*(hour|hr|h|min|sec|s|seconds?|minutes?)", body, re.IGNORECASE)
            if tm:
                t_global = _to_hr(float(tm.group(1)), tm.group(2))
            else:
                tm2 = re.search(r"([\d.]+)\s*(seconds?|sec|s)\s+(?:after|post)", body, re.IGNORECASE)
                if tm2:
                    t_global = _to_hr(float(tm2.group(1)), tm2.group(2))
            for tm_match in text_mags:
                band = _norm_band(tm_match.group(1))
                try:
                    val = float(tm_match.group(2))
                except ValueError:
                    continue
                _add(band, val, t_global, is_limit_context)

    return bands, mags


def _to_hours(value: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith("min"):
        return value / 60.0
    if u.startswith("hr") or u.startswith("hour"):
        return value
    if u.startswith("day"):
        return value * 24.0
    if u.startswith("sec"):
        return value / 3600.0
    if u.startswith("s"):
        return value / 3600.0
    return value


def extract_obs_start(body: str) -> Optional[str]:
    m = RE_OBS_START.search(body or "")
    if m:
        return m.group(1).replace(" ", "T")
    return None


def extract_trigger_time(body: str) -> Optional[str]:
    m = RE_TRIGGER_TIME.search(body or "")
    if m:
        return m.group(2).replace(" ", "T")
    return None


def extract_post_trigger_hours(body: str) -> Optional[float]:
    text = body or ""
    # 优先匹配 "from X hours to Y hours after/post" → 取观测开始时间 X
    m_range = RE_POST_TRIGGER_RANGE.search(text)
    if m_range:
        val = float(m_range.group(1))
        unit = m_range.group(2)
        return _to_hours(val, unit)
    m = RE_POST_TRIGGER.search(text)
    if not m:
        return None
    val = float(m.group(2))
    unit = m.group(3)
    return _to_hours(val, unit)


def extract_exposure(body: str) -> List[str]:
    exps: List[str] = []
    for m in re.finditer(
        r"(\d+\s*\*\s*\d+\s*s|\d+\s*x\s*\d+\s*s|\d+\s*\*\s*\d+\s*sec|\d+\s*s\s*expos\w*|\d+\s*sec\s*expos\w*)",
        body or "", re.IGNORECASE,
    ):
        s = m.group(1).strip()
        if s not in exps:
            exps.append(s)
    return exps


def extract_event_name(subject: str, body: str, fallback_event_id: Optional[str] = None) -> str:
    text = f"{subject}\n{body}"
    m = RE_EVENT.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return fallback_event_id or "UNKNOWN"


def enrich(circular: dict) -> Optional[dict]:
    """返回增强后的 dict；若不是 SVOM/VT 团队报告则返回 None。"""
    subject = circular.get("subject", "") or ""
    body = circular.get("body", "") or ""
    submitter = circular.get("submitter", "") or ""
    event_id = circular.get("eventId")

    # —— VT 相关性判定（精确口径）——
    # 1) subject 含 VT 词 + submitter 属 SVOM 团队（排除 COLIBRÍ/LCO/CrAO 等"探测到 VT 候选体"的其他团队）
    # 2) body 作者署名段含 SVOM/VT team（兜底，无需 subject 命中）
    is_vt = (_subject_is_vt(subject) and _submitter_is_svom(submitter)) or _body_is_vt_team(body, submitter)
    if not is_vt:
        return None

    report_type = classify_report(subject, body)
    bands, mags = extract_bands_and_mags(subject, body)
    obs_start = extract_obs_start(body)
    trigger_time = extract_trigger_time(body)
    post_trigger_hr = extract_post_trigger_hours(body)
    exposures = extract_exposure(body)
    event_name = extract_event_name(subject, body, event_id)
    trigger_source = identify_trigger_source(subject, body)

    # Auto-fix is_limit: if report_type is upper_limit, force all mags to is_limit=True
    if report_type == "upper_limit":
        for m in mags:
            m["is_limit"] = True

    enriched = dict(circular)
    enriched.update({
        "is_vt": True,
        "report_type": report_type,
        "bands": bands,
        "magnitudes": mags,
        "exposure_times": exposures,
        "obs_start_utc": obs_start,
        "trigger_time_utc": trigger_time,
        "trigger_to_obs_hr": post_trigger_hr,
        "event_name": event_name,
        "trigger_source": trigger_source,
    })
    return enriched


def keep_only_vt(circulars: List[dict]) -> List[dict]:
    out: List[dict] = []
    for c in circulars:
        e = enrich(c)
        if e is not None:
            out.append(e)
    return out
