"""
Persistent JSONL storage for the Volatility Index.

Layout:
    uploads/vol_history/{underlying}/
        history.jsonl        — one record per trading day (vol snapshot)
        price_history.jsonl  — daily close prices (for GARCH estimation)

Thread-safe (per-underlying lock).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Lock registry (one lock per underlying) ─────────────────────────────────
_locks: dict[str, threading.Lock] = {}
_lock_registry = threading.Lock()


def _get_lock(key: str) -> threading.Lock:
    with _lock_registry:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


# ── File helpers ─────────────────────────────────────────────────────────────

def _sanitize(name: str) -> str:
    return ''.join(c if (c.isalnum() or c in '-_.') else '_' for c in name)


def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _atomic_replace(temp_path: str, target_path: str) -> None:
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            os.replace(temp_path, target_path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _tmp_path(path: str) -> str:
    return f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"


def _save_jsonl(path: str, records: list[dict]) -> None:
    """Atomic-ish write: write to a process-local temp file then rename with retries."""
    tmp = _tmp_path(path)
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    try:
        _atomic_replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _save_json(path: str, payload: dict) -> None:
    tmp = _tmp_path(path)
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    try:
        _atomic_replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _upsert(path: str, date_key: str, new_record: dict, lock: threading.Lock) -> None:
    """
    Insert-or-replace record by `date_key` field in a JSONL file.
    """
    with lock:
        records = _load_jsonl(path)
        date_val = new_record.get(date_key)
        replaced = False
        for i, r in enumerate(records):
            if r.get(date_key) == date_val:
                records[i] = new_record
                replaced = True
                break
        if not replaced:
            records.append(new_record)
        # Keep sorted by date
        records.sort(key=lambda r: r.get(date_key, ''))
        _save_jsonl(path, records)


def _append_or_replace(path: str, key_name: str, new_record: dict, lock: threading.Lock) -> None:
    """
    Append a JSONL record, replacing an older record with the same key when present.
    """
    with lock:
        records = _load_jsonl(path)
        key_value = new_record.get(key_name)
        replaced = False
        for index, record in enumerate(records):
            if record.get(key_name) == key_value:
                records[index] = new_record
                replaced = True
                break
        if not replaced:
            records.append(new_record)
        records.sort(key=lambda r: r.get(key_name, ''))
        _save_jsonl(path, records)


# ── Public class ─────────────────────────────────────────────────────────────

class VolHistoryStore:
    """
    Per-underlying persistence for vol index snapshots and price history.
    """

    def __init__(self, base_dir: str, underlying: str):
        self._underlying = underlying
        slug = _sanitize(underlying)
        self._dir = os.path.join(base_dir, slug)
        os.makedirs(self._dir, exist_ok=True)
        self._history_path = os.path.join(self._dir, 'history.jsonl')
        self._intraday_path = os.path.join(self._dir, 'intraday_history.jsonl')
        self._intraday_latest_path = os.path.join(self._dir, 'intraday_latest.json')
        self._price_path   = os.path.join(self._dir, 'price_history.jsonl')
        self._lock = _get_lock(f'vol_history:{underlying}')

    # ── Vol snapshots ────────────────────────────────────────────────────────

    def append_snapshot(self, record: dict) -> None:
        """Upsert a vol snapshot keyed by 'date'."""
        _upsert(self._history_path, 'date', record, self._lock)

    def load_history(self, days: int = 252) -> list[dict]:
        """Load up to `days` most-recent snapshots, sorted oldest→newest."""
        with self._lock:
            records = _load_jsonl(self._history_path)
        records.sort(key=lambda r: r.get('date', ''))
        return records[-days:] if days else records

    def has_date(self, date: str) -> bool:
        """Return True if a snapshot for `date` already exists."""
        with self._lock:
            records = _load_jsonl(self._history_path)
        return any(r.get('date') == date for r in records)

    def get_latest(self) -> Optional[dict]:
        h = self.load_history(1)
        return h[-1] if h else None

    def append_intraday_snapshot(self, record: dict) -> None:
        """Append an intraday snapshot with a fast path for strictly newer records."""
        captured_at = str(record.get('captured_at') or '').strip()
        if not captured_at:
            return

        with self._lock:
            latest_record: dict | None = None
            if os.path.exists(self._intraday_latest_path):
                try:
                    with open(self._intraday_latest_path, 'r', encoding='utf-8') as f:
                        payload = json.load(f)
                    if isinstance(payload, dict):
                        latest_record = payload
                except Exception:
                    logger.warning("Failed to read cached latest intraday snapshot", exc_info=True)

            latest_captured_at = str((latest_record or {}).get('captured_at') or '').strip()

            if latest_captured_at == captured_at:
                _save_json(self._intraday_latest_path, record)
                return

            # Common case: tracker keeps emitting newer points in chronological order.
            # Appending one line is much cheaper than loading/re-sorting the full JSONL.
            if not latest_captured_at or captured_at > latest_captured_at:
                with open(self._intraday_path, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + '\n')
                _save_json(self._intraday_latest_path, record)
                return

            # Fallback for rare out-of-order inserts/replacements.
            records = _load_jsonl(self._intraday_path)
            replaced = False
            for index, existing in enumerate(records):
                if str(existing.get('captured_at') or '').strip() == captured_at:
                    records[index] = record
                    replaced = True
                    break
            if not replaced:
                records.append(record)
            records.sort(key=lambda r: r.get('captured_at', ''))
            _save_jsonl(self._intraday_path, records)
            _save_json(self._intraday_latest_path, records[-1] if records else record)

    def load_intraday_history(self, days: int = 5) -> list[dict]:
        """
        Load intraday snapshots for the most recent `days` session dates.
        """
        with self._lock:
            records = _load_jsonl(self._intraday_path)
        records.sort(key=lambda r: r.get('captured_at', ''))
        if not days or not records:
            return records

        latest_dates: list[str] = []
        seen_dates: set[str] = set()
        for record in reversed(records):
            session_date = str(record.get('date') or '')[:10]
            if not session_date:
                session_date = str(record.get('captured_at') or '')[:10]
            if not session_date or session_date in seen_dates:
                continue
            seen_dates.add(session_date)
            latest_dates.append(session_date)
            if len(latest_dates) >= days:
                break

        allowed_dates = set(latest_dates)
        return [
            record
            for record in records
            if str(record.get('date') or record.get('captured_at') or '')[:10] in allowed_dates
        ]

    def load_latest_intraday(self) -> Optional[dict]:
        with self._lock:
            if os.path.exists(self._intraday_latest_path):
                try:
                    with open(self._intraday_latest_path, 'r', encoding='utf-8') as f:
                        payload = json.load(f)
                    if isinstance(payload, dict):
                        return payload
                except Exception:
                    logger.warning("Failed to read cached latest intraday snapshot", exc_info=True)
            records = _load_jsonl(self._intraday_path)
        records.sort(key=lambda r: r.get('captured_at', ''))
        return records[-1] if records else None

    # ── Price history ────────────────────────────────────────────────────────

    def append_price(self, date: str, close: float) -> None:
        """Upsert a daily close price keyed by 'date'."""
        record = {'date': date, 'close': round(float(close), 6)}
        _upsert(self._price_path, 'date', record, self._lock)

    def upsert_prices(self, records: list[dict]) -> None:
        for record in records:
            date = str(record.get('date') or '').strip()
            close = record.get('close')
            if not date or close is None:
                continue
            self.append_price(date, float(close))

    def load_prices(self, days: int = 756) -> list[dict]:
        """Load up to `days` most-recent close prices, sorted oldest→newest."""
        with self._lock:
            records = _load_jsonl(self._price_path)
        records.sort(key=lambda r: r.get('date', ''))
        return records[-days:] if days else records

    def get_log_returns(self, days: int = 756) -> tuple[list[str], list[float]]:
        """
        Compute daily log-returns from stored price history.

        Returns (dates, log_returns) where len(dates) == len(log_returns).
        """
        prices = self.load_prices(days + 1)
        if len(prices) < 2:
            return [], []

        dates = []
        rets  = []
        for i in range(1, len(prices)):
            p0 = prices[i - 1].get('close', 0)
            p1 = prices[i].get('close', 0)
            if p0 > 0 and p1 > 0:
                dates.append(prices[i]['date'])
                rets.append(float(np.log(p1 / p0)))
        return dates, rets

    def n_price_obs(self) -> int:
        with self._lock:
            return len(_load_jsonl(self._price_path))
