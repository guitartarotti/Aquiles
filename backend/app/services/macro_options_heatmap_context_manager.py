"""Lifecycle management for options heatmap context collection."""

from __future__ import annotations

import threading
import time
from typing import Any

from ..config import Config
from ..utils.logger import get_logger
from .macro_options_heatmap_context_schedule import options_poll_interval_seconds
from .macro_options_heatmap_context_service import MacroOptionsHeatmapContextService, _now_iso

logger = get_logger("mirofish.macro_options_heatmap_context")


class MacroOptionsHeatmapContextManager:
    """Own the options heatmap collector thread and runtime status."""

    _instance: "MacroOptionsHeatmapContextManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.service = MacroOptionsHeatmapContextService()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "MacroOptionsHeatmapContextManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @staticmethod
    def _poll_interval_seconds() -> int:
        return options_poll_interval_seconds()

    def _run_loop(self, interval_seconds: int) -> None:
        while not self._stop_event.is_set():
            started_at = time.time()
            try:
                self.service.capture_once()
            except Exception:
                logger.exception("Options heatmap context iteration failed")
            elapsed = time.time() - started_at
            remaining = max(0.05, float(max(2, interval_seconds)) - elapsed)
            self._stop_event.wait(remaining)

    def start(self) -> dict[str, Any]:
        with self._lock:
            state = self.service.read_state()
            collector = state.get("collector") or {}
            collector.update(
                {
                    "enabled": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE),
                    "auto_start": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START),
                    "loop_seconds": int(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS),
                    "live_capture_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
                    "fair_value_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
                    "poll_seconds": self._poll_interval_seconds(),
                    "running": True,
                    "last_started_at": _now_iso(),
                    "last_error": None,
                }
            )
            state["collector"] = collector
            with self.service._lock:
                self.service._save_state_unlocked(state)
            if not self._thread_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._run_loop,
                    args=(self._poll_interval_seconds(),),
                    daemon=True,
                    name="macro-options-heatmap-context",
                )
                self._thread.start()
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._thread_alive():
                self._stop_event.set()
                self._thread.join(timeout=3)
            self._thread = None
            state = self.service.read_state()
            collector = state.get("collector") or {}
            collector["running"] = False
            state["collector"] = collector
            with self.service._lock:
                self.service._save_state_unlocked(state)
            return self.status()

    def status(self) -> dict[str, Any]:
        collector = self.service.collector_status()
        collector.update(
            {
                "enabled": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE),
                "auto_start": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START),
                "loop_seconds": int(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS),
                "live_capture_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
                "fair_value_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
                "poll_seconds": self._poll_interval_seconds(),
                "running": self._thread_alive(),
            }
        )
        return collector

    def resume_if_needed(self) -> dict[str, Any]:
        should_run = bool(
            Config.MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE
            and Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START
        )
        if should_run:
            return self.start()
        return self.status()
