from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..config import Config
from ..utils.atomic_io import atomic_json_dump, atomic_text_write
from ..utils.logger import get_logger

logger = get_logger("mirofish.options_store")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _deep_copy_json(data: Any) -> Any:
    return json.loads(json.dumps(data, ensure_ascii=False))


def _normalize_trade_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


class OptionsStore:
    def __init__(self, root_dir: str | None = None):
        self.root_dir = root_dir or Config.OPTIONS_DATA_DIR
        self.contracts_dir = os.path.join(self.root_dir, "contracts")
        self.universe_dir = os.path.join(self.root_dir, "universe")
        self.snapshots_dir = os.path.join(self.root_dir, "snapshots")
        self.history_dir = os.path.join(self.root_dir, "history")
        self.jobs_dir = os.path.join(self.root_dir, "jobs")
        self.quality_dir = os.path.join(self.root_dir, "quality")
        self.ticks_dir = os.path.join(self.root_dir, "ticks")
        self.analytics_dir = os.path.join(self.root_dir, "analytics")
        self.model_runs_dir = os.path.join(self.analytics_dir, "runs")
        self.global_runs_dir = os.path.join(self.analytics_dir, "global_runs")
        self.fair_value_runs_dir = os.path.join(self.analytics_dir, "fair_value_runs")
        self.intraday_correlation_runs_dir = os.path.join(self.analytics_dir, "intraday_correlation_runs")
        self.regime_price_making_runs_dir = os.path.join(self.analytics_dir, "regime_price_making_runs")
        self.regime_price_making_tables_dir = os.path.join(self.analytics_dir, "regime_price_making_tables")
        self.daily_insights_dir = os.path.join(self.analytics_dir, "daily_insights")
        self.chat_threads_dir = os.path.join(self.analytics_dir, "chat_threads")
        # ─── Volume Activity Tracker ──────────────────────────────────────────
        self.volume_dir = os.path.join(self.root_dir, "volume")
        self.volume_state_path = os.path.join(self.volume_dir, "state.json")
        self.volume_activity_dir = os.path.join(self.volume_dir, "activity")
        self.volume_iv_history_dir = os.path.join(self.volume_dir, "iv_history")

        self.state_path = os.path.join(self.root_dir, "state.json")
        self.contracts_master_path = os.path.join(self.contracts_dir, "contracts_master.json")
        self.contracts_by_underlying_path = os.path.join(self.contracts_dir, "contracts_by_underlying.json")
        self.universe_state_path = os.path.join(self.universe_dir, "universe_state.json")
        self.universe_history_path = os.path.join(self.universe_dir, "universe_history.jsonl")
        self.batches_manifest_path = os.path.join(self.snapshots_dir, "batches_manifest.json")
        self.oi_daily_dir = os.path.join(self.history_dir, "oi_daily")
        self.oi_manifest_path = os.path.join(self.oi_daily_dir, "manifest.json")
        self.jobs_state_path = os.path.join(self.jobs_dir, "state.json")
        self.jobs_history_path = os.path.join(self.jobs_dir, "history.jsonl")
        self.backfill_checkpoints_path = os.path.join(self.jobs_dir, "backfill_checkpoints.json")
        self.scheduler_locks_db_path = os.path.join(self.jobs_dir, "scheduler_locks.sqlite3")
        self.quality_flags_path = os.path.join(self.quality_dir, "flags.jsonl")
        self.model_runs_manifest_path = os.path.join(self.analytics_dir, "model_runs_manifest.json")
        self.global_runs_manifest_path = os.path.join(self.analytics_dir, "global_runs_manifest.json")
        self.fair_value_runs_manifest_path = os.path.join(self.analytics_dir, "fair_value_runs_manifest.json")
        self.intraday_correlation_runs_manifest_path = os.path.join(self.analytics_dir, "intraday_correlation_runs_manifest.json")
        self.regime_price_making_runs_manifest_path = os.path.join(self.analytics_dir, "regime_price_making_runs_manifest.json")
        self._lock = threading.RLock()
        self._ensure_dirs()

    def _connect_scheduler_locks(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.scheduler_locks_db_path), exist_ok=True)
        conn = sqlite3.connect(self.scheduler_locks_db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_job_locks (
                checkpoint_key TEXT PRIMARY KEY,
                job_kind TEXT,
                trade_date TEXT,
                slot TEXT,
                underlying_security TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                complete INTEGER NOT NULL DEFAULT 0,
                owner TEXT,
                lease_until TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                completed_at TEXT,
                last_error TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_scheduled_job_locks_lookup
            ON scheduled_job_locks(job_kind, trade_date, slot, underlying_security)
            """
        )
        return conn

    def _ensure_dirs(self) -> None:
        for path in (
            self.root_dir,
            self.contracts_dir,
            self.universe_dir,
            self.snapshots_dir,
            self.history_dir,
            self.oi_daily_dir,
            self.jobs_dir,
            self.quality_dir,
            self.ticks_dir,
            self.analytics_dir,
            self.model_runs_dir,
            self.global_runs_dir,
            self.fair_value_runs_dir,
            self.intraday_correlation_runs_dir,
            self.regime_price_making_runs_dir,
            self.regime_price_making_tables_dir,
            self.daily_insights_dir,
            self.chat_threads_dir,
            self.volume_dir,
            self.volume_activity_dir,
            self.volume_iv_history_dir,
        ):
            os.makedirs(path, exist_ok=True)

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "updated_at": None,
            "collector": {
                "running": False,
                "desired_running": False,
                "auto_restart_enabled": Config.OPTIONS_INGEST_AUTO_RESTART,
                "supervisor_running": False,
                "restart_count": 0,
                "last_restart_at": None,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
                "last_structural_completed_at": None,
                "last_liquid_completed_at": None,
                "last_critical_completed_at": None,
                "last_history_update_at": None,
                "last_history_trade_date": None,
                "last_b3_snapshot_at": None,
                "last_b3_snapshot_trade_date": None,
                "last_b3_snapshot_rows_saved": 0,
                "last_scheduled_model_run_at": None,
                "last_scheduled_model_trade_date": None,
                "last_scheduled_model_slot": None,
                "last_scheduled_model_run_id": None,
                "run_count": 0,
                "stopped_reason": None,
            },
            "latest_batches": {},
            "underlyings": {},
        }

    @staticmethod
    def _default_contract_master() -> dict[str, Any]:
        return {
            "updated_at": None,
            "contract_count": 0,
            "contracts": {},
        }

    @staticmethod
    def _default_contracts_by_underlying() -> dict[str, Any]:
        return {
            "updated_at": None,
            "underlyings": {},
        }

    @staticmethod
    def _default_universe_state() -> dict[str, Any]:
        return {
            "updated_at": None,
            "underlyings": {},
        }

    @staticmethod
    def _default_batches_manifest() -> dict[str, Any]:
        return {
            "updated_at": None,
            "batches": {},
        }

    @staticmethod
    def _default_oi_manifest() -> dict[str, Any]:
        return {
            "updated_at": None,
            "dates": {},
            "options": {},
        }

    @staticmethod
    def _default_jobs_state() -> dict[str, Any]:
        return {
            "updated_at": None,
            "jobs": {},
        }

    @staticmethod
    def _default_model_runs_manifest() -> dict[str, Any]:
        return {
            "updated_at": None,
            "runs": {},
            "latest_by_underlying": {},
            "latest_by_underlying_tier": {},
        }

    @staticmethod
    def _default_backfill_checkpoints() -> dict[str, Any]:
        return {
            "updated_at": None,
            "jobs": {},
        }

    @staticmethod
    def _default_global_runs_manifest() -> dict[str, Any]:
        return {
            "updated_at": None,
            "latest_by_underlying": {},
            "runs": {},
        }

    @staticmethod
    def _default_fair_value_runs_manifest() -> dict[str, Any]:
        return {
            "updated_at": None,
            "latest_by_underlying": {},
            "runs": {},
        }

    @staticmethod
    def _default_intraday_correlation_runs_manifest() -> dict[str, Any]:
        return {
            "updated_at": None,
            "latest_by_selection": {},
            "runs": {},
        }

    @staticmethod
    def _default_regime_price_making_runs_manifest() -> dict[str, Any]:
        return {
            "updated_at": None,
            "latest_by_underlying": {},
            "runs": {},
        }

    def _load_json_unlocked(self, path: str, default_factory) -> dict[str, Any]:
        if not os.path.exists(path):
            return default_factory()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            logger.exception("Failed to load options store file: %s", path)
        return default_factory()

    def _save_json_unlocked(self, path: str, payload: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            atomic_json_dump(
                path,
                payload,
                ensure_ascii=False,
                indent=2,
                retries=30,
                retry_sleep=0.15,
            )
        except PermissionError as exc:
            logger.warning("Skipped options store write after retries for %s: %s", path, exc)

    def _load_jsonl_rows_unlocked(self, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not os.path.exists(path):
            return rows
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        item = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        rows.append(item)
        except Exception:
            logger.exception("Failed to read JSONL rows from %s", path)
        return rows

    def _write_jsonl_rows_unlocked(self, path: str, rows: list[dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        atomic_text_write(path, content)

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            return _deep_copy_json(self._load_json_unlocked(self.state_path, self._default_state))

    def update_collector_status(self, **fields: Any) -> dict[str, Any]:
        with self._lock:
            state = self._load_json_unlocked(self.state_path, self._default_state)
            state["collector"].update(fields)
            state["updated_at"] = _now_iso()
            self._save_json_unlocked(self.state_path, state)
            return _deep_copy_json(state["collector"])

    def _load_contract_master_unlocked(self) -> dict[str, Any]:
        return self._load_json_unlocked(self.contracts_master_path, self._default_contract_master)

    def _load_contracts_by_underlying_unlocked(self) -> dict[str, Any]:
        return self._load_json_unlocked(self.contracts_by_underlying_path, self._default_contracts_by_underlying)

    def upsert_contracts(self, contracts: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            master = self._load_contract_master_unlocked()
            grouped = self._load_contracts_by_underlying_unlocked()
            existing_contracts = master.get("contracts", {}) or {}
            underlyings = grouped.get("underlyings", {}) or {}
            inserted = 0
            updated = 0

            for contract in contracts:
                option_id = str(contract.get("option_id") or "").strip()
                if not option_id:
                    continue
                previous = existing_contracts.get(option_id)
                existing_contracts[option_id] = contract
                if previous is None:
                    inserted += 1
                else:
                    updated += 1

                underlying_security = str(contract.get("underlying_security") or "").strip()
                if underlying_security:
                    ids = set(underlyings.get(underlying_security, []))
                    ids.add(option_id)
                    underlyings[underlying_security] = sorted(ids)

            master["contracts"] = existing_contracts
            master["updated_at"] = _now_iso()
            master["contract_count"] = len(existing_contracts)
            grouped["underlyings"] = underlyings
            grouped["updated_at"] = _now_iso()

            self._save_json_unlocked(self.contracts_master_path, master)
            self._save_json_unlocked(self.contracts_by_underlying_path, grouped)
            return {
                "inserted": inserted,
                "updated": updated,
                "total": len(existing_contracts),
            }

    def list_contracts(
        self,
        underlying_security: str | None = None,
        only_active: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            master = self._load_contract_master_unlocked()
            contracts = list((master.get("contracts") or {}).values())
            if underlying_security:
                contracts = [
                    row for row in contracts
                    if row.get("underlying_security") == underlying_security
                ]
            if only_active:
                contracts = [row for row in contracts if row.get("status") == "active"]
            contracts.sort(
                key=lambda row: (
                    row.get("expiry_date") or "",
                    float(row.get("strike") or 0),
                    row.get("put_call") or "",
                )
            )
            if limit is not None:
                contracts = contracts[:limit]
            return _deep_copy_json(contracts)

    def save_universe_state(self, underlying_security: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_json_unlocked(self.universe_state_path, self._default_universe_state)
            state["underlyings"][underlying_security] = payload
            state["updated_at"] = _now_iso()
            self._save_json_unlocked(self.universe_state_path, state)

            with open(self.universe_history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "underlying_security": underlying_security,
                    "captured_at": payload.get("captured_at") or _now_iso(),
                    "session_date": payload.get("session_date"),
                    "summary": payload.get("summary") or {},
                    "version": payload.get("universe_version"),
                }, ensure_ascii=False) + "\n")

            return _deep_copy_json(payload)

    def load_universe_state(self, underlying_security: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._load_json_unlocked(self.universe_state_path, self._default_universe_state)
            if underlying_security:
                return _deep_copy_json(state.get("underlyings", {}).get(underlying_security, {}))
            return _deep_copy_json(state)

    def _snapshot_batch_path(self, universe_tier: str, session_date: str, batch_key: str) -> str:
        return os.path.join(self.snapshots_dir, universe_tier, session_date, f"{batch_key}.jsonl")

    def write_snapshot_batch(
        self,
        universe_tier: str,
        session_date: str,
        batch_key: str,
        rows: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        with self._lock:
            batch_path = self._snapshot_batch_path(universe_tier, session_date, batch_key)
            self._write_jsonl_rows_unlocked(batch_path, rows)

            manifest = self._load_json_unlocked(self.batches_manifest_path, self._default_batches_manifest)
            batch_id = str(metadata.get("batch_id") or batch_key)
            manifest_key = f"{universe_tier}::{session_date}::{batch_key}"
            captured_at = str(metadata.get("captured_at") or _now_iso())
            batch_payload = {
                "batch_id": batch_id,
                "batch_key": batch_key,
                "universe_tier": universe_tier,
                "session_date": session_date,
                "captured_at": captured_at,
                "row_count": len(rows),
                "path": batch_path,
                "underlying_security": metadata.get("underlying_security"),
                "underlying_trade_symbol": metadata.get("underlying_trade_symbol"),
            }
            manifest["batches"][manifest_key] = batch_payload
            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.batches_manifest_path, manifest)

            state = self._load_json_unlocked(self.state_path, self._default_state)
            latest_batches = state.get("latest_batches", {})
            latest_key = universe_tier
            existing = latest_batches.get(latest_key)
            if not existing or str(existing.get("captured_at") or "") <= captured_at:
                latest_batches[latest_key] = batch_payload
            state["latest_batches"] = latest_batches
            state["updated_at"] = _now_iso()
            self._save_json_unlocked(self.state_path, state)
            return _deep_copy_json(batch_payload)

    def read_latest_snapshot(
        self,
        universe_tier: str,
        underlying_security: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        with self._lock:
            manifest = self._load_json_unlocked(self.batches_manifest_path, self._default_batches_manifest)
            candidates = []
            for item in (manifest.get("batches") or {}).values():
                if item.get("universe_tier") != universe_tier:
                    continue
                if underlying_security and item.get("underlying_security") != underlying_security:
                    continue
                candidates.append(item)

            if not candidates:
                return {}

            candidates.sort(key=lambda row: row.get("captured_at") or "", reverse=True)
            latest = candidates[0]
            rows = self._load_jsonl_rows_unlocked(latest["path"])[:limit]
            return {
                "batch": _deep_copy_json(latest),
                "rows": rows,
            }

    def read_snapshot_batch(
        self,
        universe_tier: str,
        session_date: str,
        batch_key: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            path = self._snapshot_batch_path(universe_tier, session_date, batch_key)
            if not os.path.exists(path):
                return {}
            rows = self._load_jsonl_rows_unlocked(path)
            if limit is not None:
                rows = rows[:limit]
            manifest = self._load_json_unlocked(self.batches_manifest_path, self._default_batches_manifest)
            metadata = (manifest.get("batches") or {}).get(f"{universe_tier}::{session_date}::{batch_key}", {})
            return {
                "batch": _deep_copy_json(metadata),
                "rows": _deep_copy_json(rows),
            }

    def list_snapshot_batches(
        self,
        universe_tier: str | None = None,
        underlying_security: str | None = None,
        session_date: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock:
            manifest = self._load_json_unlocked(self.batches_manifest_path, self._default_batches_manifest)
            rows = list((manifest.get("batches") or {}).values())
            if universe_tier:
                rows = [row for row in rows if row.get("universe_tier") == universe_tier]
            if underlying_security:
                rows = [row for row in rows if row.get("underlying_security") == underlying_security]
            if session_date:
                rows = [row for row in rows if row.get("session_date") == session_date]
            rows.sort(key=lambda row: row.get("captured_at") or "", reverse=True)
            return _deep_copy_json(rows[:limit])

    def upsert_oi_daily_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            trade_date = _normalize_trade_date(row.get("trade_date"))
            if not trade_date:
                continue
            normalized = dict(row)
            normalized["trade_date"] = trade_date
            grouped_rows[trade_date].append(normalized)

        if not grouped_rows:
            return {"dates_written": 0, "rows_written": 0, "affected_option_ids": []}

        with self._lock:
            manifest = self._load_json_unlocked(self.oi_manifest_path, self._default_oi_manifest)
            affected_option_ids: set[str] = set()
            rows_written = 0

            for trade_date, date_rows in grouped_rows.items():
                date_path = os.path.join(self.oi_daily_dir, f"{trade_date}.jsonl")
                existing_rows = {
                    str(item.get("option_id")): item
                    for item in self._load_jsonl_rows_unlocked(date_path)
                    if item.get("option_id")
                }
                for row in date_rows:
                    option_id = str(row.get("option_id") or "").strip()
                    if not option_id:
                        continue
                    existing_rows[option_id] = row
                    affected_option_ids.add(option_id)

                ordered_rows = list(existing_rows.values())
                ordered_rows.sort(
                    key=lambda item: (
                        item.get("underlying_security") or "",
                        item.get("expiry_date") or "",
                        float(item.get("strike") or 0),
                        item.get("put_call") or "",
                    )
                )
                self._write_jsonl_rows_unlocked(date_path, ordered_rows)
                rows_written += len(date_rows)
                manifest["dates"][trade_date] = {
                    "path": date_path,
                    "row_count": len(ordered_rows),
                    "updated_at": _now_iso(),
                }

            for option_id in affected_option_ids:
                option_dates = set((manifest.get("options") or {}).get(option_id, {}).get("dates", []))
                for trade_date, date_rows in grouped_rows.items():
                    if any(str(row.get("option_id")) == option_id for row in date_rows):
                        option_dates.add(trade_date)
                sorted_dates = sorted(option_dates)
                manifest.setdefault("options", {})[option_id] = {
                    "dates": sorted_dates,
                    "latest_trade_date": sorted_dates[-1] if sorted_dates else None,
                    "updated_at": _now_iso(),
                }

            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.oi_manifest_path, manifest)
            return {
                "dates_written": len(grouped_rows),
                "rows_written": rows_written,
                "affected_option_ids": sorted(affected_option_ids),
            }

    def get_latest_oi_row_before(self, option_id: str, trade_date: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(self.oi_manifest_path, self._default_oi_manifest)
            option_info = (manifest.get("options") or {}).get(option_id) or {}
            dates = [date for date in option_info.get("dates", []) if date < trade_date]
            if not dates:
                return None
            latest_date = max(dates)
            date_path = os.path.join(self.oi_daily_dir, f"{latest_date}.jsonl")
            for row in self._load_jsonl_rows_unlocked(date_path):
                if str(row.get("option_id")) == option_id:
                    return row
            return None

    def get_latest_trade_date_for_option(self, option_id: str) -> str | None:
        with self._lock:
            manifest = self._load_json_unlocked(self.oi_manifest_path, self._default_oi_manifest)
            option_info = (manifest.get("options") or {}).get(option_id) or {}
            latest_trade_date = option_info.get("latest_trade_date")
            return str(latest_trade_date) if latest_trade_date else None

    def recompute_oi_changes(self, option_ids: list[str]) -> dict[str, Any]:
        option_ids = [str(option_id).strip() for option_id in option_ids if str(option_id).strip()]
        if not option_ids:
            return {"updated_rows": 0}

        with self._lock:
            manifest = self._load_json_unlocked(self.oi_manifest_path, self._default_oi_manifest)
            updated_dates: set[str] = set()
            rows_cache: dict[str, dict[str, dict[str, Any]]] = {}
            updated_rows = 0

            def load_date_rows(date_text: str) -> dict[str, dict[str, Any]]:
                if date_text not in rows_cache:
                    date_path = os.path.join(self.oi_daily_dir, f"{date_text}.jsonl")
                    rows_cache[date_text] = {
                        str(row.get("option_id")): row
                        for row in self._load_jsonl_rows_unlocked(date_path)
                        if row.get("option_id")
                    }
                return rows_cache[date_text]

            def oi_value(row: dict[str, Any]) -> float | None:
                for key in ("opt_open_interest", "open_int", "OPT_OPEN_INTEREST", "OPEN_INT"):
                    value = row.get(key)
                    if value in (None, ""):
                        continue
                    try:
                        return float(value)
                    except Exception:
                        continue
                return None

            for option_id in option_ids:
                option_info = (manifest.get("options") or {}).get(option_id) or {}
                dates = sorted(option_info.get("dates", []))
                previous_value: float | None = None
                for date_text in dates:
                    rows = load_date_rows(date_text)
                    row = rows.get(option_id)
                    if not row:
                        continue
                    current_value = oi_value(row)
                    if current_value is None:
                        row["oi_change_abs"] = None
                        row["oi_change_pct"] = None
                    elif previous_value in (None, 0):
                        row["oi_change_abs"] = None if previous_value is None else current_value - previous_value
                        row["oi_change_pct"] = None
                    else:
                        row["oi_change_abs"] = current_value - previous_value
                        row["oi_change_pct"] = (current_value - previous_value) / previous_value
                    if current_value is not None:
                        previous_value = current_value
                    updated_dates.add(date_text)
                    updated_rows += 1

            for date_text in updated_dates:
                date_path = os.path.join(self.oi_daily_dir, f"{date_text}.jsonl")
                rows = list(rows_cache.get(date_text, {}).values())
                rows.sort(
                    key=lambda item: (
                        item.get("underlying_security") or "",
                        item.get("expiry_date") or "",
                        float(item.get("strike") or 0),
                        item.get("put_call") or "",
                    )
                )
                self._write_jsonl_rows_unlocked(date_path, rows)
                if date_text in manifest.get("dates", {}):
                    manifest["dates"][date_text]["updated_at"] = _now_iso()

            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.oi_manifest_path, manifest)
            return {"updated_rows": updated_rows}

    def list_oi_history(
        self,
        underlying_security: str | None = None,
        option_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        with self._lock:
            manifest = self._load_json_unlocked(self.oi_manifest_path, self._default_oi_manifest)
            dates = sorted((manifest.get("dates") or {}).keys(), reverse=True)
            if start_date:
                start_date = _normalize_trade_date(start_date)
                dates = [date for date in dates if date >= start_date]
            if end_date:
                end_date = _normalize_trade_date(end_date)
                dates = [date for date in dates if date <= end_date]

            results: list[dict[str, Any]] = []
            for trade_date in dates:
                path = os.path.join(self.oi_daily_dir, f"{trade_date}.jsonl")
                for row in self._load_jsonl_rows_unlocked(path):
                    if option_id and str(row.get("option_id")) != option_id:
                        continue
                    if underlying_security and row.get("underlying_security") != underlying_security:
                        continue
                    results.append(row)
                    if len(results) >= limit:
                        return _deep_copy_json(results)
            return _deep_copy_json(results)

    def load_oi_rows_for_trade_date(
        self,
        trade_date: str,
        underlying_security: str | None = None,
    ) -> list[dict[str, Any]]:
        trade_date = _normalize_trade_date(trade_date)
        if not trade_date:
            return []

        with self._lock:
            path = os.path.join(self.oi_daily_dir, f"{trade_date}.jsonl")
            rows = self._load_jsonl_rows_unlocked(path)
            if underlying_security:
                rows = [row for row in rows if row.get("underlying_security") == underlying_security]
            return _deep_copy_json(rows)

    def load_latest_oi_map(
        self,
        option_ids: list[str],
        trade_date: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        normalized_ids = {str(option_id).strip() for option_id in option_ids if str(option_id).strip()}
        if not normalized_ids:
            return {}

        cutoff = _normalize_trade_date(trade_date) if trade_date else None
        with self._lock:
            manifest = self._load_json_unlocked(self.oi_manifest_path, self._default_oi_manifest)
            results: dict[str, dict[str, Any]] = {}
            for option_id in normalized_ids:
                option_info = (manifest.get("options") or {}).get(option_id) or {}
                dates = sorted(option_info.get("dates", []), reverse=True)
                if cutoff:
                    dates = [date for date in dates if date <= cutoff]
                for date_text in dates:
                    path = os.path.join(self.oi_daily_dir, f"{date_text}.jsonl")
                    for row in self._load_jsonl_rows_unlocked(path):
                        if str(row.get("option_id")) == option_id:
                            results[option_id] = row
                            break
                    if option_id in results:
                        break
            return _deep_copy_json(results)

    def record_job_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise ValueError("job_id is required")

        with self._lock:
            state = self._load_json_unlocked(self.jobs_state_path, self._default_jobs_state)
            state.setdefault("jobs", {})[job_id] = payload
            state["updated_at"] = _now_iso()
            self._save_json_unlocked(self.jobs_state_path, state)

            with open(self.jobs_history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return _deep_copy_json(payload)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._load_json_unlocked(self.jobs_state_path, self._default_jobs_state)
            job = (state.get("jobs") or {}).get(job_id)
            return _deep_copy_json(job) if job else None

    @staticmethod
    def _scheduled_lock_row_to_payload(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        payload = {
            "checkpoint_key": row["checkpoint_key"],
            "job_kind": row["job_kind"],
            "trade_date": row["trade_date"],
            "slot": row["slot"],
            "underlying_security": row["underlying_security"],
            "status": row["status"],
            "complete": bool(row["complete"]),
            "owner": row["owner"],
            "lease_until": row["lease_until"],
            "attempts": int(row["attempts"] or 0),
            "last_attempt_at": row["last_attempt_at"],
            "completed_at": row["completed_at"],
            "last_error": row["last_error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        details_json = row["details_json"]
        if details_json:
            try:
                payload["details"] = json.loads(details_json)
            except Exception:
                payload["details"] = {}
        return payload

    def load_scheduled_checkpoint(self, checkpoint_key: str) -> dict[str, Any]:
        checkpoint_key = str(checkpoint_key or "").strip()
        if not checkpoint_key:
            return {}
        with self._lock:
            with closing(self._connect_scheduler_locks()) as conn:
                row = conn.execute(
                    "SELECT * FROM scheduled_job_locks WHERE checkpoint_key = ?",
                    (checkpoint_key,),
                ).fetchone()
                if row is not None:
                    return _deep_copy_json(self._scheduled_lock_row_to_payload(row))

            legacy = self.load_backfill_checkpoint(checkpoint_key)
            if legacy:
                self.save_scheduled_checkpoint(checkpoint_key, legacy)
            return legacy

    def try_acquire_scheduled_checkpoint(
        self,
        checkpoint_key: str,
        metadata: dict[str, Any],
        *,
        owner: str,
        lease_seconds: int,
    ) -> dict[str, Any]:
        checkpoint_key = str(checkpoint_key or "").strip()
        if not checkpoint_key:
            raise ValueError("checkpoint_key is required")
        metadata = dict(metadata or {})
        owner = str(owner or "").strip() or "unknown"
        now = _utc_now()
        now_iso = now.isoformat()
        lease_until = (now + timedelta(seconds=max(60, int(lease_seconds or 60)))).isoformat()

        with self._lock:
            with closing(self._connect_scheduler_locks()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM scheduled_job_locks WHERE checkpoint_key = ?",
                    (checkpoint_key,),
                ).fetchone()
                checkpoint = self._scheduled_lock_row_to_payload(row)
                if checkpoint.get("complete"):
                    conn.rollback()
                    return {"acquired": False, "reason": "complete", "checkpoint": _deep_copy_json(checkpoint)}

                locked_until = _parse_iso(checkpoint.get("lease_until"))
                if checkpoint.get("status") == "running" and locked_until and locked_until > now:
                    conn.rollback()
                    return {"acquired": False, "reason": "locked", "checkpoint": _deep_copy_json(checkpoint)}

                attempts = int(checkpoint.get("attempts") or 0) + 1
                details_json = json.dumps(metadata.get("details") or {}, ensure_ascii=False)
                values = {
                    "checkpoint_key": checkpoint_key,
                    "job_kind": metadata.get("job_kind"),
                    "trade_date": metadata.get("trade_date"),
                    "slot": metadata.get("slot"),
                    "underlying_security": metadata.get("underlying_security"),
                    "status": "running",
                    "complete": 0,
                    "owner": owner,
                    "lease_until": lease_until,
                    "attempts": attempts,
                    "last_attempt_at": now_iso,
                    "completed_at": None,
                    "last_error": None,
                    "details_json": details_json,
                    "created_at": checkpoint.get("created_at") or now_iso,
                    "updated_at": now_iso,
                }
                conn.execute(
                    """
                    INSERT INTO scheduled_job_locks (
                        checkpoint_key, job_kind, trade_date, slot, underlying_security,
                        status, complete, owner, lease_until, attempts, last_attempt_at,
                        completed_at, last_error, details_json, created_at, updated_at
                    ) VALUES (
                        :checkpoint_key, :job_kind, :trade_date, :slot, :underlying_security,
                        :status, :complete, :owner, :lease_until, :attempts, :last_attempt_at,
                        :completed_at, :last_error, :details_json, :created_at, :updated_at
                    )
                    ON CONFLICT(checkpoint_key) DO UPDATE SET
                        job_kind = excluded.job_kind,
                        trade_date = excluded.trade_date,
                        slot = excluded.slot,
                        underlying_security = excluded.underlying_security,
                        status = excluded.status,
                        complete = excluded.complete,
                        owner = excluded.owner,
                        lease_until = excluded.lease_until,
                        attempts = excluded.attempts,
                        last_attempt_at = excluded.last_attempt_at,
                        completed_at = excluded.completed_at,
                        last_error = excluded.last_error,
                        details_json = excluded.details_json,
                        updated_at = excluded.updated_at
                    """,
                    values,
                )
                conn.commit()
                acquired = self.load_scheduled_checkpoint(checkpoint_key)
                return {"acquired": True, "reason": "acquired", "checkpoint": acquired}

    def save_scheduled_checkpoint(self, checkpoint_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        checkpoint_key = str(checkpoint_key or "").strip()
        if not checkpoint_key:
            raise ValueError("checkpoint_key is required")
        payload = dict(payload or {})
        now_iso = _now_iso()
        complete = bool(payload.get("complete"))
        status = "completed" if complete else "failed" if payload.get("last_error") else str(payload.get("status") or "pending")
        details_json = json.dumps(payload.get("details") or {}, ensure_ascii=False)

        with self._lock:
            with closing(self._connect_scheduler_locks()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT * FROM scheduled_job_locks WHERE checkpoint_key = ?",
                    (checkpoint_key,),
                ).fetchone()
                existing_payload = self._scheduled_lock_row_to_payload(existing)
                values = {
                    "checkpoint_key": checkpoint_key,
                    "job_kind": payload.get("job_kind") or existing_payload.get("job_kind"),
                    "trade_date": payload.get("trade_date") or existing_payload.get("trade_date"),
                    "slot": payload.get("slot") or existing_payload.get("slot"),
                    "underlying_security": payload.get("underlying_security") or existing_payload.get("underlying_security"),
                    "status": status,
                    "complete": 1 if complete else 0,
                    "owner": payload.get("owner") or existing_payload.get("owner"),
                    "lease_until": None,
                    "attempts": int(existing_payload.get("attempts") or payload.get("attempts") or 0),
                    "last_attempt_at": payload.get("last_attempt_at") or existing_payload.get("last_attempt_at") or now_iso,
                    "completed_at": payload.get("completed_at") or (now_iso if complete else None),
                    "last_error": payload.get("last_error"),
                    "details_json": details_json,
                    "created_at": existing_payload.get("created_at") or now_iso,
                    "updated_at": now_iso,
                }
                conn.execute(
                    """
                    INSERT INTO scheduled_job_locks (
                        checkpoint_key, job_kind, trade_date, slot, underlying_security,
                        status, complete, owner, lease_until, attempts, last_attempt_at,
                        completed_at, last_error, details_json, created_at, updated_at
                    ) VALUES (
                        :checkpoint_key, :job_kind, :trade_date, :slot, :underlying_security,
                        :status, :complete, :owner, :lease_until, :attempts, :last_attempt_at,
                        :completed_at, :last_error, :details_json, :created_at, :updated_at
                    )
                    ON CONFLICT(checkpoint_key) DO UPDATE SET
                        job_kind = excluded.job_kind,
                        trade_date = excluded.trade_date,
                        slot = excluded.slot,
                        underlying_security = excluded.underlying_security,
                        status = excluded.status,
                        complete = excluded.complete,
                        owner = excluded.owner,
                        lease_until = excluded.lease_until,
                        attempts = excluded.attempts,
                        last_attempt_at = excluded.last_attempt_at,
                        completed_at = excluded.completed_at,
                        last_error = excluded.last_error,
                        details_json = excluded.details_json,
                        updated_at = excluded.updated_at
                    """,
                    values,
                )
                conn.commit()

            saved = self.load_scheduled_checkpoint(checkpoint_key)
            self.save_backfill_checkpoint(checkpoint_key, saved)
            return _deep_copy_json(saved)

    def save_backfill_checkpoint(self, checkpoint_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            checkpoints = self._load_json_unlocked(
                self.backfill_checkpoints_path,
                self._default_backfill_checkpoints,
            )
            checkpoints.setdefault("jobs", {})[checkpoint_key] = payload
            checkpoints["updated_at"] = _now_iso()
            self._save_json_unlocked(self.backfill_checkpoints_path, checkpoints)
            return _deep_copy_json(payload)

    def load_backfill_checkpoint(self, checkpoint_key: str) -> dict[str, Any]:
        with self._lock:
            checkpoints = self._load_json_unlocked(
                self.backfill_checkpoints_path,
                self._default_backfill_checkpoints,
            )
            return _deep_copy_json((checkpoints.get("jobs") or {}).get(checkpoint_key, {}))

    # ─── B3 Open Interest (scraping diario) ─────────────────────────────

    def save_b3_oi_rows(
        self,
        trade_date: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Persiste as posicoes em aberto da B3 para uma data.
        Salva em:  oi_daily/{YYYY-MM-DD}/b3_oi.jsonl   (append-safe, idempotente)
        E atualiza o manifest: oi_daily/manifest.json

        Retorna dict com rows_written e caminho do arquivo.
        """
        if not rows:
            return {"rows_written": 0, "trade_date": trade_date}

        trade_date = _normalize_trade_date(trade_date)
        date_dir = os.path.join(self.oi_daily_dir, trade_date)

        with self._lock:
            os.makedirs(date_dir, exist_ok=True)
            b3_path = os.path.join(date_dir, "b3_oi.jsonl")

            # Idempotencia: apaga arquivo existente antes de re-escrever
            if os.path.exists(b3_path):
                os.remove(b3_path)

            with open(b3_path, "w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

            # Atualiza manifest
            manifest = self._load_json_unlocked(
                self.oi_manifest_path,
                lambda: {"dates": {}, "updated_at": None},
            )
            manifest.setdefault("dates", {})[trade_date] = {
                "b3_row_count": len(rows),
                "b3_saved_at": _now_iso(),
                "b3_path": b3_path,
            }
            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.oi_manifest_path, manifest)

        return {
            "rows_written": len(rows),
            "trade_date": trade_date,
            "path": b3_path,
        }

    def load_b3_oi_rows(self, trade_date: str) -> list[dict[str, Any]]:
        """
        Carrega as posicoes em aberto B3 para uma data.
        Retorna lista vazia se nao houver dados.
        """
        trade_date = _normalize_trade_date(trade_date)
        b3_path = os.path.join(self.oi_daily_dir, trade_date, "b3_oi.jsonl")
        if not os.path.exists(b3_path):
            return []
        rows = []
        with self._lock:
            with open(b3_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return rows

    def get_b3_oi_for_symbol(
        self,
        symbol: str,
        trade_date: str,
    ) -> dict[str, Any] | None:
        """
        Retorna o registro de OI para um simbolo e data especificos.
        Exemplo: symbol='IBOVF178', trade_date='2026-05-14'
        """
        rows = self.load_b3_oi_rows(trade_date)
        for row in rows:
            if row.get("symbol") == symbol:
                return _deep_copy_json(row)
        return None

    def list_b3_oi_dates(self) -> list[str]:
        """Lista todas as datas que tem dados de OI B3 salvos."""
        manifest = {}
        with self._lock:
            manifest = self._load_json_unlocked(
                self.oi_manifest_path,
                lambda: {"dates": {}, "updated_at": None},
            )
        dates = [
            d for d, v in (manifest.get("dates") or {}).items()
            if v.get("b3_row_count", 0) > 0
        ]
        return sorted(dates)

    def append_quality_flags(self, flags: list[dict[str, Any]]) -> int:
        if not flags:
            return 0
        with self._lock:
            with open(self.quality_flags_path, "a", encoding="utf-8") as f:
                for flag in flags:
                    f.write(json.dumps(flag, ensure_ascii=False) + "\n")
        return len(flags)

    def write_tick_rows(
        self,
        option_id: str,
        trade_date: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        trade_date = _normalize_trade_date(trade_date)
        if not option_id or not trade_date or not rows:
            return {"rows_written": 0}

        with self._lock:
            date_dir = os.path.join(self.ticks_dir, trade_date)
            os.makedirs(date_dir, exist_ok=True)
            path = os.path.join(date_dir, f"{option_id}.jsonl")
            existing_rows = self._load_jsonl_rows_unlocked(path)
            existing_keys = {
                (
                    row.get("event_time"),
                    row.get("price"),
                    row.get("size"),
                    row.get("condition_code"),
                )
                for row in existing_rows
            }
            for row in rows:
                key = (
                    row.get("event_time"),
                    row.get("price"),
                    row.get("size"),
                    row.get("condition_code"),
                )
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                existing_rows.append(row)
            existing_rows.sort(key=lambda item: item.get("event_time") or "")
            self._write_jsonl_rows_unlocked(path, existing_rows)
            return {
                "rows_written": len(rows),
                "path": path,
            }

    def _model_run_path(self, run_id: str, session_date: str) -> str:
        return os.path.join(self.model_runs_dir, session_date, f"{run_id}.json")

    def _global_run_path(self, run_id: str, session_date: str) -> str:
        return os.path.join(self.global_runs_dir, session_date, f"{run_id}.json")

    def _fair_value_run_path(self, run_id: str, session_date: str) -> str:
        return os.path.join(self.fair_value_runs_dir, session_date, f"{run_id}.json")

    def _intraday_correlation_run_path(self, run_id: str, session_date: str) -> str:
        return os.path.join(self.intraday_correlation_runs_dir, session_date, f"{run_id}.json")

    def _regime_price_making_run_path(self, run_id: str, session_date: str) -> str:
        return os.path.join(self.regime_price_making_runs_dir, session_date, f"{run_id}.json")

    def _regime_price_making_table_path(self, table_name: str, session_date: str) -> str:
        return os.path.join(self.regime_price_making_tables_dir, table_name, f"{session_date}.jsonl")

    def _daily_insight_path(self, underlying_security: str, trade_date: str, sign_convention: str) -> str:
        safe_underlying = re.sub(r"[^A-Za-z0-9_.-]+", "_", underlying_security.strip() or "underlying")
        safe_sign = re.sub(r"[^A-Za-z0-9_.-]+", "_", sign_convention.strip() or "neutral")
        return os.path.join(self.daily_insights_dir, trade_date, f"{safe_underlying}__{safe_sign}.json")

    def _chat_thread_path(self, underlying_security: str, trade_date: str, sign_convention: str) -> str:
        safe_underlying = re.sub(r"[^A-Za-z0-9_.-]+", "_", underlying_security.strip() or "underlying")
        safe_sign = re.sub(r"[^A-Za-z0-9_.-]+", "_", sign_convention.strip() or "neutral")
        return os.path.join(self.chat_threads_dir, trade_date, f"{safe_underlying}__{safe_sign}.json")

    @staticmethod
    def _intraday_correlation_selection_key(
        underlying_security: str,
        lookback_days: int,
        horizon_minutes: int,
        factors_signature: str,
        modes_signature: str,
    ) -> str:
        safe_underlying = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(underlying_security or "").strip() or "underlying")
        safe_factors = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(factors_signature or "").strip() or "__default__")
        safe_modes = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(modes_signature or "").strip() or "pure__neural")
        return f"{safe_underlying}__d{int(lookback_days)}__h{int(horizon_minutes)}__{safe_factors}__{safe_modes}"

    def write_model_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")

        session_date = _normalize_trade_date(payload.get("session_date") or payload.get("captured_at"))
        if not session_date:
            session_date = _utc_now().date().isoformat()

        with self._lock:
            path = self._model_run_path(run_id, session_date)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._save_json_unlocked(path, payload)

            manifest = self._load_json_unlocked(self.model_runs_manifest_path, self._default_model_runs_manifest)
            run_entry = {
                "run_id": run_id,
                "session_date": session_date,
                "captured_at": payload.get("captured_at") or _now_iso(),
                "underlying_security": payload.get("underlying_security"),
                "source_universe_tier": payload.get("source", {}).get("universe_tier"),
                "source_batch_key": payload.get("source", {}).get("batch_key"),
                "path": path,
                "summary": payload.get("summary") or {},
            }
            manifest.setdefault("runs", {})[run_id] = run_entry
            underlying_security = str(payload.get("underlying_security") or "").strip()
            source_universe_tier = str(payload.get("source", {}).get("universe_tier") or "").strip().lower()
            if underlying_security:
                latest = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
                if not latest or str(latest.get("captured_at") or "") <= str(run_entry.get("captured_at") or ""):
                    manifest.setdefault("latest_by_underlying", {})[underlying_security] = run_entry
                if source_universe_tier:
                    tier_map = manifest.setdefault("latest_by_underlying_tier", {}).setdefault(underlying_security, {})
                    latest_tier = tier_map.get(source_universe_tier)
                    if not latest_tier or str(latest_tier.get("captured_at") or "") <= str(run_entry.get("captured_at") or ""):
                        tier_map[source_universe_tier] = run_entry
            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.model_runs_manifest_path, manifest)
            return _deep_copy_json(run_entry)

    def read_model_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(self.model_runs_manifest_path, self._default_model_runs_manifest)
            run_entry = (manifest.get("runs") or {}).get(run_id)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def read_latest_model_run(
        self,
        underlying_security: str,
        universe_tier: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(self.model_runs_manifest_path, self._default_model_runs_manifest)
            run_entry = None
            normalized_tier = str(universe_tier or "").strip().lower()
            if normalized_tier:
                run_entry = (
                    ((manifest.get("latest_by_underlying_tier") or {}).get(underlying_security) or {}).get(normalized_tier)
                )
                if not run_entry:
                    matching_runs = [
                        entry for entry in (manifest.get("runs") or {}).values()
                        if str(entry.get("underlying_security") or "").strip() == str(underlying_security or "").strip()
                        and str(entry.get("source_universe_tier") or "").strip().lower() == normalized_tier
                    ]
                    if matching_runs:
                        run_entry = max(matching_runs, key=lambda item: str(item.get("captured_at") or ""))
            if not run_entry:
                run_entry = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def write_global_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")

        session_date = _normalize_trade_date(payload.get("session_date") or payload.get("captured_at"))
        if not session_date:
            session_date = _utc_now().date().isoformat()

        with self._lock:
            path = self._global_run_path(run_id, session_date)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._save_json_unlocked(path, payload)

            manifest = self._load_json_unlocked(self.global_runs_manifest_path, self._default_global_runs_manifest)
            run_entry = {
                "run_id": run_id,
                "session_date": session_date,
                "captured_at": payload.get("captured_at") or _now_iso(),
                "underlying_security": payload.get("underlying_security"),
                "path": path,
                "summary": payload.get("summary") or {},
            }
            manifest.setdefault("runs", {})[run_id] = run_entry
            underlying_security = str(payload.get("underlying_security") or "").strip()
            if underlying_security:
                latest = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
                if not latest or str(latest.get("captured_at") or "") <= str(run_entry.get("captured_at") or ""):
                    manifest.setdefault("latest_by_underlying", {})[underlying_security] = run_entry
            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.global_runs_manifest_path, manifest)
            return _deep_copy_json(run_entry)

    def read_global_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(self.global_runs_manifest_path, self._default_global_runs_manifest)
            run_entry = (manifest.get("runs") or {}).get(run_id)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def read_latest_global_run(self, underlying_security: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(self.global_runs_manifest_path, self._default_global_runs_manifest)
            run_entry = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def write_fair_value_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")

        session_date = _normalize_trade_date(payload.get("session_date") or payload.get("captured_at"))
        if not session_date:
            session_date = _utc_now().date().isoformat()

        with self._lock:
            path = self._fair_value_run_path(run_id, session_date)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._save_json_unlocked(path, payload)

            manifest = self._load_json_unlocked(
                self.fair_value_runs_manifest_path,
                self._default_fair_value_runs_manifest,
            )
            run_entry = {
                "run_id": run_id,
                "session_date": session_date,
                "captured_at": payload.get("captured_at") or _now_iso(),
                "underlying_security": payload.get("underlying_security"),
                "path": path,
                "summary": payload.get("summary") or {},
            }
            manifest.setdefault("runs", {})[run_id] = run_entry
            underlying_security = str(payload.get("underlying_security") or "").strip()
            if underlying_security:
                latest = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
                if not latest or str(latest.get("captured_at") or "") <= str(run_entry.get("captured_at") or ""):
                    manifest.setdefault("latest_by_underlying", {})[underlying_security] = run_entry
            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.fair_value_runs_manifest_path, manifest)
            return _deep_copy_json(run_entry)

    def read_fair_value_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(
                self.fair_value_runs_manifest_path,
                self._default_fair_value_runs_manifest,
            )
            run_entry = (manifest.get("runs") or {}).get(run_id)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def read_latest_fair_value_run(self, underlying_security: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(
                self.fair_value_runs_manifest_path,
                self._default_fair_value_runs_manifest,
            )
            run_entry = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def write_intraday_correlation_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")

        session_date = _normalize_trade_date(payload.get("session_date") or payload.get("captured_at"))
        if not session_date:
            session_date = _utc_now().date().isoformat()

        lookback_days = int(payload.get("lookback_days") or 1)
        horizon_minutes = int(payload.get("horizon_minutes") or 5)
        factors_signature = str(payload.get("factors_signature") or "__default__").strip() or "__default__"
        modes_signature = str(payload.get("modes_signature") or "pure__neural").strip() or "pure__neural"
        selection_key = self._intraday_correlation_selection_key(
            str(payload.get("underlying_security") or ""),
            lookback_days,
            horizon_minutes,
            factors_signature,
            modes_signature,
        )

        with self._lock:
            path = self._intraday_correlation_run_path(run_id, session_date)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._save_json_unlocked(path, payload)

            manifest = self._load_json_unlocked(
                self.intraday_correlation_runs_manifest_path,
                self._default_intraday_correlation_runs_manifest,
            )
            run_entry = {
                "run_id": run_id,
                "session_date": session_date,
                "captured_at": payload.get("captured_at") or _now_iso(),
                "underlying_security": payload.get("underlying_security"),
                "lookback_days": lookback_days,
                "horizon_minutes": horizon_minutes,
                "factors_signature": factors_signature,
                "modes_signature": modes_signature,
                "selection_key": selection_key,
                "path": path,
                "summary": {
                    "status": payload.get("status"),
                    "selected_sessions": payload.get("selected_sessions") or [],
                    "row_count": payload.get("row_count"),
                    "selected_factors": payload.get("selected_factors") or [],
                },
            }
            manifest.setdefault("runs", {})[run_id] = run_entry
            latest = (manifest.get("latest_by_selection") or {}).get(selection_key)
            if not latest or str(latest.get("captured_at") or "") <= str(run_entry.get("captured_at") or ""):
                manifest.setdefault("latest_by_selection", {})[selection_key] = run_entry
            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.intraday_correlation_runs_manifest_path, manifest)
            return _deep_copy_json(run_entry)

    def read_latest_intraday_correlation_run(
        self,
        underlying_security: str,
        lookback_days: int,
        horizon_minutes: int,
        factors_signature: str,
        modes_signature: str,
    ) -> dict[str, Any] | None:
        selection_key = self._intraday_correlation_selection_key(
            underlying_security,
            lookback_days,
            horizon_minutes,
            factors_signature,
            modes_signature,
        )
        with self._lock:
            manifest = self._load_json_unlocked(
                self.intraday_correlation_runs_manifest_path,
                self._default_intraday_correlation_runs_manifest,
            )
            run_entry = (manifest.get("latest_by_selection") or {}).get(selection_key)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def list_recent_fair_value_runs(
        self,
        underlying_security: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        with self._lock:
            manifest = self._load_json_unlocked(
                self.fair_value_runs_manifest_path,
                self._default_fair_value_runs_manifest,
            )
            entries = [
                dict(entry or {})
                for entry in (manifest.get("runs") or {}).values()
                if str((entry or {}).get("underlying_security") or "").strip() == underlying_security
            ]
            entries.sort(key=lambda item: str(item.get("captured_at") or ""), reverse=True)
            payloads: list[dict[str, Any]] = []
            for entry in entries[:limit]:
                path = str(entry.get("path") or "")
                if not path or not os.path.exists(path):
                    continue
                payloads.append(_deep_copy_json(self._load_json_unlocked(path, dict)))
            payloads.sort(key=lambda item: str(item.get("captured_at") or ""))
            return payloads

    def write_regime_price_making_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")

        session_date = _normalize_trade_date(payload.get("session_date") or payload.get("captured_at"))
        if not session_date:
            session_date = _utc_now().date().isoformat()

        with self._lock:
            path = self._regime_price_making_run_path(run_id, session_date)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._save_json_unlocked(path, payload)

            manifest = self._load_json_unlocked(
                self.regime_price_making_runs_manifest_path,
                self._default_regime_price_making_runs_manifest,
            )
            run_entry = {
                "run_id": run_id,
                "session_date": session_date,
                "captured_at": payload.get("captured_at") or _now_iso(),
                "underlying_security": payload.get("underlying_security"),
                "path": path,
                "summary": payload.get("summary") or {},
            }
            manifest.setdefault("runs", {})[run_id] = run_entry
            underlying_security = str(payload.get("underlying_security") or "").strip()
            if underlying_security:
                latest = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
                if not latest or str(latest.get("captured_at") or "") <= str(run_entry.get("captured_at") or ""):
                    manifest.setdefault("latest_by_underlying", {})[underlying_security] = run_entry
            manifest["updated_at"] = _now_iso()
            self._save_json_unlocked(self.regime_price_making_runs_manifest_path, manifest)
            return _deep_copy_json(run_entry)

    def read_regime_price_making_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(
                self.regime_price_making_runs_manifest_path,
                self._default_regime_price_making_runs_manifest,
            )
            run_entry = (manifest.get("runs") or {}).get(run_id)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def read_latest_regime_price_making_run(self, underlying_security: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._load_json_unlocked(
                self.regime_price_making_runs_manifest_path,
                self._default_regime_price_making_runs_manifest,
            )
            run_entry = (manifest.get("latest_by_underlying") or {}).get(underlying_security)
            if not run_entry:
                return None
            path = str(run_entry.get("path") or "")
            if not path or not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def append_regime_price_making_snapshots(
        self,
        *,
        session_date: str,
        asset_rows: list[dict[str, Any]],
        leg_rows: list[dict[str, Any]],
        market_state_row: dict[str, Any],
        regime_row: dict[str, Any],
    ) -> dict[str, Any]:
        session_date = _normalize_trade_date(session_date)
        if not session_date:
            session_date = _utc_now().date().isoformat()
        with self._lock:
            counts = {}
            mapping = {
                "asset_regime_snapshots": list(asset_rows or []),
                "leg_price_making_snapshots": list(leg_rows or []),
                "market_state_snapshots": [dict(market_state_row or {})] if market_state_row else [],
                "regime_snapshots": [dict(regime_row or {})] if regime_row else [],
            }
            for table_name, rows in mapping.items():
                if not rows:
                    counts[table_name] = 0
                    continue
                path = self._regime_price_making_table_path(table_name, session_date)
                existing = self._load_jsonl_rows_unlocked(path)
                existing.extend(rows)
                self._write_jsonl_rows_unlocked(path, existing)
                counts[table_name] = len(rows)
            return counts

    def write_daily_insight(
        self,
        underlying_security: str,
        trade_date: str,
        sign_convention: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        trade_date = _normalize_trade_date(trade_date)
        if not trade_date:
            raise ValueError("trade_date is required")
        with self._lock:
            path = self._daily_insight_path(underlying_security, trade_date, sign_convention)
            self._save_json_unlocked(path, payload)
            return _deep_copy_json(payload)

    def read_daily_insight(
        self,
        underlying_security: str,
        trade_date: str,
        sign_convention: str,
    ) -> dict[str, Any] | None:
        trade_date = _normalize_trade_date(trade_date)
        if not trade_date:
            return None
        with self._lock:
            path = self._daily_insight_path(underlying_security, trade_date, sign_convention)
            if not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    def write_chat_thread(
        self,
        underlying_security: str,
        trade_date: str,
        sign_convention: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        trade_date = _normalize_trade_date(trade_date)
        if not trade_date:
            raise ValueError("trade_date is required")
        with self._lock:
            path = self._chat_thread_path(underlying_security, trade_date, sign_convention)
            self._save_json_unlocked(path, payload)
            return _deep_copy_json(payload)

    def read_chat_thread(
        self,
        underlying_security: str,
        trade_date: str,
        sign_convention: str,
    ) -> dict[str, Any] | None:
        trade_date = _normalize_trade_date(trade_date)
        if not trade_date:
            return None
        with self._lock:
            path = self._chat_thread_path(underlying_security, trade_date, sign_convention)
            if not os.path.exists(path):
                return None
            return _deep_copy_json(self._load_json_unlocked(path, dict))

    # ─────────────────────────────────────────────────────────────────────────
    # Volume Activity Tracker
    # Rastreia variação de volume em TODAS as opções da cadeia.
    # ─────────────────────────────────────────────────────────────────────────

    def load_volume_state(self) -> dict[str, float]:
        """Retorna o último volume conhecido por símbolo: {symbol: volume}."""
        with self._lock:
            data = self._load_json_unlocked(
                self.volume_state_path,
                lambda: {"volumes": {}, "updated_at": None},
            )
            raw = data.get("volumes") or {}
            return {str(k): float(v) for k, v in raw.items()}

    def save_volume_state(self, volumes: dict[str, float]) -> None:
        """Persiste atomicamente o estado de volume (último volume visto por símbolo)."""
        with self._lock:
            self._save_json_unlocked(
                self.volume_state_path,
                {
                    "updated_at": _now_iso(),
                    "count": len(volumes),
                    "volumes": {str(k): float(v) for k, v in volumes.items()},
                },
            )

    def append_volume_activity(self, events: list[dict[str, Any]]) -> int:
        """
        Acrescenta eventos de variação de volume ao JSONL diário.
        Cada evento representa uma opção cujo volume aumentou desde a última poll.
        Retorna o número de eventos gravados.
        """
        if not events:
            return 0
        with self._lock:
            by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for ev in events:
                date = str(ev.get("session_date") or str(ev.get("captured_at", ""))[:10])
                if date:
                    by_date[date].append(ev)
            total = 0
            for date, rows in by_date.items():
                path = os.path.join(self.volume_activity_dir, f"{date}.jsonl")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    for row in rows:
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                total += len(rows)
            return total

    def read_volume_activity(
        self,
        session_date: str | None = None,
        symbol: str | None = None,
        underlying_security: str | None = None,
        limit: int = 500,
        lookback_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lê eventos de variação de volume.
        - session_date: filtra por data específica (YYYY-MM-DD).
          Quando None, usa hoje em BRT se o arquivo existir, caso contrário
          usa o arquivo mais recente disponível (sessão anterior).
        - symbol: filtra por ticker da opção
        - underlying_security: filtra por ativo-objeto
        - limit: máximo de eventos retornados (mais recentes primeiro)
        - lookback_days: quando passado junto com session_date=None e
          lookback_days > 1, retorna múltiplas datas (uso explícito).
        """
        import glob as _glob
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZI

        _BRT = _ZI('America/Sao_Paulo')

        def _today_brt() -> str:
            return _dt.now(_BRT).strftime('%Y-%m-%d')

        _lookback = lookback_days or Config.OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS

        with self._lock:
            if session_date:
                # Pedido explícito por uma data específica
                dates = [session_date]
            else:
                # Sem data explícita → determina a sessão mais relevante
                today = _today_brt()
                today_path = os.path.join(self.volume_activity_dir, f"{today}.jsonl")

                if os.path.exists(today_path):
                    # Arquivo de hoje existe → usa apenas ele
                    dates = [today]
                else:
                    # Hoje ainda sem arquivo → pega apenas o arquivo mais recente disponível
                    # (1 sessão, não o lookback inteiro, para não misturar dias)
                    pattern = os.path.join(self.volume_activity_dir, "*.jsonl")
                    files = sorted(
                        _glob.glob(pattern),
                        key=lambda f: os.path.basename(f),
                        reverse=True,
                    )
                    if files:
                        # lookback_days > 1 explícito → multi-dia; caso padrão → 1 arquivo
                        n = int(_lookback) if (lookback_days and int(lookback_days) > 1) else 1
                        dates = [os.path.basename(f).replace(".jsonl", "") for f in files[:n]]
                    else:
                        dates = []

            rows: list[dict[str, Any]] = []
            for date in dates:
                path = os.path.join(self.volume_activity_dir, f"{date}.jsonl")
                rows.extend(self._load_jsonl_rows_unlocked(path))

            if symbol:
                rows = [r for r in rows if r.get("symbol") == symbol]
            elif underlying_security:
                rows = [r for r in rows if r.get("underlying_security") == underlying_security]

            rows.sort(key=lambda r: r.get("captured_at") or "", reverse=True)
            return _deep_copy_json(rows[:limit])

    def volume_activity_summary(
        self,
        session_date: str | None = None,
        underlying_security: str | None = None,
    ) -> dict[str, Any]:
        """
        Retorna sumário agregado da atividade de volume do dia:
        total de eventos, contratos únicos com atividade, volume delta total.
        """
        events = self.read_volume_activity(
            session_date=session_date,
            underlying_security=underlying_security,
            limit=10_000,
        )
        symbols_seen: set[str] = set()
        total_delta = 0.0
        for ev in events:
            symbols_seen.add(str(ev.get("symbol") or ""))
            total_delta += float(ev.get("volume_delta") or 0.0)
        return {
            "session_date": session_date,
            "underlying_security": underlying_security,
            "event_count": len(events),
            "active_contracts": len(symbols_seen),
            "total_volume_delta": round(total_delta, 0),
        }

    def append_volume_iv_snapshot(self, payload: dict[str, Any]) -> int:
        """
        Persiste um snapshot intraday de IV mensal derivado do tracker de volume.
        """
        if not payload:
            return 0
        session_date = str(payload.get("session_date") or str(payload.get("captured_at") or "")[:10]).strip()
        if not session_date:
            return 0
        with self._lock:
            path = os.path.join(self.volume_iv_history_dir, f"{session_date}.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return 1

    def read_volume_iv_history(
        self,
        session_date: str | None = None,
        underlying_security: str | None = None,
        limit: int = 500,
        lookback_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lê snapshots intraday de IV mensal do tracker de volume.
        """
        import glob as _glob
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZI

        _BRT = _ZI('America/Sao_Paulo')

        def _today_brt() -> str:
            return _dt.now(_BRT).strftime('%Y-%m-%d')

        _lookback = lookback_days or Config.OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS

        with self._lock:
            if session_date:
                dates = [session_date]
            else:
                today = _today_brt()
                today_path = os.path.join(self.volume_iv_history_dir, f"{today}.jsonl")
                if os.path.exists(today_path):
                    dates = [today]
                else:
                    pattern = os.path.join(self.volume_iv_history_dir, "*.jsonl")
                    files = sorted(
                        _glob.glob(pattern),
                        key=lambda f: os.path.basename(f),
                        reverse=True,
                    )
                    if files:
                        n = int(_lookback) if (lookback_days and int(lookback_days) > 1) else 1
                        dates = [os.path.basename(f).replace(".jsonl", "") for f in files[:n]]
                    else:
                        dates = []

            rows: list[dict[str, Any]] = []
            for date in dates:
                path = os.path.join(self.volume_iv_history_dir, f"{date}.jsonl")
                rows.extend(self._load_jsonl_rows_unlocked(path))

            if underlying_security:
                rows = [row for row in rows if row.get("underlying_security") == underlying_security]

            rows.sort(key=lambda row: row.get("captured_at") or "", reverse=True)
            return _deep_copy_json(rows[:limit])

    def read_latest_volume_iv_snapshot(
        self,
        underlying_security: str | None = None,
        lookback_days: int | None = None,
    ) -> dict[str, Any] | None:
        rows = self.read_volume_iv_history(
            underlying_security=underlying_security,
            limit=1,
            lookback_days=lookback_days,
        )
        return rows[0] if rows else None
