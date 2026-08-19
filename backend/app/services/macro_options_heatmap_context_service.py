from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..config import Config
from ..utils.logger import get_logger
from .macro_options_heatmap_context_schedule import options_poll_interval_seconds
from .options_bloomberg_service import OptionsBloombergService
from .options_fair_value_modeling import OptionsFairValueService
from .options_global_modeling import OptionsGlobalTriangulationService
from .options_modeling import OptionsModelingService
from .options_snapshot_service import OptionsSnapshotService
from .options_store import OptionsStore

logger = get_logger("aquiles.macro_options_heatmap_context")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _deep_copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


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


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _is_live_excel_price_source(value: Any) -> bool:
    return str(value or "").strip().startswith("live_reference:excel_fair_value_basket:")


def _session_date_from_timestamp(value: Any) -> str | None:
    parsed = _parse_iso(value)
    if parsed is None:
        return None
    return parsed.astimezone(LOCAL_TZ).date().isoformat()


def _median(values: list[float]) -> float | None:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return None
    mid = len(finite) // 2
    if len(finite) % 2:
        return finite[mid]
    return (finite[mid - 1] + finite[mid]) / 2.0


def _median_abs_deviation(values: list[float], center: float | None = None) -> float | None:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return None
    median_value = center if center is not None else _median(finite)
    if median_value is None:
        return None
    deviations = [abs(value - median_value) for value in finite]
    return _median(deviations)


def _curve_conditions_delta_magnitude(curve_conditions: dict[str, Any] | None) -> float:
    curve_conditions = curve_conditions or {}
    deltas = [
        _finite_float(curve_conditions.get("short_day_change_pct")),
        _finite_float(curve_conditions.get("belly_day_change_pct")),
        _finite_float(curve_conditions.get("long_day_change_pct")),
        _finite_float(curve_conditions.get("level_day_change_pct")),
        _finite_float(curve_conditions.get("slope_change")),
        _finite_float(curve_conditions.get("twist_change")),
    ]
    finite = [abs(value) for value in deltas if value is not None]
    return max(finite) if finite else 0.0


def _is_degraded_curve_snapshot(curve_conditions: dict[str, Any] | None) -> bool:
    curve_conditions = curve_conditions or {}
    if not curve_conditions:
        return True
    state = str(curve_conditions.get("state") or "").strip().lower()
    macro_regime = str(curve_conditions.get("macro_regime") or "").strip().lower()
    summary = str(curve_conditions.get("summary") or "").strip().lower()
    if _curve_conditions_delta_magnitude(curve_conditions) > 0.01:
        return False
    return (
        state == "mixed_curve"
        or "curva mista" in summary
        or macro_regime == "misto / sem vetor unico"
    )


def _has_meaningful_curve_snapshot(curve_conditions: dict[str, Any] | None) -> bool:
    curve_conditions = curve_conditions or {}
    if not curve_conditions:
        return False
    return _curve_conditions_delta_magnitude(curve_conditions) > 0.01


class MacroOptionsHeatmapContextService:
    STATE_VERSION = "macro-options-heatmap-context-v1"

    def __init__(self, root_dir: str | None = None):
        self.root_dir = root_dir or Config.MACRO_DATA_DIR
        self.state_path = os.path.join(self.root_dir, "options_heatmap_context.json")
        self.fair_value_history_path = os.path.join(self.root_dir, "options_heatmap_fair_value_history.json")
        self.live_capture_archive_dir = os.path.join(self.root_dir, "live_capture_archive")
        self._lock = threading.RLock()
        self._capture_lock = threading.Lock()
        self._async_lock = threading.RLock()
        self._correlation_worker_thread: threading.Thread | None = None
        self._correlation_pending_snapshot: dict[str, Any] | None = None
        self._fair_value_worker_thread: threading.Thread | None = None
        self._fair_value_pending_snapshot: dict[str, Any] | None = None
        self._payload_cache: dict[str, Any] | None = None
        self._payload_cache_at: float = 0.0
        self._latest_model_run_cache: dict[str, dict[str, Any]] = {}
        self._latest_model_run_cache_at: dict[str, float] = {}
        self._latest_fair_value_run_cache: dict[str, dict[str, Any]] = {}
        self._latest_fair_value_run_cache_at: dict[str, float] = {}
        self.store = OptionsStore()
        self.snapshot_service = OptionsSnapshotService(store=self.store)
        self.modeling_service = OptionsModelingService(store=self.store)
        self.global_service = OptionsGlobalTriangulationService(store=self.store)
        self.bloomberg_service = OptionsBloombergService()
        self.fair_value_service = OptionsFairValueService(
            store=self.store,
            options_modeling=self.modeling_service,
            global_service=self.global_service,
        )
        os.makedirs(self.root_dir, exist_ok=True)
        os.makedirs(self.live_capture_archive_dir, exist_ok=True)

    @staticmethod
    def _scheduled_underlyings() -> list[str]:
        values = [str(item or "").strip() for item in (Config.OPTIONS_WYRM_AUTORUN_UNDERLYINGS or [])]
        values = [item for item in values if item]
        return values or ["IBOVE Index"]

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "version": MacroOptionsHeatmapContextService.STATE_VERSION,
            "generated_at": None,
            "collector": {
                "enabled": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE),
                "auto_start": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START),
                "loop_seconds": int(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS),
                "live_capture_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
                "fair_value_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
                "running": False,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
                "restart_count": 0,
                "last_wyrm_run_at": None,
                "last_wyrm_trade_date": None,
                "last_wyrm_model_run_id": None,
                "last_wyrm_global_run_id": None,
                "last_wyrm_fair_value_run_id": None,
                "last_live_snapshot_at": None,
                "last_projection_requested_at": None,
                "last_intraday_correlation_requested_at": None,
                "last_projection_completed_at": None,
                "last_projection_error": None,
                "underlyings": MacroOptionsHeatmapContextService._scheduled_underlyings(),
            },
            "live_capture_history": {
                "underlying_security": "IBOVE Index",
                "sample_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
                "max_samples": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_STATE_LIMIT),
                "current_session_date": None,
                "latest_snapshot": None,
                "snapshots": [],
            },
            "gamma_context": {
                "underlying_security": "IBOVE Index",
                "latest_model_run_id": None,
                "latest_model_captured_at": None,
                "current_future_price": None,
                "current_spot_price": None,
                "basis_points": None,
                "regions": [],
                "special_regions": [],
                "summary": {},
            },
            "fair_value_history": {
                "underlying_security": "IBOVE Index",
                "sample_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
                "max_samples": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_LIMIT),
                "current_session_date": None,
                "latest_sample": None,
                "samples": [],
            },
        }

    @staticmethod
    def _default_fair_value_history() -> dict[str, Any]:
        return {
            "underlying_security": "IBOVE Index",
            "sample_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
            "max_samples": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_LIMIT),
            "current_session_date": None,
            "latest_sample": None,
            "samples": [],
        }

    def _load_fair_value_history_unlocked(self) -> dict[str, Any]:
        if not os.path.exists(self.fair_value_history_path):
            return self._default_fair_value_history()
        try:
            with open(self.fair_value_history_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            logger.exception("Failed to load fair value history state")
            return self._default_fair_value_history()
        history = self._default_fair_value_history()
        history.update(payload or {})
        return history

    def _replace_file_with_retry(
        self,
        *,
        temp_path: str,
        target_path: str,
        label: str,
        max_attempts: int = 30,
        retry_sleep_seconds: float = 0.15,
    ) -> bool:
        attempts = 0
        while True:
            try:
                os.replace(temp_path, target_path)
                return True
            except PermissionError as exc:
                attempts += 1
                if attempts >= max(int(max_attempts), 1):
                    logger.warning(
                        "Skipped %s write after %s replace retries for %s: %s",
                        label,
                        attempts,
                        target_path,
                        exc,
                    )
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except Exception:
                        pass
                    return False
                time.sleep(max(float(retry_sleep_seconds), 0.0))

    def _save_fair_value_history_unlocked(self, history: dict[str, Any]) -> None:
        temp_path = f"{self.fair_value_history_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(history, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        self._replace_file_with_retry(
            temp_path=temp_path,
            target_path=self.fair_value_history_path,
            label="fair value history",
        )

    def _load_state_unlocked(self) -> dict[str, Any]:
        if not os.path.exists(self.state_path):
            default = self._default_state()
            default["fair_value_history"] = self._load_fair_value_history_unlocked()
            return default
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            logger.exception("Failed to load options heatmap context state")
            default = self._default_state()
            default["fair_value_history"] = self._load_fair_value_history_unlocked()
            return default
        default = self._default_state()
        raw = payload or {}
        default.update({
            key: value
            for key, value in raw.items()
            if key not in {"collector", "gamma_context", "fair_value_history", "live_capture_history"}
        })
        default["collector"].update(raw.get("collector") or {})
        default["live_capture_history"].update(raw.get("live_capture_history") or {})
        live_history = default.get("live_capture_history") or {}
        if isinstance(live_history.get("latest_snapshot"), dict):
            live_history["latest_snapshot"] = self._expand_live_snapshot_from_disk(live_history.get("latest_snapshot") or {})
        live_history["snapshots"] = [
            self._expand_live_snapshot_from_disk(dict(item or {}))
            for item in (live_history.get("snapshots") or [])
            if isinstance(item, dict)
        ]
        default["gamma_context"].update(raw.get("gamma_context") or {})
        raw_fair_value_history = raw.get("fair_value_history") or {}
        if raw_fair_value_history:
            default["fair_value_history"].update(raw_fair_value_history)
        if os.path.exists(self.fair_value_history_path):
            default["fair_value_history"].update(self._load_fair_value_history_unlocked() or {})
        return default

    def _save_state_unlocked(self, state: dict[str, Any], *, persist_fair_value_history: bool = False) -> None:
        if persist_fair_value_history:
            self._save_fair_value_history_unlocked(state.get("fair_value_history") or self._default_fair_value_history())
        temp_path = f"{self.state_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(
                self._compact_state_for_disk(state),
                handle,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            handle.flush()
            os.fsync(handle.fileno())
        self._replace_file_with_retry(
            temp_path=temp_path,
            target_path=self.state_path,
            label="options heatmap context state",
        )

    @staticmethod
    def _compact_workbook_values_for_disk(values: dict[str, Any] | None) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for security, raw_dynamic in (values or {}).items():
            key = str(security or "").strip()
            if not key:
                continue
            if isinstance(raw_dynamic, (list, tuple)):
                raw_value = _finite_float(raw_dynamic[0] if len(raw_dynamic) >= 1 else None)
                daily_change_pct = _finite_float(raw_dynamic[1] if len(raw_dynamic) >= 2 else None)
            else:
                dynamic = dict(raw_dynamic or {})
                raw_value = _finite_float(dynamic.get("raw_value"))
                daily_change_pct = _finite_float(dynamic.get("daily_change_pct"))
            compact[key] = [raw_value, daily_change_pct]
        return compact

    @staticmethod
    def _expand_workbook_values_from_disk(values: dict[str, Any] | None, *, snapshot_timestamp: Any = None) -> dict[str, Any]:
        expanded: dict[str, Any] = {}
        for security, raw_dynamic in (values or {}).items():
            key = str(security or "").strip()
            if not key:
                continue
            if isinstance(raw_dynamic, (list, tuple)):
                raw_value = _finite_float(raw_dynamic[0] if len(raw_dynamic) >= 1 else None)
                daily_change_pct = _finite_float(raw_dynamic[1] if len(raw_dynamic) >= 2 else None)
                expanded[key] = {
                    "raw_value": raw_value,
                    "daily_change_pct": daily_change_pct,
                    "timestamp": snapshot_timestamp,
                }
            else:
                dynamic = dict(raw_dynamic or {})
                expanded[key] = {
                    "raw_value": _finite_float(dynamic.get("raw_value")),
                    "daily_change_pct": _finite_float(dynamic.get("daily_change_pct")),
                    "timestamp": dynamic.get("timestamp") or snapshot_timestamp,
                    "row_number": dynamic.get("row_number"),
                    "worksheet_name": dynamic.get("worksheet_name"),
                    "fallback_source": dynamic.get("fallback_source"),
                }
        return expanded

    @staticmethod
    def _workbook_pair_from_disk(values: dict[str, Any] | None, security: str) -> tuple[float | None, float | None]:
        target = str(security or "").strip()
        if not target:
            return None, None
        direct = (values or {}).get(target)
        if direct is None:
            lowered = target.lower()
            for key, raw_dynamic in (values or {}).items():
                if str(key or "").strip().lower() == lowered:
                    direct = raw_dynamic
                    break
        if isinstance(direct, (list, tuple)):
            raw_value = _finite_float(direct[0] if len(direct) >= 1 else None)
            daily_change_pct = _finite_float(direct[1] if len(direct) >= 2 else None)
            return raw_value, daily_change_pct
        dynamic = dict(direct or {})
        return _finite_float(dynamic.get("raw_value")), _finite_float(dynamic.get("daily_change_pct"))

    @staticmethod
    def _compact_factor_values_for_disk(values: dict[str, Any] | None) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for factor, raw_dynamic in (values or {}).items():
            key = str(factor or "").strip()
            if not key:
                continue
            if isinstance(raw_dynamic, (list, tuple)):
                raw_value = _finite_float(raw_dynamic[0] if len(raw_dynamic) >= 1 else None)
                daily_change_pct = _finite_float(raw_dynamic[1] if len(raw_dynamic) >= 2 else None)
                compact[key] = [raw_value, daily_change_pct]
            else:
                dynamic = dict(raw_dynamic or {})
                compact[key] = [
                    _finite_float(dynamic.get("raw_value")),
                    _finite_float(dynamic.get("daily_change_pct")),
                ]
        return compact

    @staticmethod
    def _expand_factor_values_from_disk(values: dict[str, Any] | None, *, snapshot_timestamp: Any = None) -> dict[str, Any]:
        expanded: dict[str, Any] = {}
        for factor, raw_dynamic in (values or {}).items():
            key = str(factor or "").strip()
            if not key:
                continue
            if isinstance(raw_dynamic, (list, tuple)):
                expanded[key] = {
                    "raw_value": _finite_float(raw_dynamic[0] if len(raw_dynamic) >= 1 else None),
                    "daily_change_pct": _finite_float(raw_dynamic[1] if len(raw_dynamic) >= 2 else None),
                    "timestamp": snapshot_timestamp,
                }
            else:
                dynamic = dict(raw_dynamic or {})
                expanded[key] = {
                    "raw_value": _finite_float(dynamic.get("raw_value")),
                    "daily_change_pct": _finite_float(dynamic.get("daily_change_pct")),
                    "timestamp": dynamic.get("timestamp") or snapshot_timestamp,
                    "is_live": bool(dynamic.get("is_live")),
                    "live_source": dynamic.get("live_source"),
                }
        return expanded

    def _compact_live_snapshot_for_disk(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        compact = dict(snapshot or {})
        compact["workbook_values"] = self._compact_workbook_values_for_disk(snapshot.get("workbook_values") or {})
        compact["factor_values"] = self._compact_factor_values_for_disk(snapshot.get("factor_values") or {})
        compact["workbook_value_count"] = int(snapshot.get("workbook_value_count") or len(compact["workbook_values"]))
        compact["factor_count"] = int(snapshot.get("factor_count") or len(compact["factor_values"]))
        return compact

    def _expand_live_snapshot_from_disk(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        expanded = dict(snapshot or {})
        snapshot_timestamp = expanded.get("captured_at") or expanded.get("current_price_timestamp")
        expanded["workbook_values"] = self._expand_workbook_values_from_disk(
            expanded.get("workbook_values") or {},
            snapshot_timestamp=snapshot_timestamp,
        )
        expanded["factor_values"] = self._expand_factor_values_from_disk(
            expanded.get("factor_values") or {},
            snapshot_timestamp=snapshot_timestamp,
        )
        expanded["workbook_value_count"] = int(expanded.get("workbook_value_count") or len(expanded["workbook_values"]))
        expanded["factor_count"] = int(expanded.get("factor_count") or len(expanded["factor_values"]))
        return expanded

    def _compact_state_for_disk(self, state: dict[str, Any]) -> dict[str, Any]:
        compact_state = {
            key: _deep_copy_json(value)
            for key, value in (state or {}).items()
            if key != "fair_value_history"
        }
        live_history = dict(compact_state.get("live_capture_history") or {})
        max_live_samples = max(2, int(Config.MACRO_OPTIONS_LIVE_CAPTURE_STATE_LIMIT))
        if isinstance(live_history.get("latest_snapshot"), dict):
            live_history["latest_snapshot"] = self._compact_live_snapshot_for_disk(live_history.get("latest_snapshot") or {})
        live_snapshots = [
            self._compact_live_snapshot_for_disk(dict(item or {}))
            for item in (live_history.get("snapshots") or [])
            if isinstance(item, dict)
        ]
        if len(live_snapshots) > max_live_samples:
            live_snapshots = live_snapshots[-max_live_samples:]
        live_history["snapshots"] = live_snapshots
        live_history["max_samples"] = max_live_samples
        compact_state["live_capture_history"] = live_history
        fair_history = dict((state or {}).get("fair_value_history") or {})
        fair_samples = fair_history.get("samples") or []
        latest_sample = fair_history.get("latest_sample") or {}
        compact_state["fair_value_history"] = {
            "underlying_security": fair_history.get("underlying_security") or "IBOVE Index",
            "sample_interval_seconds": int(fair_history.get("sample_interval_seconds") or Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
            "max_samples": int(fair_history.get("max_samples") or Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_LIMIT),
            "current_session_date": fair_history.get("current_session_date"),
            "latest_sample": {
                "captured_at": latest_sample.get("captured_at"),
                "fair_value_final_future": latest_sample.get("fair_value_final_future"),
                "current_future_price": latest_sample.get("current_future_price"),
            } if latest_sample else None,
            "samples_total": len(fair_samples),
        }
        return compact_state

    @staticmethod
    def _archive_underlying_key(underlying_security: str) -> str:
        text = str(underlying_security or "IBOVE Index").strip().replace(" ", "_")
        return "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-"}).upper() or "IBOVE_INDEX"

    def _live_capture_archive_path(self, *, session_date: str, underlying_security: str) -> str:
        filename = f"{session_date}_{self._archive_underlying_key(underlying_security)}.jsonl"
        return os.path.join(self.live_capture_archive_dir, filename)

    def _append_live_capture_archive_unlocked(self, snapshot: dict[str, Any]) -> None:
        session_date = str(snapshot.get("session_date") or "").strip()
        underlying_security = str(snapshot.get("underlying_security") or "IBOVE Index").strip()
        if not session_date:
            return
        archive_path = self._live_capture_archive_path(
            session_date=session_date,
            underlying_security=underlying_security,
        )
        compact_snapshot = self._compact_live_snapshot_for_disk(snapshot)
        with open(archive_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(compact_snapshot, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")

    def _load_live_capture_archive_unlocked(
        self,
        *,
        session_date: str,
        underlying_security: str,
    ) -> list[dict[str, Any]]:
        archive_path = self._live_capture_archive_path(
            session_date=session_date,
            underlying_security=underlying_security,
        )
        if not os.path.exists(archive_path):
            return []
        snapshots: list[dict[str, Any]] = []
        try:
            with open(archive_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    raw = str(line or "").strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    snapshots.append(self._expand_live_snapshot_from_disk(payload))
        except Exception:
            logger.exception("Failed to load live capture archive")
            return []
        return snapshots

    def _load_live_capture_archive_workbook_series_unlocked(
        self,
        *,
        session_date: str,
        underlying_security: str,
        security: str,
    ) -> list[dict[str, Any]]:
        archive_path = self._live_capture_archive_path(
            session_date=session_date,
            underlying_security=underlying_security,
        )
        if not os.path.exists(archive_path):
            return []
        rows: list[dict[str, Any]] = []
        try:
            with open(archive_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    raw = str(line or "").strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    raw_value, daily_change_pct = self._workbook_pair_from_disk(
                        payload.get("workbook_values") or {},
                        security,
                    )
                    if raw_value is None:
                        continue
                    captured_at = payload.get("captured_at") or payload.get("current_price_timestamp")
                    if not captured_at:
                        continue
                    resolved_session_date = str(payload.get("session_date") or session_date or "").strip()
                    rows.append({
                        "date": resolved_session_date,
                        "session_date": resolved_session_date,
                        "captured_at": captured_at,
                        "security": security,
                        "raw_value": raw_value,
                        "daily_change_pct": daily_change_pct,
                        "underlying_security": underlying_security,
                    })
        except Exception:
            logger.exception("Failed to load workbook series from live capture archive")
            return []
        return rows

    def _load_all_live_capture_archives_unlocked(
        self,
        *,
        underlying_security: str,
    ) -> list[dict[str, Any]]:
        prefix = f"_{self._archive_underlying_key(underlying_security)}.jsonl"
        snapshots: list[dict[str, Any]] = []
        try:
            for entry in sorted(os.listdir(self.live_capture_archive_dir)):
                if not entry.endswith(prefix):
                    continue
                archive_path = os.path.join(self.live_capture_archive_dir, entry)
                with open(archive_path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        raw = str(line or "").strip()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            continue
                        if isinstance(payload, dict):
                            snapshots.append(self._expand_live_snapshot_from_disk(payload))
        except Exception:
            logger.exception("Failed to load all live capture archives")
            return []
        return snapshots

    def _list_live_capture_archive_session_dates_unlocked(
        self,
        *,
        underlying_security: str,
    ) -> list[str]:
        suffix = f"_{self._archive_underlying_key(underlying_security)}.jsonl"
        try:
            return sorted(
                str(entry)[:-len(suffix)]
                for entry in os.listdir(self.live_capture_archive_dir)
                if str(entry).endswith(suffix) and str(entry)[:-len(suffix)]
            )
        except Exception:
            logger.exception("Failed to enumerate live capture archive session dates")
            return []

    def _load_live_capture_archive_latest_workbook_value_unlocked(
        self,
        *,
        session_date: str,
        underlying_security: str,
        security: str,
    ) -> dict[str, Any] | None:
        archive_path = self._live_capture_archive_path(
            session_date=session_date,
            underlying_security=underlying_security,
        )
        if not os.path.exists(archive_path):
            return None

        try:
            with open(archive_path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                position = handle.tell()
                buffer = b""
                while position > 0:
                    read_size = min(8192, position)
                    position -= read_size
                    handle.seek(position)
                    buffer = handle.read(read_size) + buffer
                    lines = buffer.splitlines()
                    if position > 0:
                        buffer = lines[0] if lines else b""
                        lines = lines[1:] if len(lines) > 1 else []
                    else:
                        buffer = b""

                    for raw_line in reversed(lines):
                        raw = raw_line.decode("utf-8", errors="ignore").strip()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        raw_value, daily_change_pct = self._workbook_pair_from_disk(
                            payload.get("workbook_values") or {},
                            security,
                        )
                        if raw_value is None:
                            continue
                        captured_at = payload.get("captured_at") or payload.get("current_price_timestamp")
                        if not captured_at:
                            continue
                        resolved_session_date = str(payload.get("session_date") or session_date or "").strip()
                        return {
                            "date": resolved_session_date,
                            "session_date": resolved_session_date,
                            "captured_at": captured_at,
                            "security": security,
                            "raw_value": raw_value,
                            "daily_change_pct": daily_change_pct,
                            "underlying_security": underlying_security,
                        }
        except Exception:
            logger.exception("Failed to load latest workbook value from live capture archive")
        return None

    def read_live_capture_snapshots(
        self,
        *,
        session_date: str | None = None,
        underlying_security: str = "IBOVE Index",
    ) -> list[dict[str, Any]]:
        with self._lock:
            state = self._load_state_unlocked()
            history = state.get("live_capture_history") or {}
            resolved_session_date = (
                str(session_date or "").strip()
                or str(history.get("current_session_date") or "").strip()
            )
            recent_snapshots = [
                dict(item or {})
                for item in (history.get("snapshots") or [])
                if str((item or {}).get("underlying_security") or "IBOVE Index") == underlying_security
                and (
                    not resolved_session_date
                    or str((item or {}).get("session_date") or "") == resolved_session_date
                )
            ]
        archived_snapshots = (
            self._load_live_capture_archive_unlocked(
                session_date=resolved_session_date,
                underlying_security=underlying_security,
            )
            if resolved_session_date
            else self._load_all_live_capture_archives_unlocked(
                underlying_security=underlying_security,
            )
        )
        merged: dict[str, dict[str, Any]] = {}
        for snapshot in [*archived_snapshots, *recent_snapshots]:
            captured_at = str((snapshot or {}).get("captured_at") or "").strip()
            if captured_at:
                merged[captured_at] = dict(snapshot or {})
        return sorted(merged.values(), key=lambda item: str(item.get("captured_at") or ""))

    def read_live_capture_workbook_series(
        self,
        *,
        session_date: str,
        underlying_security: str = "IBOVE Index",
        security: str,
        include_recent_state: bool = False,
    ) -> list[dict[str, Any]]:
        resolved_session_date = str(session_date or "").strip()
        if not resolved_session_date:
            return []
        recent_rows: list[dict[str, Any]] = []
        if include_recent_state:
            with self._lock:
                state = self._load_state_unlocked()
                history = state.get("live_capture_history") or {}
                for snapshot in (history.get("snapshots") or []):
                    item = dict(snapshot or {})
                    if str(item.get("underlying_security") or "IBOVE Index") != underlying_security:
                        continue
                    if str(item.get("session_date") or "") != resolved_session_date:
                        continue
                    raw_value, daily_change_pct = self._workbook_pair_from_disk(
                        item.get("workbook_values") or {},
                        security,
                    )
                    if raw_value is None:
                        continue
                    captured_at = item.get("captured_at") or item.get("current_price_timestamp")
                    if not captured_at:
                        continue
                    recent_rows.append({
                        "date": resolved_session_date,
                        "session_date": resolved_session_date,
                        "captured_at": captured_at,
                        "security": security,
                        "raw_value": raw_value,
                        "daily_change_pct": daily_change_pct,
                        "underlying_security": underlying_security,
                    })
        archived_rows = self._load_live_capture_archive_workbook_series_unlocked(
            session_date=resolved_session_date,
            underlying_security=underlying_security,
            security=security,
        )
        merged: dict[str, dict[str, Any]] = {}
        for row in [*archived_rows, *recent_rows]:
            captured_at = str((row or {}).get("captured_at") or "").strip()
            if captured_at:
                merged[captured_at] = dict(row or {})
        return sorted(merged.values(), key=lambda item: str(item.get("captured_at") or ""))

    def read_live_capture_latest_workbook_value(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        security: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            state = self._load_state_unlocked()
            history = state.get("live_capture_history") or {}
            current_session_date = str(history.get("current_session_date") or "").strip()
            candidates: list[dict[str, Any]] = []
            latest_snapshot = dict(history.get("latest_snapshot") or {})
            if latest_snapshot:
                candidates.append(latest_snapshot)
            recent_snapshots = [
                dict(item or {})
                for item in reversed(history.get("snapshots") or [])
                if isinstance(item, dict)
            ]
            candidates.extend(recent_snapshots)

        best_state: dict[str, Any] | None = None
        best_state_dt: datetime | None = None
        for snapshot in candidates:
            if str(snapshot.get("underlying_security") or "IBOVE Index") != underlying_security:
                continue
            raw_value, daily_change_pct = self._workbook_pair_from_disk(
                snapshot.get("workbook_values") or {},
                security,
            )
            if raw_value is None:
                continue
            captured_at = snapshot.get("captured_at") or snapshot.get("current_price_timestamp")
            if not captured_at:
                continue
            session_date = str(snapshot.get("session_date") or str(captured_at)[:10] or "").strip()
            candidate = {
                "date": session_date,
                "session_date": session_date,
                "captured_at": captured_at,
                "security": security,
                "raw_value": raw_value,
                "daily_change_pct": daily_change_pct,
                "underlying_security": underlying_security,
            }
            candidate_dt = _parse_iso(captured_at)
            if best_state is None or (candidate_dt and (best_state_dt is None or candidate_dt >= best_state_dt)):
                best_state = candidate
                best_state_dt = candidate_dt

        archive_sessions: list[str] = []
        if current_session_date:
            archive_sessions.append(current_session_date)
        if best_state:
            best_state_session = str(best_state.get("session_date") or "").strip()
            if best_state_session and best_state_session not in archive_sessions:
                archive_sessions.append(best_state_session)
        for session_date in reversed(self._list_live_capture_archive_session_dates_unlocked(underlying_security=underlying_security)):
            if session_date and session_date not in archive_sessions:
                archive_sessions.append(session_date)
            if len(archive_sessions) >= 3:
                break

        best_archive: dict[str, Any] | None = None
        best_archive_dt: datetime | None = None
        for session_date in archive_sessions:
            candidate = self._load_live_capture_archive_latest_workbook_value_unlocked(
                session_date=session_date,
                underlying_security=underlying_security,
                security=security,
            )
            if not candidate:
                continue
            candidate_dt = _parse_iso(candidate.get("captured_at"))
            if best_archive is None or (candidate_dt and (best_archive_dt is None or candidate_dt >= best_archive_dt)):
                best_archive = candidate
                best_archive_dt = candidate_dt

        if best_state and best_archive:
            if best_archive_dt and (best_state_dt is None or best_archive_dt >= best_state_dt):
                return best_archive
            return best_state
        return best_state or best_archive

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            return _deep_copy_json(self._load_state_unlocked())

    def _read_cached_latest_model_run(
        self,
        underlying_security: str,
        *,
        max_age_seconds: float = 90.0,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        now_ts = time.time()
        if not force_refresh:
            cached = self._latest_model_run_cache.get(underlying_security)
            cached_at = self._latest_model_run_cache_at.get(underlying_security, 0.0)
            if cached is not None and (now_ts - cached_at) <= max_age_seconds:
                return _deep_copy_json(cached)
        payload = self.store.read_latest_model_run(underlying_security) or {}
        self._latest_model_run_cache[underlying_security] = _deep_copy_json(payload)
        self._latest_model_run_cache_at[underlying_security] = now_ts
        return payload

    def _read_cached_latest_fair_value_run(
        self,
        underlying_security: str,
        *,
        max_age_seconds: float = 90.0,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        now_ts = time.time()
        if not force_refresh:
            cached = self._latest_fair_value_run_cache.get(underlying_security)
            cached_at = self._latest_fair_value_run_cache_at.get(underlying_security, 0.0)
            if cached is not None and (now_ts - cached_at) <= max_age_seconds:
                return _deep_copy_json(cached)
        payload = self.store.read_latest_fair_value_run(underlying_security) or {}
        self._latest_fair_value_run_cache[underlying_security] = _deep_copy_json(payload)
        self._latest_fair_value_run_cache_at[underlying_security] = now_ts
        return payload

    def _build_block_tones(
        self,
        summary: dict[str, Any],
        factor_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        block_contributions = (((summary or {}).get("block_contributions") or {}).get("macro_structural") or {})
        grouped: dict[str, dict[str, Any]] = {}
        for row in factor_rows or []:
            block = str(row.get("block") or "other").strip() or "other"
            entry = grouped.setdefault(block, {
                "block": block,
                "count": 0,
                "zscore_sum": 0.0,
                "zscore_abs_sum": 0.0,
                "dominant_factor": None,
                "dominant_abs_zscore": -1.0,
            })
            zscore = _finite_float(row.get("feature_zscore"), 0.0) or 0.0
            entry["count"] += 1
            entry["zscore_sum"] += zscore
            entry["zscore_abs_sum"] += abs(zscore)
            if abs(zscore) >= float(entry["dominant_abs_zscore"]):
                entry["dominant_factor"] = row.get("label") or row.get("factor")
                entry["dominant_abs_zscore"] = abs(zscore)
        result: list[dict[str, Any]] = []
        for block, entry in grouped.items():
            count = max(int(entry["count"]), 1)
            avg_zscore = float(entry["zscore_sum"]) / count
            intensity = min(100.0, (float(entry["zscore_abs_sum"]) / count) * 18.0)
            contribution_points = _finite_float(block_contributions.get(block), 0.0) or 0.0
            tone = "buy" if contribution_points > 0 else "sell" if contribution_points < 0 else "neutral"
            commentary = (
                f"{block} com contribuicao {contribution_points:+.1f} pts, "
                f"zscore medio {avg_zscore:+.2f} e fator dominante {entry['dominant_factor'] or '--'}."
            )
            result.append({
                "block": block,
                "contribution_points": round(contribution_points, 2),
                "avg_zscore": round(avg_zscore, 3),
                "intensity_score": round(intensity, 2),
                "dominant_factor": entry["dominant_factor"],
                "factor_count": count,
                "tone": tone,
                "commentary": commentary,
            })
        result.sort(key=lambda item: abs(float(item.get("contribution_points") or 0.0)), reverse=True)
        return result

    def _sample_from_fair_value_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = payload.get("summary") or {}
        factor_rows = summary.get("live_factor_rows") or []
        block_tones = self._build_block_tones(summary, factor_rows)
        us_rates_context = summary.get("us_rates_context") or {}
        fair_value_model_version = (
            "fair_value_ois_v2"
            if summary.get("us_ois_short_factor") or summary.get("us_ois_long_factor") or us_rates_context
            else "fair_value_legacy_v1"
        )
        current_future = _finite_float(summary.get("current_future_price"), 0.0) or 0.0
        fair_value = _finite_float(summary.get("fair_value_final_future"), 0.0) or 0.0
        mispricing_value = _finite_float(summary.get("mispricing_value"))
        if mispricing_value is None and current_future and fair_value:
            mispricing_value = current_future - fair_value
        mispricing_pct = _finite_float(summary.get("mispricing_pct"))
        if mispricing_pct is None and fair_value:
            mispricing_pct = (mispricing_value or 0.0) / fair_value
        quality_ribbon = summary.get("quality_ribbon") or {}
        core_legs = summary.get("core_legs") or {}
        shadow_legs = summary.get("shadow_legs") or {}
        return {
            "captured_at": payload.get("captured_at") or _now_iso(),
            "session_date": payload.get("session_date"),
            "anchor_xb1": _finite_float(summary.get("anchor_xb1")),
            "session_anchor_xb1": _finite_float(summary.get("session_anchor_xb1")),
            "anchor_type": summary.get("anchor_type"),
            "intraday_anchor_type": summary.get("intraday_anchor_type"),
            "model_mode": summary.get("model_mode"),
            "current_future_price": current_future or None,
            "current_spot_price": _finite_float(summary.get("current_spot_price")),
            "live_basis_points": _finite_float(summary.get("live_basis_points")),
            "live_basis_pct": _finite_float(summary.get("live_basis_pct")),
            "fair_value_structural_future": _finite_float(summary.get("fair_value_structural_future")),
            "fair_value_intraday_anchor_future": _finite_float(summary.get("fair_value_intraday_anchor_future")),
            "fair_value_state_space_future": _finite_float(summary.get("fair_value_state_space_future")),
            "fair_value_tactical_future": _finite_float(summary.get("fair_value_tactical_future")),
            "fair_value_final_future": _finite_float(summary.get("fair_value_final_future")),
            "core_fair_value_xb1": _finite_float(summary.get("core_fair_value_xb1")),
            "quality_adjusted_fair_value_xb1": _finite_float(summary.get("quality_adjusted_fair_value_xb1")),
            "shadow_haircut_points": _finite_float(summary.get("shadow_haircut_points")),
            "fair_value_band_low": _finite_float(summary.get("fair_value_band_low")),
            "fair_value_band_high": _finite_float(summary.get("fair_value_band_high")),
            "mispricing_value": mispricing_value,
            "mispricing_pct": mispricing_pct,
            "mispricing_zscore": _finite_float(summary.get("mispricing_zscore")),
            "confidence": _finite_float(summary.get("confidence")),
            "risk_quality_score": _finite_float(summary.get("risk_quality_score")),
            "implicit_sentiment": summary.get("implicit_sentiment"),
            "sentiment_confidence": _finite_float(summary.get("sentiment_confidence")),
            "core_shadow_alignment": _finite_float(summary.get("core_shadow_alignment")),
            "divergence_score": _finite_float(summary.get("divergence_score")),
            "coherence_score": _finite_float(summary.get("coherence_score")),
            "convergence_probability": _finite_float(summary.get("convergence_probability")),
            "regime_break_probability": _finite_float(summary.get("regime_break_probability")),
            "quality_gauge": _finite_float(summary.get("quality_gauge")),
            "quality_ribbon": {
                "upper": _finite_float(quality_ribbon.get("upper")),
                "lower": _finite_float(quality_ribbon.get("lower")),
                "width": _finite_float(quality_ribbon.get("width")),
                "asymmetry": _finite_float(quality_ribbon.get("asymmetry")),
                "reason": quality_ribbon.get("reason"),
            },
            "curve_conditions": summary.get("curve_conditions") or {},
            "core_legs": core_legs,
            "shadow_legs": shadow_legs,
            "ranking_up": summary.get("ranking_up") or [],
            "ranking_down": summary.get("ranking_down") or [],
            "quality_explanation": summary.get("explanation") or {},
            "market_regime": summary.get("market_regime"),
            "dealer_pressure_state": summary.get("dealer_pressure_state"),
            "global_distortion_state": summary.get("global_distortion_state"),
            "residual_sigma_points": _finite_float(summary.get("residual_sigma_points")),
            "factor_expected_returns": summary.get("factor_expected_returns") or {},
            "factor_cumulative_contributions_from_anchor": summary.get("factor_cumulative_contributions_from_anchor") or {},
            "state_space": summary.get("state_space") or {},
            "fair_value_model_version": fair_value_model_version,
            "fair_value_model_label": (
                "fair value OIS enhanced"
                if fair_value_model_version == "fair_value_ois_v2"
                else "fair value legacy"
            ),
            "us_rates_context_state": us_rates_context.get("summary_state"),
            "current_price_source": summary.get("current_price_source"),
            "current_price_timestamp": summary.get("current_price_timestamp"),
            "current_spot_source": summary.get("current_spot_source"),
            "current_spot_timestamp": summary.get("current_spot_timestamp"),
            "block_tones": block_tones,
            "top_factors": summary.get("top_factors") or [],
            "factor_rows": factor_rows[:12],
        }

    @staticmethod
    def _reproject_leg_buckets(sample: dict[str, Any]) -> dict[str, Any]:
        normalized_sample = dict(sample)

        core_legs = dict(normalized_sample.get("core_legs") or {})
        core_reference = (
            _finite_float(normalized_sample.get("core_fair_value_xb1"))
            or _finite_float(normalized_sample.get("fair_value_final_future"))
        )
        isolated_core_reference = (
            _finite_float(normalized_sample.get("current_future_price"))
            or core_reference
        )
        core_total = 0.0
        for leg_payload in core_legs.values():
            if not isinstance(leg_payload, dict):
                continue
            contribution_points = _finite_float(leg_payload.get("contribution_points"))
            if contribution_points is not None:
                core_total += contribution_points
        if core_reference is not None and core_legs:
            core_base_reference = core_reference - core_total
            for leg_key, leg_payload in core_legs.items():
                if not isinstance(leg_payload, dict):
                    continue
                leg_row = dict(leg_payload)
                contribution_points = _finite_float(leg_row.get("contribution_points"))
                if contribution_points is None:
                    continue
                leg_row["model_relative_implied_fair_value_xb1"] = core_base_reference + contribution_points
                if isolated_core_reference is not None:
                    leg_row["isolated_implied_fair_value_xb1"] = isolated_core_reference + contribution_points
                    leg_row["implied_fair_value_xb1"] = isolated_core_reference + contribution_points
                else:
                    leg_row["implied_fair_value_xb1"] = core_base_reference + contribution_points
                core_legs[leg_key] = leg_row
            normalized_sample["core_legs"] = core_legs

        shadow_legs = dict(normalized_sample.get("shadow_legs") or {})
        shadow_reference = (
            _finite_float(normalized_sample.get("quality_adjusted_fair_value_xb1"))
            or _finite_float(normalized_sample.get("core_fair_value_xb1"))
            or _finite_float(normalized_sample.get("fair_value_final_future"))
        )
        isolated_shadow_reference = (
            _finite_float(normalized_sample.get("current_future_price"))
            or shadow_reference
        )
        shadow_total = 0.0
        for leg_payload in shadow_legs.values():
            if not isinstance(leg_payload, dict):
                continue
            quality_impact = _finite_float(leg_payload.get("quality_impact"))
            if quality_impact is not None:
                shadow_total += (quality_impact * 0.65)
        if shadow_reference is not None and shadow_legs:
            shadow_base_reference = shadow_reference - shadow_total
            for leg_key, leg_payload in shadow_legs.items():
                if not isinstance(leg_payload, dict):
                    continue
                leg_row = dict(leg_payload)
                quality_impact = _finite_float(leg_row.get("quality_impact"))
                if quality_impact is None:
                    continue
                leg_row["model_relative_implied_fair_value_xb1"] = shadow_base_reference + (quality_impact * 0.65)
                if isolated_shadow_reference is not None:
                    leg_row["isolated_implied_fair_value_xb1"] = isolated_shadow_reference + (quality_impact * 0.65)
                    leg_row["implied_fair_value_xb1"] = isolated_shadow_reference + (quality_impact * 0.65)
                else:
                    leg_row["implied_fair_value_xb1"] = shadow_base_reference + (quality_impact * 0.65)
                shadow_legs[leg_key] = leg_row
            normalized_sample["shadow_legs"] = shadow_legs

        return normalized_sample

    @staticmethod
    def _shift_projected_fair_value_fields(sample: dict[str, Any], shift_points: float) -> dict[str, Any]:
        if abs(shift_points) <= 1e-9:
            return dict(sample)
        shifted_sample = dict(sample)
        for key in (
            "fair_value_structural_future",
            "fair_value_tactical_future",
            "fair_value_final_future",
            "core_fair_value_xb1",
            "quality_adjusted_fair_value_xb1",
            "fair_value_band_low",
            "fair_value_band_high",
        ):
            value = _finite_float(shifted_sample.get(key))
            if value is not None:
                shifted_sample[key] = value + shift_points
        quality_ribbon = dict(shifted_sample.get("quality_ribbon") or {})
        for key in ("upper", "lower"):
            value = _finite_float(quality_ribbon.get(key))
            if value is not None:
                quality_ribbon[key] = value + shift_points
        if quality_ribbon:
            shifted_sample["quality_ribbon"] = quality_ribbon
        return shifted_sample

    @staticmethod
    def _compact_live_factor_value_map(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
        compact: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            factor = str((row or {}).get("factor") or "").strip()
            if not factor:
                continue
            compact[factor] = {
                "label": (row or {}).get("label"),
                "block": (row or {}).get("block"),
                "source_kind": (row or {}).get("source_kind"),
                "source_key": (row or {}).get("source_key"),
                "raw_value": _finite_float((row or {}).get("raw_value")),
                "daily_change_pct": _finite_float((row or {}).get("daily_change_pct")),
                "timestamp": (row or {}).get("timestamp"),
                "is_live": bool((row or {}).get("is_live")),
                "live_source": (row or {}).get("live_source"),
            }
        return compact

    @staticmethod
    def _compact_workbook_value_map(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
        compact: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            security = str((row or {}).get("security") or "").strip()
            if not security:
                continue
            compact[security] = {
                "raw_value": _finite_float((row or {}).get("price")),
                "daily_change_pct": _finite_float((row or {}).get("daily_change_pct")),
                "timestamp": (row or {}).get("timestamp"),
                "row_number": int((row or {}).get("row_number") or 0),
                "worksheet_name": (row or {}).get("worksheet_name"),
                "fallback_source": (row or {}).get("fallback_source"),
            }
        return compact

    def _build_live_workbook_snapshot(self, underlying_security: str) -> dict[str, Any]:
        workbook_payload = self.fair_value_service.excel_live_workbook.read_fair_value_basket()
        normalized_security_map = dict(workbook_payload.get("normalized_security_map") or {})
        live_future_row = normalized_security_map.get("XB1 INDEX") or {}
        live_spot_row = normalized_security_map.get("IBOV INDEX") or {}

        captured_at = str(workbook_payload.get("captured_at") or _now_iso())
        session_date = datetime.now(LOCAL_TZ).date().isoformat()
        workbook_values = self._compact_workbook_value_map(workbook_payload.get("rows") or [])
        live_future = _finite_float(live_future_row.get("price"))
        live_spot = _finite_float(live_spot_row.get("price"))
        live_basis = (live_future - live_spot) if live_future is not None and live_spot is not None else None
        live_basis_pct = (
            ((live_future - live_spot) / live_spot)
            if live_future is not None and live_spot not in (None, 0.0)
            else None
        )
        return {
            "captured_at": captured_at,
            "session_date": session_date,
            "underlying_security": underlying_security,
            "current_future_price": live_future,
            "current_spot_price": live_spot,
            "live_basis_points": live_basis,
            "live_basis_pct": live_basis_pct,
            "current_price_source": (
                f"live_reference:excel_fair_value_basket:{live_future_row.get('security')}"
                if live_future_row else None
            ),
            "current_price_timestamp": (
                live_future_row.get("timestamp") if live_future_row else None
            ),
            "current_spot_source": (
                f"live_reference:excel_fair_value_basket:{live_spot_row.get('security')}"
                if live_spot_row else None
            ),
            "current_spot_timestamp": (
                live_spot_row.get("timestamp") if live_spot_row else None
            ),
            "source": str(workbook_payload.get("source") or "excel_live_workbook"),
            "row_count": int(workbook_payload.get("row_count") or 0),
            "factor_count": 0,
            "factor_values": {},
            "workbook_value_count": len(workbook_values),
            "workbook_values": workbook_values,
            "ok": bool(workbook_payload.get("ok")),
        }

    @staticmethod
    def _recompute_quote_derived_fields(sample: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(sample or {})
        current_future = _finite_float(normalized.get("current_future_price"))
        current_spot = _finite_float(normalized.get("current_spot_price"))
        fair_value = _finite_float(normalized.get("fair_value_final_future"))
        if current_future is not None and current_spot not in (None, 0.0):
            normalized["live_basis_points"] = current_future - current_spot
            normalized["live_basis_pct"] = (current_future - current_spot) / current_spot
        if current_future is not None and fair_value is not None:
            normalized["mispricing_value"] = current_future - fair_value
            normalized["mispricing_pct"] = ((current_future - fair_value) / fair_value) if fair_value else None
            band_low = _finite_float(normalized.get("fair_value_band_low"))
            band_high = _finite_float(normalized.get("fair_value_band_high"))
            if band_low is not None and band_high is not None:
                band_half_width = max(abs(band_high - band_low) / 2.0, 1.0)
                normalized["mispricing_zscore"] = (current_future - fair_value) / band_half_width
        return normalized

    @staticmethod
    def _recent_live_excel_samples(
        samples: list[dict[str, Any]] | None,
        *,
        reference_dt: datetime | None,
        lookback_minutes: int = 30,
        max_samples: int = 9,
    ) -> list[dict[str, Any]]:
        if reference_dt is None:
            return []
        cutoff = reference_dt - timedelta(minutes=max(lookback_minutes, 5))
        recent: list[dict[str, Any]] = []
        for sample in reversed(samples or []):
            if not _is_live_excel_price_source((sample or {}).get("current_price_source")):
                continue
            sample_dt = _parse_iso((sample or {}).get("captured_at") or (sample or {}).get("current_price_timestamp"))
            if sample_dt is None or sample_dt < cutoff or sample_dt > reference_dt:
                continue
            if _finite_float((sample or {}).get("current_future_price")) is None:
                continue
            recent.append(dict(sample or {}))
            if len(recent) >= max_samples:
                break
        return list(reversed(recent))

    def _stabilize_excel_quote_outlier(
        self,
        sample: dict[str, Any],
        recent_samples: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        sample = dict(sample or {})
        if not _is_live_excel_price_source(sample.get("current_price_source")):
            return sample
        current_future = _finite_float(sample.get("current_future_price"))
        current_spot = _finite_float(sample.get("current_spot_price"))
        current_basis = _finite_float(sample.get("live_basis_points"))
        if current_future is None:
            return sample
        anchors = [dict(item or {}) for item in (recent_samples or []) if _finite_float((item or {}).get("current_future_price")) is not None]
        if len(anchors) < 3:
            return sample

        future_values = [_finite_float(item.get("current_future_price")) for item in anchors]
        future_values = [value for value in future_values if value is not None]
        future_median = _median(future_values)
        future_mad = _median_abs_deviation(future_values, future_median)
        if future_median is None:
            return sample

        basis_values = [_finite_float(item.get("live_basis_points")) for item in anchors]
        basis_values = [value for value in basis_values if value is not None]
        basis_median = _median(basis_values)
        basis_mad = _median_abs_deviation(basis_values, basis_median) if basis_values else None

        future_threshold = max(
            (future_mad or 0.0) * 7.0,
            abs(future_median) * 0.0035,
            750.0,
        )
        basis_threshold = max(
            (basis_mad or 0.0) * 8.0,
            abs(basis_median or 0.0) * 2.5,
            1100.0,
        )
        future_delta = abs(current_future - future_median)
        basis_delta = abs(current_basis - basis_median) if current_basis is not None and basis_median is not None else None

        is_future_outlier = future_delta > future_threshold
        is_basis_outlier = basis_delta is not None and basis_delta > basis_threshold
        if not is_future_outlier and not is_basis_outlier:
            return sample

        fallback = anchors[-1]
        stabilized = dict(sample)
        stabilized["raw_current_future_price"] = current_future
        stabilized["raw_current_spot_price"] = current_spot
        stabilized["raw_live_basis_points"] = current_basis
        stabilized["quote_outlier_filtered"] = True
        stabilized["quote_outlier_reason"] = (
            f"future_delta={future_delta:.1f}>{future_threshold:.1f}; "
            f"basis_delta={(basis_delta if basis_delta is not None else 0.0):.1f}>{basis_threshold:.1f}"
        )
        if is_future_outlier:
            stabilized["current_future_price"] = _finite_float(fallback.get("current_future_price"))
            stabilized["current_price_source"] = fallback.get("current_price_source") or stabilized.get("current_price_source")
            stabilized["current_price_timestamp"] = fallback.get("current_price_timestamp") or stabilized.get("current_price_timestamp")
        stabilized["current_spot_price"] = _finite_float(fallback.get("current_spot_price"))
        stabilized["current_spot_source"] = fallback.get("current_spot_source") or stabilized.get("current_spot_source")
        stabilized["current_spot_timestamp"] = fallback.get("current_spot_timestamp") or stabilized.get("current_spot_timestamp")
        stabilized = self._recompute_quote_derived_fields(stabilized)
        logger.warning(
            "Filtered live Excel quote outlier for %s at %s: future=%s median=%.2f threshold=%.2f basis=%s basis_median=%s",
            sample.get("underlying_security") or "IBOVE Index",
            sample.get("captured_at"),
            current_future,
            future_median,
            future_threshold,
            current_basis,
            basis_median,
        )
        return stabilized

    @staticmethod
    def _normalize_value_payload(
        payload: Any,
        *,
        snapshot_timestamp: Any = None,
    ) -> dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, (list, tuple)):
            return {
                "raw_value": _finite_float(payload[0] if len(payload) >= 1 else None),
                "daily_change_pct": _finite_float(payload[1] if len(payload) >= 2 else None),
                "timestamp": snapshot_timestamp,
            }
        return {}

    def _stabilize_factor_values_with_previous_snapshot(
        self,
        sample: dict[str, Any],
        previous_sample: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sample = dict(sample or {})
        current_factor_values = sample.get("factor_values")
        previous_factor_values = (previous_sample or {}).get("factor_values")
        if not isinstance(current_factor_values, dict) or not current_factor_values:
            return sample
        if not isinstance(previous_factor_values, dict) or not previous_factor_values:
            return sample

        current_session_date = str(sample.get("session_date") or datetime.now(LOCAL_TZ).date().isoformat())
        captured_at = _parse_iso(sample.get("captured_at") or sample.get("current_price_timestamp"))
        staleness_cutoff = timedelta(minutes=20)
        stabilized_values: dict[str, dict[str, Any]] = {}
        replaced_factors: list[str] = []

        def _has_factor_value(payload: dict[str, Any] | None) -> bool:
            payload = payload or {}
            return any(
                _finite_float(payload.get(key)) is not None
                for key in ("raw_value", "daily_change_pct")
            )

        def _should_prefer_previous(current_value: dict[str, Any], previous_value: dict[str, Any]) -> bool:
            if not _has_factor_value(previous_value):
                return False
            previous_session = _session_date_from_timestamp(previous_value.get("timestamp"))
            if previous_session != current_session_date:
                return False

            current_timestamp = _parse_iso(current_value.get("timestamp"))
            previous_timestamp = _parse_iso(previous_value.get("timestamp"))
            current_session = _session_date_from_timestamp(current_value.get("timestamp"))

            if not _has_factor_value(current_value):
                return True
            if current_session and current_session != current_session_date:
                return True
            if current_timestamp is None:
                return True
            if previous_timestamp is not None and current_timestamp < previous_timestamp - timedelta(seconds=1):
                return True
            if captured_at is not None and (captured_at - current_timestamp) > staleness_cutoff:
                return True
            return False

        for factor, current_payload in current_factor_values.items():
            current_value = self._normalize_value_payload(
                current_payload,
                snapshot_timestamp=sample.get("captured_at") or sample.get("current_price_timestamp"),
            )
            previous_value = self._normalize_value_payload(
                previous_factor_values.get(factor),
                snapshot_timestamp=(previous_sample or {}).get("captured_at") or (previous_sample or {}).get("current_price_timestamp"),
            )
            if _should_prefer_previous(current_value, previous_value):
                stabilized_values[str(factor)] = previous_value
                replaced_factors.append(str(factor))
            else:
                stabilized_values[str(factor)] = current_value

        sample["factor_values"] = stabilized_values
        sample["factor_count"] = len(stabilized_values)
        if replaced_factors:
            sample["factor_value_stale_replacements"] = replaced_factors
        return sample

    def _stabilize_workbook_values_with_previous_snapshot(
        self,
        sample: dict[str, Any],
        previous_sample: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sample = dict(sample or {})
        current_values = sample.get("workbook_values")
        previous_values = (previous_sample or {}).get("workbook_values")
        if not isinstance(current_values, dict) or not current_values:
            if isinstance(previous_values, dict) and previous_values:
                sample["workbook_values"] = dict(previous_values)
                sample["workbook_value_count"] = len(sample["workbook_values"])
            return sample
        if not isinstance(previous_values, dict) or not previous_values:
            return sample

        stabilized_values: dict[str, dict[str, Any]] = {}
        for security, current_payload in current_values.items():
            current_value = self._normalize_value_payload(
                current_payload,
                snapshot_timestamp=sample.get("captured_at") or sample.get("current_price_timestamp"),
            )
            previous_value = self._normalize_value_payload(
                previous_values.get(security),
                snapshot_timestamp=(previous_sample or {}).get("captured_at") or (previous_sample or {}).get("current_price_timestamp"),
            )
            has_current = (
                _finite_float(current_value.get("raw_value")) is not None
                or _finite_float(current_value.get("daily_change_pct")) is not None
            )
            if has_current:
                stabilized_values[str(security)] = current_value
            elif previous_value:
                stabilized_values[str(security)] = previous_value
            else:
                stabilized_values[str(security)] = current_value

        for security, previous_payload in previous_values.items():
            if security in stabilized_values:
                continue
            stabilized_values[str(security)] = self._normalize_value_payload(
                previous_payload,
                snapshot_timestamp=(previous_sample or {}).get("captured_at") or (previous_sample or {}).get("current_price_timestamp"),
            )

        sample["workbook_values"] = stabilized_values
        sample["workbook_value_count"] = len(stabilized_values)
        return sample

    def _build_live_capture_sample(
        self,
        underlying_security: str,
        live_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        latest_run = self._read_cached_latest_fair_value_run(underlying_security) or {}
        latest_summary = latest_run.get("summary") or {}
        live_snapshot = dict(live_snapshot or self._build_live_workbook_snapshot(underlying_security))

        if latest_run:
            sample = self._sample_from_fair_value_payload(latest_run)
        else:
            sample = {
                "captured_at": str(live_snapshot.get("captured_at") or _now_iso()),
                "session_date": str(
                    live_snapshot.get("session_date")
                    or datetime.now(LOCAL_TZ).date().isoformat()
                ),
                "current_future_price": None,
                "current_spot_price": None,
                "live_basis_points": None,
                "live_basis_pct": None,
                "fair_value_structural_future": None,
                "fair_value_tactical_future": None,
                "fair_value_final_future": None,
                "core_fair_value_xb1": None,
                "quality_adjusted_fair_value_xb1": None,
                "fair_value_band_low": None,
                "fair_value_band_high": None,
                "mispricing_value": None,
                "mispricing_pct": None,
                "mispricing_zscore": None,
                "confidence": None,
                "risk_quality_score": None,
                "implicit_sentiment": None,
                "sentiment_confidence": None,
                "core_shadow_alignment": None,
                "divergence_score": None,
                "coherence_score": None,
                "convergence_probability": None,
                "regime_break_probability": None,
                "quality_gauge": None,
                "quality_ribbon": {"upper": None, "lower": None, "width": None, "asymmetry": None, "reason": None},
                "curve_conditions": {},
                "core_legs": {},
                "shadow_legs": {},
                "ranking_up": [],
                "ranking_down": [],
                "quality_explanation": {},
                "market_regime": None,
                "dealer_pressure_state": None,
                "global_distortion_state": None,
                "fair_value_model_version": "fair_value_uninitialized",
                "fair_value_model_label": "fair value aguardando Wyrm",
                "us_rates_context_state": None,
                "current_price_source": None,
                "current_price_timestamp": None,
                "current_spot_source": None,
                "current_spot_timestamp": None,
                "block_tones": [],
                "top_factors": [],
                "factor_rows": [],
            }

        live_future = _finite_float(live_snapshot.get("current_future_price"))
        live_spot = _finite_float(live_snapshot.get("current_spot_price"))
        live_basis = _finite_float(live_snapshot.get("live_basis_points"))
        live_basis_pct = _finite_float(live_snapshot.get("live_basis_pct"))
        base_future = _finite_float(latest_summary.get("current_future_price"))
        base_basis = (
            _finite_float(latest_summary.get("live_basis_points"))
            or _finite_float(latest_summary.get("basis_ibov_xb1"))
            or _finite_float(latest_summary.get("basis_points"))
        )
        shift_points = 0.0
        projection_mode = "static"
        if live_basis is not None and base_basis is not None:
            shift_points = live_basis - base_basis
            projection_mode = "basis_shift"
        elif live_future is not None and base_future is not None:
            shift_points = live_future - base_future
            projection_mode = "future_shift"

        sample = self._shift_projected_fair_value_fields(sample, shift_points)
        sample["captured_at"] = str(live_snapshot.get("captured_at") or _now_iso())
        sample["session_date"] = str(live_snapshot.get("session_date") or datetime.now(LOCAL_TZ).date().isoformat())
        sample["current_future_price"] = live_future if live_future is not None else _finite_float(sample.get("current_future_price"))
        sample["current_spot_price"] = live_spot if live_spot is not None else _finite_float(sample.get("current_spot_price"))
        sample["live_basis_points"] = live_basis if live_basis is not None else _finite_float(sample.get("live_basis_points"))
        sample["live_basis_pct"] = live_basis_pct if live_basis_pct is not None else _finite_float(sample.get("live_basis_pct"))
        sample["current_price_source"] = (
            live_snapshot.get("current_price_source")
            or sample.get("current_price_source")
        )
        sample["current_price_timestamp"] = (
            live_snapshot.get("current_price_timestamp")
            or sample.get("current_price_timestamp")
        )
        sample["current_spot_source"] = (
            live_snapshot.get("current_spot_source")
            or sample.get("current_spot_source")
        )
        sample["current_spot_timestamp"] = (
            live_snapshot.get("current_spot_timestamp")
            or sample.get("current_spot_timestamp")
        )
        sample["projection_mode"] = projection_mode
        sample["options_base_run_id"] = latest_run.get("run_id")
        sample["options_base_captured_at"] = latest_run.get("captured_at")
        sample["sample_origin"] = "live_context_projection"

        sample = self._reproject_leg_buckets(sample)

        fair_value = _finite_float(sample.get("fair_value_final_future"))
        current_future = _finite_float(sample.get("current_future_price"))
        if fair_value is not None and current_future is not None:
            sample["mispricing_value"] = current_future - fair_value
            sample["mispricing_pct"] = ((current_future - fair_value) / fair_value) if fair_value else None
            band_low = _finite_float(sample.get("fair_value_band_low"))
            band_high = _finite_float(sample.get("fair_value_band_high"))
            if band_low is not None and band_high is not None:
                band_half_width = max(abs(band_high - band_low) / 2.0, 1.0)
                sample["mispricing_zscore"] = (current_future - fair_value) / band_half_width

        if live_basis is None:
            current_spot = _finite_float(sample.get("current_spot_price"))
            if current_future is not None and current_spot not in (None, 0.0):
                sample["live_basis_points"] = current_future - current_spot
                sample["live_basis_pct"] = (current_future - current_spot) / current_spot

        return sample

    def _stabilize_sample_with_previous_live_quote(
        self,
        previous_sample: dict[str, Any] | None,
        sample: dict[str, Any],
    ) -> dict[str, Any]:
        previous_sample = previous_sample or {}
        previous_source = previous_sample.get("current_price_source")
        current_source = sample.get("current_price_source")
        if not _is_live_excel_price_source(previous_source):
            return sample
        if _is_live_excel_price_source(current_source):
            return sample

        stabilized = dict(sample)
        previous_future = _finite_float(previous_sample.get("current_future_price"))
        current_future_raw = _finite_float(sample.get("current_future_price"))
        future_delta = (
            (previous_future - current_future_raw)
            if previous_future is not None and current_future_raw is not None
            else None
        )
        stabilized["current_future_price"] = previous_future
        stabilized["current_spot_price"] = _finite_float(previous_sample.get("current_spot_price"))
        stabilized["live_basis_points"] = _finite_float(previous_sample.get("live_basis_points"))
        stabilized["live_basis_pct"] = _finite_float(previous_sample.get("live_basis_pct"))
        stabilized["current_price_source"] = previous_sample.get("current_price_source")
        stabilized["current_price_timestamp"] = previous_sample.get("current_price_timestamp")
        stabilized["current_spot_source"] = previous_sample.get("current_spot_source")
        stabilized["current_spot_timestamp"] = previous_sample.get("current_spot_timestamp")

        if future_delta is not None and abs(future_delta) > 1e-9:
            if _finite_float(stabilized.get("quality_adjusted_fair_value_xb1")) is not None:
                stabilized["quality_adjusted_fair_value_xb1"] = _finite_float(stabilized.get("quality_adjusted_fair_value_xb1")) + future_delta
            quality_ribbon = dict(stabilized.get("quality_ribbon") or {})
            if _finite_float(quality_ribbon.get("upper")) is not None:
                quality_ribbon["upper"] = _finite_float(quality_ribbon.get("upper")) + future_delta
            if _finite_float(quality_ribbon.get("lower")) is not None:
                quality_ribbon["lower"] = _finite_float(quality_ribbon.get("lower")) + future_delta
            if quality_ribbon:
                stabilized["quality_ribbon"] = quality_ribbon

            for leg_bucket_key in ("core_legs", "shadow_legs"):
                leg_bucket = dict(stabilized.get(leg_bucket_key) or {})
                for leg_key, leg_payload in leg_bucket.items():
                    if not isinstance(leg_payload, dict):
                        continue
                    leg_row = dict(leg_payload)
                    implied_value = _finite_float(leg_row.get("implied_fair_value_xb1"))
                    if implied_value is not None:
                        leg_row["implied_fair_value_xb1"] = implied_value + future_delta
                    leg_bucket[leg_key] = leg_row
                stabilized[leg_bucket_key] = leg_bucket

        fair_value = _finite_float(stabilized.get("fair_value_final_future"))
        current_future = _finite_float(stabilized.get("current_future_price"))
        if fair_value is not None and current_future is not None:
            stabilized["mispricing_value"] = current_future - fair_value
            stabilized["mispricing_pct"] = (current_future - fair_value) / fair_value if fair_value else None
            band_low = _finite_float(stabilized.get("fair_value_band_low"))
            band_high = _finite_float(stabilized.get("fair_value_band_high"))
            if band_low is not None and band_high is not None:
                band_half_width = max(abs(band_high - band_low) / 2.0, 1.0)
                stabilized["mispricing_zscore"] = (current_future - fair_value) / band_half_width

        current_spot = _finite_float(stabilized.get("current_spot_price"))
        if current_future is not None and current_spot is not None and current_spot:
            stabilized["live_basis_points"] = current_future - current_spot
            stabilized["live_basis_pct"] = (current_future - current_spot) / current_spot
        return stabilized

    def _stabilize_curve_conditions_with_previous_sample(
        self,
        previous_sample: dict[str, Any] | None,
        sample: dict[str, Any],
    ) -> dict[str, Any]:
        previous_curve = (previous_sample or {}).get("curve_conditions") or {}
        current_curve = (sample or {}).get("curve_conditions") or {}
        if not _is_degraded_curve_snapshot(current_curve):
            return sample
        if not _has_meaningful_curve_snapshot(previous_curve):
            return sample
        stabilized = dict(sample)
        stabilized["curve_conditions"] = _deep_copy_json(previous_curve)
        return stabilized

    @staticmethod
    def _find_latest_trusted_live_sample(samples: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        for sample in reversed(samples or []):
            if _is_live_excel_price_source((sample or {}).get("current_price_source")):
                return dict(sample or {})
        return None

    def _compress_fair_value_samples_for_payload(
        self,
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(samples) <= 180:
            return [_deep_copy_json(item) for item in samples]
        latest_dt = _parse_iso((samples[-1] or {}).get("captured_at"))
        if latest_dt is None:
            return [_deep_copy_json(item) for item in samples[-240:]]
        recent_cutoff = latest_dt - timedelta(minutes=15)
        compressed: list[dict[str, Any]] = []
        for index, sample in enumerate(samples):
            sample_dt = _parse_iso((sample or {}).get("captured_at"))
            keep = False
            if sample_dt is None:
                keep = index >= max(len(samples) - 240, 0)
            elif sample_dt >= recent_cutoff:
                keep = True
            elif index % 15 == 0:
                keep = True
            if keep:
                compressed.append(_deep_copy_json(sample))
        if samples:
            latest_sample = _deep_copy_json(samples[-1])
            if not compressed or compressed[-1].get("captured_at") != latest_sample.get("captured_at"):
                compressed.append(latest_sample)
        return compressed

    def _normalize_fair_value_samples_for_payload(
        self,
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        def _realign_leg_buckets(sample: dict[str, Any]) -> dict[str, Any]:
            normalized_sample = self._reproject_leg_buckets(sample)

            current_future = _finite_float(normalized_sample.get("current_future_price"))
            core_fair_value = _finite_float(normalized_sample.get("core_fair_value_xb1"))
            quality_adjusted = _finite_float(normalized_sample.get("quality_adjusted_fair_value_xb1"))
            band_low = _finite_float(normalized_sample.get("fair_value_band_low"))
            band_high = _finite_float(normalized_sample.get("fair_value_band_high"))
            if (
                current_future is not None
                and current_future > 0
                and
                core_fair_value is not None
                and quality_adjusted is not None
                and band_low is not None
                and band_high is not None
            ):
                band_half_width = max(abs(band_high - band_low) / 2.0, 35.0)
                if core_fair_value > current_future:
                    lower_bound = current_future - (band_half_width * 0.15)
                    upper_bound = core_fair_value + (band_half_width * 0.20)
                elif core_fair_value < current_future:
                    lower_bound = core_fair_value - (band_half_width * 0.20)
                    upper_bound = current_future + (band_half_width * 0.15)
                else:
                    lower_bound = core_fair_value - (band_half_width * 0.20)
                    upper_bound = core_fair_value + (band_half_width * 0.20)
                normalized_sample["quality_adjusted_fair_value_xb1"] = _clamp(
                    quality_adjusted,
                    lower_bound,
                    upper_bound,
                )
            return normalized_sample

        normalized: list[dict[str, Any]] = []
        previous_sample: dict[str, Any] | None = None
        for raw_sample in samples:
            sample = _deep_copy_json(raw_sample)
            recent_excel_samples = self._recent_live_excel_samples(
                normalized,
                reference_dt=_parse_iso(sample.get("captured_at") or sample.get("current_price_timestamp")),
            )
            sample = self._stabilize_excel_quote_outlier(sample, recent_excel_samples)
            trusted_anchor = self._find_latest_trusted_live_sample(normalized) or previous_sample
            if trusted_anchor is not None:
                sample = self._stabilize_sample_with_previous_live_quote(trusted_anchor, sample)
                sample = self._stabilize_curve_conditions_with_previous_sample(trusted_anchor, sample)
            sample = _realign_leg_buckets(sample)

            previous_sample = sample
            normalized.append(sample)
        return normalized

    def _normalize_live_snapshots_for_payload(
        self,
        snapshots: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw_snapshot in snapshots:
            snapshot = _deep_copy_json(raw_snapshot)
            recent_excel_samples = self._recent_live_excel_samples(
                normalized,
                reference_dt=_parse_iso(snapshot.get("captured_at") or snapshot.get("current_price_timestamp")),
            )
            snapshot = self._stabilize_excel_quote_outlier(snapshot, recent_excel_samples)
            previous_snapshot = normalized[-1] if normalized else None
            if previous_snapshot is not None:
                snapshot = self._stabilize_workbook_values_with_previous_snapshot(snapshot, previous_snapshot)
                snapshot = self._stabilize_factor_values_with_previous_snapshot(snapshot, previous_snapshot)
            snapshot = self._recompute_quote_derived_fields(snapshot)
            normalized.append(snapshot)
        return normalized

    def _append_fair_value_sample(self, state: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
        history = dict(state.get("fair_value_history") or {})
        current_session_date = str(sample.get("session_date") or datetime.now(LOCAL_TZ).date().isoformat())
        samples = [dict(item or {}) for item in (history.get("samples") or [])]
        if str(history.get("current_session_date") or "") != current_session_date:
            samples = []
        if (
            str(sample.get("projection_mode") or "") == "full_recalc"
            and str(sample.get("sample_origin") or "") == "live_context_recalculated"
        ):
            samples = [
                item
                for item in samples
                if not (
                    str(item.get("session_date") or current_session_date) == current_session_date
                    and str(item.get("projection_mode") or "") == "basis_shift"
                    and str(item.get("sample_origin") or "") == "live_context_projection"
                )
            ]
        samples.append(sample)
        max_samples = max(int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_LIMIT), 120)
        if len(samples) > max_samples:
            samples = samples[-max_samples:]
        history.update({
            "underlying_security": "IBOVE Index",
            "sample_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
            "max_samples": max_samples,
            "current_session_date": current_session_date,
            "latest_sample": sample,
            "samples": samples,
        })
        state["fair_value_history"] = history
        return state

    def _append_live_capture_snapshot(self, state: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
        if not self._is_valid_live_snapshot(snapshot):
            return state
        history = dict(state.get("live_capture_history") or {})
        current_session_date = str(snapshot.get("session_date") or datetime.now(LOCAL_TZ).date().isoformat())
        snapshots = [dict(item or {}) for item in (history.get("snapshots") or [])]
        if str(history.get("current_session_date") or "") != current_session_date:
            snapshots = []
        self._append_live_capture_archive_unlocked(snapshot)
        snapshots.append(snapshot)
        max_samples = max(2, int(Config.MACRO_OPTIONS_LIVE_CAPTURE_STATE_LIMIT))
        if len(snapshots) > max_samples:
            snapshots = snapshots[-max_samples:]
        history.update({
            "underlying_security": str(snapshot.get("underlying_security") or "IBOVE Index"),
            "sample_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
            "max_samples": max_samples,
            "current_session_date": current_session_date,
            "latest_snapshot": snapshot,
            "snapshots": snapshots,
        })
        state["live_capture_history"] = history
        return state

    @staticmethod
    def _is_valid_live_snapshot(snapshot: dict[str, Any] | None) -> bool:
        snapshot = snapshot or {}
        return bool(snapshot.get("ok")) and _finite_float(snapshot.get("current_future_price")) is not None

    @staticmethod
    def _intraday_correlation_refresh_bucket(captured_at: Any, horizon_minutes: int) -> str:
        parsed = _parse_iso(captured_at)
        if parsed is None:
            return ""
        resolved_horizon = max(int(horizon_minutes), 1)
        floored_minute = (parsed.minute // resolved_horizon) * resolved_horizon
        bucket = parsed.replace(minute=floored_minute, second=0, microsecond=0)
        return bucket.isoformat()

    def _continuous_intraday_correlation_horizons_due(
        self,
        *,
        collector: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> list[int]:
        if not bool(Config.OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_ENABLE):
            return []
        captured_at = snapshot.get("captured_at") or snapshot.get("current_price_timestamp")
        if not captured_at:
            return []
        due: list[int] = []
        refresh_state = dict(collector.get("intraday_correlation_live") or {})
        for horizon_minutes in sorted({
            int(value)
            for value in (Config.OPTIONS_INTRADAY_DEPENDENCY_HORIZONS or [1, 5, 15])
            if int(value) > 0
        }):
            bucket = self._intraday_correlation_refresh_bucket(captured_at, horizon_minutes)
            if not bucket:
                continue
            if str(refresh_state.get(f"{horizon_minutes}m_bucket") or "") == bucket:
                continue
            due.append(horizon_minutes)
        return due

    def _refresh_continuous_intraday_correlation(
        self,
        *,
        collector: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        due_horizons = self._continuous_intraday_correlation_horizons_due(
            collector=collector,
            snapshot=snapshot,
        )
        if not due_horizons:
            return collector
        from .options_fair_value_modeling.intraday_correlation_history_service import (
            refresh_live_pure_intraday_correlation_payloads,
        )

        refreshed = refresh_live_pure_intraday_correlation_payloads(
            store=self.store,
            context_service=self,
            underlying_security=str(snapshot.get("underlying_security") or "IBOVE Index"),
            lookback_days=max(1, int(Config.OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_LOOKBACK_DAYS)),
            horizons=due_horizons,
        )
        refresh_state = dict(collector.get("intraday_correlation_live") or {})
        for item in refreshed:
            horizon_minutes = int(item.get("horizon_minutes") or 0)
            if horizon_minutes <= 0:
                continue
            refresh_state[f"{horizon_minutes}m_bucket"] = self._intraday_correlation_refresh_bucket(
                snapshot.get("captured_at") or snapshot.get("current_price_timestamp"),
                horizon_minutes,
            )
            refresh_state[f"{horizon_minutes}m_series_latest_timestamp"] = item.get("series_latest_timestamp")
            refresh_state[f"{horizon_minutes}m_run_id"] = item.get("run_id")
            refresh_state[f"{horizon_minutes}m_status"] = item.get("status")
        refresh_state["last_refreshed_at"] = _now_iso()
        refresh_state["last_horizons"] = due_horizons
        collector["intraday_correlation_live"] = refresh_state
        return collector

    def _schedule_continuous_intraday_correlation(
        self,
        *,
        snapshot: dict[str, Any],
    ) -> None:
        if not self._is_valid_live_snapshot(snapshot):
            return
        with self._async_lock:
            self._correlation_pending_snapshot = _deep_copy_json(snapshot)
            if self._correlation_worker_thread and self._correlation_worker_thread.is_alive():
                return
            self._correlation_worker_thread = threading.Thread(
                target=self._run_continuous_intraday_correlation_worker,
                daemon=True,
                name="options-intraday-correlation-live",
            )
            self._correlation_worker_thread.start()

    def _run_continuous_intraday_correlation_worker(self) -> None:
        while True:
            with self._async_lock:
                snapshot = _deep_copy_json(self._correlation_pending_snapshot)
                self._correlation_pending_snapshot = None
                if snapshot is None:
                    self._correlation_worker_thread = None
                    return
            try:
                with self._lock:
                    state = self._load_state_unlocked()
                collector = dict(state.get("collector") or {})
                collector["last_intraday_correlation_requested_at"] = _now_iso()
                collector["last_intraday_correlation_error"] = None
                state["collector"] = collector
                state["generated_at"] = _now_iso()
                with self._lock:
                    self._save_state_unlocked(state)
                collector = self._refresh_continuous_intraday_correlation(
                    collector=collector,
                    snapshot=snapshot,
                )
                collector["last_intraday_correlation_error"] = None
                state["collector"] = collector
                state["generated_at"] = _now_iso()
                with self._lock:
                    self._save_state_unlocked(state)
                self._payload_cache = None
                self._payload_cache_at = 0.0
            except Exception as exc:
                logger.exception("Failed to refresh continuous intraday correlation payloads")
                try:
                    with self._lock:
                        state = self._load_state_unlocked()
                    collector = dict(state.get("collector") or {})
                    collector["last_intraday_correlation_error"] = str(exc)
                    state["collector"] = collector
                    state["generated_at"] = _now_iso()
                    with self._lock:
                        self._save_state_unlocked(state)
                except Exception:
                    logger.exception("Failed to persist intraday correlation worker error state")

    def _schedule_fair_value_projection(
        self,
        *,
        underlying_security: str,
        snapshot: dict[str, Any],
    ) -> None:
        if not self._is_valid_live_snapshot(snapshot):
            return
        payload = {
            "underlying_security": str(underlying_security or "IBOVE Index"),
            "snapshot": _deep_copy_json(snapshot),
        }
        with self._async_lock:
            self._fair_value_pending_snapshot = payload
            if self._fair_value_worker_thread and self._fair_value_worker_thread.is_alive():
                return
            self._fair_value_worker_thread = threading.Thread(
                target=self._run_fair_value_projection_worker,
                daemon=True,
                name="options-fair-value-live",
            )
            self._fair_value_worker_thread.start()

    def _run_fair_value_projection_worker(self) -> None:
        while True:
            with self._async_lock:
                pending = _deep_copy_json(self._fair_value_pending_snapshot)
                self._fair_value_pending_snapshot = None
                if pending is None:
                    self._fair_value_worker_thread = None
                    return
            snapshot = dict((pending or {}).get("snapshot") or {})
            underlying_security = str((pending or {}).get("underlying_security") or "IBOVE Index")
            if not self._is_valid_live_snapshot(snapshot):
                continue
            try:
                with self._lock:
                    state = self._load_state_unlocked()
                collector = dict(state.get("collector") or {})
                collector["last_projection_requested_at"] = _now_iso()
                collector["last_projection_error"] = None
                state["collector"] = collector
                state["generated_at"] = _now_iso()
                with self._lock:
                    self._save_state_unlocked(state)
                state = self._project_fair_value_sample_from_snapshot(state, underlying_security, snapshot)
                collector = dict(state.get("collector") or {})
                collector["last_projection_completed_at"] = _now_iso()
                collector["last_projection_error"] = None
                state["collector"] = collector
                latest_model_run = self._read_cached_latest_model_run(underlying_security) or {}
                latest_fair_value_run = self._read_cached_latest_fair_value_run(underlying_security) or {}
                latest_sample = ((state.get("fair_value_history") or {}).get("latest_sample") or {})
                state["gamma_context"] = self._build_gamma_context(
                    underlying_security,
                    latest_model_run,
                    latest_fair_value_run,
                    latest_sample,
                )
                state["generated_at"] = _now_iso()
                with self._lock:
                    self._save_state_unlocked(state, persist_fair_value_history=True)
                self._payload_cache = None
                self._payload_cache_at = 0.0
            except Exception as exc:
                logger.exception("Failed to project async fair value sample from live snapshot")
                try:
                    with self._lock:
                        state = self._load_state_unlocked()
                    collector = dict(state.get("collector") or {})
                    collector["last_projection_error"] = str(exc)
                    state["collector"] = collector
                    state["generated_at"] = _now_iso()
                    with self._lock:
                        self._save_state_unlocked(state)
                except Exception:
                    logger.exception("Failed to persist fair value worker error state")

    def _load_persisted_fair_value_backfill(
        self,
        *,
        session_date: str,
        underlying_security: str,
    ) -> list[dict[str, Any]]:
        manifest_path = getattr(self.store, "fair_value_runs_manifest_path", "")
        if not manifest_path or not os.path.exists(manifest_path):
            return []
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
        except Exception:
            logger.debug("Failed to read fair value manifest for backfill", exc_info=True)
            return []

        runs = manifest.get("runs") or {}
        backfill: list[dict[str, Any]] = []
        for run_id, run_entry in runs.items():
            if not isinstance(run_entry, dict):
                continue
            if str(run_entry.get("session_date") or "") != session_date:
                continue
            if str(run_entry.get("underlying_security") or "") != underlying_security:
                continue
            payload = self.store.read_fair_value_run(str(run_id))
            if not payload:
                continue
            try:
                sample = self._sample_from_fair_value_payload(payload)
            except Exception:
                logger.debug("Failed to convert persisted fair value run to sample", exc_info=True)
                continue
            backfill.append(sample)
        backfill.sort(key=lambda item: str(item.get("captured_at") or ""))
        return backfill

    @staticmethod
    def _estimate_gamma_step(strikes: list[float], current_future_price: float) -> float:
        ordered = sorted({float(value) for value in strikes if _finite_float(value) is not None})
        deltas = [
            ordered[index] - ordered[index - 1]
            for index in range(1, len(ordered))
            if ordered[index] > ordered[index - 1]
        ]
        if deltas:
            positive = sorted(delta for delta in deltas if delta > 0)
            if positive:
                return max(positive[0], 10.0)
        return max(abs(current_future_price) * 0.0012, 40.0)

    @staticmethod
    def _build_price_band(center: float, step: float, multiplier: float = 0.5) -> tuple[float, float]:
        half = max(step * multiplier, 8.0)
        return center - half, center + half

    def _build_gamma_context(
        self,
        underlying_security: str,
        latest_model_run: dict[str, Any] | None,
        latest_fair_value_run: dict[str, Any] | None,
        latest_sample: dict[str, Any] | None,
    ) -> dict[str, Any]:
        latest_model_run = latest_model_run or {}
        latest_fair_value_run = latest_fair_value_run or {}
        latest_sample = latest_sample or {}
        pressure = latest_model_run.get("pressure") or {}
        summary = latest_model_run.get("summary") or {}
        fair_summary = latest_fair_value_run.get("summary") or {}
        market_context = latest_model_run.get("market_context") or {}

        current_future_price = (
            _finite_float(latest_sample.get("current_future_price"))
            or _finite_float(fair_summary.get("current_future_price"))
            or _finite_float(summary.get("forward_price"))
            or _finite_float(market_context.get("forward_price"))
            or 0.0
        )
        current_spot_price = (
            _finite_float(latest_sample.get("current_spot_price"))
            or _finite_float(fair_summary.get("current_spot_price"))
            or _finite_float(summary.get("spot_price"))
            or _finite_float(market_context.get("spot_price"))
            or 0.0
        )
        basis_points = _finite_float(latest_sample.get("live_basis_points"))
        if basis_points is None and current_future_price and current_spot_price:
            basis_points = current_future_price - current_spot_price
        if basis_points is None:
            basis_points = (
                _finite_float(fair_summary.get("live_basis_points"))
                or _finite_float(fair_summary.get("basis_points"))
                or _finite_float(summary.get("future_basis_points"))
                or _finite_float(market_context.get("future_basis_points"))
                or 0.0
            )

        strike_profiles = [dict(item or {}) for item in (latest_model_run.get("strike_profiles") or [])]
        strike_step = self._estimate_gamma_step(
            [float(item.get("strike") or 0.0) for item in strike_profiles if _finite_float(item.get("strike")) is not None],
            current_future_price,
        )
        max_region_score = max(
            (
                abs(_finite_float(item.get("gex_notional_future_net"), 0.0) or 0.0)
                + abs(_finite_float(item.get("open_interest_total"), 0.0) or 0.0) * 10_000.0
            )
            for item in strike_profiles
        ) if strike_profiles else 1.0

        ranked_profiles = sorted(
            strike_profiles,
            key=lambda item: (
                abs(_finite_float(item.get("gex_notional_future_net"), 0.0) or 0.0)
                + abs(_finite_float(item.get("open_interest_total"), 0.0) or 0.0) * 10_000.0
            ),
            reverse=True,
        )[: max(1, int(Config.MACRO_OPTIONS_GAMMA_REGION_LIMIT))]

        regions: list[dict[str, Any]] = []
        for index, row in enumerate(ranked_profiles):
            strike = _finite_float(row.get("strike"))
            if strike is None:
                continue
            price = strike + (basis_points or 0.0)
            band_low, band_high = self._build_price_band(price, strike_step)
            gex_future = _finite_float(row.get("gex_notional_future_net"), 0.0) or 0.0
            gamma_net = _finite_float(row.get("gamma_net"), 0.0) or 0.0
            oi_total = _finite_float(row.get("open_interest_total"), 0.0) or 0.0
            oi_call = _finite_float(row.get("open_interest_call"), 0.0) or 0.0
            oi_put = _finite_float(row.get("open_interest_put"), 0.0) or 0.0
            oi_imbalance = _finite_float(row.get("open_interest_imbalance"), 0.0) or 0.0
            if gex_future > 0:
                gamma_sign = "positive"
                region_type = "positive_gamma"
                role = "pinning_support"
                symbol = "G+"
                description = "Dealer gamma positiva: tende a amortecer o deslocamento e prender o preco se houver liquidez suficiente."
            elif gex_future < 0:
                gamma_sign = "negative"
                region_type = "negative_gamma"
                role = "acceleration_zone"
                symbol = "G-"
                description = "Dealer gamma negativa: risco de aceleracao, chase e deslocamento maior quando o preco invade a regiao."
            else:
                gamma_sign = "balanced"
                region_type = "balanced_gamma"
                role = "inventory_balance"
                symbol = "G0"
                description = "Gamma balanceada: regiao mais neutra, util como referencia de inventario e aceitacao."
            normalized_score = (
                abs(gex_future) + abs(oi_total) * 10_000.0
            ) / max(max_region_score, 1.0)
            relevance_score = _clamp(normalized_score * 100.0, 5.0, 100.0)
            direction_hint = "sell" if oi_imbalance > 0 else "buy" if oi_imbalance < 0 else "neutral"
            commentary = (
                f"{description} OI total {oi_total:,.0f}, calls {oi_call:,.0f}, puts {oi_put:,.0f}, "
                f"gama fut {gex_future:,.0f} e desequilibrio de OI {oi_imbalance:+,.0f}."
            )
            regions.append({
                "region_key": f"gamma-strike-{index}-{int(round(price))}",
                "kind": "strike_region",
                "strike": strike,
                "price": round(price, 2),
                "band_low": round(band_low, 2),
                "band_high": round(band_high, 2),
                "gamma_sign": gamma_sign,
                "region_type": region_type,
                "role": role,
                "symbol": symbol,
                "short_label": f"{symbol} {int(round(price))}",
                "display_label": f"{symbol} {int(round(price))}",
                "description": description,
                "commentary": commentary,
                "relevance_score": round(relevance_score, 2),
                "open_interest_total": oi_total,
                "open_interest_call": oi_call,
                "open_interest_put": oi_put,
                "open_interest_imbalance": oi_imbalance,
                "gamma_net": gamma_net,
                "gex_net": _finite_float(row.get("gex_net"), 0.0) or 0.0,
                "gex_notional_future_net": gex_future,
                "direction_hint": direction_hint,
                "distance_to_current_points": round(price - current_future_price, 2) if current_future_price else None,
            })

        special_regions: list[dict[str, Any]] = []

        def _append_special_region(
            key: str,
            label: str,
            symbol: str,
            role: str,
            price: float | None,
            band_low: float | None = None,
            band_high: float | None = None,
            commentary: str | None = None,
        ) -> None:
            if price is None:
                return
            low = band_low if band_low is not None else price
            high = band_high if band_high is not None else price
            special_regions.append({
                "region_key": key,
                "kind": "special_region",
                "price": round(price, 2),
                "band_low": round(min(low, high), 2),
                "band_high": round(max(low, high), 2),
                "symbol": symbol,
                "short_label": symbol,
                "display_label": label,
                "role": role,
                "description": commentary or label,
                "distance_to_current_points": round(price - current_future_price, 2) if current_future_price else None,
            })

        zero_pressure = pressure.get("zero_pressure") or {}
        zero_pressure_spot = _finite_float(zero_pressure.get("spot"))
        if zero_pressure_spot is not None:
            zero_price = zero_pressure_spot + (basis_points or 0.0)
            _append_special_region(
                "zero-pressure",
                "Zero Pressure",
                "ZP",
                "inventory_balance",
                zero_price,
                commentary="Ponto de equilibrio do pressure curve: acima/abaixo disso o viés de dealer muda.",
            )

        max_acceleration = pressure.get("max_acceleration") or {}
        max_accel_spot = _finite_float(max_acceleration.get("spot"))
        if max_accel_spot is not None:
            accel_price = max_accel_spot + (basis_points or 0.0)
            _append_special_region(
                "max-acceleration",
                "Max Acceleration",
                "ACC",
                "acceleration_zone",
                accel_price,
                commentary="Regiao onde a curvatura do pressure sugere aceleracao maxima do movimento.",
            )

        for band_key, label, symbol, role, commentary in (
            ("pinning_band", "Pinning Band", "PIN", "pinning_support", "Faixa de pinning: dealers tendem a estabilizar o preco enquanto a liquidez permitir."),
            ("acceleration_band", "Acceleration Band", "RUN", "acceleration_zone", "Faixa de aceleracao: risco de chase maior quando o preco invade essa regiao."),
            ("decompression_band", "Decompression Band", "DEC", "vol_release", "Faixa de descompressao: perda de suporte de gama e liberacao de volatilidade."),
        ):
            band_payload = pressure.get(band_key) or {}
            low_spot = _finite_float(band_payload.get("low"))
            high_spot = _finite_float(band_payload.get("high"))
            if low_spot is None and high_spot is None:
                continue
            low_price = (low_spot if low_spot is not None else high_spot) + (basis_points or 0.0)
            high_price = (high_spot if high_spot is not None else low_spot) + (basis_points or 0.0)
            center = (low_price + high_price) / 2.0
            _append_special_region(
                band_key,
                label,
                symbol,
                role,
                center,
                low_price,
                high_price,
                commentary=commentary,
            )

        special_regions.sort(key=lambda item: abs(_finite_float(item.get("distance_to_current_points"), 0.0) or 0.0))
        regions.sort(key=lambda item: abs(_finite_float(item.get("distance_to_current_points"), 0.0) or 0.0))

        fair_value_final = _finite_float(latest_sample.get("fair_value_final_future"))
        if fair_value_final is None:
            fair_value_final = _finite_float(fair_summary.get("fair_value_final_future"))
        return {
            "underlying_security": underlying_security,
            "latest_model_run_id": latest_model_run.get("run_id"),
            "latest_model_captured_at": latest_model_run.get("captured_at"),
            "current_future_price": current_future_price or None,
            "current_spot_price": current_spot_price or None,
            "basis_points": basis_points,
            "basis_pct": ((basis_points or 0.0) / current_spot_price) if current_spot_price else None,
            "fair_value_price": fair_value_final,
            "regions": regions,
            "special_regions": special_regions,
            "summary": {
                "region_count": len(regions),
                "special_region_count": len(special_regions),
                "nearest_region": regions[0] if regions else None,
                "nearest_special_region": special_regions[0] if special_regions else None,
                "strike_step": strike_step,
            },
        }

    @staticmethod
    def _merge_async_collector_fields(
        collector: dict[str, Any] | None,
        latest_collector: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(collector or {})
        latest_collector = dict(latest_collector or {})

        local_projection_anchor = max(
            _parse_iso(merged.get("last_projection_completed_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _parse_iso(merged.get("last_projection_requested_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        latest_projection_anchor = max(
            _parse_iso(latest_collector.get("last_projection_completed_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _parse_iso(latest_collector.get("last_projection_requested_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        if latest_projection_anchor >= local_projection_anchor:
            for key in (
                "last_projection_requested_at",
                "last_projection_completed_at",
                "last_projection_error",
            ):
                if key in latest_collector:
                    merged[key] = latest_collector.get(key)

        local_corr_live = dict(merged.get("intraday_correlation_live") or {})
        latest_corr_live = dict(latest_collector.get("intraday_correlation_live") or {})
        local_corr_anchor = max(
            _parse_iso(local_corr_live.get("last_refreshed_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _parse_iso(merged.get("last_intraday_correlation_requested_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        latest_corr_anchor = max(
            _parse_iso(latest_corr_live.get("last_refreshed_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _parse_iso(latest_collector.get("last_intraday_correlation_requested_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        if latest_corr_anchor >= local_corr_anchor:
            for key in (
                "last_intraday_correlation_requested_at",
                "last_intraday_correlation_error",
                "intraday_correlation_live",
            ):
                if key in latest_collector:
                    merged[key] = latest_collector.get(key)

        return merged

    def _should_capture_live_snapshot(
        self,
        state: dict[str, Any],
        local_now: datetime,
        force: bool = False,
    ) -> bool:
        if force:
            return True
        history = state.get("live_capture_history") or {}
        latest_snapshot = history.get("latest_snapshot") or {}
        captured_at = _parse_iso(latest_snapshot.get("captured_at"))
        if captured_at is None:
            return True
        interval_seconds = max(2, int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS))
        return (local_now.astimezone(timezone.utc) - captured_at).total_seconds() >= interval_seconds

    def _should_capture_fair_value_sample(
        self,
        state: dict[str, Any],
        local_now: datetime,
        force: bool = False,
    ) -> bool:
        if force:
            return True
        history = state.get("fair_value_history") or {}
        latest_sample = history.get("latest_sample") or {}
        captured_at = _parse_iso(latest_sample.get("captured_at"))
        if captured_at is None:
            return True
        interval_seconds = max(2, int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS))
        return (local_now.astimezone(timezone.utc) - captured_at).total_seconds() >= interval_seconds

    def _should_run_wyrm(
        self,
        state: dict[str, Any],
        local_now: datetime,
        force: bool = False,
    ) -> bool:
        if force:
            return True
        if not bool(Config.OPTIONS_WYRM_AUTORUN_ENABLE):
            return False
        target_hour = max(0, min(23, int(Config.OPTIONS_WYRM_AUTORUN_HOUR)))
        target_minute = max(0, min(59, int(Config.OPTIONS_WYRM_AUTORUN_MINUTE)))
        if (local_now.hour, local_now.minute) < (target_hour, target_minute):
            return False
        collector = state.get("collector") or {}
        last_trade_date = str(collector.get("last_wyrm_trade_date") or "")
        if last_trade_date >= local_now.date().isoformat():
            # Ja rodou com sucesso hoje
            return False
        # Respeita cooldown entre tentativas falhas para evitar loop infinito
        # quando Bloomberg nao retorna opcoes (ex: WORKFLOW_REVIEW_NEEDED)
        last_attempt_iso = str(collector.get("last_wyrm_attempt_at") or "")
        if last_attempt_iso:
            try:
                last_attempt_dt = datetime.fromisoformat(last_attempt_iso.replace("Z", "+00:00"))
                if last_attempt_dt.tzinfo is None:
                    last_attempt_dt = last_attempt_dt.replace(tzinfo=timezone.utc)
                elapsed = (local_now.astimezone(timezone.utc) - last_attempt_dt).total_seconds()
                cooldown = max(60, int(Config.OPTIONS_WYRM_RETRY_COOLDOWN_SECONDS))
                if elapsed < cooldown:
                    return False
            except Exception:
                pass
        return True

    def _bloomberg_ready_for_wyrm(self) -> bool:
        status = self.bloomberg_service.status()
        return bool(
            status.get("enabled")
            and status.get("blpapi_available")
            and status.get("tcp_available")
        )

    def _run_wyrm_for_underlying(self, underlying_security: str) -> dict[str, Any]:
        snapshot_capture = self.snapshot_service.collect_critical_snapshot(underlying_security)
        batch = snapshot_capture.get("batch") or {}
        session_date = str(batch.get("session_date") or "").strip()
        batch_key = str(batch.get("batch_key") or "").strip()
        if not session_date or not batch_key:
            raise ValueError(f"Critical snapshot batch missing for {underlying_security}")
        snapshot_payload = self.store.read_snapshot_batch("critical", session_date, batch_key)
        if not snapshot_payload:
            raise ValueError(f"Unable to reload critical snapshot payload for {underlying_security}")

        model_run = self.modeling_service.run_from_snapshot_payload(snapshot_payload, persist=True)
        global_run = self.global_service.run_latest(
            underlying_security=underlying_security,
            refresh_local_model=False,
            persist=True,
        )
        fair_value_run = self.fair_value_service.run_latest(
            underlying_security=underlying_security,
            refresh_options_model=False,
            refresh_global_overlay=False,
            persist=True,
            workbook_only=False,
        )
        self._latest_model_run_cache[underlying_security] = _deep_copy_json(model_run)
        self._latest_model_run_cache_at[underlying_security] = time.time()
        self._latest_fair_value_run_cache[underlying_security] = _deep_copy_json(fair_value_run)
        self._latest_fair_value_run_cache_at[underlying_security] = time.time()
        return {
            "captured_at": _now_iso(),
            "snapshot_batch": snapshot_payload.get("batch") or {},
            "model_run": {
                "run_id": model_run.get("run_id"),
                "captured_at": model_run.get("captured_at"),
            },
            "global_run": {
                "run_id": global_run.get("run_id"),
                "captured_at": global_run.get("captured_at"),
            },
            "fair_value_run": {
                "run_id": fair_value_run.get("run_id"),
                "captured_at": fair_value_run.get("captured_at"),
            },
        }

    def _capture_live_workbook_snapshot(self, state: dict[str, Any], underlying_security: str) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshot = self._build_live_workbook_snapshot(underlying_security)
        history = state.get("live_capture_history") or {}
        latest_snapshot = history.get("latest_snapshot") or {}
        recent_snapshots = self._recent_live_excel_samples(
            history.get("snapshots") or [],
            reference_dt=_parse_iso(snapshot.get("captured_at") or snapshot.get("current_price_timestamp")),
        )
        snapshot = self._stabilize_excel_quote_outlier(snapshot, recent_snapshots)
        snapshot = self._stabilize_workbook_values_with_previous_snapshot(snapshot, latest_snapshot)
        snapshot = self._stabilize_factor_values_with_previous_snapshot(snapshot, latest_snapshot)
        state = self._append_live_capture_snapshot(state, snapshot)
        return state, snapshot

    def _project_fair_value_sample_from_snapshot(
        self,
        state: dict[str, Any],
        underlying_security: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        history = state.get("fair_value_history") or {}
        history_samples = [dict(item or {}) for item in (history.get("samples") or [])]
        previous_sample = (history.get("latest_sample") or {})
        previous_live_sample = self._find_latest_trusted_live_sample(history_samples) or previous_sample
        sample: dict[str, Any]
        try:
            payload = self.fair_value_service.run_latest(
                underlying_security=underlying_security,
                refresh_options_model=False,
                refresh_global_overlay=False,
                persist=False,
                workbook_only=True,
            )
            sample = self._sample_from_fair_value_payload(payload)
            sample["captured_at"] = str(snapshot.get("captured_at") or sample.get("captured_at") or _now_iso())
            sample["session_date"] = str(snapshot.get("session_date") or sample.get("session_date") or datetime.now(LOCAL_TZ).date().isoformat())
            sample["options_base_run_id"] = (((payload.get("source") or {}).get("fair_value_run_id")) or payload.get("run_id"))
            sample["options_base_captured_at"] = payload.get("captured_at")
            sample["projection_mode"] = "full_recalc"
            sample["sample_origin"] = "live_context_recalculated"
            for key in (
                "current_future_price",
                "current_spot_price",
                "live_basis_points",
                "live_basis_pct",
                "current_price_source",
                "current_price_timestamp",
                "current_spot_source",
                "current_spot_timestamp",
            ):
                snapshot_value = snapshot.get(key)
                if snapshot_value not in (None, ""):
                    sample[key] = snapshot_value
            current_future = _finite_float(sample.get("current_future_price"))
            fair_value = _finite_float(sample.get("fair_value_final_future"))
            if current_future is not None and fair_value is not None:
                sample["mispricing_value"] = current_future - fair_value
                sample["mispricing_pct"] = ((current_future - fair_value) / fair_value) if fair_value else None
                band_low = _finite_float(sample.get("fair_value_band_low"))
                band_high = _finite_float(sample.get("fair_value_band_high"))
                if band_low is not None and band_high is not None:
                    band_half_width = max(abs(band_high - band_low) / 2.0, 1.0)
                    sample["mispricing_zscore"] = (current_future - fair_value) / band_half_width
            sample = self._reproject_leg_buckets(sample)
        except Exception:
            logger.exception("Failed to fully recalculate live fair value sample; falling back to projection mode")
            sample = self._build_live_capture_sample(underlying_security, snapshot)
        sample = self._stabilize_sample_with_previous_live_quote(previous_live_sample, sample)
        sample = self._stabilize_curve_conditions_with_previous_sample(previous_live_sample, sample)
        return self._append_fair_value_sample(state, sample)

    def collector_status(self) -> dict[str, Any]:
        with self._lock:
            return _deep_copy_json((self._load_state_unlocked().get("collector") or {}))

    def capture_once(
        self,
        *,
        force_wyrm: bool = False,
        force_fair_value: bool = False,
        allow_scheduled_wyrm: bool = True,
    ) -> dict[str, Any]:
        with self._capture_lock:
            with self._lock:
                state = self._load_state_unlocked()
                collector = dict(state.get("collector") or {})
                collector.update({
                    "enabled": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE),
                    "auto_start": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START),
                    "loop_seconds": int(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS),
                    "live_capture_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
                    "fair_value_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
                    "underlyings": self._scheduled_underlyings(),
                    "running": True,
                    "last_error": None,
                    "last_started_at": collector.get("last_started_at") or _now_iso(),
                })
                state["collector"] = collector

            local_now = datetime.now(LOCAL_TZ)
            primary_underlying = collector["underlyings"][0] if collector.get("underlyings") else "IBOVE Index"

            try:
                scheduled_wyrm_due = (
                    allow_scheduled_wyrm and self._should_run_wyrm(state, local_now, force=False)
                )
                should_run_wyrm = force_wyrm or scheduled_wyrm_due
                if should_run_wyrm:
                    if scheduled_wyrm_due and not force_wyrm and not self._bloomberg_ready_for_wyrm():
                        logger.info(
                            "Scheduled Wyrm run is waiting for Bloomberg connectivity to return before running."
                        )
                    else:
                        try:
                            wyrm_result = self._run_wyrm_for_underlying(primary_underlying)
                            collector.update({
                                "last_wyrm_run_at": wyrm_result.get("captured_at"),
                                "last_wyrm_trade_date": local_now.date().isoformat(),
                                "last_wyrm_attempt_at": _now_iso(),
                                "last_wyrm_model_run_id": ((wyrm_result.get("model_run") or {}).get("run_id")),
                                "last_wyrm_global_run_id": ((wyrm_result.get("global_run") or {}).get("run_id")),
                                "last_wyrm_fair_value_run_id": ((wyrm_result.get("fair_value_run") or {}).get("run_id")),
                            })
                            state["collector"] = collector
                        except Exception as exc:
                            err_msg = str(exc)
                            collector["last_error"] = err_msg
                            collector["last_wyrm_attempt_at"] = _now_iso()
                            state["collector"] = collector
                            # "No eligible options" indica Bloomberg sem dados (ex: WORKFLOW_REVIEW_NEEDED).
                            # Usa warning em vez de exception para nao poluir o log com stack traces.
                            no_options = "No eligible options" in err_msg or "eligible options" in err_msg.lower()
                            if no_options:
                                logger.warning(
                                    "Wyrm autorun: Bloomberg nao retornou opcoes para %s (%s). "
                                    "Proximo retry em %ds. Verifique permissoes Bloomberg (WFBS).",
                                    primary_underlying,
                                    err_msg,
                                    Config.OPTIONS_WYRM_RETRY_COOLDOWN_SECONDS,
                                )
                            else:
                                logger.exception("Wyrm autorun failed; continuing with live snapshot capture")

                live_snapshot: dict[str, Any] | None = None
                if self._should_capture_live_snapshot(state, local_now, force=force_fair_value):
                    state, live_snapshot = self._capture_live_workbook_snapshot(state, primary_underlying)
                    if self._is_valid_live_snapshot(live_snapshot):
                        collector["last_live_snapshot_at"] = live_snapshot.get("captured_at")
                        collector["last_error"] = None
                        collector["last_completed_at"] = _now_iso()
                        state["collector"] = collector
                        state["generated_at"] = collector["last_completed_at"]
                        with self._lock:
                            self._save_state_unlocked(state)
                        self._schedule_continuous_intraday_correlation(snapshot=live_snapshot)
                        self._schedule_fair_value_projection(
                            underlying_security=primary_underlying,
                            snapshot=live_snapshot,
                        )
                        self._payload_cache = None
                        self._payload_cache_at = 0.0
                    else:
                        collector["last_error"] = "live_workbook_snapshot_invalid"
                        collector["last_projection_error"] = "live_workbook_snapshot_invalid"
                        state["collector"] = collector

                if force_fair_value:
                    if not self._is_valid_live_snapshot(live_snapshot):
                        live_snapshot = dict(
                            ((state.get("live_capture_history") or {}).get("latest_snapshot") or {})
                        )
                    if self._is_valid_live_snapshot(live_snapshot):
                        state = self._project_fair_value_sample_from_snapshot(state, primary_underlying, live_snapshot)
                        collector["last_projection_completed_at"] = _now_iso()
                        collector["last_projection_error"] = None
                        state["collector"] = collector

                latest_model_run = self._read_cached_latest_model_run(primary_underlying) or {}
                latest_fair_value_run = self._read_cached_latest_fair_value_run(primary_underlying) or {}
                latest_sample = ((state.get("fair_value_history") or {}).get("latest_sample") or {})
                state["gamma_context"] = self._build_gamma_context(
                    primary_underlying,
                    latest_model_run,
                    latest_fair_value_run,
                    latest_sample,
                )
                state["generated_at"] = _now_iso()
                collector["last_completed_at"] = state["generated_at"]
                with self._lock:
                    latest_state = self._load_state_unlocked()
                collector = self._merge_async_collector_fields(
                    collector,
                    latest_state.get("collector") or {},
                )
                latest_fair_history = dict(latest_state.get("fair_value_history") or {})
                latest_fair_sample = (latest_fair_history.get("latest_sample") or {})
                local_fair_history = dict(state.get("fair_value_history") or {})
                local_fair_sample = (local_fair_history.get("latest_sample") or {})
                latest_fair_dt = _parse_iso(latest_fair_sample.get("captured_at"))
                local_fair_dt = _parse_iso(local_fair_sample.get("captured_at"))
                if latest_fair_dt and (local_fair_dt is None or latest_fair_dt > local_fair_dt):
                    state["fair_value_history"] = latest_fair_history
                state["collector"] = collector
                with self._lock:
                    self._save_state_unlocked(
                        state,
                        persist_fair_value_history=bool(
                            force_fair_value and self._is_valid_live_snapshot(live_snapshot)
                        ),
                    )
                self._payload_cache = None
                self._payload_cache_at = 0.0
                return _deep_copy_json(state)
            except Exception as exc:
                collector["last_error"] = str(exc)
                collector["last_projection_error"] = str(exc)
                collector["last_completed_at"] = _now_iso()
                state["collector"] = collector
                state["generated_at"] = collector["last_completed_at"]
                with self._lock:
                    self._save_state_unlocked(state)
                self._payload_cache = None
                self._payload_cache_at = 0.0
                logger.exception("Failed to capture options heatmap context")
                return _deep_copy_json(state)

    def build_payload(self, *, refresh: bool = False) -> dict[str, Any]:
        now_ts = time.time()
        cache_ttl_seconds = max(5.0, min(float(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS), 30.0))
        state = self.read_state()
        collector = dict(state.get("collector") or {})
        live_history_state = dict(state.get("live_capture_history") or {})
        fair_history_state = dict(state.get("fair_value_history") or {})
        state_generated_at = _parse_iso(state.get("generated_at"))
        state_latest_live_at = _parse_iso((live_history_state.get("latest_snapshot") or {}).get("captured_at"))
        state_latest_sample_at = _parse_iso((fair_history_state.get("latest_sample") or {}).get("captured_at"))
        projection_lag_seconds = None
        if state_latest_live_at and state_latest_sample_at:
            projection_lag_seconds = (state_latest_live_at - state_latest_sample_at).total_seconds()
        elif state_latest_live_at and state_latest_sample_at is None:
            projection_lag_seconds = float("inf")

        if not refresh and self._payload_cache is not None and (now_ts - self._payload_cache_at) <= cache_ttl_seconds:
            cached_generated_at = _parse_iso((self._payload_cache or {}).get("generated_at"))
            cached_latest_sample_at = _parse_iso((((self._payload_cache or {}).get("fair_value_history") or {}).get("latest_sample") or {}).get("captured_at"))
            state_is_newer_than_cache = (
                state_generated_at is not None
                and (cached_generated_at is None or state_generated_at > cached_generated_at)
            )
            sample_is_newer_than_cache = (
                state_latest_sample_at is not None
                and (cached_latest_sample_at is None or state_latest_sample_at > cached_latest_sample_at)
            )
            projection_is_materially_behind = (
                projection_lag_seconds is not None
                and projection_lag_seconds > max(4.0, float(max(2, int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS))) * 2.5)
            )
            has_recent_projection_error = bool(collector.get("last_projection_error"))
            if not state_is_newer_than_cache and not sample_is_newer_than_cache and not projection_is_materially_behind and not has_recent_projection_error:
                return _deep_copy_json(self._payload_cache)

        latest_sample = ((state.get("fair_value_history") or {}).get("latest_sample") or {})
        should_force_capture = False
        if projection_lag_seconds is not None:
            if projection_lag_seconds > max(4.0, float(max(2, int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS))) * 2.5):
                should_force_capture = True
        if refresh or not latest_sample or should_force_capture:
            state = self.capture_once(
                force_fair_value=bool(refresh),
                force_wyrm=False,
                allow_scheduled_wyrm=False,
            )
        collector = dict(state.get("collector") or {})
        collector.update({
            "enabled": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE),
            "auto_start": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START),
            "loop_seconds": int(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS),
            "live_capture_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
            "fair_value_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
            "poll_seconds": options_poll_interval_seconds(),
        })
        payload = _deep_copy_json(state)
        payload["collector"] = collector
        live_history = dict(payload.get("live_capture_history") or {})
        underlying_security = str(live_history.get("underlying_security") or "IBOVE Index")
        current_session_date = str(live_history.get("current_session_date") or "")
        raw_live_snapshots = self.read_live_capture_snapshots(
            session_date=current_session_date or None,
            underlying_security=underlying_security,
        )
        live_snapshots = self._normalize_live_snapshots_for_payload(raw_live_snapshots)
        live_history["snapshots_total"] = len(live_snapshots)
        live_history["latest_snapshot"] = live_snapshots[-1] if live_snapshots else live_history.get("latest_snapshot")
        live_history["snapshots"] = live_snapshots
        payload["live_capture_history"] = live_history
        history = dict(payload.get("fair_value_history") or {})
        raw_samples = [dict(item or {}) for item in (history.get("samples") or [])]
        session_date = str(history.get("current_session_date") or "")
        underlying_security = str(history.get("underlying_security") or "IBOVE Index")
        merged_by_ts: dict[str, dict[str, Any]] = {}
        should_load_persisted_backfill = not raw_samples
        if not should_load_persisted_backfill and session_date:
            raw_session_dates = {
                str(item.get("session_date") or "")
                for item in raw_samples
                if isinstance(item, dict)
            }
            normalized_raw_session_dates = {value for value in raw_session_dates if value}
            if normalized_raw_session_dates and normalized_raw_session_dates != {session_date}:
                should_load_persisted_backfill = True
        if should_load_persisted_backfill:
            for sample in self._load_persisted_fair_value_backfill(
                session_date=session_date,
                underlying_security=underlying_security,
            ):
                ts = str(sample.get("captured_at") or "")
                if ts:
                    merged_by_ts[ts] = sample
        for sample in raw_samples:
            ts = str(sample.get("captured_at") or "")
            if ts:
                merged_by_ts[ts] = sample
        merged_samples = sorted(merged_by_ts.values(), key=lambda item: str(item.get("captured_at") or ""))
        has_full_recalc = any(
            str(item.get("projection_mode") or "") == "full_recalc"
            and str(item.get("sample_origin") or "") == "live_context_recalculated"
            for item in merged_samples
        )
        if has_full_recalc:
            merged_samples = [
                item
                for item in merged_samples
                if not (
                    str(item.get("projection_mode") or "") == "basis_shift"
                    and str(item.get("sample_origin") or "") == "live_context_projection"
                )
            ]
        normalized_samples = self._normalize_fair_value_samples_for_payload(merged_samples)
        history["samples_total"] = len(normalized_samples)
        history["latest_sample"] = normalized_samples[-1] if normalized_samples else None
        history["samples"] = self._compress_fair_value_samples_for_payload(normalized_samples)
        history["samples_payload_count"] = len(history["samples"])
        payload["fair_value_history"] = history
        if should_force_capture and not refresh:
            payload["projection_status"] = {
                "stale": True,
                "lag_seconds": projection_lag_seconds,
                "mode": "serve_last_good_state",
            }
        self._payload_cache = _deep_copy_json(payload)
        self._payload_cache_at = now_ts
        return payload
