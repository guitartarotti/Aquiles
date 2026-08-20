from __future__ import annotations

import os
import socket
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from ..config import Config
from ..utils.logger import get_logger
from .b3_oi_service import B3OIService
from .options_history_service import OptionsHistoryService
from .options_modeling import OptionsModelingService
from .options_snapshot_service import OptionsSnapshotService
from .options_store import OptionsStore

logger = get_logger("aquiles.options_collector")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_schedule_slot(value: Any) -> tuple[str, int, int] | None:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    hour_text, minute_text = text.split(":", 1)
    if not hour_text.isdigit() or not minute_text.isdigit():
        return None
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}", hour, minute


def _scheduled_checkpoint_key(job_kind: str, trade_date: str, slot: str, underlying_security: str | None = None) -> str:
    parts = [job_kind, trade_date, slot]
    if underlying_security:
        parts.append(underlying_security)
    return "::".join(parts)


def _env_truthy(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _collector_disabled_in_process() -> bool:
    return _env_truthy("AQUILES_DISABLE_OPTIONS_COLLECTOR")


class OptionsCollectorManager:
    _instance: Optional["OptionsCollectorManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.store = OptionsStore()
        self.snapshot_service = OptionsSnapshotService(store=self.store)
        self.history_service = OptionsHistoryService(store=self.store, snapshot_service=self.snapshot_service)
        self.b3_oi_service = B3OIService(store=self.store)
        self.modeling_service = OptionsModelingService(store=self.store)
        self._owner_id = f"{socket.gethostname()}:{os.getpid()}:{id(self)}"
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._runtime_lock = threading.RLock()
        self._supervisor_thread: Optional[threading.Thread] = None
        self._supervisor_stop_event = threading.Event()
        self._manual_stop_requested = False

    @classmethod
    def get_instance(cls) -> "OptionsCollectorManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_supervisor_running(self) -> None:
        with self._runtime_lock:
            if self._supervisor_thread and self._supervisor_thread.is_alive():
                return
            self._supervisor_stop_event = threading.Event()
            self._supervisor_thread = threading.Thread(
                target=self._supervisor_loop,
                daemon=True,
                name="options-collector-supervisor",
            )
            self._supervisor_thread.start()
            self.store.update_collector_status(supervisor_running=True)

    def _supervisor_loop(self) -> None:
        interval = max(5, int(Config.OPTIONS_INGEST_SUPERVISOR_INTERVAL_SECONDS))
        while not self._supervisor_stop_event.wait(interval):
            try:
                self.recover_if_needed()
            except Exception:
                logger.exception("Options collector supervisor iteration failed")
        self.store.update_collector_status(supervisor_running=False)

    def _loop_alive(self) -> bool:
        return bool(self._loop_thread and self._loop_thread.is_alive())

    def _spawn_loop_thread(self) -> None:
        self._stop_event = threading.Event()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="options-collector-loop",
        )
        self._loop_thread.start()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_due_work()
            except Exception as exc:
                logger.exception("Options collector iteration failed")
                self.store.update_collector_status(last_error=str(exc))
            if self._stop_event.wait(max(1, int(Config.OPTIONS_LOOP_POLL_SECONDS))):
                break

        with self._runtime_lock:
            current_thread = threading.current_thread()
            if self._loop_thread is current_thread:
                self._loop_thread = None
        stopped_reason = "manual_stop" if self._manual_stop_requested else "collector_stopped"
        self.store.update_collector_status(running=False, stopped_reason=stopped_reason)

    def _run_due_work(self) -> None:
        if Config.OPTIONS_INGEST_ENABLE:
            state = self.store.read_state()
            collector = state.get("collector", {}) or {}
            now = _utc_now()

            last_structural = _parse_iso(collector.get("last_structural_completed_at"))
            last_liquid = _parse_iso(collector.get("last_liquid_completed_at"))
            last_critical = _parse_iso(collector.get("last_critical_completed_at"))

            structural_due = last_structural is None or (now - last_structural).total_seconds() >= Config.OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS
            liquid_due = last_liquid is None or (now - last_liquid).total_seconds() >= Config.OPTIONS_LIQUID_SNAPSHOT_INTERVAL_SECONDS
            critical_due = last_critical is None or (now - last_critical).total_seconds() >= Config.OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS

            if structural_due or liquid_due or critical_due:
                for underlying in Config.OPTIONS_BLOOMBERG_UNDERLYINGS:
                    result = self.snapshot_service.collect_underlying_snapshot(
                        underlying_security=underlying,
                        include_structural=structural_due,
                        include_liquid=liquid_due,
                        include_critical=critical_due,
                        include_ticks=Config.OPTIONS_TICK_CAPTURE_ENABLE,
                    )
                    snapshot_times = {
                        "last_completed_at": result.get("captured_at"),
                        "last_error": None,
                        "run_count": int(collector.get("run_count", 0)) + 1,
                    }
                    if structural_due:
                        snapshot_times["last_structural_completed_at"] = result.get("captured_at")
                    if liquid_due:
                        snapshot_times["last_liquid_completed_at"] = result.get("captured_at")
                    if critical_due:
                        snapshot_times["last_critical_completed_at"] = result.get("captured_at")
                    self.store.update_collector_status(**snapshot_times)

            self._run_daily_history_update_if_due()

        local_now = datetime.now(LOCAL_TZ)
        self._run_scheduled_b3_snapshot_if_due(local_now)
        self._run_scheduled_models_if_due(local_now)

    def _run_daily_history_update_if_due(self) -> None:
        state = self.store.read_state()
        collector = state.get("collector", {}) or {}
        last_history_trade_date = str(collector.get("last_history_trade_date") or "")
        local_now = datetime.now(LOCAL_TZ)
        target_trade_date = local_now.date().isoformat()
        if local_now.hour < int(Config.OPTIONS_DAILY_HISTORY_UPDATE_HOUR):
            return
        if last_history_trade_date >= target_trade_date:
            return

        for underlying in Config.OPTIONS_BLOOMBERG_UNDERLYINGS:
            result = self.history_service.update_daily_open_interest(underlying, trade_date=target_trade_date)
            self.store.update_collector_status(
                last_history_update_at=_now_iso(),
                last_history_trade_date=target_trade_date,
                last_error=None if not result.get("errors") else result["errors"][0].get("error"),
            )

    def _background_jobs_enabled(self) -> bool:
        return bool(
            Config.OPTIONS_INGEST_ENABLE
            or Config.OPTIONS_B3_DAILY_SNAPSHOT_ENABLE
            or Config.OPTIONS_MODEL_SCHEDULE_ENABLE
        )

    def _scheduled_model_underlyings(self) -> list[str]:
        values = [str(item or "").strip() for item in (Config.OPTIONS_MODEL_SCHEDULE_UNDERLYINGS or [])]
        values = [item for item in values if item]
        if values:
            return values
        defaults = [str(item or "").strip() for item in (Config.OPTIONS_BLOOMBERG_UNDERLYINGS or [])]
        defaults = [item for item in defaults if item]
        return defaults or ["IBOVE Index"]

    def _b3_snapshot_slot(self) -> tuple[str, int, int] | None:
        return _parse_schedule_slot(Config.OPTIONS_B3_DAILY_SNAPSHOT_TIME)

    def _model_schedule_slots(self) -> list[tuple[str, int, int]]:
        slots: list[tuple[str, int, int]] = []
        seen: set[str] = set()
        for raw_value in Config.OPTIONS_MODEL_SCHEDULE_TIMES or []:
            parsed = _parse_schedule_slot(raw_value)
            if not parsed:
                continue
            slot_label, _, _ = parsed
            if slot_label in seen:
                continue
            seen.add(slot_label)
            slots.append(parsed)
        slots.sort(key=lambda item: (item[1], item[2]))
        return slots

    def _should_attempt_scheduled_job(self, checkpoint_key: str, local_now: datetime) -> bool:
        checkpoint = self.store.load_scheduled_checkpoint(checkpoint_key)
        if checkpoint.get("complete"):
            return False
        last_attempt = _parse_iso(checkpoint.get("last_attempt_at"))
        if last_attempt is None:
            return True
        cooldown = max(60, int(Config.OPTIONS_SCHEDULE_RETRY_COOLDOWN_SECONDS))
        elapsed = (local_now.astimezone(timezone.utc) - last_attempt).total_seconds()
        return elapsed >= cooldown

    def _try_acquire_scheduled_job(
        self,
        checkpoint_key: str,
        *,
        job_kind: str,
        trade_date: str,
        slot: str,
        underlying_security: str | None,
        local_now: datetime,
    ) -> bool:
        if not self._should_attempt_scheduled_job(checkpoint_key, local_now):
            return False
        lock_result = self.store.try_acquire_scheduled_checkpoint(
            checkpoint_key,
            {
                "job_kind": job_kind,
                "trade_date": trade_date,
                "slot": slot,
                "underlying_security": underlying_security,
            },
            owner=self._owner_id,
            lease_seconds=max(60, int(Config.OPTIONS_SCHEDULE_LOCK_LEASE_SECONDS)),
        )
        if lock_result.get("acquired"):
            return True
        checkpoint = lock_result.get("checkpoint") or {}
        reason = str(lock_result.get("reason") or "unknown")
        logger.info(
            "Skipping scheduled job %s reason=%s owner=%s lease_until=%s complete=%s",
            checkpoint_key,
            reason,
            checkpoint.get("owner"),
            checkpoint.get("lease_until"),
            checkpoint.get("complete"),
        )
        return False

    def _save_scheduled_checkpoint(
        self,
        checkpoint_key: str,
        *,
        job_kind: str,
        trade_date: str,
        slot: str,
        underlying_security: str | None = None,
        complete: bool,
        last_error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        existing = self.store.load_backfill_checkpoint(checkpoint_key) or {}
        payload = {
            **existing,
            "job_kind": job_kind,
            "trade_date": trade_date,
            "slot": slot,
            "underlying_security": underlying_security,
            "owner": self._owner_id,
            "complete": complete,
            "last_attempt_at": _now_iso(),
            "last_error": last_error,
        }
        if details:
            payload["details"] = details
        if complete:
            payload["completed_at"] = _now_iso()
        self.store.save_scheduled_checkpoint(checkpoint_key, payload)

    def _run_scheduled_b3_snapshot_if_due(self, local_now: datetime) -> None:
        if not bool(Config.OPTIONS_B3_DAILY_SNAPSHOT_ENABLE):
            return
        if local_now.weekday() >= 5:
            return
        slot = self._b3_snapshot_slot()
        if slot is None:
            return
        slot_label, target_hour, target_minute = slot
        if (local_now.hour, local_now.minute) < (target_hour, target_minute):
            return

        trade_date = self.b3_oi_service.last_published_trade_date(local_now.date().isoformat())
        checkpoint_key = _scheduled_checkpoint_key("scheduled_b3_oi", trade_date, slot_label)
        if not self._try_acquire_scheduled_job(
            checkpoint_key,
            job_kind="scheduled_b3_oi",
            trade_date=trade_date,
            slot=slot_label,
            underlying_security=None,
            local_now=local_now,
        ):
            return

        result = self.b3_oi_service.collect_daily_oi(trade_date=trade_date, force=False)
        if result.get("error"):
            self._save_scheduled_checkpoint(
                checkpoint_key,
                job_kind="scheduled_b3_oi",
                trade_date=trade_date,
                slot=slot_label,
                complete=False,
                last_error=str(result.get("error")),
                details={"rows_saved": int(result.get("rows_saved", 0))},
            )
            self.store.update_collector_status(last_error=str(result.get("error")))
            logger.warning("Scheduled B3 OI snapshot failed for %s at %s: %s", trade_date, slot_label, result.get("error"))
            return

        rows_saved = int(result.get("rows_saved", 0))
        self._save_scheduled_checkpoint(
            checkpoint_key,
            job_kind="scheduled_b3_oi",
            trade_date=trade_date,
            slot=slot_label,
            complete=True,
            details={
                "rows_saved": rows_saved,
                "skipped": bool(result.get("skipped")),
                "skip_reason": result.get("skip_reason"),
            },
        )
        self.store.update_collector_status(
            last_b3_snapshot_at=_now_iso(),
            last_b3_snapshot_trade_date=trade_date,
            last_b3_snapshot_rows_saved=rows_saved,
            last_error=None,
        )

    def _run_scheduled_models_if_due(self, local_now: datetime) -> None:
        if not bool(Config.OPTIONS_MODEL_SCHEDULE_ENABLE):
            return
        if local_now.weekday() >= 5:
            return

        trade_date = self.b3_oi_service.last_published_trade_date(local_now.date().isoformat())
        underlyings = self._scheduled_model_underlyings()
        slots = self._model_schedule_slots()
        if not underlyings or not slots:
            return

        for slot_label, target_hour, target_minute in slots:
            if (local_now.hour, local_now.minute) < (target_hour, target_minute):
                continue

            for underlying in underlyings:
                checkpoint_key = _scheduled_checkpoint_key("scheduled_options_model", trade_date, slot_label, underlying)
                if not self._try_acquire_scheduled_job(
                    checkpoint_key,
                    job_kind="scheduled_options_model",
                    trade_date=trade_date,
                    slot=slot_label,
                    underlying_security=underlying,
                    local_now=local_now,
                ):
                    continue

                b3_result = self.b3_oi_service.collect_daily_oi(trade_date=trade_date, force=False)
                if not b3_result.get("error"):
                    self.store.update_collector_status(
                        last_b3_snapshot_at=_now_iso(),
                        last_b3_snapshot_trade_date=trade_date,
                        last_b3_snapshot_rows_saved=int(b3_result.get("rows_saved", 0)),
                        last_error=None,
                    )
                else:
                    logger.warning(
                        "Scheduled model run for %s at %s is continuing without fresh B3 OI: %s",
                        underlying,
                        slot_label,
                        b3_result.get("error"),
                    )

                try:
                    result = self._run_scheduled_model_for_underlying(underlying)
                except Exception as exc:
                    self._save_scheduled_checkpoint(
                        checkpoint_key,
                        job_kind="scheduled_options_model",
                        trade_date=trade_date,
                        slot=slot_label,
                        underlying_security=underlying,
                        complete=False,
                        last_error=str(exc),
                    )
                    self.store.update_collector_status(
                        last_scheduled_model_trade_date=trade_date,
                        last_scheduled_model_slot=slot_label,
                        last_error=str(exc),
                    )
                    logger.exception("Scheduled options model run failed for %s at %s", underlying, slot_label)
                    continue

                self._save_scheduled_checkpoint(
                    checkpoint_key,
                    job_kind="scheduled_options_model",
                    trade_date=trade_date,
                    slot=slot_label,
                    underlying_security=underlying,
                    complete=True,
                    details={
                        "run_id": result.get("run_id"),
                        "source_tier": (result.get("source") or {}).get("universe_tier"),
                        "b3_skipped": bool(b3_result.get("skipped")),
                        "b3_rows_saved": int(b3_result.get("rows_saved", 0)),
                    },
                )
                self.store.update_collector_status(
                    last_scheduled_model_run_at=result.get("captured_at") or _now_iso(),
                    last_scheduled_model_trade_date=trade_date,
                    last_scheduled_model_slot=slot_label,
                    last_scheduled_model_run_id=result.get("run_id"),
                    last_error=None,
                )

    def _run_scheduled_model_for_underlying(self, underlying_security: str) -> dict[str, Any]:
        tier = str(Config.OPTIONS_MODEL_DEFAULT_TIER or "structural").strip().lower()
        if tier == "full":
            capture_result = self.snapshot_service.collect_full_snapshot(underlying_security)
        elif tier == "liquid":
            capture_result = self.snapshot_service.collect_liquid_snapshot(underlying_security)
        elif tier == "critical":
            capture_result = self.snapshot_service.collect_critical_snapshot(underlying_security)
        else:
            tier = "structural"
            capture_result = self.snapshot_service.collect_structural_snapshot(underlying_security)

        batch = capture_result.get("batch") or {}
        session_date = str(batch.get("session_date") or "").strip()
        batch_key = str(batch.get("batch_key") or "").strip()
        if not session_date or not batch_key:
            raise ValueError(f"Scheduled model snapshot missing batch metadata for {underlying_security}")

        snapshot_payload = self.store.read_snapshot_batch(tier, session_date, batch_key)
        if not snapshot_payload:
            raise ValueError(f"Unable to reload scheduled {tier} snapshot payload for {underlying_security}")

        return self.modeling_service.run_from_snapshot_payload(
            snapshot_payload,
            sign_convention=Config.OPTIONS_MODEL_SIGN_CONVENTION,
            persist=True,
        )

    def start(self) -> dict[str, Any]:
        if _collector_disabled_in_process():
            self.store.update_collector_status(
                running=False,
                supervisor_running=False,
                stopped_reason="delegated_to_options_collector_service",
                last_error="options_collector_disabled_in_this_process",
            )
            return self.status()
        with self._runtime_lock:
            self._ensure_supervisor_running()
            self._manual_stop_requested = False
            self.store.update_collector_status(
                running=True,
                desired_running=True,
                auto_restart_enabled=Config.OPTIONS_INGEST_AUTO_RESTART,
                last_started_at=_now_iso(),
                last_error=None,
                stopped_reason=None,
            )
            if not self._loop_alive():
                self._spawn_loop_thread()
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._runtime_lock:
            self._manual_stop_requested = True
            loop_thread = self._loop_thread
            if loop_thread is not None and loop_thread.is_alive():
                self._stop_event.set()
                loop_thread.join(timeout=3)
                if not self._loop_alive():
                    self._loop_thread = None
            self.store.update_collector_status(
                running=False,
                desired_running=False,
                stopped_reason="manual_stop",
            )
            return self.status()

    def status(self) -> dict[str, Any]:
        state = self.store.read_state()
        collector = state.get("collector", {}) or {}
        delegated = _collector_disabled_in_process()
        collector["running"] = False if delegated else self._loop_alive()
        collector["supervisor_running"] = (
            False if delegated else bool(self._supervisor_thread and self._supervisor_thread.is_alive())
        )
        collector["delegated"] = delegated
        if delegated:
            collector["service_url"] = Config.OPTIONS_COLLECTOR_SERVICE_URL
        return collector

    def recover_if_needed(self) -> dict[str, Any]:
        if _collector_disabled_in_process():
            return self.status()
        with self._runtime_lock:
            status = self.store.read_state().get("collector", {}) or {}
            desired_running = bool(status.get("desired_running"))
            auto_restart_enabled = bool(status.get("auto_restart_enabled", Config.OPTIONS_INGEST_AUTO_RESTART))
            if not desired_running or not auto_restart_enabled:
                return self.status()
            if not self._loop_alive():
                self._manual_stop_requested = False
                self._spawn_loop_thread()
                restart_count = int(status.get("restart_count", 0)) + 1
                self.store.update_collector_status(
                    running=True,
                    restart_count=restart_count,
                    last_restart_at=_now_iso(),
                    last_started_at=_now_iso(),
                    stopped_reason="auto_restart",
                )
                logger.warning("Options collector worker was down and has been restarted automatically")
            return self.status()

    def resume_if_needed(self) -> dict[str, Any]:
        if _collector_disabled_in_process():
            logger.info("Options collector disabled in this process; external service owns scheduled jobs.")
            return self.status()
        self._ensure_supervisor_running()
        status = self.store.read_state().get("collector", {}) or {}
        if self._background_jobs_enabled() and not status.get("desired_running"):
            self.store.update_collector_status(
                desired_running=True,
                auto_restart_enabled=Config.OPTIONS_INGEST_AUTO_RESTART,
            )
        if self._background_jobs_enabled():
            return self.recover_if_needed()
        return self.status()

    def collect_once(
        self,
        include_structural: bool = True,
        include_liquid: bool = True,
        include_critical: bool = True,
        include_ticks: bool | None = None,
    ) -> dict[str, Any]:
        if _collector_disabled_in_process():
            raise RuntimeError("Options collector is disabled in this process; use aquiles-options-collector-service.")
        result: dict[str, Any] = {
            "captured_at": _now_iso(),
            "underlyings": {},
        }
        underlying_results: dict[str, Any] = result["underlyings"]
        for underlying in Config.OPTIONS_BLOOMBERG_UNDERLYINGS:
            underlying_results[underlying] = self.snapshot_service.collect_underlying_snapshot(
                underlying_security=underlying,
                include_structural=include_structural,
                include_liquid=include_liquid,
                include_critical=include_critical,
                include_ticks=include_ticks,
            )
        self.store.update_collector_status(
            last_completed_at=result["captured_at"],
            last_structural_completed_at=result["captured_at"] if include_structural else None,
            last_liquid_completed_at=result["captured_at"] if include_liquid else None,
            last_critical_completed_at=result["captured_at"] if include_critical else None,
            last_error=None,
        )
        return result

    def backfill_once(self, underlying_security: str, max_contracts: int | None = None) -> dict[str, Any]:
        if _collector_disabled_in_process():
            raise RuntimeError("Options collector is disabled in this process; use aquiles-options-collector-service.")
        return self.history_service.backfill_open_interest_history(
            underlying_security,
            max_contracts=max_contracts,
        )

    def update_daily_history_once(
        self,
        underlying_security: str,
        trade_date: str | None = None,
        max_contracts: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        if _collector_disabled_in_process():
            raise RuntimeError("Options collector is disabled in this process; use aquiles-options-collector-service.")
        result = self.history_service.update_daily_open_interest(
            underlying_security,
            trade_date=trade_date,
            max_contracts=max_contracts,
            force=force,
        )
        if trade_date or result.get("trade_date"):
            self.store.update_collector_status(
                last_history_update_at=_now_iso(),
                last_history_trade_date=trade_date or result.get("trade_date"),
            )
        return result
