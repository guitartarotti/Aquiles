"""Lifecycle management for participant heatmap collection."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from ..config import Config
from .macro_live_service import MacroStateStore
from .macro_participant_heatmap_service import MacroParticipantHeatmapService


class MacroParticipantHeatmapCollectorManager:
    """Own the participant heatmap background thread and its status."""

    _instance: "MacroParticipantHeatmapCollectorManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.store = MacroStateStore()
        self.service = MacroParticipantHeatmapService(store=self.store)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "MacroParticipantHeatmapCollectorManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run_loop(self, interval_seconds: int) -> None:
        while not self._stop_event.is_set():
            try:
                state = self.service.capture_once(refresh=True)
                collector = state.get("collector") or {}
                collector.update(
                    {
                        "running": True,
                        "last_completed_at": state.get("generated_at"),
                        "sample_count": self.service._count_samples(state),
                        "last_error": None,
                    }
                )
                state["collector"] = collector
                self.service._write_state(state)
            except Exception as exc:
                state = self.service._read_state()
                collector = state.get("collector") or {}
                collector.update({"running": True, "last_error": str(exc)})
                state["collector"] = collector
                self.service._write_state(state)
            self._stop_event.wait(max(5, interval_seconds))

    def start(self) -> dict[str, Any]:
        with self._lock:
            interval_seconds = max(5, int(Config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS))
            state = self.service._read_state()
            collector = state.get("collector") or {}
            collector.update(
                {
                    "enabled": bool(Config.MACRO_PARTICIPANT_HEATMAP_ENABLE),
                    "auto_start": bool(Config.MACRO_PARTICIPANT_HEATMAP_AUTO_START),
                    "interval_seconds": interval_seconds,
                    "session_sample_limit": int(
                        Config.MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT
                    ),
                    "running": True,
                    "last_started_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": None,
                }
            )
            state["collector"] = collector
            self.service._write_state(state)
            if not self._thread_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._run_loop,
                    args=(interval_seconds,),
                    daemon=True,
                    name="macro-participant-heatmap-collector",
                )
                self._thread.start()
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                self._stop_event.set()
                thread.join(timeout=3)
            self._thread = None
            state = self.service._read_state()
            collector = state.get("collector") or {}
            collector.update({"running": False})
            state["collector"] = collector
            self.service._write_state(state)
            return self.status()

    def status(self) -> dict[str, Any]:
        state = self.service._read_state()
        collector = state.get("collector") or {}
        collector.update(
            {
                "enabled": bool(Config.MACRO_PARTICIPANT_HEATMAP_ENABLE),
                "auto_start": bool(Config.MACRO_PARTICIPANT_HEATMAP_AUTO_START),
                "interval_seconds": int(Config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS),
                "session_sample_limit": int(Config.MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT),
                "running": self._thread_alive(),
                "sample_count": self.service._count_samples(state),
            }
        )
        return collector

    def resume_if_needed(self) -> dict[str, Any]:
        should_run = bool(
            Config.MACRO_PARTICIPANT_HEATMAP_ENABLE and Config.MACRO_PARTICIPANT_HEATMAP_AUTO_START
        )
        if should_run:
            return self.start()
        return self.status()
