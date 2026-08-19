"""Lifecycle management for the seasonal CVM CDA collector."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from typing import Any

from ..config import Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger
from .cvm_cda_service import LOCAL_TZ, CvmCdaService, _clean_json, _local_now, _utc_now

logger = get_logger("aquiles.cvm_cda")


class CvmCdaManager:
    """Run and monitor the scheduled CVM CDA ingestion loop."""

    _instance: "CvmCdaManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.service = CvmCdaService()
        self.root_dir = self.service.root_dir
        self.state_path = self.root_dir / "collector_status.json"
        self._runtime_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "CvmCdaManager":
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
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="cvm-cda-seasonal")
            self._thread.start()
            self._save_status(
                desired_running=True,
                running=True,
                last_started_at=_utc_now(),
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
        service_status = self.service.status()
        state.update(
            {
                "enabled": bool(getattr(Config, "CVM_CDA_ENABLE", True)),
                "auto_start": bool(getattr(Config, "CVM_CDA_AUTO_START", False)),
                "running": running,
                "update_time": str(getattr(Config, "CVM_CDA_UPDATE_TIME", "08:25")),
                "lookback_months": int(getattr(Config, "CVM_CDA_RECENT_MONTH_LOOKBACK", 3)),
                "next_run_at": self._next_run_at(_local_now()).astimezone(timezone.utc).isoformat(),
                "latest_month": service_status.get("latest_month"),
                "latest_label": service_status.get("latest_label"),
            }
        )
        return state

    def resume_if_needed(self) -> dict[str, Any]:
        state = self._read_status()
        should_run = bool(getattr(Config, "CVM_CDA_ENABLE", True)) and (
            bool(getattr(Config, "CVM_CDA_AUTO_START", False))
            or bool(state.get("desired_running"))
        )
        if should_run:
            return self.start()
        return self.status()

    def collect_once(self, *, force: bool = False, lookback_months: int | None = None) -> dict[str, Any]:
        self._save_status(last_started_at=_utc_now(), last_error=None)
        try:
            result = self.service.ingest_latest(
                force=force,
                lookback_months=lookback_months or int(getattr(Config, "CVM_CDA_RECENT_MONTH_LOOKBACK", 3)),
            )
            completed_at = _utc_now()
            self._save_status(
                last_completed_at=completed_at,
                last_success_at=completed_at if result.get("ok") else None,
                last_error=None if result.get("ok") else "No CVM CDA payload generated.",
                run_count=int(self._read_status().get("run_count") or 0) + 1,
            )
            return result
        except Exception as exc:
            logger.exception("CVM CDA collection failed")
            self._save_status(
                last_completed_at=_utc_now(),
                last_error=str(exc),
                run_count=int(self._read_status().get("run_count") or 0) + 1,
            )
            raise

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._due_to_collect():
                    self.collect_once(force=False)
            except Exception:
                logger.exception("CVM CDA collector iteration failed")
            if self._stop_event.wait(self._seconds_until_next_check()):
                break
        self._save_status(running=False, stopped_reason="loop_stopped")

    def _due_to_collect(self) -> bool:
        latest = self._parse_iso(self._read_status().get("last_success_at"))
        now = _local_now()
        due_today = now.time() >= self._configured_update_time()
        if latest is None:
            return due_today
        latest_local_date = latest.astimezone(LOCAL_TZ).date()
        if latest_local_date >= now.date():
            return False
        if now.weekday() == 0:
            return due_today
        return due_today and now.weekday() in {1, 2, 3, 4, 5}

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
        raw = str(getattr(Config, "CVM_CDA_UPDATE_TIME", "08:25") or "08:25")
        try:
            hour_text, minute_text = raw.split(":", 1)
            return dt_time(hour=max(0, min(int(hour_text), 23)), minute=max(0, min(int(minute_text[:2]), 59)))
        except Exception:
            return dt_time(hour=8, minute=25)

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    def _read_status(self) -> dict[str, Any]:
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        except FileNotFoundError:
            state = {}
        except Exception:
            logger.exception("Failed to read CVM CDA collector status")
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
        atomic_json_dump(str(self.state_path), _clean_json(state), indent=2)
