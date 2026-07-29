"""
GCN Circulars 数据抓取模块

策略：
1. 首次运行时下载官方提供的完整 archive.json.tar.gz（每日生成一次），
   作为扫描基线，用于一次性遍历所有历史 circulars，提取 SVOM/VT 相关条目。
2. 后续更新时通过已知最大 circularId 顺序向后增量抓取 /circulars/{id}.json，
   这是稳定可靠的官方接口。
3. 所有结果持久化到 data/vt_circulars.json，作为本地缓存与展示数据源。

注：GCN 官方并未提供稳定的全文搜索 REST 接口（/api/circulars 会返回 400），
    上述策略在不依赖搜索接口的情况下覆盖「历史全量 + 增量」两类需求。
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
import tarfile
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import requests

import config

log = logging.getLogger("gcn_fetcher")


class GCNFetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self.cache_all_path = os.path.join(config.CACHE_DIR, "archive_all.json")

    # ---------- 网络底层 ----------
    def _get(self, url: str, *, stream: bool = False) -> requests.Response:
        last_err: Optional[Exception] = None
        for attempt in range(1, config.HTTP_RETRY + 1):
            try:
                resp = self.session.get(url, timeout=config.HTTP_TIMEOUT, stream=stream)
                if resp.status_code == 404:
                    return resp  # 调用方判断
                if resp.status_code == 200:
                    return resp
                log.warning("HTTP %s on %s (attempt %d/%d)", resp.status_code, url, attempt, config.HTTP_RETRY)
            except requests.RequestException as exc:  # pragma: no cover - 网络
                last_err = exc
                log.warning("Request error %s on %s (attempt %d/%d)", exc, url, attempt, config.HTTP_RETRY)
            time.sleep(1.5 * attempt)
        raise RuntimeError(f"Failed to fetch {url}: {last_err}")

    # ---------- 单条获取 ----------
    def fetch_one(self, circular_id: int) -> Optional[dict]:
        """按 circularId 获取单条。404/不存在返回 None。"""
        url = config.GCN_CIRC_URL.format(cid=circular_id)
        resp = self._get(url)
        if resp.status_code == 404:
            return None
        data = resp.json()
        data["_source_url"] = url
        return data

    # ---------- 探测最新 circularId ----------
    def discover_latest_id(self, start_hint: Optional[int] = None) -> int:
        """通过二分查找定位最新发布的 circularId。

        GCN circularId 单调递增；我们用指数后退找到上界，再二分。
        """
        # 先用起始提示值验证
        if start_hint is None or start_hint < 1:
            # 从最近已知的一个较新 ID 开始探测（避免从头扫描）
            probe = 45000
            # 向前回退到一个存在的 ID
            for _ in range(200):
                if self.fetch_one(probe) is not None:
                    break
                probe -= 1
            start_hint = max(probe, 1)

        # 指数扩张找上界（不存在的 ID）
        known = start_hint
        step = 50
        upper = known + step
        while True:
            if self.fetch_one(upper) is None:
                break
            known = upper
            step *= 2
            upper = known + step
            if step > 2000:
                break

        # 二分收缩到最大存在 ID
        lo, hi = known, upper
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.fetch_one(mid) is not None:
                lo = mid
            else:
                hi = mid - 1
            time.sleep(config.HTTP_SLEEP_BETWEEN)
        return lo

    # ---------- 完整归档（一次性基线） ----------
    def download_full_archive(self) -> List[dict]:
        """下载 archive.json.tar.gz 并解析为 list[dict]。

        archive 实际是一个 tar 包，里面每个 circular 一个 {circularId}.json 文件。
        本方法流式读取 tar 成员，逐个解析 JSON。
        解析失败时若存在本地缓存则回退使用。
        """
        try:
            resp = self._get(config.GCN_ARCHIVE_URL, stream=True)
            raw = resp.content
            log.info("Downloaded archive %d bytes", len(raw))
            records: List[dict] = []
            # 直接对 gzip+tara 进行流式解析
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
                for member in tar:
                    if not member.isfile() or not member.name.endswith(".json"):
                        continue
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    try:
                        txt = f.read().decode("utf-8", errors="replace")
                        records.append(json.loads(txt))
                    except (json.JSONDecodeError, OSError):
                        continue
            if records:
                with open(self.cache_all_path, "w", encoding="utf-8") as f:
                    json.dump(records, f)
                log.info("Full archive parsed: %d records cached", len(records))
                return records
            raise RuntimeError("Archive parsed 0 records")
        except Exception as exc:
            log.error("download_full_archive failed: %s", exc)
            if os.path.exists(self.cache_all_path):
                log.warning("Falling back to cached archive")
                with open(self.cache_all_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            raise

    # ---------- 增量：按 ID 区间批量 ----------
    def fetch_range(self, start_id: int, end_id: int) -> Iterable[dict]:
        """顺序抓取 [start_id, end_id] 区间内存在的 circular。"""
        for cid in range(start_id, end_id + 1):
            data = self.fetch_one(cid)
            if data is not None:
                yield data
            time.sleep(config.HTTP_SLEEP_BETWEEN)


def created_on_to_iso(ms: int) -> str:
    """GCN createdOn 是毫秒级 UNIX 时间戳，转 ISO 字符串。"""
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""
