"""
VT Circulars 数据存储与更新管理

负责：
- 本地 JSON 持久化（data/vt_circulars.json）
- 全量初始化（首次运行，下载完整归档并过滤）
- 增量更新（基于最大 circularId 向后抓取）
- 提供 Web 使用的查询/统计接口
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import config
from gcn_fetcher import GCNFetcher, created_on_to_iso
from vt_parser import enrich, keep_only_vt

log = logging.getLogger("store")


class VTStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[int, dict] = {}
        self._meta: dict = {
            "last_full_update": None,
            "last_incremental_update": None,
            "max_circular_id": 0,
            "total_scanned": 0,
            "update_history": [],   # 每次更新摘要
        }
        self.fetcher = GCNFetcher()
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        if not os.path.exists(config.DB_PATH):
            return
        try:
            with open(config.DB_PATH, "r", encoding="utf-8") as f:
                blob = json.load(f)
            with self._lock:
                self._records = {int(k): v for k, v in blob.get("records", {}).items()}
                self._meta = blob.get("meta", self._meta)
            log.info("Loaded %d VT records (max id=%s)", len(self._records), self._meta.get("max_circular_id"))
        except Exception as exc:
            log.error("Failed to load store: %s", exc)
        # 加载时重新解析（确保 parser 改进生效）
        self._reparse_all()
        # 应用人工分类覆盖（每次加载都重新应用，确保继承）
        self._apply_manual_overrides()

    def _reparse_all(self) -> None:
        """用最新 parser 重新 enrich 所有记录（保留 body 等原始字段）。"""
        with self._lock:
            items = list(self._records.items())
        n = 0
        for cid, raw in items:
            enriched = enrich(dict(raw))
            if enriched is not None:
                with self._lock:
                    self._records[cid] = enriched
                n += 1
        if n:
            log.info("Re-parsed %d records with latest parser", n)

    def _apply_manual_overrides(self) -> None:
        """加载并应用 data/manual_overrides.json 中的人工分类。"""
        try:
            from manual_override import apply_overrides
            n = apply_overrides(self._records)
            if n:
                log.info("Applied %d manual overrides", n)
        except Exception as exc:
            log.warning("Failed to apply manual overrides: %s", exc)

    def _save(self) -> None:
        with self._lock:
            blob = {"records": {str(k): v for k, v in self._records.items()}, "meta": self._meta}
        tmp = config.DB_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(blob, f, ensure_ascii=False)
        os.replace(tmp, config.DB_PATH)

    # ---------- 写入 ----------
    def _upsert(self, circular: dict) -> bool:
        cid = int(circular.get("circularId", -1))
        if cid <= 0:
            return False
        enriched = enrich(circular)
        if enriched is None:
            # 即使不是 VT，也更新 max_circular_id 范围信息（不存储）
            return False
        with self._lock:
            self._records[cid] = enriched
            if cid > self._meta.get("max_circular_id", 0):
                self._meta["max_circular_id"] = cid
        return True

    # ---------- 初始化（全量） ----------
    def initialize_from_full_archive(self) -> int:
        log.info("Initializing from full GCN archive (this may take a minute)...")
        all_records = self.fetcher.download_full_archive()
        added = 0
        scanned = 0
        max_id_seen = 0
        for rec in all_records:
            try:
                cid = int(rec.get("circularId", 0))
            except (TypeError, ValueError):
                continue
            scanned += 1
            if cid > max_id_seen:
                max_id_seen = cid
            if self._upsert(rec):
                added += 1
        with self._lock:
            self._meta["last_full_update"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self._meta["total_scanned"] = scanned
            if max_id_seen > self._meta.get("max_circular_id", 0):
                self._meta["max_circular_id"] = max_id_seen
            self._meta["update_history"].append({
                "at": self._meta["last_full_update"],
                "kind": "full",
                "added": added,
                "scanned": scanned,
                "max_id": self._meta["max_circular_id"],
            })
        self._apply_manual_overrides()
        self._save()
        log.info("Full init done: scanned=%d, VT added=%d, max_id=%d", scanned, added, self._meta["max_circular_id"])
        return added

    # ---------- 增量更新 ----------
    def update_incremental(self) -> int:
        """从已知的 max_circular_id+1 开始向后增量抓取。"""
        with self._lock:
            start = self._meta.get("max_circular_id", 0) + 1
        if start < 1:
            # 还没初始化，先做全量
            return self.initialize_from_full_archive()

        log.info("Incremental update from id=%d", start)
        # 先探测最新 id
        try:
            latest = self.fetcher.discover_latest_id(start_hint=max(start - 10, 1))
        except Exception as exc:
            log.error("discover_latest_id failed: %s", exc)
            latest = start + 200  # 兜底：试探一段区间

        if latest < start:
            log.info("No new circulars (latest=%d < start=%d)", latest, start)
            self._record_update("incremental", added=0, scanned=0, max_id=self._meta.get("max_circular_id", 0))
            return 0

        added = 0
        scanned = 0
        # 限制单次最多扫描数量，避免过载
        hard_cap = max(500, latest - start + 10)
        for rec in self.fetcher.fetch_range(start, latest):
            scanned += 1
            if self._upsert(rec):
                added += 1
            if scanned >= hard_cap:
                break

        with self._lock:
            self._meta["last_incremental_update"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self._meta["max_circular_id"] = max(self._meta.get("max_circular_id", 0), latest)
            self._meta["total_scanned"] = self._meta.get("total_scanned", 0) + scanned
        self._record_update("incremental", added=added, scanned=scanned, max_id=self._meta["max_circular_id"])
        self._apply_manual_overrides()
        self._save()
        if added > 0:
            self._refresh_static_figures()
        log.info("Incremental done: scanned=%d, VT added=%d, latest=%d", scanned, added, latest)
        return added

    def _record_update(self, kind: str, *, added: int, scanned: int, max_id: int) -> None:
        with self._lock:
            now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if kind == "incremental" and not self._meta.get("last_incremental_update"):
                self._meta["last_incremental_update"] = now
            self._meta["update_history"].append({
                "at": now, "kind": kind, "added": added, "scanned": scanned, "max_id": max_id,
            })
            # 仅保留最近 200 条历史
            self._meta["update_history"] = self._meta["update_history"][-200:]

    def _refresh_static_figures(self) -> None:
        """增量更新后自动重新生成静态光变图（PNG）。"""
        try:
            import subprocess, sys, os
            script = os.path.join(os.path.dirname(__file__), "lc_density_plot.py")
            if os.path.exists(script):
                subprocess.run(
                    [sys.executable, script],
                    capture_output=True, timeout=120,
                    cwd=os.path.dirname(__file__),
                )
                log.info("Static figures refreshed after incremental update")
        except Exception as exc:
            log.warning("Failed to refresh static figures: %s", exc)

    # ---------- 查询 ----------
    def all_records(self) -> List[dict]:
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.get("circularId", 0), reverse=True)

    def meta(self) -> dict:
        with self._lock:
            return dict(self._meta)

    def get(self, cid: int) -> Optional[dict]:
        with self._lock:
            return self._records.get(cid)

    def upper_limit_events(self) -> list:
        """Events where VT only has upper limits (no detection in any band)."""
        records = self.all_records()
        events = {}
        for r in records:
            rtype = r.get("report_type", "")
            if rtype in ("stellar_flare", "clarification", "other"):
                continue
            event = r.get("event_name") or ""
            if not event:
                continue
            ev = events.setdefault(event, {
                "event": event, "source": "", "gcns": set(),
                "detections": [], "limits": [], "delay_hr": None,
                "is_svom": False, "is_auto_followup": False,
            })
            ev["source"] = r.get("trigger_source", "") or ev["source"]
            ev["gcns"].add(r.get("circularId"))
            d = r.get("trigger_to_obs_hr")
            if isinstance(d, (int, float)) and (ev["delay_hr"] is None or d < ev["delay_hr"]):
                ev["delay_hr"] = round(d, 2)
            src = (r.get("trigger_source", "") or "")
            if src.startswith("SVOM"):
                ev["is_svom"] = True
                if isinstance(d, (int, float)) and 0 < d <= 1.0:
                    ev["is_auto_followup"] = True
            # Check manual override for is_auto_followup
            if r.get("is_auto_followup"):
                ev["is_auto_followup"] = True
            for m in r.get("magnitudes", []):
                entry = {
                    "gcn": r.get("circularId"),
                    "band": m.get("band", ""),
                    "value": m.get("value"),
                    "t_mid_hr": m.get("t_mid_hr"),
                    "is_limit": m.get("is_limit", False),
                }
                if entry["is_limit"]:
                    ev["limits"].append(entry)
                else:
                    ev["detections"].append(entry)
        result = [v for v in events.values() if not v["detections"] and v["limits"]]
        result.sort(key=lambda x: min(x["gcns"]))
        for v in result:
            v["gcns"] = sorted(v["gcns"])
            # Merge limits: deduplicate by (band), keep deepest limit per band
            band_best = {}
            for lim in v["limits"]:
                b = lim["band"]
                if b not in band_best or (lim["value"] and (not band_best[b]["value"] or lim["value"] > band_best[b]["value"])):
                    band_best[b] = lim
            v["limits_merged"] = sorted(band_best.values(), key=lambda x: x["band"])
            # Build display strings
            v["limit_str"] = "; ".join(
                f'{l["band"]}&gt;{l["value"]:.1f}' for l in v["limits_merged"]
            )
            v["t_mid_str"] = "; ".join(
                f'{l["t_mid_hr"]:.2f}h' if l.get("t_mid_hr") else '—' for l in v["limits_merged"]
            )
            v["gcn_str"] = ", ".join(str(g) for g in v["gcns"])
            v["primary_gcn"] = v["gcns"][0] if v["gcns"] else None
        return result

    def ul_comments_map(self) -> dict:
        """Map GCN ID -> ul_comment from overrides."""
        overrides = {}
        try:
            from manual_override import load_overrides
            ovs = load_overrides()
            for cid, ov in ovs.items():
                if "ul_comment" in ov:
                    overrides[int(cid)] = ov["ul_comment"]
        except Exception:
            pass
        return overrides

    def stats(self) -> dict:
        records = self.all_records()
        total = len(records)
        by_type: Dict[str, int] = {}
        by_band: Dict[str, int] = {}
        by_trigger: Dict[str, int] = {}
        by_event: Dict[str, int] = {}
        monthly: Dict[str, int] = {}
        delay_hours: List[float] = []
        delay_svom: List[float] = []
        delay_others: List[float] = []
        for r in records:
            rt = r.get("report_type", "other")
            by_type[rt] = by_type.get(rt, 0) + 1
            # 波段：每条只计一次每种波段（bands 已去重）
            for b in r.get("bands", []) or []:
                by_band[b] = by_band.get(b, 0) + 1
            ts = r.get("trigger_source", "Unknown")
            by_trigger[ts] = by_trigger.get(ts, 0) + 1
            ev = r.get("event_name") or "UNKNOWN"
            by_event[ev] = by_event.get(ev, 0) + 1
            try:
                co = r.get("createdOn")
                if co:
                    dt = datetime.fromtimestamp(co / 1000.0, tz=timezone.utc)
                    key = dt.strftime("%Y-%m")
                    monthly[key] = monthly.get(key, 0) + 1
            except Exception:
                pass
            d = r.get("trigger_to_obs_hr")
            if isinstance(d, (int, float)) and d >= 0:
                delay_hours.append(float(d))
                # 按触发卫星分组（SVOM 自家 vs 其他）
                ts_raw = r.get("trigger_source", "Unknown")
                if ts_raw.startswith("SVOM"):
                    delay_svom.append(float(d))
                else:
                    delay_others.append(float(d))
        delay_hours_sorted = sorted(delay_hours)
        n = len(delay_hours_sorted)
        def _pctile(p):
            if n == 0:
                return None
            k = max(0, min(n - 1, int(round(p / 100.0 * (n - 1)))))
            return delay_hours_sorted[k]
        def _frac_within(thr):
            if n == 0:
                return None
            return sum(1 for d in delay_hours_sorted if d <= thr) / n

        # 自动后随证认率 (SVOM≤1h, EP/Swift≤2h, or is_auto_followup override)
        af_det, af_ul = 0, 0
        for r in records:
            d = r.get("trigger_to_obs_hr")
            rt = r.get("report_type", "")
            if rt not in ("detection", "upper_limit"):
                continue
            src = r.get("trigger_source", "") or ""
            thr = 1.0 if src.startswith("SVOM") else 2.0
            is_af = (isinstance(d, (int, float)) and 0 < d <= thr) or r.get("is_auto_followup")
            if not is_af:
                continue
            if rt == "detection":
                af_det += 1
            else:
                af_ul += 1
        auto_rate = af_det / (af_det + af_ul) if (af_det + af_ul) > 0 else 0

        return {
            "total": total,
            "by_type": by_type,
            "by_band": dict(sorted(by_band.items(), key=lambda kv: kv[1], reverse=True)),
            "by_trigger": dict(sorted(by_trigger.items(), key=lambda kv: kv[1], reverse=True)),
            "by_event": dict(sorted(by_event.items(), key=lambda kv: kv[1], reverse=True)),
            "monthly": dict(sorted(monthly.items())),
            "delay_hours": delay_hours,
            "detection_count": by_type.get("detection", 0),
            "upper_limit_count": by_type.get("upper_limit", 0),
            "stellar_flare_count": by_type.get("stellar_flare", 0),
            "clarification_count": by_type.get("clarification", 0),
            "detection_rate": (by_type.get("detection", 0) / (by_type.get("detection", 0) + by_type.get("upper_limit", 0)))
                if (by_type.get("detection", 0) + by_type.get("upper_limit", 0)) > 0 else 0,
            "auto_followup_rate": auto_rate,
            "events_count": len(by_event),
            "median_delay_hr": delay_hours_sorted[n // 2] if n else None,
            "min_delay_hr": delay_hours_sorted[0] if n else None,
            "max_delay_hr": delay_hours_sorted[-1] if n else None,
            "p25_delay_hr": _pctile(25),
            "p50_delay_hr": _pctile(50),
            "p75_delay_hr": _pctile(75),
            "p90_delay_hr": _pctile(90),
            "frac_within_1h": _frac_within(1.0),
            "frac_within_2h": _frac_within(2.0),
            "frac_within_6h": _frac_within(6.0),
            "frac_within_12h": _frac_within(12.0),
            "frac_within_24h": _frac_within(24.0),
            "delay_svom": sorted(delay_svom),
            "delay_others": sorted(delay_others),
        }


# 单例（供 app 与 scheduler 共享）
_store_singleton: Optional[VTStore] = None
_store_lock = threading.Lock()


def get_store() -> VTStore:
    global _store_singleton
    with _store_lock:
        if _store_singleton is None:
            _store_singleton = VTStore()
        return _store_singleton
