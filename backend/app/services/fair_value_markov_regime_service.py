from __future__ import annotations

import json
import math
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import numpy as np

from ..config import Config
from ..utils.logger import get_logger
from .fair_value_legs_chart_service import (
    DEFAULT_LEG_DEFINITIONS,
    FairValueLegsChartService,
)
from .fair_value_markov_contracts import (
    EXTRA_FEATURE_DEFINITIONS,
    FULL_MEMORY_CACHE_TTL_SECONDS,
    MARKOV_REGIME_MODEL_VERSION,
    MIN_OBSERVATIONS,
    SNAPSHOT_STALE_SECONDS,
    STATE_DEFINITIONS,
    TAPE_STATE_DEFINITIONS,
)
from .fair_value_markov_math import (
    _clip,
    _logsumexp,
    _normalize_probabilities,
    _round_float,
    _safe_float,
)
from .fair_value_markov_model import FairValueMarkovModelMixin
from .fair_value_markov_regime_store import FairValueMarkovRegimeStore
from .flow_activity_radar_service import FlowActivityRadarService
from .macro_curve_discovery_service import MacroCurveDiscoveryService
from .market_screen_chart_service import MarketScreenChartService

logger = get_logger("aquiles.fair_value_markov_regime")


class FairValueMarkovRegimeService(FairValueMarkovModelMixin):
    """Robust Markov-regime model over XB1 and Fair Value leg features."""

    def __init__(
        self,
        legs_chart_service: FairValueLegsChartService | None = None,
        curve_discovery_service: MacroCurveDiscoveryService | None = None,
    ) -> None:
        self.root_dir = os.path.abspath(
            os.path.join(Config.OPTIONS_DATA_DIR, "market_screen_capture")
        )
        if legs_chart_service is None:
            self.legs_chart_service = FairValueLegsChartService(
                chart_service=MarketScreenChartService()
            )
            self.legs_chart_service.payload_cache_path = os.path.join(
                self.root_dir,
                "fair_value_markov_source_legs_latest.json",
            )
        else:
            self.legs_chart_service = legs_chart_service
        self.curve_discovery_service = curve_discovery_service or MacroCurveDiscoveryService(
            chart_service=MarketScreenChartService()
        )
        self.regime_store = FairValueMarkovRegimeStore(root_dir=self.root_dir)
        self.flow_activity_radar_service = FlowActivityRadarService()
        self.snapshot_path = os.path.join(self.root_dir, "fair_value_markov_regime_latest.json")
        self._lock = threading.RLock()
        self._build_lock = threading.Lock()
        self._snapshot_refresh_lock = threading.Lock()
        self._snapshot_refresh_thread: threading.Thread | None = None
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._curve_cache: dict[str, tuple[float, list[dict[str, float]]]] = {}
        self._flow_radar_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _default_leg_keys() -> list[str]:
        return [str(item.get("key")) for item in DEFAULT_LEG_DEFINITIONS if item.get("key")]

    @staticmethod
    def _leg_keys_from_payload(payload: dict[str, Any]) -> list[str]:
        keys: list[str] = []
        for leg in payload.get("legs") or []:
            if not isinstance(leg, dict):
                continue
            key = str(leg.get("key") or "").strip()
            if key and bool(leg.get("enabled", True)):
                keys.append(key)
        return keys or FairValueMarkovRegimeService._default_leg_keys()

    @staticmethod
    def _feature_definitions(leg_keys: list[str]) -> list[dict[str, str]]:
        definitions = [
            {
                "key": f"leg_{key}_impact",
                "label": f"{key.replace('_', ' ').title()} impact",
                "source": f"leg_{key}_impact_decimal",
            }
            for key in leg_keys
        ]
        definitions.extend(EXTRA_FEATURE_DEFINITIONS)
        return definitions

    @staticmethod
    def _base_extra_feature_keys() -> list[str]:
        return [
            "rpc_pressure",
            "rpc_slope",
            "rpc_acceleration",
            "fair_value_gap_z",
            "core_shadow_gap",
            "edge_bias",
        ]

    @classmethod
    def _base_feature_keys(cls, leg_keys: list[str]) -> list[str]:
        keys = [f"leg_{key}_impact" for key in leg_keys]
        keys.extend(cls._base_extra_feature_keys())
        return keys

    def _di_curve_history_for_session(self, session_date: str) -> list[dict[str, float]]:
        resolved_date = str(session_date or "").strip()
        if not resolved_date:
            return []
        cache_key = f"di::{resolved_date}"
        now = time.time()
        with self._lock:
            cached = self._curve_cache.get(cache_key)
            if cached and (now - cached[0]) <= FULL_MEMORY_CACHE_TTL_SECONDS:
                return deepcopy(cached[1])

        history: list[dict[str, float]] = []
        try:
            payload = self.curve_discovery_service.build_payload(
                curves=["di"],
                session_date=resolved_date,
                lookback_minutes=900,
                max_points=900,
                include_shape_points=False,
            )
            curves = payload.get("curves") if isinstance(payload.get("curves"), list) else []
            raw_history = (curves[0] if curves else {}).get("history") if curves else []
            if not isinstance(raw_history, list):
                raw_history = []
            history = sorted([
                {
                    "timestamp_ms": int(_safe_float(point.get("timestamp_ms"), 0.0) or 0),
                    "slope_change": _clip((_safe_float(point.get("slope_change_bp"), 0.0) or 0.0) / 100.0, -0.25, 0.25),
                    "level_change": _clip((_safe_float(point.get("level_change_bp"), 0.0) or 0.0) / 100.0, -0.25, 0.25),
                }
                for point in raw_history
                if int(_safe_float(point.get("timestamp_ms"), 0.0) or 0) > 0
            ], key=lambda item: item["timestamp_ms"])
        except Exception:
            logger.exception("Failed to load DI geometric curve history for Markov session %s", resolved_date)
            history = []

        with self._lock:
            self._curve_cache[cache_key] = (now, deepcopy(history))
            while len(self._curve_cache) > 16:
                self._curve_cache.pop(next(iter(self._curve_cache)), None)
        return history

    @staticmethod

    def _load_snapshot(self) -> dict[str, Any] | None:
        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return None
        if not isinstance(payload, dict) or not payload.get("ok"):
            return None
        if payload.get("model_version") != MARKOV_REGIME_MODEL_VERSION:
            return None
        return payload

    @staticmethod
    def _payload_last_session_date(payload: dict[str, Any] | None) -> str | None:
        if not isinstance(payload, dict):
            return None
        session_dates: list[str] = []
        for item in payload.get("sessions") or []:
            if isinstance(item, dict):
                value = str(item.get("date") or item.get("session_date") or "").strip()
                if value:
                    session_dates.append(value[:10])
        rows = payload.get("rows") or []
        if rows and isinstance(rows[-1], dict):
            value = str(rows[-1].get("session_date") or "").strip()
            if value:
                session_dates.append(value[:10])
        latest = payload.get("latest")
        if isinstance(latest, dict):
            value = str(latest.get("session_date") or "").strip()
            if value:
                session_dates.append(value[:10])
        return max(session_dates) if session_dates else None

    @staticmethod
    def _payload_last_timestamp_ms(payload: dict[str, Any] | None) -> int | None:
        if not isinstance(payload, dict):
            return None
        candidates: list[float] = []
        rows = payload.get("rows") or []
        if rows and isinstance(rows[-1], dict):
            value = _safe_float(rows[-1].get("timestamp_ms"))
            if value is not None:
                candidates.append(value)
        latest = payload.get("latest")
        if isinstance(latest, dict):
            value = _safe_float(latest.get("timestamp_ms"))
            if value is not None:
                candidates.append(value)
        if not candidates:
            return None
        return int(max(candidates))

    @staticmethod
    def _refresh_payload_latest_fields(payload: dict[str, Any]) -> None:
        rows = [
            row for row in (payload.get("rows") or [])
            if isinstance(row, dict)
        ]
        latest = rows[-1] if rows else None
        payload["latest"] = latest
        if latest and latest.get("timestamp_ms") is not None:
            payload["source_latest_timestamp_ms"] = latest.get("timestamp_ms")
        risk_thermometer = payload.get("risk_thermometer")
        if isinstance(risk_thermometer, dict):
            risk_thermometer["latest"] = (
                deepcopy(latest.get("risk_thermometer"))
                if isinstance(latest, dict)
                else None
            )
        meta_regime = payload.get("meta_regime")
        if isinstance(meta_regime, dict):
            meta_regime["latest"] = (
                {
                    "key": latest.get("meta_regime_key"),
                    "name": latest.get("meta_regime_name"),
                    "color": latest.get("meta_regime_color"),
                    "description": latest.get("meta_regime_description"),
                    "confidence": latest.get("meta_regime_confidence"),
                    "scores": deepcopy(latest.get("meta_regime_scores")) if isinstance(latest.get("meta_regime_scores"), dict) else {},
                    "drivers": deepcopy(latest.get("meta_regime_drivers")) if isinstance(latest.get("meta_regime_drivers"), list) else [],
                    "flow_activity": deepcopy(latest.get("meta_regime_flow_activity")) if isinstance(latest.get("meta_regime_flow_activity"), dict) else None,
                    "core_legs": deepcopy(latest.get("core_leg_context")) if isinstance(latest.get("core_leg_context"), dict) else {},
                    "secondary_hmm": (
                        {
                            "key": latest.get("meta_regime_secondary_state_key"),
                            "name": FairValueMarkovRegimeService._meta_regime_definition(latest.get("meta_regime_secondary_state_key")).get("name")
                            if latest.get("meta_regime_secondary_state_key")
                            else None,
                            "color": FairValueMarkovRegimeService._meta_regime_definition(latest.get("meta_regime_secondary_state_key")).get("color")
                            if latest.get("meta_regime_secondary_state_key")
                            else None,
                            "confidence": latest.get("meta_regime_secondary_probability"),
                            "probabilities": deepcopy(latest.get("meta_regime_secondary_probability_map"))
                            if isinstance(latest.get("meta_regime_secondary_probability_map"), dict)
                            else {},
                        }
                    ),
                }
                if isinstance(latest, dict)
                else None
            )

    def _apply_regime_persistence(
        self,
        payload: dict[str, Any],
        *,
        request_signature: str,
    ) -> dict[str, Any]:
        if not payload.get("ok"):
            return payload
        rows = [
            row for row in (payload.get("rows") or [])
            if isinstance(row, dict)
        ]
        if not rows:
            return payload
        try:
            current_session_date = self.regime_store.current_session_date_from_rows(rows)
            current_live_timestamp_ms = self.regime_store.current_live_timestamp_from_rows(
                rows,
                current_session_date,
            )
            merged_rows, merge_metadata = self.regime_store.merge_frozen_rows(
                rows=rows,
                request_signature=request_signature,
                model_version=MARKOV_REGIME_MODEL_VERSION,
                current_session_date=current_session_date,
                current_live_timestamp_ms=current_live_timestamp_ms,
            )
            payload["rows"] = merged_rows
            self._refresh_payload_latest_fields(payload)
            metrics = self.regime_store.build_metrics(
                payload=payload,
                current_session_date=current_session_date,
                merge_metadata=merge_metadata,
            )
            run_id = self.regime_store.build_run_id(
                payload=payload,
                request_signature=request_signature,
                model_version=MARKOV_REGIME_MODEL_VERSION,
            )
            payload["metrics"] = metrics
            payload["persistence"] = {
                "enabled": True,
                "ok": True,
                "run_id": run_id,
                "current_session_date": current_session_date,
                "current_live_timestamp_ms": current_live_timestamp_ms,
                "frozen_row_count": int(merge_metadata.get("frozen_row_count") or 0),
                "frozen_current_session_row_count": int(
                    merge_metadata.get("frozen_current_session_row_count") or 0
                ),
                "frozen_sessions": list(merge_metadata.get("frozen_sessions") or []),
            }
            persistence = self.regime_store.persist_payload(
                payload=payload,
                request_signature=request_signature,
                model_version=MARKOV_REGIME_MODEL_VERSION,
                current_session_date=current_session_date,
                current_live_timestamp_ms=current_live_timestamp_ms,
                run_id=run_id,
                metrics=metrics,
                merge_metadata=merge_metadata,
            )
            payload["metrics"] = persistence.get("metrics") or metrics
            persistence_summary = deepcopy(persistence)
            persistence_summary.pop("metrics", None)
            payload["persistence"] = persistence_summary
        except Exception:
            logger.exception("Failed to apply fair-value Markov SQLite persistence")
            payload["persistence"] = {
                "enabled": True,
                "ok": False,
                "error": "failed_to_apply_markov_persistence",
            }
        return payload

    def _latest_source_probe(
        self,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            latest_payload = self.legs_chart_service.build_latest_payload(
                config=params["config"],
                sessions=params["sessions"],
                bar_minutes=params["bar_minutes"],
                session_start=params["session_start"],
                session_end=params["session_end"],
                rolling_window_points=params["rolling_window_points"],
                vol_context=params["vol_context"],
            )
        except Exception:
            logger.debug("Failed to probe latest fair-value legs row for Markov freshness", exc_info=True)
            return {
                "timestamp_ms": None,
                "session_date": None,
                "min_history_timestamp_ms": None,
            }
        latest = latest_payload.get("latest") if isinstance(latest_payload, dict) else None
        timestamp_ms = None
        session_date = None
        if isinstance(latest, dict):
            parsed_timestamp = _safe_float(latest.get("timestamp_ms"))
            if parsed_timestamp is not None:
                timestamp_ms = int(parsed_timestamp)
            session_value = str(latest.get("session_date") or "").strip()
            session_date = session_value[:10] if session_value else None
        interval_ms = max(int(params.get("bar_minutes") or 5), 1) * 60_000
        return {
            "timestamp_ms": timestamp_ms,
            "session_date": session_date,
            "min_history_timestamp_ms": max(timestamp_ms - interval_ms, 0) if timestamp_ms is not None else None,
        }

    def _payload_covers_source_probe(
        self,
        payload: dict[str, Any] | None,
        source_probe: dict[str, Any],
    ) -> bool:
        if not isinstance(payload, dict):
            return False
        latest_session = source_probe.get("session_date")
        min_history_timestamp = source_probe.get("min_history_timestamp_ms")
        payload_last_session = self._payload_last_session_date(payload)
        payload_last_timestamp = self._payload_last_timestamp_ms(payload)
        covers_session = not latest_session or (
            payload_last_session is not None
            and str(payload_last_session) >= str(latest_session)
        )
        covers_timestamp = min_history_timestamp is None or (
            payload_last_timestamp is not None
            and int(payload_last_timestamp) >= int(min_history_timestamp)
        )
        return bool(covers_session and covers_timestamp)

    def _store_snapshot(self, payload: dict[str, Any]) -> None:
        if not payload.get("ok"):
            return
        try:
            existing = self._load_snapshot()
            existing_last_timestamp = self._payload_last_timestamp_ms(existing)
            next_last_timestamp = self._payload_last_timestamp_ms(payload)
            if (
                existing_last_timestamp is not None
                and next_last_timestamp is not None
                and existing_last_timestamp > next_last_timestamp
            ):
                logger.info(
                    "Skipping stale fair-value Markov snapshot overwrite: existing_ts=%s next_ts=%s",
                    existing_last_timestamp,
                    next_last_timestamp,
                )
                return

            existing_last_session = self._payload_last_session_date(existing)
            next_last_session = self._payload_last_session_date(payload)
            if (
                existing_last_session
                and next_last_session
                and existing_last_session > next_last_session
            ):
                logger.info(
                    "Skipping stale fair-value Markov snapshot overwrite: existing_session=%s next_session=%s",
                    existing_last_session,
                    next_last_session,
                )
                return

            os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)
            tmp_path = (
                f"{self.snapshot_path}."
                f"{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, allow_nan=False, default=str)
            for attempt in range(5):
                try:
                    os.replace(tmp_path, self.snapshot_path)
                    break
                except PermissionError:
                    if attempt >= 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))
        except Exception:
            logger.exception("Failed to store fair-value Markov regime snapshot")

    def snapshot_age_seconds(self) -> float | None:
        try:
            return max(datetime.now(timezone.utc).timestamp() - os.stat(self.snapshot_path).st_mtime, 0.0)
        except OSError:
            return None

    def _snapshot_response(
        self,
        snapshot: dict[str, Any],
        *,
        refresh_started: bool = False,
        cache_stale: bool = True,
    ) -> dict[str, Any]:
        payload = deepcopy(snapshot)
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        payload["snapshot_generated_at"] = snapshot.get("generated_at")
        payload["cache_source"] = "disk_snapshot"
        payload["cache_stale"] = bool(cache_stale)
        payload["background_refresh_started"] = bool(refresh_started)
        age_seconds = self.snapshot_age_seconds()
        if age_seconds is not None:
            payload["snapshot_age_seconds"] = round(age_seconds, 3)
        return payload

    @staticmethod
    def _cache_key(params: dict[str, Any]) -> str:
        try:
            return json.dumps(params, sort_keys=True, default=str)
        except Exception:
            return str(sorted(params.items()))

    @staticmethod
    def _snapshot_matches_request(snapshot: dict[str, Any] | None, cache_key: str) -> bool:
        if not isinstance(snapshot, dict):
            return False
        snapshot_version = int(_safe_float(snapshot.get("model_version"), 0.0) or 0)
        return (
            snapshot_version == MARKOV_REGIME_MODEL_VERSION
            and snapshot.get("request_signature") == cache_key
        )

    def _apply_latest_tape_overlay(
        self,
        *,
        snapshot: dict[str, Any],
        latest_row: dict[str, Any],
        source_row: dict[str, Any],
    ) -> None:
        tape_payload = snapshot.get("tape_regime") if isinstance(snapshot.get("tape_regime"), dict) else {}
        spec = tape_payload.get("model_spec") if isinstance(tape_payload.get("model_spec"), dict) else None
        if not spec:
            return
        previous_source_row = snapshot.get("source_latest_row") if isinstance(snapshot.get("source_latest_row"), dict) else None
        observations = self._build_observations(
            [source_row],
            leg_keys=["di"],
            previous_source_row=previous_source_row,
        )
        if not observations:
            return
        tape = self._build_tape_feature_matrices(observations=observations, rows=[latest_row])
        feature_keys = [str(item) for item in spec.get("feature_keys") or []]
        if not feature_keys:
            return
        current_keys = list(tape.get("feature_keys") or [])
        current_values = {
            key: float(tape["raw_x"][0, index])
            for index, key in enumerate(current_keys)
        }
        x_raw = np.asarray([current_values.get(key, 0.0) for key in feature_keys], dtype=float)
        x_center = np.asarray(spec.get("x_center") or [0.0] * len(feature_keys), dtype=float)
        x_scale = np.asarray(spec.get("x_scale") or [1.0] * len(feature_keys), dtype=float)
        x_scale = np.where(np.abs(x_scale) > 1e-9, x_scale, 1.0)
        x_scaled = np.clip((x_raw - x_center) / x_scale, -6.0, 6.0)
        emission_indices = [int(value) for value in spec.get("emission_indices") or []]
        if not emission_indices:
            emission_indices = [
                feature_keys.index(key)
                for key in spec.get("emission_feature_keys") or []
                if key in feature_keys
            ]
        if not emission_indices:
            return
        emission = x_scaled[emission_indices]
        means = np.asarray(spec.get("emission_means"), dtype=float)
        scales = np.asarray(spec.get("emission_scales"), dtype=float)
        transition = np.asarray(spec.get("transition_matrix"), dtype=float)
        previous_latest = snapshot.get("latest") if isinstance(snapshot.get("latest"), dict) else {}
        previous_probs = np.asarray(
            previous_latest.get("tape_state_probabilities")
            or spec.get("initial_probabilities")
            or [1.0 / len(TAPE_STATE_DEFINITIONS)] * len(TAPE_STATE_DEFINITIONS),
            dtype=float,
        )
        if transition.shape[0] != len(TAPE_STATE_DEFINITIONS) or means.shape[0] != len(TAPE_STATE_DEFINITIONS):
            return
        predicted_probs = _normalize_probabilities(previous_probs @ transition)
        log_like = self._emission_loglikelihood(
            emission[None, :],
            means,
            scales,
            TAPE_STATE_DEFINITIONS,
        )[0]
        log_probs = np.log(np.maximum(predicted_probs, 1e-12)) + log_like
        log_probs -= _logsumexp(log_probs)
        probs = np.exp(log_probs)
        state_index = int(np.argmax(probs))
        state = TAPE_STATE_DEFINITIONS[state_index]
        line_value = (tape.get("line_values") or [None])[0]
        direction = (tape.get("directions") or ["flat"])[0]
        latest_row.update({
            "tape_regime": state_index,
            "tape_regime_key": state["key"],
            "tape_regime_name": state["name"],
            "tape_regime_color": state["color"],
            "tape_state_probabilities": [round(float(value), 6) for value in probs],
            "tape_state_probability_map": {
                str(TAPE_STATE_DEFINITIONS[index]["key"]): round(float(value), 6)
                for index, value in enumerate(probs)
            },
            "tape_direction": direction,
            "tape_line_key": "leg_di",
            "tape_line_label": "DI leg",
            "tape_line_value": _round_float(line_value, 4),
            "tape_features": {
                key: _round_float(value, 8)
                for key, value in current_values.items()
            },
        })

    def refresh_snapshot_async(self, *, params: dict[str, Any], cache_key: str) -> bool:
        with self._snapshot_refresh_lock:
            if self._snapshot_refresh_thread is not None and self._snapshot_refresh_thread.is_alive():
                return False

            def _refresh() -> None:
                try:
                    self._build_fresh_payload(
                        params=deepcopy(params),
                        cache_key=cache_key,
                        wait_for_lock=False,
                        use_memory_cache=False,
                    )
                except Exception:
                    logger.exception("Failed to refresh fair-value Markov regime snapshot in background")

            self._snapshot_refresh_thread = threading.Thread(
                target=_refresh,
                name="fair-value-markov-regime-snapshot-refresh",
                daemon=True,
            )
            self._snapshot_refresh_thread.start()
            return True

    def _build_fresh_payload(
        self,
        *,
        params: dict[str, Any],
        cache_key: str,
        wait_for_lock: bool = True,
        use_memory_cache: bool = True,
    ) -> dict[str, Any] | None:
        acquired = self._build_lock.acquire(blocking=wait_for_lock)
        if not acquired:
            return None
        try:
            return self._build_fresh_payload_locked(
                params=params,
                cache_key=cache_key,
                use_memory_cache=use_memory_cache,
            )
        finally:
            self._build_lock.release()

    def _build_fresh_payload_locked(
        self,
        *,
        params: dict[str, Any],
        cache_key: str,
        use_memory_cache: bool = True,
    ) -> dict[str, Any]:
        regime_mode = self._normalize_regime_mode(params.get("regime_mode"))
        target_session_date = str(params.get("target_session_date") or "").strip()
        if use_memory_cache:
            with self._lock:
                cached = self._cache.get(cache_key)
                if cached and (time.time() - cached[0]) <= FULL_MEMORY_CACHE_TTL_SECONDS:
                    payload = deepcopy(cached[1])
                    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
                    payload["cache_source"] = "memory"
                    payload["cache_stale"] = False
                    payload["background_refresh_started"] = False
                    return payload

        source_probe = self._latest_source_probe(params=params)
        legs_payload = self.legs_chart_service.build_payload(
            config=params["config"],
            sessions=params["sessions"],
            bar_minutes=params["bar_minutes"],
            session_start=params["session_start"],
            session_end=params["session_end"],
            rolling_window_points=params["rolling_window_points"],
            vol_context=params["vol_context"],
            min_timestamp_ms=source_probe.get("min_history_timestamp_ms"),
        )
        source_rows = list(legs_payload.get("chart_rows") or [])
        if target_session_date:
            source_rows = [
                row
                for row in source_rows
                if str((row or {}).get("session_date") or "").strip() == target_session_date
            ]
        leg_keys = self._leg_keys_from_payload(legs_payload)
        feature_defs = self._feature_definitions(leg_keys)
        observations = self._build_observations(source_rows, leg_keys=leg_keys)
        observations = self._enrich_cross_asset_context(observations)
        corr_regime = self._apply_correlation_regime_layer(observations=observations)
        if len(observations) < MIN_OBSERVATIONS:
            snapshot = self._load_snapshot()
            if isinstance(snapshot, dict) and snapshot.get("ok") and len(snapshot.get("rows") or []) >= MIN_OBSERVATIONS:
                payload = self._snapshot_response(
                    snapshot,
                    refresh_started=False,
                    cache_stale=True,
                )
                payload["current_source_status"] = "insufficient_history"
                payload["current_source_row_count"] = len(source_rows)
                payload["current_source_error"] = (
                    f"Need at least {MIN_OBSERVATIONS} observations; found {len(observations)}."
                )
                return payload
            payload = {
                "ok": False,
                "status": "insufficient_history",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": "robust_sticky_student_t_markov_regression",
                "model_version": MARKOV_REGIME_MODEL_VERSION,
                "error": f"Need at least {MIN_OBSERVATIONS} observations; found {len(observations)}.",
                "source_ok": bool(legs_payload.get("ok")),
                "source_row_count": len(source_rows),
            }
            return payload

        matrices = self._build_feature_matrices(observations, feature_defs)
        initial_labels = self._initial_state_labels(observations, matrices)
        hmm = self._fit_hmm(
            np.asarray(matrices["emission"], dtype=float),
            initial_labels,
            transition_inputs={
                "x_scaled": np.asarray(matrices["x_scaled"], dtype=float),
                "feature_keys": list(matrices["feature_keys"]),
            },
        )
        hmm = self._apply_local_relief_probability_overlay(matrices=matrices, hmm=hmm)
        regressions = self._fit_state_regressions(
            x_scaled=np.asarray(matrices["x_scaled"], dtype=float),
            y=np.asarray(matrices["y"], dtype=float),
            probs=np.asarray(hmm["probabilities"], dtype=float),
            feature_keys=list(matrices["feature_keys"]),
        )
        rows = self._build_rows(
            observations=observations,
            matrices=matrices,
            hmm=hmm,
            regressions=regressions,
        )
        self._annotate_core_leg_contexts(rows)
        tape_regime = self._apply_tape_regime_layer(
            observations=observations,
            rows=rows,
        )
        risk_thermometer = self._build_risk_thermometer(
            rows=rows,
            observations=observations,
            matrices=matrices,
            hmm=hmm,
            regime_mode=regime_mode,
        )
        flow_activity_meta = self._build_flow_activity_meta(rows[-1].get("session_date") if rows else None)
        meta_regime = self._apply_meta_regime_layer(
            rows=rows,
            flow_activity_meta=flow_activity_meta,
        )
        transition = np.asarray(hmm["transition"], dtype=float)
        base_transition = np.asarray(
            hmm.get("base_transition") if hmm.get("base_transition") is not None else transition,
            dtype=float,
        )
        payload = {
            "ok": bool(rows),
            "status": "ready" if rows else "empty",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": "robust_sticky_student_t_markov_regression",
            "model_version": MARKOV_REGIME_MODEL_VERSION,
            "cache_source": "fresh_build",
            "cache_stale": False,
            "background_refresh_started": False,
            "methodology": {
                "state_model": "Sticky hidden Markov filter with diagonal Student-t emissions over robust-z XB1 returns, fair-value signal, local/external block pressure and correlation-break features.",
                "regression": "Per-regime robust ridge regression of XB1 returns against robust-scaled Fair Value leg impacts and pressure features.",
                "outliers": "Outliers are not discarded; Student-t likelihood and residual robust weights reduce leverage while the stress/dislocation states absorb tail events.",
                "no_lookahead": "Filtering is forward-only; transition probabilities are time-varying and conditioned on the current local-vs-external structure and correlation regime.",
            },
            "benchmark_symbol": legs_payload.get("benchmark_symbol") or "XB1",
            "bar_minutes": params["bar_minutes"],
            "requested_sessions": params["sessions"],
            "request_signature": cache_key,
            "source_params": deepcopy(params),
            "sessions": legs_payload.get("sessions") or [],
            "source_generated_at": legs_payload.get("generated_at"),
            "source_latest_timestamp_ms": rows[-1]["timestamp_ms"] if rows else None,
            "source_latest_session_date": rows[-1].get("session_date") if rows else None,
            "states": self._state_payloads(np.asarray(hmm["probabilities"]), transition),
            "transition_matrix": [
                [round(float(value), 6) for value in row]
                for row in transition
            ],
            "correlation_regime": corr_regime,
            "feature_definitions": feature_defs,
            "tape_regime": tape_regime,
            "risk_thermometer": risk_thermometer,
            "meta_regime": meta_regime,
            "state_betas": self._state_betas_payload(
                regressions,
                feature_defs,
                float(matrices["y_scale"]),
            ),
            "rows": rows,
            "latest": rows[-1] if rows else None,
            "visualization": {
                "primary": "candles_with_regime_background",
                "panels": [
                    "state_probability_stack",
                    "state_beta_heatmap",
                    "outlier_dislocation_strip",
                    "transition_matrix",
                ],
                "recommended_colors": {
                    str(state["key"]): str(state["color"])
                    for state in STATE_DEFINITIONS
                },
            },
            "model_spec": self._model_spec(
                matrices=matrices,
                hmm=hmm,
                regressions=regressions,
                feature_defs=feature_defs,
            ),
            "base_transition_matrix": [
                [round(float(value), 6) for value in row]
                for row in base_transition
            ],
            "source_latest_row": deepcopy(observations[-1].get("source_row")) if observations else None,
            "source_previous_row": deepcopy(observations[-1].get("previous_source_row")) if observations else None,
        }
        payload = self._apply_regime_persistence(payload, request_signature=cache_key)
        with self._lock:
            self._cache[cache_key] = (time.time(), deepcopy(payload))
            while len(self._cache) > 8:
                self._cache.pop(next(iter(self._cache)), None)
        self._store_snapshot(payload)
        return payload

    def build_payload(
        self,
        *,
        config: dict[str, Any] | None = None,
        sessions: int = 5,
        bar_minutes: int = 5,
        session_start: str = "09:00",
        session_end: str = "18:30",
        rolling_window_points: int = 60,
        vol_context: dict[str, Any] | None = None,
        regime_mode: str = "smart",
        target_session_date: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        params = {
            "config": config if isinstance(config, dict) else {},
            "sessions": max(int(sessions or 5), 1),
            "bar_minutes": max(int(bar_minutes or 5), 1),
            "session_start": str(session_start or "09:00"),
            "session_end": str(session_end or "18:30"),
            "rolling_window_points": max(int(rolling_window_points or 60), 12),
            "vol_context": vol_context if isinstance(vol_context, dict) else {},
            "regime_mode": self._normalize_regime_mode(regime_mode),
            "target_session_date": str(target_session_date or "").strip() or None,
        }
        cache_key = self._cache_key(params)
        now = time.time()
        source_probe = self._latest_source_probe(params=params)
        with self._lock:
            cached = self._cache.get(cache_key)
            if (
                cached
                and not force_refresh
                and (now - cached[0]) <= FULL_MEMORY_CACHE_TTL_SECONDS
                and self._payload_covers_source_probe(cached[1], source_probe)
            ):
                payload = deepcopy(cached[1])
                payload["generated_at"] = datetime.now(timezone.utc).isoformat()
                payload["cache_source"] = "memory"
                payload["cache_stale"] = False
                payload["background_refresh_started"] = False
                return payload

        snapshot = self._load_snapshot()
        snapshot_matches_request = self._snapshot_matches_request(snapshot, cache_key)
        if snapshot_matches_request:
            snapshot_age = self.snapshot_age_seconds()
            snapshot_covers_source = self._payload_covers_source_probe(snapshot, source_probe)
            if force_refresh:
                fresh_payload = self._build_fresh_payload(
                    params=params,
                    cache_key=cache_key,
                    wait_for_lock=True,
                    use_memory_cache=False,
                )
                if fresh_payload is not None:
                    return fresh_payload
            should_refresh = (
                snapshot_age is None
                or snapshot_age > SNAPSHOT_STALE_SECONDS
                or not snapshot_covers_source
            )
            refresh_started = False
            if should_refresh:
                refresh_started = self.refresh_snapshot_async(params=params, cache_key=cache_key)
            return self._snapshot_response(
                snapshot,
                refresh_started=refresh_started,
                cache_stale=should_refresh,
            )

        fresh_payload = self._build_fresh_payload(
            params=params,
            cache_key=cache_key,
            wait_for_lock=True,
        )
        if fresh_payload is not None:
            return fresh_payload
        return {
            "ok": False,
            "status": "build_in_progress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": "robust_sticky_student_t_markov_regression",
            "model_version": MARKOV_REGIME_MODEL_VERSION,
            "error": "Fair Value Markov full build is already in progress.",
        }

    def _latest_from_spec(
        self,
        *,
        snapshot: dict[str, Any],
        source_row: dict[str, Any],
    ) -> dict[str, Any] | None:
        spec = snapshot.get("model_spec") if isinstance(snapshot.get("model_spec"), dict) else None
        if not spec:
            return None
        feature_defs = list(spec.get("feature_definitions") or [])
        feature_keys = [str(item.get("key")) for item in feature_defs if item.get("key")]
        leg_keys = [
            key.removeprefix("leg_").removesuffix("_impact")
            for key in feature_keys
            if key.startswith("leg_") and key.endswith("_impact")
        ]
        base_feature_keys = self._base_feature_keys(leg_keys)
        history_rows = [
            row for row in (snapshot.get("rows") or [])
            if isinstance(row, dict)
        ][-24:]
        history_observations: list[dict[str, Any]] = []
        for row in history_rows:
            feature_values = row.get("feature_values") if isinstance(row.get("feature_values"), dict) else {}
            history_observations.append({
                "timestamp": row.get("timestamp"),
                "timestamp_ms": int(_safe_float(row.get("timestamp_ms"), 0.0) or 0),
                "session_date": row.get("session_date"),
                "close": _safe_float(row.get("close"), 0.0) or 0.0,
                "previous_close": _safe_float(row.get("previous_close"), 0.0) or 0.0,
                "return_decimal": _safe_float(row.get("return_decimal"), 0.0) or 0.0,
                "move_points": (_safe_float(row.get("close"), 0.0) or 0.0) - (_safe_float(row.get("previous_close"), 0.0) or 0.0),
                "features": {
                    key: _safe_float(feature_values.get(key), 0.0) or 0.0
                    for key in base_feature_keys
                },
                "model_signal": _safe_float(row.get("model_signal_decimal"), 0.0) or 0.0,
                "source_row": {},
                "previous_source_row": {},
            })
        previous_source_row = snapshot.get("source_latest_row") if isinstance(snapshot.get("source_latest_row"), dict) else None
        latest_observations = self._build_observations(
            [source_row],
            leg_keys=leg_keys,
            previous_source_row=previous_source_row,
        )
        if not latest_observations:
            return None
        observations = history_observations + latest_observations
        observations = self._enrich_cross_asset_context(observations)
        self._apply_correlation_regime_layer(observations=observations)
        if not observations:
            return None
        obs = observations[-1]
        x_raw = np.asarray([_safe_float(obs.get("features", {}).get(key), 0.0) or 0.0 for key in feature_keys], dtype=float)
        x_center = np.asarray(spec.get("x_center") or [0.0] * len(feature_keys), dtype=float)
        x_scale = np.asarray(spec.get("x_scale") or [1.0] * len(feature_keys), dtype=float)
        x_scale = np.where(np.abs(x_scale) > 1e-9, x_scale, 1.0)
        x_scaled = np.clip((x_raw - x_center) / x_scale, -6.0, 6.0)
        y = _safe_float(obs.get("return_decimal"), 0.0) or 0.0
        signal = _safe_float(obs.get("model_signal"), 0.0) or 0.0
        residual_prelim = y - signal
        y_z = _clip((y - float(spec.get("y_center") or 0.0)) / max(float(spec.get("y_scale") or 1.0), 1e-9), -8.0, 8.0)
        signal_z = _clip((signal - float(spec.get("signal_center") or 0.0)) / max(float(spec.get("signal_scale") or 1.0), 1e-9), -8.0, 8.0)
        residual_z_prelim = _clip(
            (residual_prelim - float(spec.get("residual_center") or 0.0))
            / max(float(spec.get("residual_scale") or 1.0), 1e-9),
            -8.0,
            8.0,
        )
        rpc_index = feature_keys.index("rpc_pressure") if "rpc_pressure" in feature_keys else None
        consensus_index = feature_keys.index("block_consensus") if "block_consensus" in feature_keys else None
        gap_index = feature_keys.index("block_gap") if "block_gap" in feature_keys else None
        local_relief_index = feature_keys.index("local_relief_impulse") if "local_relief_impulse" in feature_keys else None
        local_stress_index = feature_keys.index("local_stress_impulse") if "local_stress_impulse" in feature_keys else None
        corr_break_index = feature_keys.index("corr_break_score") if "corr_break_score" in feature_keys else None
        dislocation_index = feature_keys.index("dislocation_pressure") if "dislocation_pressure" in feature_keys else None
        edge_index = feature_keys.index("edge_bias") if "edge_bias" in feature_keys else None
        emission = np.asarray([
            y_z,
            signal_z,
            residual_z_prelim,
            x_scaled[consensus_index] if consensus_index is not None else 0.0,
            x_scaled[gap_index] if gap_index is not None else 0.0,
            x_scaled[local_relief_index] if local_relief_index is not None else 0.0,
            x_scaled[local_stress_index] if local_stress_index is not None else 0.0,
            x_scaled[corr_break_index] if corr_break_index is not None else 0.0,
            x_scaled[dislocation_index] if dislocation_index is not None else 0.0,
            x_scaled[rpc_index] if rpc_index is not None else 0.0,
            x_scaled[edge_index] if edge_index is not None else 0.0,
        ], dtype=float)

        means = np.asarray(spec.get("emission_means"), dtype=float)
        scales = np.asarray(spec.get("emission_scales"), dtype=float)
        base_transition = np.asarray(spec.get("base_transition_matrix") or spec.get("transition_matrix"), dtype=float)
        transition = self._transition_matrix_for_features(
            base_transition=base_transition,
            feature_vector=x_scaled,
            feature_keys=feature_keys,
            state_definitions=STATE_DEFINITIONS,
        )
        previous_latest = snapshot.get("latest") if isinstance(snapshot.get("latest"), dict) else {}
        previous_probs = np.asarray(previous_latest.get("state_probabilities") or spec.get("initial_probabilities"), dtype=float)
        predicted_probs = _normalize_probabilities(previous_probs @ transition)
        log_like = self._emission_loglikelihood(emission[None, :], means, scales)[0]
        log_probs = np.log(np.maximum(predicted_probs, 1e-12)) + log_like
        log_probs -= _logsumexp(log_probs)
        probs = np.exp(log_probs)
        probs = np.asarray(
            self._apply_local_relief_probability_overlay(
                matrices={
                    "feature_keys": feature_keys,
                    "x_raw": x_raw.reshape((1, -1)),
                },
                hmm={"probabilities": [probs.tolist()]},
            )["probabilities"],
            dtype=float,
        )[0]

        models = list(spec.get("regression_models") or [])
        predictions: list[float] = []
        design = np.asarray([1.0, *x_scaled], dtype=float)
        for model in models:
            beta = [float(model.get("alpha") or 0.0)]
            beta.extend(float((model.get("beta") or {}).get(key) or 0.0) for key in feature_keys)
            predictions.append(float(design @ np.asarray(beta, dtype=float)))
        if len(predictions) != len(STATE_DEFINITIONS):
            return None
        predictions_array = np.asarray(predictions, dtype=float)
        expected_return = float(np.sum(probs * predictions_array))
        state_sigmas = np.asarray([float(model.get("sigma") or 1e-6) for model in models], dtype=float)
        blended_sigma = max(float(np.sum(probs * state_sigmas)), 1e-6)
        residual = y - expected_return
        residual_z = residual / blended_sigma
        outlier_score = abs(residual_z)
        gap_z = float(x_raw[feature_keys.index("fair_value_gap_z")]) if "fair_value_gap_z" in feature_keys else 0.0
        dislocation_pressure = float(x_raw[dislocation_index]) if dislocation_index is not None else 0.0
        dislocation_score = math.tanh(
            (0.58 * outlier_score)
            + (0.21 * abs(gap_z))
            + (0.12 * abs(residual_z_prelim))
            + (0.18 * max(dislocation_pressure, 0.0))
        ) * 100.0
        dominant_state = int(np.argmax(probs))
        close = _safe_float(obs.get("close"), 0.0) or 0.0
        latest_row = {
            "timestamp": obs.get("timestamp"),
            "timestamp_ms": int(obs.get("timestamp_ms") or 0),
            "session_date": obs.get("session_date"),
            "open": _round_float(_safe_float(source_row.get("open"), close), 4),
            "high": _round_float(_safe_float(source_row.get("high"), close), 4),
            "low": _round_float(_safe_float(source_row.get("low"), close), 4),
            "close": _round_float(close, 4),
            "previous_close": _round_float(obs.get("previous_close"), 4),
            "fair_value_core": _round_float(source_row.get("fair_value_core"), 4),
            "fair_value_shadow": _round_float(source_row.get("fair_value_shadow"), 4),
            "fair_value_range_points": _round_float(source_row.get("fair_value_range_points"), 4),
            "return_decimal": _round_float(y, 8),
            "return_bps": _round_float(y * 10_000.0, 3),
            "expected_return_decimal": _round_float(expected_return, 8),
            "expected_return_bps": _round_float(expected_return * 10_000.0, 3),
            "expected_move_points": _round_float(close * expected_return, 4),
            "residual_decimal": _round_float(residual, 8),
            "residual_bps": _round_float(residual * 10_000.0, 3),
            "residual_z": _round_float(residual_z, 4),
            "outlier_score": _round_float(outlier_score, 4),
            "dislocation_score": _round_float(dislocation_score, 4),
            "dominant_state": dominant_state,
            "dominant_state_key": STATE_DEFINITIONS[dominant_state]["key"],
            "dominant_state_name": STATE_DEFINITIONS[dominant_state]["name"],
            "state_probabilities": [round(float(value), 6) for value in probs],
            "state_probability_map": {
                str(STATE_DEFINITIONS[index]["key"]): round(float(value), 6)
                for index, value in enumerate(probs)
            },
            "corr_regime": obs.get("corr_regime"),
            "corr_regime_key": obs.get("corr_regime_key"),
            "corr_regime_name": obs.get("corr_regime_name"),
            "corr_regime_color": obs.get("corr_regime_color"),
            "corr_state_probabilities": obs.get("corr_state_probabilities"),
            "corr_state_probability_map": obs.get("corr_state_probability_map"),
            "fair_value_gap_z": _round_float(gap_z, 4),
            "rpc_pressure": _round_float(float(x_raw[rpc_index]) if rpc_index is not None else 0.0, 6),
            "model_signal_decimal": _round_float(signal, 8),
            "feature_values": {
                key: _round_float(float(x_raw[index]), 8)
                for index, key in enumerate(feature_keys)
            },
        }
        self._apply_latest_tape_overlay(
            snapshot=snapshot,
            latest_row=latest_row,
            source_row=source_row,
        )
        return latest_row

    def build_latest_payload(
        self,
        *,
        config: dict[str, Any] | None = None,
        sessions: int = 5,
        bar_minutes: int = 5,
        session_start: str = "09:00",
        session_end: str = "18:30",
        rolling_window_points: int = 60,
        vol_context: dict[str, Any] | None = None,
        regime_mode: str = "smart",
        target_session_date: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "config": config if isinstance(config, dict) else {},
            "sessions": max(int(sessions or 5), 1),
            "bar_minutes": max(int(bar_minutes or 5), 1),
            "session_start": str(session_start or "09:00"),
            "session_end": str(session_end or "18:30"),
            "rolling_window_points": max(int(rolling_window_points or 60), 12),
            "vol_context": vol_context if isinstance(vol_context, dict) else {},
            "regime_mode": self._normalize_regime_mode(regime_mode),
            "target_session_date": str(target_session_date or "").strip() or None,
        }
        request_signature = self._cache_key(params)
        snapshot = self._load_snapshot()
        if not self._snapshot_matches_request(snapshot, request_signature):
            return self.build_payload(
                config=config,
                sessions=sessions,
                bar_minutes=bar_minutes,
                session_start=session_start,
                session_end=session_end,
                rolling_window_points=rolling_window_points,
                vol_context=vol_context,
                regime_mode=regime_mode,
                target_session_date=target_session_date,
            )
        latest_source_payload = self.legs_chart_service.build_latest_payload(
            config=config,
            sessions=sessions,
            bar_minutes=bar_minutes,
            session_start=session_start,
            session_end=session_end,
            rolling_window_points=rolling_window_points,
            vol_context=vol_context,
        )
        source_row = latest_source_payload.get("latest") if isinstance(latest_source_payload, dict) else None
        latest_row = None
        if isinstance(source_row, dict):
            latest_row = self._latest_from_spec(snapshot=snapshot, source_row=source_row)
        if latest_row is None:
            latest_row = snapshot.get("latest")
        return {
            "ok": bool(latest_row),
            "status": "ready" if latest_row else "empty",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": snapshot.get("model"),
            "model_version": snapshot.get("model_version"),
            "source": "markov_hot_overlay",
            "snapshot_generated_at": snapshot.get("generated_at"),
            "benchmark_symbol": snapshot.get("benchmark_symbol"),
            "bar_minutes": snapshot.get("bar_minutes"),
            "states": snapshot.get("states") or STATE_DEFINITIONS,
            "correlation_regime": snapshot.get("correlation_regime"),
            "tape_regime": snapshot.get("tape_regime"),
            "risk_thermometer": snapshot.get("risk_thermometer"),
            "meta_regime": snapshot.get("meta_regime"),
            "metrics": snapshot.get("metrics"),
            "persistence": snapshot.get("persistence"),
            "transition_matrix": snapshot.get("transition_matrix"),
            "state_betas": snapshot.get("state_betas"),
            "latest": latest_row,
            "rows": [latest_row] if latest_row else [],
            "source_latest_timestamp_ms": (
                int(source_row.get("timestamp_ms"))
                if isinstance(source_row, dict) and source_row.get("timestamp_ms") is not None
                else snapshot.get("source_latest_timestamp_ms")
            ),
        }
