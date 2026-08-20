"""Thread-safe persistence for macro live state and event history."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Optional

from ..config import Config
from ..utils.logger import get_logger
from .macro_live_utils import (
    LOCAL_TZ,
    _deep_copy_json,
    _now_iso,
    _parse_iso_datetime,
    _sha1_text,
    _utc_now,
)

logger = get_logger("aquiles.macro_live.state")

class MacroStateStore:
    _state_lock = threading.RLock()

    def __init__(self, root_dir: str | None = None):
        self.root_dir = root_dir or Config.MACRO_DATA_DIR
        self.state_path = os.path.join(self.root_dir, "state.json")
        self.events_path = os.path.join(self.root_dir, "events.jsonl")
        self.snapshots_path = os.path.join(self.root_dir, "snapshots.jsonl")
        self._lock = self.__class__._state_lock
        os.makedirs(self.root_dir, exist_ok=True)

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "updated_at": None,
            "event_count": 0,
            "collector": {
                "running": False,
                "interval_seconds": Config.MACRO_INGEST_INTERVAL_SECONDS,
                "desired_running": False,
                "auto_restart_enabled": Config.MACRO_INGEST_AUTO_RESTART,
                "market_poller_running": False,
                "news_listener_running": False,
                "restart_count": 0,
                "last_restart_at": None,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
                "last_market_completed_at": None,
                "last_news_connected_at": None,
                "last_news_event_at": None,
                "last_news_batch_at": None,
                "last_news_error": None,
                "news_messages_received": 0,
                "news_events_persisted": 0,
                "news_reconnect_count": 0,
                "stopped_reason": None,
                "supervisor_running": False,
                "run_count": 0,
            },
            "snapshot": {
                "generated_at": None,
                "news": {
                    "count": 0,
                    "new_count": 0,
                    "items": [],
                    "timeout_windows": 0,
                    "updated_at": None,
                },
                "market": {
                    "contracts": {},
                    "securities": {},
                    "overview": {},
                    "news_links": [],
                },
                "sources": {},
            },
            "recent_events": [],
        }

    def _load_state_unlocked(self) -> dict[str, Any]:
        if not os.path.exists(self.state_path):
            return self._default_state()

        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            logger.exception("Failed to load macro state file")
            return self._default_state()

        default = self._default_state()
        raw_state = state or {}
        default.update(
            {key: value for key, value in raw_state.items() if key not in {"collector", "snapshot"}}
        )
        default["collector"].update(raw_state.get("collector", {}))

        snapshot_state = raw_state.get("snapshot", {}) or {}
        default["snapshot"].update(
            {key: value for key, value in snapshot_state.items() if key not in {"news", "market"}}
        )
        default["snapshot"]["news"].update(snapshot_state.get("news", {}) or {})
        default["snapshot"]["market"].update(snapshot_state.get("market", {}) or {})
        return default

    def _save_state_unlocked(self, state: dict[str, Any]) -> None:
        os.makedirs(self.root_dir, exist_ok=True)
        temp_path = f"{self.state_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        last_error = None
        for _ in range(12):
            try:
                os.replace(temp_path, self.state_path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.1)
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        if last_error is not None:
            raise last_error

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            return _deep_copy_json(self._load_state_unlocked())

    def update_collector_status(self, **fields: Any) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            state["collector"].update(fields)
            state["updated_at"] = _now_iso()
            self._save_state_unlocked(state)
            return _deep_copy_json(state["collector"])

    def record_news_events(
        self,
        events: list[dict[str, Any]],
        source_status: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            existing_events = state.get("recent_events", [])
            existing_ids = {
                event.get("event_id")
                for event in existing_events
                if isinstance(event, dict) and event.get("event_id")
            }

            new_events: list[dict[str, Any]] = []
            if events:
                with open(self.events_path, "a", encoding="utf-8") as f:
                    for event in events:
                        event_id = event.get("event_id")
                        if event_id and event_id in existing_ids:
                            continue

                        existing_ids.add(event_id)
                        new_events.append(event)
                        f.write(json.dumps(event, ensure_ascii=False) + "\n")

            state["recent_events"] = (new_events + existing_events)[:200]
            state["event_count"] = int(state.get("event_count", 0)) + len(new_events)
            state["updated_at"] = _now_iso()

            snapshot = state.get("snapshot", {}) or self._default_state()["snapshot"]
            snapshot_news = snapshot.get("news", {}) or {}
            current_items = (new_events + list(snapshot_news.get("items") or []))[:20]
            snapshot_news.update(
                {
                    "count": len(current_items),
                    "new_count": len(new_events),
                    "items": current_items,
                    "timeout_windows": (source_status or {}).get(
                        "timeout_windows",
                        snapshot_news.get("timeout_windows", 0),
                    ),
                    "updated_at": _now_iso(),
                }
            )
            snapshot["news"] = snapshot_news

            snapshot_sources = snapshot.get("sources", {}) or {}
            if source_status is not None:
                snapshot_sources["bleu_ws"] = source_status
            snapshot["sources"] = snapshot_sources

            state["snapshot"] = snapshot
            self._save_state_unlocked(state)
            return _deep_copy_json(state)

    def record_collection(self, result: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            snapshot = result.get("snapshot", {})
            events = result.get("news_events", []) or []

            existing_events = state.get("recent_events", [])
            existing_ids = {
                event.get("event_id")
                for event in existing_events
                if isinstance(event, dict) and event.get("event_id")
            }

            new_events: list[dict[str, Any]] = []
            if events:
                with open(self.events_path, "a", encoding="utf-8") as f:
                    for event in events:
                        event_id = event.get("event_id")
                        if event_id and event_id in existing_ids:
                            continue

                        existing_ids.add(event_id)
                        new_events.append(event)
                        f.write(json.dumps(event, ensure_ascii=False) + "\n")

            if snapshot:
                with open(self.snapshots_path, "a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "generated_at": snapshot.get("generated_at"),
                                "snapshot": snapshot,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

            state["recent_events"] = (new_events + existing_events)[:200]
            state["event_count"] = int(state.get("event_count", 0)) + len(new_events)
            state["snapshot"] = snapshot
            state["updated_at"] = _now_iso()
            self._save_state_unlocked(state)
            return _deep_copy_json(state)

    def replace_recent_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            normalized_events = list(events or [])[:200]
            state["recent_events"] = normalized_events
            snapshot = state.get("snapshot", {}) or self._default_state()["snapshot"]
            snapshot_news = snapshot.get("news", {}) or {}
            snapshot_news["items"] = normalized_events[:20]
            snapshot_news["count"] = len(normalized_events[:20])
            snapshot_news["updated_at"] = _now_iso()
            snapshot["news"] = snapshot_news
            state["snapshot"] = snapshot
            state["updated_at"] = _now_iso()
            self._save_state_unlocked(state)
            return _deep_copy_json(state)

    def list_recent_events(
        self, limit: int = 20, source: str | None = None
    ) -> list[dict[str, Any]]:
        state = self.read_state()
        events = [
            event
            for event in (state.get("recent_events", []) or [])
            if isinstance(event, dict)
        ]
        if source:
            events = [event for event in events if event.get("source") == source]
        return events[:limit]

    def list_events_for_local_day(
        self,
        target_day: Any | None = None,
        source: str | None = None,
        limit: int | None = None,
        include_state: bool = True,
    ) -> list[dict[str, Any]]:
        if target_day is None:
            local_day = datetime.now(LOCAL_TZ).date()
        elif (
            hasattr(target_day, "year")
            and hasattr(target_day, "month")
            and hasattr(target_day, "day")
        ):
            local_day = target_day
        else:
            parsed = _parse_iso_datetime(target_day)
            local_day = (
                parsed.astimezone(LOCAL_TZ).date() if parsed else datetime.now(LOCAL_TZ).date()
            )

        merged: dict[str, dict[str, Any]] = {}

        def event_key(event: dict[str, Any]) -> str:
            return str(
                event.get("event_id") or _sha1_text(event.get("headline"), event.get("event_time"))
            )

        def matches(event: dict[str, Any]) -> bool:
            if source and event.get("source") != source:
                return False
            event_dt = _parse_iso_datetime(event.get("event_time"))
            if not event_dt:
                return False
            return event_dt.astimezone(LOCAL_TZ).date() == local_day

        if os.path.exists(self.events_path):
            try:
                with open(self.events_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except Exception:
                            continue
                        if not isinstance(event, dict) or not matches(event):
                            continue
                        merged[event_key(event)] = event
            except Exception:
                logger.exception("Failed to read macro events for local day")

        if include_state:
            state = self.read_state()
            for event in state.get("recent_events", []) or []:
                if not isinstance(event, dict) or not matches(event):
                    continue
                merged[event_key(event)] = event

        events = list(merged.values())
        events.sort(
            key=lambda item: _parse_iso_datetime(item.get("event_time")) or _utc_now(), reverse=True
        )
        if limit and limit > 0:
            return events[:limit]
        return events

    def list_events_in_local_window(
        self,
        start_local: datetime,
        end_local: datetime | None = None,
        source: str | None = None,
        limit: int | None = None,
        include_state: bool = True,
    ) -> list[dict[str, Any]]:
        if start_local.tzinfo is None:
            start_local = start_local.replace(tzinfo=LOCAL_TZ)
        else:
            start_local = start_local.astimezone(LOCAL_TZ)

        if end_local is None:
            end_local = datetime.now(LOCAL_TZ)
        elif end_local.tzinfo is None:
            end_local = end_local.replace(tzinfo=LOCAL_TZ)
        else:
            end_local = end_local.astimezone(LOCAL_TZ)

        merged: dict[str, dict[str, Any]] = {}

        def event_key(event: dict[str, Any]) -> str:
            return str(
                event.get("event_id") or _sha1_text(event.get("headline"), event.get("event_time"))
            )

        def matches(event: dict[str, Any]) -> bool:
            if source and event.get("source") != source:
                return False
            event_dt = _parse_iso_datetime(event.get("event_time"))
            if not event_dt:
                return False
            local_dt = event_dt.astimezone(LOCAL_TZ)
            return start_local <= local_dt <= end_local

        if os.path.exists(self.events_path):
            try:
                with open(self.events_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except Exception:
                            continue
                        if not isinstance(event, dict) or not matches(event):
                            continue
                        merged[event_key(event)] = event
            except Exception:
                logger.exception("Failed to read macro events for local window")

        if include_state:
            state = self.read_state()
            for event in state.get("recent_events", []) or []:
                if not isinstance(event, dict) or not matches(event):
                    continue
                merged[event_key(event)] = event

        events = list(merged.values())
        events.sort(
            key=lambda item: _parse_iso_datetime(item.get("event_time")) or _utc_now(), reverse=True
        )
        if limit and limit > 0:
            return events[:limit]
        return events

    def list_snapshot_history(self, limit: int = 40) -> list[dict[str, Any]]:
        if limit <= 0 or not os.path.exists(self.snapshots_path):
            return []

        try:
            with open(self.snapshots_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except Exception:
            logger.exception("Failed to read macro snapshot history")
            return []

        history: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    history.append(payload)
            except Exception:
                continue
        return history
