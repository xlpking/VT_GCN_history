"""
人工分类覆盖（Manual Override）。

持久化文件：data/manual_overrides.json
格式：
{
  "<circularId>": {
    "trigger_source": "SVOM/ECLAIRs",
    "note": "GCN 39041 确认为 ECLAIRs 触发",
    "updated_at": "2026-07-29T10:00:00"
  }
}

该文件独立于自动解析结果，每次加载/更新数据时自动应用，
从而保证人工分类在网页更新后被继承。
"""
import json
import os
from datetime import datetime, timezone
from typing import Dict, Optional

OVERRIDE_FILE = os.path.join(os.path.dirname(__file__), "data", "manual_overrides.json")

# 所有合法的 trigger_source 值
VALID_TRIGGERS = [
    "SVOM/ECLAIRs", "SVOM/GRM", "SVOM/MXT",
    "EP", "Swift", "Fermi", "INTEGRAL", "GECAM", "IceCube",
    "AstroSat", "Insight-HXMT", "MAXI", "LIGO/Virgo",
    "Unknown",
]


def load_overrides() -> Dict[str, dict]:
    """加载所有人工覆盖。"""
    if not os.path.exists(OVERRIDE_FILE):
        return {}
    try:
        with open(OVERRIDE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_overrides(overrides: Dict[str, dict]) -> None:
    """保存全部人工覆盖。"""
    os.makedirs(os.path.dirname(OVERRIDE_FILE), exist_ok=True)
    with open(OVERRIDE_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)


def set_override(circular_id, trigger_source: str, note: str = "") -> dict:
    """为指定 GCN 设置人工分类。返回新的覆盖条目。"""
    ts = trigger_source.strip()
    if ts not in VALID_TRIGGERS:
        raise ValueError(f"非法的 trigger_source: {ts}")
    overrides = load_overrides()
    key = str(circular_id)
    overrides[key] = {
        "trigger_source": ts,
        "note": note.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_overrides(overrides)
    return overrides[key]


def set_ul_override(circular_id, report_type: str, comment: str = "") -> dict:
    """为上限表格中的 GCN 设置 report_type 和 comment。"""
    overrides = load_overrides()
    key = str(circular_id)
    if key not in overrides:
        overrides[key] = {}
    overrides[key]["report_type"] = report_type
    overrides[key]["ul_comment"] = comment.strip()
    overrides[key]["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_overrides(overrides)
    return overrides[key]


def apply_overrides(records: dict) -> int:
    """
    将人工覆盖应用到 records dict（原地修改）。
    返回被覆盖的记录数。
    """
    overrides = load_overrides()
    if not overrides:
        return 0
    count = 0
    for key, rec in records.items():
        cid = str(rec.get("circularId", key))
        if cid in overrides:
            ov = overrides[cid]
            if "trigger_source" in ov:
                rec["trigger_source"] = ov["trigger_source"]
            if "report_type" in ov:
                rec["report_type"] = ov["report_type"]
            if "event_name" in ov:
                rec["event_name"] = ov["event_name"]
            if "trigger_to_obs_hr" in ov:
                rec["trigger_to_obs_hr"] = ov["trigger_to_obs_hr"]
            if "is_auto_followup" in ov:
                rec["is_auto_followup"] = ov["is_auto_followup"]
            if "ul_comment" in ov:
                rec["ul_comment"] = ov["ul_comment"]
            if "bands" in ov:
                rec["bands"] = ov["bands"]
            if "magnitudes" in ov:
                rec["magnitudes"] = ov["magnitudes"]
            rec["manual_override"] = True
            count += 1
    return count
