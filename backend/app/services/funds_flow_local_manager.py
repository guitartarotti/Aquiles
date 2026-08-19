"""Lifecycle management for the scheduled Funds Flow collector."""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time
from typing import Any

from ..config import Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger
from .funds_flow_local_service import FundsFlowLocalService
from .funds_flow_utils import LOCAL_TZ, _clean_json, _local_now, _now_iso, _parse_iso

logger = get_logger("aquiles.funds_flow_local")


class FundsFlowLocalManager:
    """Run and monitor the daily Funds Flow collection loop."""

    _instance: "FundsFlowLocalManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.service = FundsFlowLocalService()
        self.root_dir = self.service.root_dir
        self.state_path = os.path.join(self.root_dir, "collector_status.json")
        self._runtime_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        os.makedirs(self.root_dir, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "FundsFlowLocalManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def start(self) -> dict[str, Any]:
        with self._runtime_lock:
            if self._thread and self._thread.is_alive():
                self._save_status(desired_running=True, running=True)
                return self.status()
            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="funds-flow-local-daily")
            self._thread.start()
            self._save_status(
                desired_running=True,
                running=True,
                last_started_at=_now_iso(),
                stopped_reason=None,
                last_error=None,
            )
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._runtime_lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
            if self._thread and not self._thread.is_alive():
                self._thread = None
            self._save_status(desired_running=False, running=False, stopped_reason="manual_stop")
            return self.status()

    def status(self) -> dict[str, Any]:
        state = self._read_status()
        running = bool(self._thread and self._thread.is_alive())
        state.update(
            {
                "enabled": bool(getattr(Config, "FUNDS_FLOW_LOCAL_ENABLE", True)),
                "auto_start": bool(getattr(Config, "FUNDS_FLOW_LOCAL_AUTO_START", False)),
                "running": running,
                "update_time": str(getattr(Config, "FUNDS_FLOW_LOCAL_UPDATE_TIME", "07:40")),
                "history_days": int(getattr(Config, "FUNDS_FLOW_LOCAL_HISTORY_DAYS", 95)),
                "next_run_at": self._next_run_at(_local_now()).astimezone(timezone.utc).isoformat(),
                "latest_snapshot_at": self._latest_snapshot_at(),
            }
        )
        return state

    def resume_if_needed(self) -> dict[str, Any]:
        state = self._read_status()
        should_run = bool(getattr(Config, "FUNDS_FLOW_LOCAL_ENABLE", True)) and (
            bool(getattr(Config, "FUNDS_FLOW_LOCAL_AUTO_START", False))
            or bool(state.get("desired_running"))
        )
        if should_run:
            return self.start()
        return self.status()

    def collect_once(
        self,
        *,
        force: bool = True,
        target_date: str | date | None = None,
        period: str | None = "21d",
        history_days: int | None = None,
    ) -> dict[str, Any]:
        self._save_status(last_started_at=_now_iso(), last_error=None)
        try:
            payload = self.service.collect(
                target_date=target_date,
                period=period,
                history_days=history_days,
                force=force,
            )
            completed_at = payload.get("report", {}).get("completed_at") or _now_iso()
            self._save_status(
                last_completed_at=completed_at,
                last_success_at=completed_at if payload.get("ok") else None,
                last_error=None if payload.get("ok") else "No Funds Flow Local payload generated.",
                run_count=int(self._read_status().get("run_count") or 0) + 1,
            )
            return payload
        except Exception as exc:
            logger.exception("Funds Flow Local daily collection failed")
            self._save_status(
                last_completed_at=_now_iso(),
                last_error=str(exc),
                run_count=int(self._read_status().get("run_count") or 0) + 1,
            )
            raise

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._due_to_collect():
                    self.collect_once(force=True)
            except Exception:
                logger.exception("Funds Flow Local collector iteration failed")

            if self._stop_event.wait(self._seconds_until_next_check()):
                break

        self._save_status(running=False, stopped_reason="loop_stopped")

    def _due_to_collect(self) -> bool:
        latest_snapshot = self._latest_snapshot_at()
        if latest_snapshot is None:
            return True
        now = _local_now()
        update_time = self._configured_update_time()
        due_today = now.time() >= update_time
        latest_local_date = latest_snapshot.astimezone(LOCAL_TZ).date()
        return due_today and latest_local_date < now.date()

    def _seconds_until_next_check(self) -> float:
        now = _local_now()
        next_run = self._next_run_at(now)
        seconds = max((next_run - now).total_seconds(), 60.0)
        return min(seconds, 3600.0)

    def _next_run_at(self, now: datetime) -> datetime:
        update_time = self._configured_update_time()
        today_run = datetime.combine(now.date(), update_time, tzinfo=LOCAL_TZ)
        if now < today_run:
            return today_run
        return today_run + timedelta(days=1)

    @staticmethod
    def _configured_update_time() -> dt_time:
        raw = str(getattr(Config, "FUNDS_FLOW_LOCAL_UPDATE_TIME", "07:40") or "07:40")
        try:
            hour_text, minute_text = raw.split(":", 1)
            return dt_time(hour=max(0, min(int(hour_text), 23)), minute=max(0, min(int(minute_text[:2]), 59)))
        except Exception:
            return dt_time(hour=7, minute=40)

    def _latest_snapshot_at(self) -> datetime | None:
        snapshot = self.service._read_latest()
        report = (snapshot or {}).get("report") or {}
        return _parse_iso(report.get("last_updated_at") or (snapshot or {}).get("generated_at")) if snapshot else None

    def _read_status(self) -> dict[str, Any]:
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        except FileNotFoundError:
            state = {}
        except Exception:
            logger.exception("Failed to read Funds Flow Local collector status")
            state = {}
        return {
            "desired_running": False,
            "running": False,
            "run_count": 0,
            "last_started_at": None,
            "last_completed_at": None,
            "last_success_at": None,
            "last_error": None,
            "stopped_reason": None,
            **(state or {}),
        }

    def _save_status(self, **fields: Any) -> None:
        state = self._read_status()
        for key, value in fields.items():
            if value is not None or key in {"last_error", "stopped_reason"}:
                state[key] = value
        atomic_json_dump(self.state_path, _clean_json(state), indent=2)
