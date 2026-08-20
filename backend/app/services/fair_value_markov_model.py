from __future__ import annotations

import math
import time
from copy import deepcopy
from typing import Any

import numpy as np

from ..utils.logger import get_logger
from .fair_value_markov_contracts import (
    CORR_STATE_DEFINITIONS,
    META_HMM_STATE_DEFINITIONS,
    META_REGIME_DEFINITIONS,
    STATE_DEFINITIONS,
    STUDENT_T_NU,
    TAPE_STATE_DEFINITIONS,
)
from .fair_value_markov_math import (
    _clip,
    _delta_from_history,
    _fisher_z,
    _logsumexp,
    _mad,
    _median,
    _normalize_probabilities,
    _rolling_corr,
    _round_float,
    _safe_float,
    _student_t_logpdf,
    _weighted_average,
    _weighted_sigma,
)

logger = get_logger("aquiles.fair_value_markov.model")


class FairValueMarkovModelMixin:
    @staticmethod
    def _weighted_block(features: dict[str, float], entries: list[tuple[str, float]]) -> float:
        weighted_sum = 0.0
        total_weight = 0.0
        for key, weight in entries:
            value = _safe_float(features.get(key))
            if value is None:
                continue
            weighted_sum += float(value) * float(weight)
            total_weight += abs(float(weight))
        if total_weight <= 1e-9:
            return 0.0
        return float(weighted_sum / total_weight)

    def _build_observations(
        self,
        source_rows: list[dict[str, Any]],
        *,
        leg_keys: list[str],
        previous_source_row: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        previous_close_by_session: dict[str, float] = {}
        previous_row_by_session: dict[str, dict[str, Any]] = {}

        sorted_rows = sorted(
            [row for row in source_rows if isinstance(row, dict)],
            key=lambda item: int(_safe_float(item.get("timestamp_ms"), 0.0) or 0),
        )
        curve_history_by_session = {
            session_date: self._di_curve_history_for_session(session_date)
            for session_date in {
                str((row or {}).get("session_date") or "").strip()
                for row in sorted_rows
                if str((row or {}).get("session_date") or "").strip()
            }
        }
        curve_index_by_session = {
            session_date: 0
            for session_date in curve_history_by_session
        }
        if previous_source_row:
            previous_session = str(previous_source_row.get("session_date") or "")
            previous_close = _safe_float(previous_source_row.get("close"))
            if previous_session and previous_close is not None:
                previous_close_by_session[previous_session] = previous_close
                previous_row_by_session[previous_session] = previous_source_row

        for row in sorted_rows:
            session_date = str(row.get("session_date") or "")
            close = _safe_float(row.get("close"))
            timestamp_ms = int(_safe_float(row.get("timestamp_ms"), 0.0) or 0)
            if close is None or timestamp_ms <= 0:
                continue
            reference_close = previous_close_by_session.get(session_date)
            if reference_close is None:
                reference_close = _safe_float(row.get("previous_close"))
            if reference_close is None or abs(reference_close) <= 1e-12:
                previous_close_by_session[session_date] = close
                previous_row_by_session[session_date] = row
                continue

            return_decimal = math.log(max(close, 1e-9) / max(reference_close, 1e-9))
            features: dict[str, float] = {}
            leg_values: list[float] = []
            for key in leg_keys:
                raw_value = _safe_float(row.get(f"leg_{key}_impact_decimal"))
                if raw_value is None:
                    leg_price = _safe_float(row.get(f"leg_{key}"))
                    if leg_price is not None:
                        raw_value = (leg_price - reference_close) / max(abs(reference_close), 1e-9)
                raw_value = raw_value if raw_value is not None else 0.0
                raw_value = _clip(raw_value, -0.12, 0.12)
                features[f"leg_{key}_impact"] = raw_value
                leg_values.append(raw_value)

            rpc_pressure = (_safe_float(row.get("rpc_pressure_score"), 0.0) or 0.0) / 100.0
            rpc_slope = (_safe_float(row.get("rpc_slope"), 0.0) or 0.0) / 100.0
            rpc_acceleration = (_safe_float(row.get("rpc_acceleration"), 0.0) or 0.0) / 100.0
            components = row.get("sentiment_components") if isinstance(row.get("sentiment_components"), dict) else {}
            fair_value_gap_z = _safe_float(components.get("gap_z"))
            range_points = max(_safe_float(row.get("fair_value_range_points"), 0.0) or 0.0, 1.0)
            fair_value_core = _safe_float(row.get("fair_value_core"))
            fair_value_shadow = _safe_float(row.get("fair_value_shadow"))
            if fair_value_gap_z is None and fair_value_core is not None:
                fair_value_gap_z = (fair_value_core - close) / max(range_points * 0.58, 10.0)
            core_shadow_gap = (
                (fair_value_core - fair_value_shadow) / max(abs(reference_close), 1e-9)
                if fair_value_core is not None and fair_value_shadow is not None
                else 0.0
            )
            edge_bias = (_safe_float(row.get("edge_bias_score"), 0.0) or 0.0) / 100.0

            features["rpc_pressure"] = _clip(rpc_pressure, -1.2, 1.2)
            features["rpc_slope"] = _clip(rpc_slope, -1.2, 1.2)
            features["rpc_acceleration"] = _clip(rpc_acceleration, -1.2, 1.2)
            features["fair_value_gap_z"] = _clip(fair_value_gap_z or 0.0, -8.0, 8.0)
            features["core_shadow_gap"] = _clip(core_shadow_gap, -0.08, 0.08)
            features["edge_bias"] = _clip(edge_bias, -1.2, 1.2)
            features["vixbr_rpc_score"] = _clip((_safe_float(row.get("rpc_v2_vixbr_score"), 0.0) or 0.0) / 100.0, -1.2, 1.2)

            curve_history = curve_history_by_session.get(session_date) or []
            curve_index = curve_index_by_session.get(session_date, 0)
            while (
                curve_index + 1 < len(curve_history)
                and int(curve_history[curve_index + 1]["timestamp_ms"]) <= timestamp_ms
            ):
                curve_index += 1
            curve_index_by_session[session_date] = curve_index
            curve_point = (
                curve_history[curve_index]
                if curve_history and int(curve_history[curve_index]["timestamp_ms"]) <= timestamp_ms
                else None
            )
            features["di_curve_slope_change"] = (
                _clip(float(curve_point["slope_change"]), -0.25, 0.25)
                if isinstance(curve_point, dict)
                else 0.0
            )
            features["di_curve_level_change"] = (
                _clip(float(curve_point["level_change"]), -0.25, 0.25)
                if isinstance(curve_point, dict)
                else 0.0
            )

            model_signal = float(np.mean(leg_values)) if leg_values else 0.0
            model_signal += 0.0009 * features["rpc_pressure"]
            model_signal += 0.00045 * math.tanh(features["fair_value_gap_z"] / 2.0)

            previous_row = previous_row_by_session.get(session_date)
            observations.append({
                "timestamp": row.get("timestamp"),
                "timestamp_ms": timestamp_ms,
                "session_date": session_date,
                "close": close,
                "previous_close": reference_close,
                "return_decimal": _clip(return_decimal, -0.16, 0.16),
                "move_points": close - reference_close,
                "features": features,
                "model_signal": _clip(model_signal, -0.12, 0.12),
                "source_row": row,
                "previous_source_row": previous_row,
            })
            previous_close_by_session[session_date] = close
            previous_row_by_session[session_date] = row

        return observations

    def _enrich_cross_asset_context(
        self,
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not observations:
            return observations

        local_entries = [
            ("leg_di_impact", 0.40),
            ("leg_equity_local_impact", 0.25),
            ("leg_fx_impact", 0.20),
            ("leg_credit_impact", 0.15),
        ]
        external_entries = [
            ("leg_risk_impact", 0.40),
            ("leg_equity_foreign_impact", 0.25),
            ("leg_funding_impact", 0.20),
            ("leg_commodities_impact", 0.10),
            ("leg_sentiment_impact", 0.05),
        ]

        returns_history: list[float] = []
        local_history: list[float] = []
        external_history: list[float] = []
        consensus_history: list[float] = []
        di_curve_slope_history: list[float] = []
        di_curve_level_history: list[float] = []
        vixbr_score_history: list[float] = []
        risk_leg_history: list[float] = []

        for index, obs in enumerate(observations):
            features = obs.get("features") if isinstance(obs.get("features"), dict) else {}
            if not isinstance(features, dict):
                features = {}
                obs["features"] = features

            local_block = self._weighted_block(features, local_entries)
            external_block = self._weighted_block(features, external_entries)
            block_consensus = (0.52 * external_block) + (0.48 * local_block)
            block_gap = external_block - local_block
            agreement_denominator = abs(local_block) + abs(external_block)
            block_agreement = 1.0 - (abs(block_gap) / max(agreement_denominator, 1e-6))
            if local_block * external_block < 0.0:
                block_agreement *= 0.55
            block_agreement = _clip(block_agreement, 0.0, 1.0)
            divergence_penalty = abs(block_gap) * (1.35 if local_block * external_block < 0.0 else 0.65)

            return_decimal = _safe_float(obs.get("return_decimal"), 0.0) or 0.0
            di_curve_slope = _safe_float(features.get("di_curve_slope_change"), 0.0) or 0.0
            di_curve_level = _safe_float(features.get("di_curve_level_change"), 0.0) or 0.0
            vixbr_score = _safe_float(features.get("vixbr_rpc_score"), 0.0) or 0.0
            risk_leg = _safe_float(features.get("leg_risk_impact"), 0.0) or 0.0
            returns_history.append(return_decimal)
            local_history.append(local_block)
            external_history.append(external_block)
            consensus_history.append(block_consensus)
            di_curve_slope_history.append(di_curve_slope)
            di_curve_level_history.append(di_curve_level)
            vixbr_score_history.append(vixbr_score)
            risk_leg_history.append(risk_leg)

            delta_local_15 = _delta_from_history(local_history, index, 3)
            delta_local_30 = _delta_from_history(local_history, index, 6)
            delta_consensus_15 = _delta_from_history(consensus_history, index, 3)
            delta_consensus_30 = _delta_from_history(consensus_history, index, 6)
            delta_di_curve_slope_15 = _delta_from_history(di_curve_slope_history, index, 3)
            delta_di_curve_slope_30 = _delta_from_history(di_curve_slope_history, index, 6)
            delta_di_curve_level_15 = _delta_from_history(di_curve_level_history, index, 3)
            delta_di_curve_level_30 = _delta_from_history(di_curve_level_history, index, 6)
            delta_vixbr_15 = _delta_from_history(vixbr_score_history, index, 3)
            delta_vixbr_30 = _delta_from_history(vixbr_score_history, index, 6)
            delta_risk_leg_15 = _delta_from_history(risk_leg_history, index, 3)

            local_stress_impulse = _clip(
                (1.10 * max(block_gap, 0.0))
                + (1.65 * max(-delta_local_15, 0.0))
                + (1.05 * max(-delta_local_30, 0.0))
                + (0.85 * max(-local_block, 0.0))
                + (0.55 * divergence_penalty)
                - (0.35 * max(external_block, 0.0) * max(local_block, 0.0) / max(agreement_denominator, 1e-6)),
                0.0,
                0.035,
            )
            broad_risk_off_pressure = _clip(
                max(-block_consensus, 0.0)
                + (0.40 * max(-delta_consensus_15, 0.0))
                + (0.24 * max(-delta_consensus_30, 0.0))
                + (0.20 * max(-external_block, 0.0))
                + (0.16 * max(-local_block, 0.0)),
                0.0,
                0.16,
            )
            vixbr_rolling_peak = max(vixbr_score_history[max(0, index - 12):index + 1]) if vixbr_score_history else vixbr_score
            di_curve_shape_relief = _clip(
                (1.35 * max(-delta_di_curve_slope_15, 0.0))
                + (0.95 * max(-delta_di_curve_slope_30, 0.0))
                + (0.30 * max(-di_curve_slope, 0.0)),
                0.0,
                0.06,
            )
            di_curve_level_relief = _clip(
                (0.90 * max(-delta_di_curve_level_15, 0.0))
                + (0.60 * max(-delta_di_curve_level_30, 0.0)),
                0.0,
                0.05,
            )
            vixbr_relief_impulse = _clip(
                (0.95 * max(-delta_vixbr_15, 0.0))
                + (0.60 * max(-delta_vixbr_30, 0.0))
                + (0.35 * max(vixbr_rolling_peak - vixbr_score, 0.0)),
                0.0,
                0.06,
            )
            local_relief_impulse = _clip(
                (0.48 * di_curve_shape_relief)
                + (0.18 * di_curve_level_relief)
                + (0.18 * vixbr_relief_impulse)
                + (0.10 * max(-delta_risk_leg_15, 0.0))
                + (0.08 * max(delta_local_15, 0.0))
                + (0.10 * max(_safe_float(features.get("rpc_slope"), 0.0) or 0.0, 0.0))
                - (0.32 * max(-delta_local_15, 0.0))
                - (0.24 * max(delta_di_curve_level_15, 0.0))
                - (0.18 * max(local_stress_impulse - 0.018, 0.0))
                - (0.12 * max(broad_risk_off_pressure - 0.024, 0.0)),
                0.0,
                0.03,
            )

            corr_local_short = _rolling_corr(returns_history, local_history, 4)
            corr_local_medium = _rolling_corr(returns_history, local_history, 12)
            corr_external_short = _rolling_corr(returns_history, external_history, 4)
            corr_external_medium = _rolling_corr(returns_history, external_history, 12)
            corr_local_short_z = _fisher_z(corr_local_short)
            corr_local_medium_z = _fisher_z(corr_local_medium)
            corr_external_short_z = _fisher_z(corr_external_short)
            corr_external_medium_z = _fisher_z(corr_external_medium)
            corr_gain_local = corr_local_short_z - corr_local_medium_z
            corr_gain_external = corr_external_short_z - corr_external_medium_z
            corr_gain_gap = corr_gain_local - corr_gain_external
            corr_break_score = _clip(
                (0.55 * abs(corr_local_short_z - corr_external_short_z))
                + (0.30 * abs(corr_gain_gap))
                + (0.20 * abs(block_gap) / max(agreement_denominator, 1e-6))
                + (0.12 * max(0.45 - block_agreement, 0.0) / 0.45),
                0.0,
                4.0,
            )

            gap_z = _safe_float(features.get("fair_value_gap_z"), 0.0) or 0.0
            prelim_mismatch = abs(return_decimal - (_safe_float(obs.get("model_signal"), 0.0) or 0.0))
            dislocation_pressure = _clip(
                (0.40 * abs(gap_z))
                + (0.24 * abs(corr_gain_gap))
                + (0.18 * abs(corr_local_short_z - corr_external_short_z))
                + (0.10 * max(0.45 - block_agreement, 0.0) / 0.45)
                + (0.12 * min(prelim_mismatch / 0.0015, 4.0)),
                0.0,
                6.0,
            )

            features["local_block"] = local_block
            features["external_block"] = external_block
            features["block_consensus"] = block_consensus
            features["block_gap"] = block_gap
            features["block_agreement"] = block_agreement
            features["di_curve_shape_relief"] = di_curve_shape_relief
            features["vixbr_relief_impulse"] = vixbr_relief_impulse
            features["local_relief_impulse"] = local_relief_impulse
            features["local_stress_impulse"] = local_stress_impulse
            features["broad_risk_off_pressure"] = broad_risk_off_pressure
            features["corr_local_short"] = corr_local_short
            features["corr_local_medium"] = corr_local_medium
            features["corr_external_short"] = corr_external_short
            features["corr_external_medium"] = corr_external_medium
            features["corr_gain_local"] = corr_gain_local
            features["corr_gain_external"] = corr_gain_external
            features["corr_gain_gap"] = corr_gain_gap
            features["corr_break_score"] = corr_break_score
            features["dislocation_pressure"] = dislocation_pressure

            obs["model_signal"] = _clip(
                (0.62 * block_consensus)
                + (0.18 * external_block)
                + (0.10 * local_block)
                + (0.05 * local_relief_impulse)
                - (0.08 * local_stress_impulse)
                - (0.05 * broad_risk_off_pressure)
                + (0.0009 * (_safe_float(features.get("rpc_pressure"), 0.0) or 0.0))
                + (0.00045 * math.tanh(gap_z / 2.0)),
                -0.12,
                0.12,
            )

        return observations

    @staticmethod
    def _corr_feature_definitions() -> list[dict[str, str]]:
        return [
            {"key": "corr_local_short", "label": "Corr local short"},
            {"key": "corr_external_short", "label": "Corr external short"},
            {"key": "corr_gain_gap", "label": "Corr gain gap"},
            {"key": "corr_break_score", "label": "Corr break score"},
            {"key": "block_gap", "label": "Block gap"},
            {"key": "block_agreement", "label": "Block agreement"},
        ]

    @staticmethod
    def _initial_corr_state_labels(raw_x: np.ndarray, feature_keys: list[str]) -> np.ndarray:
        def raw(index: int, key: str) -> float:
            return float(raw_x[index, feature_keys.index(key)]) if key in feature_keys else 0.0

        labels: list[int] = []
        for index in range(len(raw_x)):
            corr_break = raw(index, "corr_break_score")
            block_agreement = raw(index, "block_agreement")
            corr_gain_gap = raw(index, "corr_gain_gap")
            local_short = raw(index, "corr_local_short")
            external_short = raw(index, "corr_external_short")
            if corr_break > 1.55 or (block_agreement < 0.08 and abs(corr_gain_gap) > 0.35):
                labels.append(3)
            elif corr_gain_gap > 0.30 or (local_short - external_short) > 0.20:
                labels.append(2)
            elif corr_gain_gap < -0.30 or (external_short - local_short) > 0.20:
                labels.append(1)
            else:
                labels.append(0)
        return np.asarray(labels, dtype=int)

    def _apply_correlation_regime_layer(
        self,
        *,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if len(observations) < 8:
            for obs in observations:
                features = obs.get("features") if isinstance(obs.get("features"), dict) else {}
                if not isinstance(features, dict):
                    features = {}
                    obs["features"] = features
                features["corr_state_aligned"] = 1.0
                features["corr_state_external_dominance"] = 0.0
                features["corr_state_local_dominance"] = 0.0
                features["corr_state_corr_break"] = 0.0
            return {
                "ok": False,
                "status": "insufficient_history",
                "states": CORR_STATE_DEFINITIONS,
            }

        feature_defs = self._corr_feature_definitions()
        feature_keys = [item["key"] for item in feature_defs]
        raw_x = np.asarray([
            [_safe_float((obs.get("features") or {}).get(key), 0.0) or 0.0 for key in feature_keys]
            for obs in observations
        ], dtype=float)
        x_scaled, x_center, x_scale = self._center_scale_matrix(raw_x)
        initial_labels = self._initial_corr_state_labels(raw_x, feature_keys)
        hmm = self._fit_hmm(
            x_scaled,
            initial_labels,
            state_definitions=CORR_STATE_DEFINITIONS,
            sticky_bias=5.75,
            iterations=5,
        )
        probs = np.asarray(hmm["probabilities"], dtype=float)
        latest_transition_source = hmm.get("transition")
        latest_transition = np.asarray(
            latest_transition_source if latest_transition_source is not None else np.eye(len(CORR_STATE_DEFINITIONS)),
            dtype=float,
        )

        for index, obs in enumerate(observations):
            features = obs.get("features") if isinstance(obs.get("features"), dict) else {}
            if not isinstance(features, dict):
                features = {}
                obs["features"] = features
            state_probs = probs[index, :]
            state_index = int(np.argmax(state_probs))
            state = CORR_STATE_DEFINITIONS[state_index]
            obs["corr_regime"] = state_index
            obs["corr_regime_key"] = state["key"]
            obs["corr_regime_name"] = state["name"]
            obs["corr_regime_color"] = state["color"]
            obs["corr_state_probabilities"] = [round(float(value), 6) for value in state_probs]
            obs["corr_state_probability_map"] = {
                str(CORR_STATE_DEFINITIONS[item]["key"]): round(float(value), 6)
                for item, value in enumerate(state_probs)
            }
            features["corr_state_aligned"] = float(state_probs[0])
            features["corr_state_external_dominance"] = float(state_probs[1])
            features["corr_state_local_dominance"] = float(state_probs[2])
            features["corr_state_corr_break"] = float(state_probs[3])

        return {
            "ok": True,
            "status": "ready",
            "model": "sticky_student_t_cross_asset_corr_regime",
            "states": self._state_payloads(probs, latest_transition, CORR_STATE_DEFINITIONS),
            "transition_matrix": [
                [round(float(value), 6) for value in row]
                for row in latest_transition
            ],
            "latest": {
                "regime": observations[-1].get("corr_regime_key"),
                "probabilities": observations[-1].get("corr_state_probability_map"),
            },
            "model_spec": {
                "feature_keys": feature_keys,
                "x_center": [float(value) for value in x_center],
                "x_scale": [float(value) for value in x_scale],
                "emission_feature_keys": feature_keys,
                "emission_means": np.asarray(hmm["means"]).tolist(),
                "emission_scales": np.asarray(hmm["scales"]).tolist(),
                "transition_matrix": latest_transition.tolist(),
                "initial_probabilities": np.asarray(hmm["initial"]).tolist(),
            },
        }

    @staticmethod
    def _center_scale_matrix(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        matrix = np.asarray(matrix, dtype=float)
        centers = np.nanmedian(matrix, axis=0)
        centers = np.where(np.isfinite(centers), centers, 0.0)
        scales: list[float] = []
        for column_index in range(matrix.shape[1]):
            column = [
                float(value)
                for value in matrix[:, column_index]
                if math.isfinite(float(value))
            ]
            scales.append(_mad(column, float(centers[column_index])))
        scale_array = np.asarray(scales, dtype=float)
        scale_array = np.where(scale_array > 1e-9, scale_array, 1.0)
        scaled = np.clip((matrix - centers) / scale_array, -6.0, 6.0)
        return scaled, centers, scale_array

    def _build_feature_matrices(
        self,
        observations: list[dict[str, Any]],
        feature_defs: list[dict[str, str]],
    ) -> dict[str, Any]:
        feature_keys = [item["key"] for item in feature_defs]
        raw_x = np.asarray([
            [_safe_float(obs.get("features", {}).get(key), 0.0) or 0.0 for key in feature_keys]
            for obs in observations
        ], dtype=float)
        x_scaled, x_center, x_scale = self._center_scale_matrix(raw_x)

        y = np.asarray([_safe_float(obs.get("return_decimal"), 0.0) or 0.0 for obs in observations], dtype=float)
        y_center = _median([float(value) for value in y])
        y_scale = _mad([float(value) for value in y], y_center)
        y_z = np.clip((y - y_center) / max(y_scale, 1e-9), -8.0, 8.0)

        signal = np.asarray([_safe_float(obs.get("model_signal"), 0.0) or 0.0 for obs in observations], dtype=float)
        signal_center = _median([float(value) for value in signal])
        signal_scale = _mad([float(value) for value in signal], signal_center)
        signal_z = np.clip((signal - signal_center) / max(signal_scale, 1e-9), -8.0, 8.0)
        residual = y - signal
        residual_center = _median([float(value) for value in residual])
        residual_scale = _mad([float(value) for value in residual], residual_center)
        residual_z = np.clip((residual - residual_center) / max(residual_scale, 1e-9), -8.0, 8.0)

        def scaled_feature(key: str) -> np.ndarray:
            return x_scaled[:, feature_keys.index(key)] if key in feature_keys else np.zeros(len(y))

        raw_emission = np.asarray([
            y_z,
            signal_z,
            residual_z,
            scaled_feature("block_consensus"),
            scaled_feature("block_gap"),
            scaled_feature("local_relief_impulse"),
            scaled_feature("local_stress_impulse"),
            scaled_feature("corr_break_score"),
            scaled_feature("dislocation_pressure"),
            scaled_feature("rpc_pressure"),
            scaled_feature("edge_bias"),
        ], dtype=float).T

        return {
            "feature_keys": feature_keys,
            "x_raw": raw_x,
            "x_scaled": x_scaled,
            "x_center": x_center,
            "x_scale": x_scale,
            "y": y,
            "y_center": y_center,
            "y_scale": y_scale,
            "signal": signal,
            "residual_prelim": residual,
            "emission": raw_emission,
            "emission_feature_keys": [
                "xb1_return_z",
                "leg_signal_z",
                "prelim_residual_z",
                "block_consensus_z",
                "block_gap_z",
                "local_relief_impulse_z",
                "local_stress_impulse_z",
                "corr_break_score_z",
                "dislocation_pressure_z",
                "rpc_pressure_z",
                "edge_bias_z",
            ],
            "signal_center": signal_center,
            "signal_scale": signal_scale,
            "residual_center": residual_center,
            "residual_scale": residual_scale,
        }

    @staticmethod
    def _initial_state_labels(observations: list[dict[str, Any]], matrices: dict[str, Any]) -> np.ndarray:
        y_z = np.asarray(matrices["emission"])[:, 0]
        signal_z = np.asarray(matrices["emission"])[:, 1]
        residual_z = np.asarray(matrices["emission"])[:, 2]
        feature_keys = list(matrices["feature_keys"])
        x_raw = np.asarray(matrices["x_raw"])
        rpc_index = feature_keys.index("rpc_pressure") if "rpc_pressure" in feature_keys else None
        consensus_index = feature_keys.index("block_consensus") if "block_consensus" in feature_keys else None
        gap_index = feature_keys.index("block_gap") if "block_gap" in feature_keys else None
        local_relief_index = feature_keys.index("local_relief_impulse") if "local_relief_impulse" in feature_keys else None
        local_stress_index = feature_keys.index("local_stress_impulse") if "local_stress_impulse" in feature_keys else None
        broad_off_index = feature_keys.index("broad_risk_off_pressure") if "broad_risk_off_pressure" in feature_keys else None
        corr_break_index = feature_keys.index("corr_break_score") if "corr_break_score" in feature_keys else None
        dislocation_index = feature_keys.index("dislocation_pressure") if "dislocation_pressure" in feature_keys else None
        corr_local_dom_index = feature_keys.index("corr_state_local_dominance") if "corr_state_local_dominance" in feature_keys else None
        corr_external_dom_index = feature_keys.index("corr_state_external_dominance") if "corr_state_external_dominance" in feature_keys else None
        labels: list[int] = []
        for index, obs in enumerate(observations):
            y_value = float(y_z[index])
            signal_value = float(signal_z[index])
            residual_value = float(residual_z[index])
            rpc = float(x_raw[index, rpc_index]) if rpc_index is not None else 0.0
            block_consensus = float(x_raw[index, consensus_index]) if consensus_index is not None else 0.0
            block_gap = float(x_raw[index, gap_index]) if gap_index is not None else 0.0
            local_relief = float(x_raw[index, local_relief_index]) if local_relief_index is not None else 0.0
            local_stress = float(x_raw[index, local_stress_index]) if local_stress_index is not None else 0.0
            broad_off = float(x_raw[index, broad_off_index]) if broad_off_index is not None else 0.0
            corr_break = float(x_raw[index, corr_break_index]) if corr_break_index is not None else 0.0
            dislocation = float(x_raw[index, dislocation_index]) if dislocation_index is not None else 0.0
            corr_local_dom = float(x_raw[index, corr_local_dom_index]) if corr_local_dom_index is not None else 0.0
            corr_external_dom = float(x_raw[index, corr_external_dom_index]) if corr_external_dom_index is not None else 0.0
            y_raw = _safe_float(obs.get("return_decimal"), 0.0) or 0.0
            signal_raw = _safe_float(obs.get("model_signal"), 0.0) or 0.0
            mismatch = (
                abs(residual_value) > 1.5
                and abs(signal_value) > 0.5
                and (y_raw * signal_raw) < 0.0
            )
            if mismatch or dislocation >= 1.55 or corr_break >= 2.25:
                labels.append(5)
            elif broad_off >= 0.035 or abs(y_value) >= 3.1 or rpc <= -0.62 or (y_value <= -1.9 and rpc < -0.12):
                labels.append(4)
            elif (
                local_relief >= 0.0075
                and broad_off < 0.028
                and dislocation < 1.25
                and not (local_stress >= 0.018 and block_gap > 0.0065 and corr_local_dom > (corr_external_dom + 0.05))
            ):
                labels.append(3)
            elif local_stress >= 0.0095 or (block_gap > 0.0025 and corr_local_dom >= corr_external_dom):
                labels.append(2)
            elif (signal_raw >= -0.0004 and rpc >= -0.18 and block_consensus >= -0.0012 and broad_off <= 0.012):
                labels.append(0)
            else:
                labels.append(1)
        return np.asarray(labels, dtype=int)

    def _estimate_emission_params(
        self,
        emission: np.ndarray,
        probs: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        state_count = probs.shape[1]
        dimension = emission.shape[1]
        global_scale = np.asarray([
            _mad([float(value) for value in emission[:, column]])
            for column in range(dimension)
        ])
        means = np.zeros((state_count, dimension), dtype=float)
        scales = np.ones((state_count, dimension), dtype=float)
        for state_index in range(state_count):
            weights = np.asarray(probs[:, state_index], dtype=float)
            if float(np.sum(weights)) < 2.0:
                means[state_index, :] = np.nanmedian(emission, axis=0)
                scales[state_index, :] = global_scale
                continue
            for column in range(dimension):
                column_values = emission[:, column]
                mean = _weighted_average(column_values, weights)
                sigma = _weighted_sigma(column_values, weights, mean)
                means[state_index, column] = _clip(mean, -5.0, 5.0)
                scales[state_index, column] = max(min(sigma, 8.0), max(global_scale[column] * 0.18, 0.22))
        return means, scales

    @staticmethod
    def _apply_local_relief_probability_overlay(
        matrices: dict[str, Any],
        hmm: dict[str, Any],
    ) -> dict[str, Any]:
        probs = np.asarray(hmm.get("probabilities"), dtype=float)
        feature_keys = list(matrices.get("feature_keys") or [])
        x_raw = np.asarray(matrices.get("x_raw"), dtype=float)
        if probs.ndim != 2 or probs.shape[0] != x_raw.shape[0] or probs.shape[1] != len(STATE_DEFINITIONS):
            return hmm

        state_index = {
            str(item["key"]): index
            for index, item in enumerate(STATE_DEFINITIONS)
        }
        relief_feature_index = feature_keys.index("local_relief_impulse") if "local_relief_impulse" in feature_keys else None
        stress_feature_index = feature_keys.index("local_stress_impulse") if "local_stress_impulse" in feature_keys else None
        broad_off_index = feature_keys.index("broad_risk_off_pressure") if "broad_risk_off_pressure" in feature_keys else None
        dislocation_index = feature_keys.index("dislocation_pressure") if "dislocation_pressure" in feature_keys else None
        curve_slope_index = feature_keys.index("di_curve_slope_change") if "di_curve_slope_change" in feature_keys else None
        vix_relief_index = feature_keys.index("vixbr_relief_impulse") if "vixbr_relief_impulse" in feature_keys else None
        if relief_feature_index is None or curve_slope_index is None:
            return hmm

        relief_state = state_index.get("local_relief")
        risk_on_state = state_index.get("risk_on")
        local_stress_state = state_index.get("local_stress")
        risk_off_state = state_index.get("risk_off")
        if None in (relief_state, risk_on_state, local_stress_state, risk_off_state):
            return hmm

        adjusted = np.asarray(probs, dtype=float).copy()
        for index in range(len(adjusted)):
            relief = float(x_raw[index, relief_feature_index])
            curve_slope = float(x_raw[index, curve_slope_index])
            local_stress = float(x_raw[index, stress_feature_index]) if stress_feature_index is not None else 0.0
            broad_off = float(x_raw[index, broad_off_index]) if broad_off_index is not None else 0.0
            dislocation = float(x_raw[index, dislocation_index]) if dislocation_index is not None else 0.0
            vix_relief = float(x_raw[index, vix_relief_index]) if vix_relief_index is not None else 0.0
            if relief < 0.009 or curve_slope > -0.01 or broad_off > 0.024 or dislocation > 1.45:
                continue

            overlay = _clip(
                0.28
                + (14.0 * max(relief - 0.009, 0.0))
                + (8.0 * max((-curve_slope) - 0.01, 0.0))
                + (5.0 * max(vix_relief - 0.015, 0.0))
                - (8.0 * max(local_stress - 0.018, 0.0))
                - (4.0 * max(broad_off - 0.018, 0.0)),
                0.0,
                0.72,
            )
            if overlay <= 1e-9:
                continue

            row = adjusted[index, :].copy()
            donors = np.asarray([
                0.62 * row[risk_on_state],
                0.48 * row[local_stress_state],
                0.22 * row[risk_off_state],
            ], dtype=float)
            donor_total = float(np.sum(donors))
            if donor_total <= 1e-12:
                continue

            max_inflow = float(
                row[risk_on_state]
                + row[local_stress_state]
                + (0.5 * row[risk_off_state])
            )
            inflow = min(float(overlay), max_inflow)
            if inflow <= 1e-12:
                continue

            deductions = inflow * (donors / donor_total)
            row[risk_on_state] = max(row[risk_on_state] - deductions[0], 0.0)
            row[local_stress_state] = max(row[local_stress_state] - deductions[1], 0.0)
            row[risk_off_state] = max(row[risk_off_state] - deductions[2], 0.0)
            row[relief_state] += inflow
            adjusted[index, :] = _normalize_probabilities(row)

        hmm["probabilities"] = adjusted.tolist()
        return hmm

    @staticmethod
    def _estimate_transition(probs: np.ndarray, sticky_bias: float = 8.0) -> np.ndarray:
        state_count = probs.shape[1]
        hard = np.argmax(probs, axis=1)
        counts = np.full((state_count, state_count), 0.35, dtype=float)
        for state_index in range(state_count):
            counts[state_index, state_index] += sticky_bias
        for index in range(1, len(hard)):
            counts[int(hard[index - 1]), int(hard[index])] += 1.0
        transition = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1e-12)
        return transition

    @staticmethod
    def _transition_matrix_for_features(
        base_transition: np.ndarray,
        feature_vector: np.ndarray,
        feature_keys: list[str],
        state_definitions: list[dict[str, Any]],
    ) -> np.ndarray:
        state_index = {
            str(item["key"]): index
            for index, item in enumerate(state_definitions)
        }
        logits = np.log(np.maximum(np.asarray(base_transition, dtype=float), 1e-12))
        features = {
            key: _clip(float(feature_vector[index]), -4.0, 4.0)
            for index, key in enumerate(feature_keys)
        }
        block_consensus = features.get("block_consensus", 0.0)
        local_relief = max(features.get("local_relief_impulse", 0.0), 0.0)
        local_stress = max(features.get("local_stress_impulse", 0.0), 0.0)
        broad_off = max(features.get("broad_risk_off_pressure", 0.0), 0.0)
        corr_break = max(features.get("corr_break_score", 0.0), 0.0)
        dislocation = max(features.get("dislocation_pressure", 0.0), 0.0)
        block_gap = max(features.get("block_gap", 0.0), 0.0)
        local_dom = max(features.get("corr_state_local_dominance", 0.0), 0.0)
        external_dom = max(features.get("corr_state_external_dominance", 0.0), 0.0)
        corr_break_prob = max(features.get("corr_state_corr_break", 0.0), 0.0)
        block_agreement = _clip(features.get("block_agreement", 0.0), -4.0, 4.0)

        def bump(source_key: str, target_key: str, value: float) -> None:
            source = state_index.get(source_key)
            target = state_index.get(target_key)
            if source is None or target is None:
                return
            logits[source, target] += float(value)

        supportive = max(block_consensus, 0.0)
        agreement_penalty = max(-block_agreement, 0.0) * 0.18
        disagreement = agreement_penalty + corr_break_prob

        bump("risk_on", "risk_on", (0.85 * supportive) + (0.32 * external_dom) - (0.58 * local_stress) - (0.62 * broad_off))
        bump("risk_on", "local_relief", (0.24 * local_relief) + (0.08 * supportive) - (0.18 * local_stress))
        bump("risk_on", "local_stress", (1.10 * local_stress) + (0.62 * local_dom) + (0.26 * block_gap))
        bump("risk_on", "risk_off", (0.92 * broad_off) + (0.25 * max(-block_consensus, 0.0)))
        bump("risk_on", "stress", (0.80 * max(broad_off - 0.55, 0.0)) + (0.30 * dislocation))
        bump("risk_on", "dislocation", (0.95 * corr_break) + (0.52 * dislocation) + (0.35 * disagreement))

        bump("risk_off", "risk_off", (0.62 * broad_off) + (0.18 * local_dom) - (0.42 * supportive))
        bump("risk_off", "local_relief", (0.90 * local_relief) + (0.20 * supportive) - (0.35 * broad_off))
        bump("risk_off", "stress", (0.88 * broad_off) + (0.28 * dislocation))
        bump("risk_off", "local_stress", (0.46 * local_stress) + (0.15 * block_gap))
        bump("risk_off", "risk_on", (0.72 * supportive) + (0.36 * external_dom) - (0.72 * broad_off))
        bump("risk_off", "dislocation", (0.42 * corr_break) + (0.22 * disagreement))

        bump("local_stress", "local_stress", (0.82 * local_stress) + (0.26 * local_dom) - (0.24 * supportive) - (0.20 * corr_break_prob) - (0.42 * local_relief))
        bump("local_stress", "local_relief", (1.15 * local_relief) + (0.20 * external_dom) - (0.30 * broad_off) - (0.15 * corr_break))
        bump("local_stress", "risk_off", (0.95 * broad_off) + (0.35 * local_dom))
        bump("local_stress", "risk_on", (0.66 * supportive) + (0.26 * external_dom) - (0.72 * local_stress))
        bump("local_stress", "dislocation", (0.44 * corr_break) + (0.24 * dislocation) + (0.15 * disagreement))
        bump("local_stress", "stress", (0.54 * broad_off) + (0.24 * dislocation))

        bump("local_relief", "local_relief", (0.75 * local_relief) + (0.22 * supportive) - (0.35 * broad_off) - (0.25 * local_stress))
        bump("local_relief", "risk_on", (0.78 * supportive) + (0.42 * external_dom) + (0.40 * local_relief) - (0.25 * corr_break))
        bump("local_relief", "local_stress", (0.82 * local_stress) + (0.24 * local_dom) - (0.60 * local_relief))
        bump("local_relief", "risk_off", (0.55 * broad_off) + (0.20 * local_dom))
        bump("local_relief", "dislocation", (0.25 * corr_break) + (0.12 * dislocation))
        bump("local_relief", "stress", (0.38 * broad_off) + (0.14 * dislocation))

        bump("stress", "stress", (1.05 * broad_off) + (0.62 * dislocation) + (0.22 * corr_break))
        bump("stress", "risk_off", (0.32 * broad_off))
        bump("stress", "local_relief", (0.46 * local_relief) + (0.18 * supportive) - (0.25 * broad_off))
        bump("stress", "local_stress", (0.28 * local_stress))
        bump("stress", "risk_on", (0.42 * supportive) - (0.78 * broad_off))
        bump("stress", "dislocation", (0.48 * corr_break) + (0.25 * disagreement))

        bump("dislocation", "dislocation", (0.72 * corr_break) + (0.40 * dislocation) + (0.20 * disagreement) - (0.24 * local_stress))
        bump("dislocation", "local_relief", (0.34 * local_relief) + (0.16 * supportive) - (0.18 * corr_break))
        bump("dislocation", "local_stress", (0.56 * local_stress) + (0.18 * local_dom) - (0.10 * corr_break))
        bump("dislocation", "risk_off", (0.32 * broad_off))
        bump("dislocation", "risk_on", (0.42 * supportive) + (0.18 * external_dom) - (0.66 * corr_break))
        bump("dislocation", "stress", (0.42 * broad_off) + (0.32 * dislocation))

        output = np.zeros_like(logits, dtype=float)
        for row_index in range(logits.shape[0]):
            row_logits = logits[row_index, :]
            row_logits -= np.max(row_logits)
            row = np.exp(row_logits)
            output[row_index, :] = row / np.maximum(np.sum(row), 1e-12)
        return output

    def _transition_sequence(
        self,
        base_transition: np.ndarray,
        x_scaled: np.ndarray,
        feature_keys: list[str],
        state_definitions: list[dict[str, Any]],
    ) -> np.ndarray:
        matrices = []
        for index in range(len(x_scaled)):
            matrices.append(
                self._transition_matrix_for_features(
                    base_transition=base_transition,
                    feature_vector=np.asarray(x_scaled[index], dtype=float),
                    feature_keys=feature_keys,
                    state_definitions=state_definitions,
                )
            )
        return np.asarray(matrices, dtype=float)

    def _emission_loglikelihood(
        self,
        emission: np.ndarray,
        means: np.ndarray,
        scales: np.ndarray,
        state_definitions: list[dict[str, Any]] | None = None,
    ) -> np.ndarray:
        state_count = means.shape[0]
        definitions = state_definitions or STATE_DEFINITIONS
        output = np.zeros((emission.shape[0], state_count), dtype=float)
        for state_index in range(state_count):
            nu = _safe_float((definitions[state_index] if state_index < len(definitions) else {}).get("nu"), STUDENT_T_NU) or STUDENT_T_NU
            for column in range(emission.shape[1]):
                output[:, state_index] += np.asarray([
                    _student_t_logpdf(
                        float(value),
                        float(means[state_index, column]),
                        float(scales[state_index, column]),
                        nu,
                    )
                    for value in emission[:, column]
                ])
        return output

    @staticmethod
    def _forward_filter(log_emissions: np.ndarray, transition: np.ndarray, initial: np.ndarray) -> np.ndarray:
        sample_count, state_count = log_emissions.shape
        transition = np.asarray(transition, dtype=float)
        transition_is_dynamic = transition.ndim == 3
        log_transition = np.log(np.maximum(transition, 1e-12))
        log_alpha = np.zeros((sample_count, state_count), dtype=float)
        log_initial = np.log(np.maximum(_normalize_probabilities(initial), 1e-12))
        log_alpha[0, :] = log_initial + log_emissions[0, :]
        log_alpha[0, :] -= _logsumexp(log_alpha[0, :])
        for index in range(1, sample_count):
            previous = log_alpha[index - 1, :]
            current_transition = log_transition[index] if transition_is_dynamic else log_transition
            for state_index in range(state_count):
                log_alpha[index, state_index] = (
                    log_emissions[index, state_index]
                    + _logsumexp(previous + current_transition[:, state_index])
                )
            log_alpha[index, :] -= _logsumexp(log_alpha[index, :])
        return np.exp(log_alpha)

    def _fit_hmm(
        self,
        emission: np.ndarray,
        initial_labels: np.ndarray,
        *,
        state_definitions: list[dict[str, Any]] | None = None,
        transition_inputs: dict[str, Any] | None = None,
        sticky_bias: float = 8.0,
        iterations: int = 5,
    ) -> dict[str, Any]:
        definitions = state_definitions or STATE_DEFINITIONS
        state_count = len(definitions)
        initial_labels = np.asarray([
            int(_clip(int(label), 0, state_count - 1))
            for label in initial_labels
        ], dtype=int)
        probs = np.full((emission.shape[0], state_count), 0.02 / max(state_count - 1, 1), dtype=float)
        for index, label in enumerate(initial_labels):
            probs[index, :] = 0.02 / max(state_count - 1, 1)
            probs[index, int(label)] = 0.98

        base_transition = self._estimate_transition(probs, sticky_bias=sticky_bias)
        transition = (
            self._transition_sequence(
                base_transition,
                np.asarray(transition_inputs.get("x_scaled"), dtype=float),
                list(transition_inputs.get("feature_keys") or []),
                definitions,
            )
            if transition_inputs
            else base_transition
        )
        initial = _normalize_probabilities(np.bincount(initial_labels, minlength=state_count).astype(float) + 0.5)
        means, scales = self._estimate_emission_params(emission, probs)
        for _ in range(max(int(iterations or 5), 1)):
            log_emissions = self._emission_loglikelihood(emission, means, scales, definitions)
            probs = self._forward_filter(log_emissions, transition, initial)
            means, scales = self._estimate_emission_params(emission, probs)
            base_transition = self._estimate_transition(probs, sticky_bias=sticky_bias)
            transition = (
                self._transition_sequence(
                    base_transition,
                    np.asarray(transition_inputs.get("x_scaled"), dtype=float),
                    list(transition_inputs.get("feature_keys") or []),
                    definitions,
                )
                if transition_inputs
                else base_transition
            )
            initial = _normalize_probabilities((0.85 * initial) + (0.15 * probs[0, :]))

        log_emissions = self._emission_loglikelihood(emission, means, scales, definitions)
        probs = self._forward_filter(log_emissions, transition, initial)
        return {
            "probabilities": probs,
            "transition": transition[-1] if np.asarray(transition).ndim == 3 else transition,
            "transition_sequence": transition if np.asarray(transition).ndim == 3 else None,
            "base_transition": base_transition,
            "initial": initial,
            "means": means,
            "scales": scales,
            "log_emissions": log_emissions,
        }

    def _fit_state_regressions(
        self,
        *,
        x_scaled: np.ndarray,
        y: np.ndarray,
        probs: np.ndarray,
        feature_keys: list[str],
    ) -> dict[str, Any]:
        design = np.column_stack([np.ones(x_scaled.shape[0]), x_scaled])
        state_models: list[dict[str, Any]] = []
        global_sigma = max(_mad([float(value) for value in y]), 1e-6)
        ridge = 1e-4
        for state_index, state in enumerate(STATE_DEFINITIONS):
            base_weights = np.asarray(probs[:, state_index], dtype=float)
            if float(np.sum(base_weights)) < 2.5:
                base_weights = np.full(y.shape, 1.0 / len(STATE_DEFINITIONS))
            weights = base_weights.copy()
            coefficients = np.zeros(design.shape[1], dtype=float)
            sigma = global_sigma
            for _ in range(4):
                weight_matrix = weights[:, None]
                xtw = design.T @ (design * weight_matrix)
                regularizer = np.eye(design.shape[1]) * ridge
                regularizer[0, 0] = ridge * 0.05
                rhs = design.T @ (y * weights)
                try:
                    coefficients = np.linalg.solve(xtw + regularizer, rhs)
                except np.linalg.LinAlgError:
                    coefficients = np.linalg.lstsq(xtw + regularizer, rhs, rcond=None)[0]
                residual = y - (design @ coefficients)
                sigma = max(_weighted_sigma(residual, weights, 0.0), global_sigma * 0.12, 1e-6)
                robust_weights = (STUDENT_T_NU + 1.0) / (
                    STUDENT_T_NU + ((residual / sigma) ** 2)
                )
                weights = base_weights * np.clip(robust_weights, 0.08, 1.8)
            beta_values = coefficients[1:]
            state_models.append({
                "state_id": int(state["id"]),
                "state_key": state["key"],
                "alpha": float(coefficients[0]),
                "beta": {key: float(beta_values[index]) for index, key in enumerate(feature_keys)},
                "sigma": float(sigma),
                "effective_samples": float(np.sum(base_weights)),
            })
        return {
            "models": state_models,
            "design_predictions": np.column_stack([
                design @ np.asarray([model["alpha"], *[model["beta"].get(key, 0.0) for key in feature_keys]], dtype=float)
                for model in state_models
            ]),
        }

    def _state_payloads(
        self,
        probs: np.ndarray,
        transition: np.ndarray,
        state_definitions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        definitions = state_definitions or STATE_DEFINITIONS
        latest_probs = probs[-1, :] if probs.size else np.full(len(definitions), 1.0 / max(len(definitions), 1))
        states: list[dict[str, Any]] = []
        for index, state in enumerate(definitions):
            stay_probability = float(transition[index, index])
            dwell = 1.0 / max(1.0 - min(stay_probability, 0.995), 0.005)
            states.append({
                **state,
                "latest_probability": round(float(latest_probs[index]), 6),
                "stay_probability": round(stay_probability, 6),
                "expected_dwell_bars": round(dwell, 2),
            })
        return states

    @staticmethod
    def _theil_sen_slope(values: list[float]) -> float:
        clean = [float(value) for value in values if math.isfinite(float(value))]
        if len(clean) < 3:
            return 0.0
        slopes: list[float] = []
        for left in range(len(clean) - 1):
            for right in range(left + 1, len(clean)):
                distance = right - left
                if distance > 0:
                    slopes.append((clean[right] - clean[left]) / distance)
        return _median(slopes)

    @classmethod
    def _rolling_theil_sen_slopes(cls, matrix: np.ndarray, window: int = 10) -> np.ndarray:
        values = np.asarray(matrix, dtype=float)
        if values.ndim == 1:
            values = values.reshape((-1, 1))
        slopes = np.zeros_like(values, dtype=float)
        resolved_window = max(int(window or 10), 3)
        for column in range(values.shape[1]):
            for index in range(values.shape[0]):
                start = max(0, index - resolved_window + 1)
                slopes[index, column] = cls._theil_sen_slope(
                    [float(value) for value in values[start:index + 1, column]]
                )
        return slopes

    @staticmethod
    def _risk_thermometer_label(score: float) -> tuple[str, str, str]:
        if score <= -70.0:
            return "Risk-off extremo", "risk_off_extreme", "#ef4444"
        if score <= -35.0:
            return "Risk-off", "risk_off", "#f97316"
        if score <= -12.0:
            return "Defensivo", "defensive", "#f59e0b"
        if score < 12.0:
            return "Neutro", "neutral", "#94a3b8"
        if score < 35.0:
            return "Construtivo", "constructive", "#14b8a6"
        if score < 70.0:
            return "Risk-on", "risk_on", "#22c55e"
        return "Risk-on forte", "risk_on_strong", "#10b981"

    @staticmethod
    def _normalize_regime_mode(value: Any) -> str:
        normalized = str(value or "smart").strip().lower()
        return normalized if normalized in {"smart", "legacy"} else "smart"

    @staticmethod
    def _leg_display_name(key: str) -> str:
        label_map = {
            "credit": "Credito",
            "equity_foreign": "Equity externo",
            "equity_local": "Equity local",
            "commodities": "Commodities",
            "fx": "FX",
            "funding": "Funding",
            "di": "DI",
            "risk": "Risk",
            "sentiment": "Sentimento",
        }
        normalized = str(key or "").strip().lower()
        if normalized in label_map:
            return label_map[normalized]
        return normalized.replace("_", " ").strip().title() or "Leg"

    def _build_core_leg_context(self, row: dict[str, Any]) -> dict[str, Any]:
        feature_values = row.get("feature_values") if isinstance(row.get("feature_values"), dict) else {}
        leg_items: list[dict[str, Any]] = []
        for key, raw_value in feature_values.items():
            if not str(key).startswith("leg_") or not str(key).endswith("_impact"):
                continue
            value = _safe_float(raw_value)
            if value is None:
                continue
            leg_key = str(key).removeprefix("leg_").removesuffix("_impact")
            leg_items.append({
                "key": leg_key,
                "label": self._leg_display_name(leg_key),
                "impact": round(float(value), 8),
            })
        if not leg_items:
            return {
                "direction": "flat",
                "direction_label": "Core neutro",
                "aligned_support": 0.0,
                "opposing_drag": 0.0,
                "breadth": 0.0,
                "concentration": 0.0,
                "leaders": [],
                "drags": [],
                "positive_legs": [],
                "negative_legs": [],
            }

        positive_legs = [item for item in leg_items if float(item["impact"]) > 0.0]
        negative_legs = [item for item in leg_items if float(item["impact"]) < 0.0]
        positive_legs.sort(key=lambda item: float(item["impact"]), reverse=True)
        negative_legs.sort(key=lambda item: float(item["impact"]))

        expected_bps = _safe_float(row.get("expected_return_bps"), 0.0) or 0.0
        if expected_bps > 0.15:
            direction = "up"
            direction_label = "Core positivo"
            aligned = list(positive_legs)
            opposing = list(negative_legs)
        elif expected_bps < -0.15:
            direction = "down"
            direction_label = "Core negativo"
            aligned = list(negative_legs)
            opposing = list(positive_legs)
            aligned.sort(key=lambda item: abs(float(item["impact"])), reverse=True)
            opposing.sort(key=lambda item: abs(float(item["impact"])), reverse=True)
        else:
            direction = "flat"
            direction_label = "Core neutro"
            aligned = sorted(leg_items, key=lambda item: abs(float(item["impact"])), reverse=True)
            opposing = []

        total_abs = max(sum(abs(float(item["impact"])) for item in leg_items), 1e-9)
        aligned_abs = sum(abs(float(item["impact"])) for item in aligned)
        opposing_abs = sum(abs(float(item["impact"])) for item in opposing)
        aligned_count = sum(1 for item in aligned if abs(float(item["impact"])) >= 0.00005)
        opposing_count = sum(1 for item in opposing if abs(float(item["impact"])) >= 0.00005)
        concentration = max(abs(float(item["impact"])) for item in leg_items) / total_abs
        breadth = (aligned_count - opposing_count) / max(len(leg_items), 1)

        return {
            "direction": direction,
            "direction_label": direction_label,
            "aligned_support": round(aligned_abs / total_abs, 4),
            "opposing_drag": round(opposing_abs / total_abs, 4),
            "breadth": round(breadth, 4),
            "concentration": round(concentration, 4),
            "leaders": aligned[:3],
            "drags": opposing[:3],
            "positive_legs": positive_legs[:3],
            "negative_legs": negative_legs[:3],
        }

    def _annotate_core_leg_contexts(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            row["core_leg_context"] = self._build_core_leg_context(row)

    def _cached_flow_activity_snapshot(self, session_date: str | None) -> dict[str, Any] | None:
        resolved_date = str(session_date or "").strip()
        if not resolved_date:
            return None
        cache_key = resolved_date
        cached = self._flow_radar_cache.get(cache_key)
        if cached and (time.time() - float(cached[0])) <= 15.0:
            return deepcopy(cached[1])
        try:
            payload = self.flow_activity_radar_service.build_dashboard(
                session_date=resolved_date,
                top_runs=12,
            )
        except Exception:
            logger.exception("Failed to build Flow Activity Radar snapshot for %s", resolved_date)
            return None
        if not isinstance(payload, dict):
            return None
        self._flow_radar_cache[cache_key] = (time.time(), deepcopy(payload))
        return payload

    def _build_flow_activity_meta(self, session_date: str | None) -> dict[str, Any] | None:
        payload = self._cached_flow_activity_snapshot(session_date)
        if not isinstance(payload, dict) or not payload.get("ok"):
            return None
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        reader = payload.get("reader") if isinstance(payload.get("reader"), dict) else {}
        detections = [
            item for item in (payload.get("detections") or [])
            if isinstance(item, dict)
        ]
        dominant_side = str(summary.get("dominant_side") or "neutral").strip().lower()
        direction_sign = 1.0 if dominant_side == "buy" else (-1.0 if dominant_side == "sell" else 0.0)
        projected_net = _safe_float(summary.get("projected_net_close"))
        current_net = _safe_float(summary.get("current_net_contracts"))
        resolved_flow = projected_net if projected_net is not None else (current_net or 0.0)
        magnitude = math.tanh(abs(float(resolved_flow or 0.0)) / 60_000.0)
        holding_level = self._scaled_positive(summary.get("holding_score_mean"), 38.0, 88.0)
        confidence_level = self._scaled_positive(summary.get("confidence_mean"), 45.0, 99.0)
        concentration_level = self._scaled_positive(summary.get("concentration"), 0.42, 0.84)
        active_runs = max(int(_safe_float(summary.get("active_runs"), 0.0) or 0), 0)
        live_factor = 1.0 if bool(summary.get("has_live_projection")) else 0.72

        style_weights = {
            "steady_inventory_builder": 1.0,
            "passive_builder": 0.82,
            "aggressive_taker": 0.58,
            "mixed_executor": 0.42,
            "rlp_recycler": 0.24,
        }
        weighted_style = 0.0
        weighted_total = 0.0
        top_runs: list[dict[str, Any]] = []
        for item in detections[:4]:
            style = item.get("style") if isinstance(item.get("style"), dict) else {}
            style_key = str(style.get("key") or "").strip()
            side_sign = 1.0 if str(item.get("side") or "").strip() == "buy" else -1.0
            size = abs(_safe_float(item.get("absolute_delta_contracts"), 0.0) or 0.0)
            weight = max(size, 1.0)
            weighted_style += side_sign * style_weights.get(style_key, 0.3) * weight
            weighted_total += weight
            top_runs.append({
                "display_name": item.get("display_name"),
                "side": item.get("side"),
                "status": item.get("status"),
                "style_label": style.get("label"),
                "delta_contracts": _round_float(item.get("delta_contracts"), 0),
                "projected_total_contracts": _round_float(item.get("projected_total_contracts"), 0),
                "holding_score": _round_float(item.get("holding_score"), 2),
                "confidence": _round_float(item.get("confidence"), 2),
                "momentum_label": (item.get("momentum") or {}).get("label") if isinstance(item.get("momentum"), dict) else None,
            })
        style_bias = 0.0 if weighted_total <= 1e-9 else _clip(weighted_style / weighted_total, -1.0, 1.0)

        structural_strength = _clip(
            (0.38 * magnitude)
            + (0.22 * holding_level)
            + (0.18 * confidence_level)
            + (0.12 * concentration_level)
            + (0.10 * abs(style_bias)),
            0.0,
            1.0,
        )
        structural_score = direction_sign * structural_strength * live_factor

        if direction_sign > 0:
            bias_label = "Fluxo comprador"
        elif direction_sign < 0:
            bias_label = "Fluxo vendedor"
        else:
            bias_label = "Fluxo neutro"

        return {
            "ok": True,
            "session_date": session_date,
            "bias_key": dominant_side or "neutral",
            "bias_label": bias_label,
            "structural_score": round(structural_score, 4),
            "strength": round(structural_strength, 4),
            "holding_level": round(holding_level, 4),
            "confidence_level": round(confidence_level, 4),
            "concentration_level": round(concentration_level, 4),
            "active_runs": active_runs,
            "reader_tone": reader.get("tone"),
            "headline": reader.get("headline"),
            "projected_net_close": _round_float(projected_net, 2),
            "current_net_contracts": _round_float(current_net, 2),
            "top_runs": top_runs,
            "top_styles": sorted({
                str(((item.get("style") or {}).get("label")) or "").strip()
                for item in detections[:4]
                if isinstance(item, dict)
            }),
        }

    @staticmethod
    def _meta_regime_definition(key: str) -> dict[str, str]:
        for item in META_REGIME_DEFINITIONS:
            if str(item.get("key")) == str(key):
                return item
        return META_REGIME_DEFINITIONS[-1]

    @staticmethod
    def _scaled_positive(value: Any, floor: float, ceiling: float) -> float:
        numeric = _safe_float(value, 0.0) or 0.0
        if ceiling <= floor:
            return 0.0
        return _clip((numeric - floor) / (ceiling - floor), 0.0, 1.0)

    @classmethod
    def _scaled_negative(cls, value: Any, floor: float, ceiling: float) -> float:
        return cls._scaled_positive(-(_safe_float(value, 0.0) or 0.0), floor, ceiling)

    @staticmethod
    def _meta_rule_selected_key(
        *,
        score_map: dict[str, float],
        meta_features: dict[str, float],
        risk_score: float,
    ) -> str:
        defensive_rally_score = float(score_map.get("defensive_rally", 0.0))
        fragile_risk_on_score = float(score_map.get("fragile_risk_on", 0.0))
        clean_risk_on_score = float(score_map.get("clean_risk_on", 0.0))
        capitulation_score = float(score_map.get("capitulation", 0.0))
        defensive_balance_score = float(score_map.get("defensive_balance", 0.0))
        trend_support = float(meta_features.get("trend_support", 0.0))
        supportive_equity = float(meta_features.get("supportive_equity", 0.0))
        panic_tail = float(meta_features.get("panic_tail", 0.0))
        dislocation_drag = float(meta_features.get("dislocation_drag", 0.0))
        corr_fracture = float(meta_features.get("corr_fracture", 0.0))
        state_defensive = float(meta_features.get("state_defensive", 0.0))
        flow_drag = float(meta_features.get("flow_drag", 0.0))
        aligned_support = float(meta_features.get("aligned_support", 0.0))

        if (
            defensive_rally_score >= 0.54
            and trend_support >= 0.42
            and supportive_equity >= 0.32
            and panic_tail < 0.52
            and (dislocation_drag >= 0.40 or corr_fracture >= 0.45)
            and (state_defensive >= 0.40 or flow_drag >= 0.50)
        ):
            return "defensive_rally"
        if capitulation_score >= 0.60 and (panic_tail >= 0.35 or state_defensive >= 0.60):
            return "capitulation"
        if (
            clean_risk_on_score >= 0.50
            and aligned_support >= 0.45
            and dislocation_drag < 0.42
            and risk_score >= 18.0
        ):
            return "clean_risk_on"
        if (
            fragile_risk_on_score >= 0.42
            and trend_support >= 0.28
            and supportive_equity >= 0.25
            and risk_score >= 8.0
        ):
            return "fragile_risk_on"
        if defensive_balance_score >= 0.50 or risk_score <= -12.0:
            return "defensive_balance"
        return "balanced"

    @staticmethod
    def _meta_driver_list(driver_map: dict[str, float]) -> list[dict[str, float]]:
        return [
            {"key": driver_key, "score": round(float(driver_score), 4)}
            for driver_key, driver_score in sorted(
                driver_map.items(),
                key=lambda item: float(item[1]),
                reverse=True,
            )[:4]
            if float(driver_score) > 0.22
        ]

    def _fit_meta_regime_hmm(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if len(rows) < 18:
            return None

        feature_keys = [
            "trend_support",
            "supportive_equity",
            "defensive_internal",
            "state_defensive",
            "positive_state",
            "dislocation_drag",
            "flow_drag",
            "corr_fracture",
            "aligned_support",
            "panic_tail",
            "core_alignment",
            "core_conflict",
            "flow_positive",
            "flow_negative",
            "risk_score_positive",
            "risk_score_negative",
        ]
        state_index = {
            str(item["key"]): int(item["id"])
            for item in META_HMM_STATE_DEFINITIONS
        }

        emission_rows: list[list[float]] = []
        initial_labels: list[int] = []
        for row in rows:
            features = row.get("meta_regime_feature_values") if isinstance(row.get("meta_regime_feature_values"), dict) else {}
            if not features:
                continue
            emission_rows.append([
                float(_clip(_safe_float(features.get(key), 0.0) or 0.0, 0.0, 1.0))
                for key in feature_keys
            ])
            initial_key = str(row.get("meta_regime_rule_key") or "").strip()
            if initial_key not in state_index:
                score_map = row.get("meta_regime_rule_scores") if isinstance(row.get("meta_regime_rule_scores"), dict) else {}
                candidate_keys = [key for key in state_index if key in score_map]
                initial_key = max(
                    candidate_keys,
                    key=lambda key: float(score_map.get(key, 0.0)),
                    default="defensive_balance",
                )
            initial_labels.append(state_index.get(initial_key, state_index["defensive_balance"]))

        if len(emission_rows) < 18:
            return None

        hmm = self._fit_hmm(
            np.asarray(emission_rows, dtype=float),
            np.asarray(initial_labels, dtype=int),
            state_definitions=META_HMM_STATE_DEFINITIONS,
            sticky_bias=12.0,
            iterations=4,
        )
        probabilities = np.asarray(hmm.get("probabilities"), dtype=float)
        transition = np.asarray(hmm.get("transition"), dtype=float)
        return {
            "feature_keys": feature_keys,
            "probabilities": probabilities,
            "transition": transition,
            "states": self._state_payloads(probabilities, transition, META_HMM_STATE_DEFINITIONS),
            "model": "sticky_meta_hmm_v1",
        }

    def _apply_meta_regime_layer(
        self,
        *,
        rows: list[dict[str, Any]],
        flow_activity_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not rows:
            return {
                "latest": None,
                "states": META_REGIME_DEFINITIONS,
                "counts": {},
                "secondary_states": META_HMM_STATE_DEFINITIONS,
                "model": "hybrid_structural_meta_regime",
                "methodology": "",
            }

        latest_index = max(len(rows) - 1, 0)
        latest_session_date = str(rows[-1].get("session_date") or "").strip() if rows else ""
        for index, row in enumerate(rows):
            risk_thermo = row.get("risk_thermometer") if isinstance(row.get("risk_thermometer"), dict) else {}
            components = risk_thermo.get("components") if isinstance(risk_thermo.get("components"), dict) else {}
            state_prob = row.get("state_probability_map") if isinstance(row.get("state_probability_map"), dict) else {}
            tape_prob = row.get("tape_state_probability_map") if isinstance(row.get("tape_state_probability_map"), dict) else {}
            corr_prob = row.get("corr_state_probability_map") if isinstance(row.get("corr_state_probability_map"), dict) else {}
            feature_z = row.get("feature_z_values") if isinstance(row.get("feature_z_values"), dict) else {}
            core_legs = row.get("core_leg_context") if isinstance(row.get("core_leg_context"), dict) else {}

            risk_score = _safe_float(risk_thermo.get("score"), 0.0) or 0.0
            markov_component = _safe_float(components.get("markov"), 0.0) or 0.0
            flow_component = _safe_float(components.get("flow"), 0.0) or 0.0
            correlation_component = _safe_float(components.get("correlation"), 0.0) or 0.0
            core_alignment = _clip(
                (0.60 * self._scaled_positive(core_legs.get("aligned_support"), 0.28, 0.86))
                + (0.40 * self._scaled_positive(core_legs.get("breadth"), 0.0, 0.8)),
                0.0,
                1.0,
            )
            core_conflict = _clip(
                (0.62 * self._scaled_positive(core_legs.get("opposing_drag"), 0.22, 0.72))
                + (0.38 * self._scaled_positive(core_legs.get("concentration"), 0.22, 0.68)),
                0.0,
                1.0,
            )
            has_live_flow_meta = (
                bool(flow_activity_meta)
                and index == latest_index
                and str(row.get("session_date") or "").strip() == latest_session_date
            )
            flow_structural_score = _safe_float((flow_activity_meta or {}).get("structural_score"), 0.0) or 0.0
            flow_positive = max(flow_structural_score, 0.0) if has_live_flow_meta else 0.0
            flow_negative = max(-flow_structural_score, 0.0) if has_live_flow_meta else 0.0

            trend_support = _clip(
                (0.66 * (_safe_float(tape_prob.get("trend"), 0.0) or 0.0))
                + (0.16 * (_safe_float(tape_prob.get("expansion"), 0.0) or 0.0))
                + (0.10 * (1.0 if str(row.get("tape_direction") or "").lower() == "up" else 0.0))
                + (0.08 * self._scaled_positive(row.get("return_bps"), 0.2, 8.0)),
                0.0,
                1.0,
            )
            panic_tail = _clip(
                (0.72 * (_safe_float(tape_prob.get("panic"), 0.0) or 0.0))
                + (0.28 * self._scaled_negative(row.get("return_bps"), 0.4, 10.0)),
                0.0,
                1.0,
            )
            supportive_equity = _clip(
                (0.56 * self._scaled_positive(feature_z.get("leg_equity_local_impact"), 0.15, 2.1))
                + (0.28 * self._scaled_positive(feature_z.get("leg_equity_foreign_impact"), 0.10, 1.8))
                + (0.16 * self._scaled_positive(feature_z.get("leg_risk_impact"), 0.05, 1.4)),
                0.0,
                1.0,
            )
            defensive_internal = _clip(
                (0.40 * self._scaled_negative(feature_z.get("leg_di_impact"), 0.10, 2.2))
                + (0.24 * self._scaled_negative(feature_z.get("leg_fx_impact"), 0.08, 1.8))
                + (0.18 * self._scaled_negative(feature_z.get("leg_funding_impact"), 0.08, 1.5))
                + (0.18 * self._scaled_negative(feature_z.get("leg_credit_impact"), 0.08, 1.4)),
                0.0,
                1.0,
            )
            state_defensive = _clip(
                (0.52 * (_safe_float(state_prob.get("risk_off"), 0.0) or 0.0))
                + (0.22 * (_safe_float(state_prob.get("stress"), 0.0) or 0.0))
                + (0.14 * (_safe_float(state_prob.get("dislocation"), 0.0) or 0.0))
                + (0.12 * self._scaled_negative(markov_component, 5.0, 80.0)),
                0.0,
                1.0,
            )
            positive_state = _clip(
                (0.58 * (_safe_float(state_prob.get("risk_on"), 0.0) or 0.0))
                + (0.42 * (_safe_float(state_prob.get("local_relief"), 0.0) or 0.0)),
                0.0,
                1.0,
            )
            dislocation_drag = _clip(
                (0.34 * self._scaled_negative(row.get("fair_value_gap_z"), 1.15, 3.8))
                + (0.28 * self._scaled_positive(row.get("dislocation_score"), 55.0, 100.0))
                + (0.22 * self._scaled_negative(feature_z.get("edge_bias"), 0.65, 3.6))
                + (0.16 * self._scaled_positive(feature_z.get("dislocation_pressure"), 0.25, 2.1)),
                0.0,
                1.0,
            )
            flow_drag = _clip(
                (0.68 * self._scaled_negative(flow_component, 5.0, 90.0))
                + (0.32 * self._scaled_negative(feature_z.get("rpc_pressure"), 0.15, 2.5)),
                0.0,
                1.0,
            )
            corr_fracture = _clip(
                (0.52 * (_safe_float(corr_prob.get("corr_break"), 0.0) or 0.0))
                + (0.18 * self._scaled_negative(correlation_component, 5.0, 75.0))
                + (0.18 * self._scaled_positive(feature_z.get("corr_break_score"), 0.20, 2.4))
                + (0.12 * self._scaled_negative(feature_z.get("corr_state_aligned"), 0.20, 2.0)),
                0.0,
                1.0,
            )
            aligned_support = _clip(
                (0.48 * (_safe_float(corr_prob.get("aligned"), 0.0) or 0.0))
                + (0.26 * (_safe_float(corr_prob.get("external_dominance"), 0.0) or 0.0))
                + (0.26 * self._scaled_positive(correlation_component, 5.0, 75.0)),
                0.0,
                1.0,
            )
            risk_score_positive = self._scaled_positive(risk_score, 8.0, 55.0)
            risk_score_negative = self._scaled_negative(risk_score, 8.0, 65.0)

            defensive_rally_score = _clip(
                (0.26 * trend_support)
                + (0.16 * supportive_equity)
                + (0.18 * state_defensive)
                + (0.16 * dislocation_drag)
                + (0.12 * flow_drag)
                + (0.12 * corr_fracture)
                + (0.10 * defensive_internal)
                + (0.10 * core_alignment)
                + (0.08 * flow_positive)
                - (0.10 * risk_score_positive),
                0.0,
                1.0,
            )
            fragile_risk_on_score = _clip(
                (0.24 * trend_support)
                + (0.21 * supportive_equity)
                + (0.18 * risk_score_positive)
                + (0.10 * positive_state)
                + (0.10 * aligned_support)
                + (0.14 * core_alignment)
                + (0.16 * flow_positive)
                - (0.10 * dislocation_drag)
                - (0.09 * flow_drag)
                - (0.08 * corr_fracture)
                - (0.08 * defensive_internal),
                0.0,
                1.0,
            )
            clean_risk_on_score = _clip(
                (0.18 * trend_support)
                + (0.18 * supportive_equity)
                + (0.22 * risk_score_positive)
                + (0.18 * positive_state)
                + (0.16 * aligned_support)
                + (0.18 * core_alignment)
                + (0.20 * flow_positive)
                - (0.12 * dislocation_drag)
                - (0.08 * flow_drag)
                - (0.06 * defensive_internal)
                - (0.06 * corr_fracture),
                0.0,
                1.0,
            )
            capitulation_score = _clip(
                (0.28 * (_safe_float(state_prob.get("stress"), 0.0) or 0.0))
                + (0.16 * (_safe_float(state_prob.get("dislocation"), 0.0) or 0.0))
                + (0.16 * panic_tail)
                + (0.14 * risk_score_negative)
                + (0.12 * dislocation_drag)
                + (0.08 * flow_drag)
                + (0.06 * corr_fracture)
                + (0.10 * core_conflict)
                + (0.12 * flow_negative),
                0.0,
                1.0,
            )
            defensive_balance_score = _clip(
                (0.28 * state_defensive)
                + (0.18 * flow_drag)
                + (0.16 * defensive_internal)
                + (0.12 * corr_fracture)
                + (0.12 * dislocation_drag)
                + (0.10 * risk_score_negative)
                + (0.14 * core_conflict)
                + (0.10 * flow_negative)
                - (0.10 * trend_support),
                0.0,
                1.0,
            )
            balanced_score = _clip(
                1.0
                - max(
                    defensive_rally_score,
                    fragile_risk_on_score,
                    clean_risk_on_score,
                    capitulation_score,
                    defensive_balance_score,
                ),
                0.0,
                1.0,
            )

            score_map = {
                "defensive_rally": defensive_rally_score,
                "fragile_risk_on": fragile_risk_on_score,
                "clean_risk_on": clean_risk_on_score,
                "capitulation": capitulation_score,
                "defensive_balance": defensive_balance_score,
                "balanced": balanced_score,
            }
            driver_map = {
                "trend_support": trend_support,
                "supportive_equity": supportive_equity,
                "defensive_internal": defensive_internal,
                "state_defensive": state_defensive,
                "positive_state": positive_state,
                "dislocation_drag": dislocation_drag,
                "flow_drag": flow_drag,
                "corr_fracture": corr_fracture,
                "aligned_support": aligned_support,
                "panic_tail": panic_tail,
                "core_alignment": core_alignment,
                "core_conflict": core_conflict,
                "flow_positive": flow_positive,
                "flow_negative": flow_negative,
            }
            meta_features = {
                "trend_support": round(trend_support, 4),
                "supportive_equity": round(supportive_equity, 4),
                "defensive_internal": round(defensive_internal, 4),
                "state_defensive": round(state_defensive, 4),
                "positive_state": round(positive_state, 4),
                "dislocation_drag": round(dislocation_drag, 4),
                "flow_drag": round(flow_drag, 4),
                "corr_fracture": round(corr_fracture, 4),
                "aligned_support": round(aligned_support, 4),
                "panic_tail": round(panic_tail, 4),
                "core_alignment": round(core_alignment, 4),
                "core_conflict": round(core_conflict, 4),
                "flow_positive": round(flow_positive, 4),
                "flow_negative": round(flow_negative, 4),
                "risk_score_positive": round(risk_score_positive, 4),
                "risk_score_negative": round(risk_score_negative, 4),
            }
            selected_key = self._meta_rule_selected_key(
                score_map=score_map,
                meta_features=meta_features,
                risk_score=risk_score,
            )
            row["meta_regime_rule_key"] = selected_key
            row["meta_regime_rule_scores"] = {
                key_name: round(float(score_value), 4)
                for key_name, score_value in score_map.items()
            }
            row["meta_regime_feature_values"] = meta_features
            row["meta_regime_driver_map"] = {
                key_name: round(float(score_value), 4)
                for key_name, score_value in driver_map.items()
            }
            row["meta_regime_flow_activity"] = deepcopy(flow_activity_meta) if has_live_flow_meta and flow_activity_meta else None
            row["meta_regime_secondary_state_key"] = None
            row["meta_regime_secondary_probability"] = None
            row["meta_regime_secondary_probability_map"] = {}

        secondary_hmm = self._fit_meta_regime_hmm(rows)
        secondary_probs = np.asarray(secondary_hmm.get("probabilities"), dtype=float) if isinstance(secondary_hmm, dict) else np.empty((0, 0))
        secondary_states = secondary_hmm.get("states") if isinstance(secondary_hmm, dict) else []
        secondary_state_by_index = {
            index: META_HMM_STATE_DEFINITIONS[index]
            for index in range(len(META_HMM_STATE_DEFINITIONS))
        }
        counts: dict[str, int] = {}
        secondary_latest: dict[str, Any] | None = None

        for index, row in enumerate(rows):
            rule_scores = row.get("meta_regime_rule_scores") if isinstance(row.get("meta_regime_rule_scores"), dict) else {}
            full_score_map = {
                key_name: float(rule_scores.get(key_name, 0.0))
                for key_name in ["defensive_rally", "fragile_risk_on", "clean_risk_on", "capitulation", "defensive_balance", "balanced"]
            }
            hmm_probability_map: dict[str, float] = {}
            hmm_key = None
            hmm_confidence = 0.0
            if secondary_probs.ndim == 2 and index < secondary_probs.shape[0]:
                row_probs = np.asarray(secondary_probs[index], dtype=float)
                for state_index, definition in secondary_state_by_index.items():
                    if state_index < row_probs.shape[0]:
                        hmm_probability_map[str(definition["key"])] = float(row_probs[state_index])
                if hmm_probability_map:
                    hmm_key = max(hmm_probability_map, key=lambda key: hmm_probability_map[key])
                    hmm_confidence = float(hmm_probability_map.get(hmm_key, 0.0))
                    row["meta_regime_secondary_state_key"] = hmm_key
                    row["meta_regime_secondary_probability"] = round(hmm_confidence * 100.0, 2)
                    row["meta_regime_secondary_probability_map"] = {
                        key_name: round(probability, 4)
                        for key_name, probability in hmm_probability_map.items()
                    }

                    blended_scores = {}
                    for key_name in ["defensive_rally", "fragile_risk_on", "clean_risk_on", "capitulation", "defensive_balance"]:
                        blended_scores[key_name] = _clip(
                            (0.58 * float(rule_scores.get(key_name, 0.0)))
                            + (0.42 * float(hmm_probability_map.get(key_name, 0.0))),
                            0.0,
                            1.0,
                        )
                    ranked = sorted(blended_scores.values(), reverse=True)
                    top_score = ranked[0] if ranked else 0.0
                    runner_up = ranked[1] if len(ranked) > 1 else 0.0
                    ambiguity = 1.0 - _clip(top_score - runner_up, 0.0, 1.0)
                    balanced_score = _clip(
                        (0.58 * float(rule_scores.get("balanced", 0.0)))
                        + (0.24 * ambiguity)
                        + (0.18 * max(0.0, 0.46 - top_score)),
                        0.0,
                        1.0,
                    )
                    full_score_map = {
                        **blended_scores,
                        "balanced": balanced_score,
                    }

            final_key = max(full_score_map, key=lambda key: float(full_score_map.get(key, 0.0)))
            top_non_balanced = max(
                (key for key in full_score_map if key != "balanced"),
                key=lambda key: float(full_score_map.get(key, 0.0)),
                default="defensive_balance",
            )
            top_non_balanced_score = float(full_score_map.get(top_non_balanced, 0.0))
            if final_key == "balanced":
                final_confidence = _clip(full_score_map.get("balanced", 0.0) * 100.0, 0.0, 100.0)
            else:
                if top_non_balanced_score < 0.40 or str(row.get("meta_regime_rule_key") or "") == "balanced" and top_non_balanced_score < 0.48:
                    final_key = "balanced"
                    final_confidence = _clip(full_score_map.get("balanced", 0.0) * 100.0, 0.0, 100.0)
                else:
                    final_confidence = _clip(
                        ((0.68 * top_non_balanced_score) + (0.32 * hmm_confidence)) * 100.0,
                        0.0,
                        100.0,
                    )
                    final_key = top_non_balanced

            definition = self._meta_regime_definition(final_key)
            drivers = self._meta_driver_list(
                row.get("meta_regime_driver_map") if isinstance(row.get("meta_regime_driver_map"), dict) else {}
            )
            row["meta_regime_key"] = definition["key"]
            row["meta_regime_name"] = definition["name"]
            row["meta_regime_color"] = definition["color"]
            row["meta_regime_description"] = definition["description"]
            row["meta_regime_confidence"] = round(final_confidence, 2)
            row["meta_regime_scores"] = {
                key_name: round(float(score_value), 4)
                for key_name, score_value in full_score_map.items()
            }
            row["meta_regime_drivers"] = drivers
            counts[definition["key"]] = counts.get(definition["key"], 0) + 1

            if index == latest_index:
                secondary_latest = {
                    "key": hmm_key,
                    "name": self._meta_regime_definition(hmm_key)["name"] if hmm_key else None,
                    "color": self._meta_regime_definition(hmm_key)["color"] if hmm_key else None,
                    "confidence": round(hmm_confidence * 100.0, 2) if hmm_key else None,
                    "probabilities": {
                        key_name: round(float(probability), 4)
                        for key_name, probability in hmm_probability_map.items()
                    },
                }

        latest = rows[-1]
        return {
            "latest": {
                "key": latest.get("meta_regime_key"),
                "name": latest.get("meta_regime_name"),
                "color": latest.get("meta_regime_color"),
                "description": latest.get("meta_regime_description"),
                "confidence": latest.get("meta_regime_confidence"),
                "scores": deepcopy(latest.get("meta_regime_scores")) if isinstance(latest.get("meta_regime_scores"), dict) else {},
                "drivers": deepcopy(latest.get("meta_regime_drivers")) if isinstance(latest.get("meta_regime_drivers"), list) else [],
                "flow_activity": deepcopy(latest.get("meta_regime_flow_activity")) if isinstance(latest.get("meta_regime_flow_activity"), dict) else None,
                "core_legs": deepcopy(latest.get("core_leg_context")) if isinstance(latest.get("core_leg_context"), dict) else {},
                "secondary_hmm": deepcopy(secondary_latest) if isinstance(secondary_latest, dict) else None,
            },
            "states": META_REGIME_DEFINITIONS,
            "secondary_states": secondary_states,
            "counts": counts,
            "model": "hybrid_structural_meta_regime",
            "secondary_model": secondary_hmm.get("model") if isinstance(secondary_hmm, dict) else None,
            "methodology": (
                "Meta-regime hibrido: regras estruturais robustas geram a leitura economica e um HMM "
                "secundario sticky, pequeno e alimentado por features agregadas suaviza a persistencia "
                "entre rali defensivo, risk-on fragil, risk-on limpo, capitulacao e balanceamento defensivo. "
                "O estado Balanceado permanece como fallback quando a mistura regra + HMM nao entrega "
                "conviccao estatistica suficiente."
            ),
        }

    def _build_risk_thermometer(
        self,
        *,
        rows: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        matrices: dict[str, Any],
        hmm: dict[str, Any],
        regime_mode: str = "smart",
    ) -> dict[str, Any]:
        if not rows:
            return {
                "latest": None,
                "model": "robust_markov_cross_asset_risk_thermometer",
                "components": [],
            }

        probabilities = np.asarray(hmm.get("probabilities"), dtype=float)
        x_scaled = np.asarray(matrices.get("x_scaled"), dtype=float)
        emission = np.asarray(matrices.get("emission"), dtype=float)
        feature_keys = list(matrices.get("feature_keys") or [])
        if probabilities.size == 0 or x_scaled.size == 0 or not feature_keys:
            return {
                "latest": None,
                "model": "robust_markov_cross_asset_risk_thermometer",
                "components": [],
            }

        feature_index = {key: index for index, key in enumerate(feature_keys)}
        leg_indices = [
            index for index, key in enumerate(feature_keys)
            if key.startswith("leg_") and key.endswith("_impact")
        ]
        slopes = self._rolling_theil_sen_slopes(x_scaled, window=10) * math.sqrt(10.0)
        y_z = emission[:, 0] if emission.ndim == 2 and emission.shape[1] else np.zeros(len(rows))
        y_slope = self._rolling_theil_sen_slopes(y_z.reshape((-1, 1)), window=10)[:, 0] * math.sqrt(10.0)

        use_legacy = self._normalize_regime_mode(regime_mode) == "legacy"
        if use_legacy:
            component_meta = [
                {"key": "markov", "label": "Markov", "weight": 0.30},
                {"key": "legs", "label": "Pernas/ativos", "weight": 0.20},
                {"key": "flow", "label": "Fluxo RPC", "weight": 0.14},
                {"key": "local", "label": "Brasil local", "weight": 0.16},
                {"key": "correlation", "label": "Correlacao", "weight": 0.12},
                {"key": "trend", "label": "Tendencia", "weight": 0.05},
                {"key": "stress", "label": "Stress", "weight": 0.03},
            ]
        else:
            component_meta = [
                {"key": "markov", "label": "Markov", "weight": 0.34},
                {"key": "legs", "label": "Pernas/ativos", "weight": 0.18},
                {"key": "flow", "label": "Fluxo RPC", "weight": 0.12},
                {"key": "local", "label": "Brasil local", "weight": 0.18},
                {"key": "correlation", "label": "Correlacao", "weight": 0.12},
                {"key": "trend", "label": "Tendencia", "weight": 0.04},
                {"key": "stress", "label": "Stress", "weight": 0.02},
            ]
        previous_score_by_session: dict[str, float] = {}
        previous_key_by_session: dict[str, str] = {}
        pending_transition_by_session: dict[str, int] = {}

        for index, row in enumerate(rows):
            source_row = (
                observations[index].get("source_row")
                if index < len(observations) and isinstance(observations[index], dict)
                else {}
            )
            if not isinstance(source_row, dict):
                source_row = {}
            z_values = x_scaled[index, :] if index < x_scaled.shape[0] else np.zeros(len(feature_keys))
            slope_values = slopes[index, :] if index < slopes.shape[0] else np.zeros(len(feature_keys))
            state_probs = probabilities[index, :] if index < probabilities.shape[0] else np.zeros(len(STATE_DEFINITIONS))
            probability_map = {
                str(STATE_DEFINITIONS[state_index]["key"]): float(state_probs[state_index])
                for state_index in range(min(len(STATE_DEFINITIONS), len(state_probs)))
            }

            state_score = _clip(
                probability_map.get("risk_on", 0.0)
                + (0.28 * probability_map.get("local_relief", 0.0))
                - (0.52 * probability_map.get("risk_off", 0.0))
                - (0.78 * probability_map.get("local_stress", 0.0))
                - (0.88 * probability_map.get("stress", 0.0))
                - (0.72 * probability_map.get("dislocation", 0.0)),
                -1.0,
                1.0,
            )

            leg_values: list[float] = []
            leg_weights: list[float] = []
            for leg_index in leg_indices:
                feature_key = feature_keys[leg_index]
                leg_key = feature_key.removeprefix("leg_").removesuffix("_impact")
                value = _clip(float(z_values[leg_index]), -4.0, 4.0)
                asset_count = max(_safe_float(source_row.get(f"leg_{leg_key}_assets"), 1.0) or 1.0, 1.0)
                band_points = abs(_safe_float(source_row.get(f"leg_{leg_key}_band_points"), 0.0) or 0.0)
                close = max(abs(_safe_float(row.get("close"), 0.0) or 0.0), 1.0)
                uncertainty_penalty = math.sqrt(1.0 + min(band_points / max(close * 0.035, 1.0), 4.0))
                leg_values.append(value)
                leg_weights.append(math.sqrt(asset_count) / uncertainty_penalty)

            if leg_values:
                weights = np.asarray(leg_weights, dtype=float)
                values = np.asarray(leg_values, dtype=float)
                weight_sum = max(float(np.sum(weights)), 1e-9)
                weighted_mean = float(np.sum(values * weights) / weight_sum)
                leg_median = _median([float(value) for value in values])
                positive_weight = float(np.sum(weights[values > 0.25]))
                negative_weight = float(np.sum(weights[values < -0.25]))
                breadth = _clip((positive_weight - negative_weight) / weight_sum, -1.0, 1.0)
                dispersion = _mad([float(value) for value in values], leg_median)
                coherence = _clip(1.0 / (1.0 + max(dispersion - 0.65, 0.0)), 0.0, 1.0)
                legs_score = _clip(
                    math.tanh((0.42 * weighted_mean) + (0.30 * leg_median) + (0.55 * breadth))
                    * (0.60 + (0.40 * coherence)),
                    -1.0,
                    1.0,
                )
                leg_slope = float(np.sum(slope_values[leg_indices] * weights) / weight_sum)
            else:
                breadth = 0.0
                coherence = 0.0
                legs_score = 0.0
                leg_slope = 0.0

            def feature_z(key: str, values: Any = z_values) -> float:
                position = feature_index.get(key)
                if position is None:
                    return 0.0
                return _clip(float(values[position]), -4.0, 4.0)

            def feature_slope(key: str, values: Any = slope_values) -> float:
                position = feature_index.get(key)
                if position is None:
                    return 0.0
                return _clip(float(values[position]), -4.0, 4.0)

            rpc_z = feature_z("rpc_pressure")
            flow_score = _clip(
                math.tanh(
                    (0.36 * rpc_z)
                    + (0.22 * feature_z("rpc_slope"))
                    + (0.14 * feature_z("rpc_acceleration"))
                    + (0.12 * feature_z("block_consensus"))
                    + (0.18 * feature_z("edge_bias"))
                    + (0.10 * feature_z("fair_value_gap_z"))
                ),
                -1.0,
                1.0,
            )
            local_score = _clip(
                math.tanh(
                    (0.28 * feature_z("local_block"))
                    + (0.22 * leg_slope)
                    + (0.22 * feature_z("local_relief_impulse"))
                    + (0.12 * feature_z("di_curve_shape_relief"))
                    + (0.20 * feature_slope("leg_di_impact"))
                    + (0.12 * feature_slope("leg_fx_impact"))
                    + (0.10 * feature_slope("leg_credit_impact"))
                    - (0.34 * feature_z("local_stress_impulse"))
                    - (0.20 * feature_z("block_gap"))
                    - (0.16 * feature_z("corr_state_local_dominance"))
                ),
                -1.0,
                1.0,
            )
            correlation_score = _clip(
                math.tanh(
                    (0.24 * feature_z("corr_state_aligned"))
                    + (0.16 * feature_z("corr_state_external_dominance"))
                    - (0.18 * feature_z("corr_state_local_dominance"))
                    - (0.38 * feature_z("corr_break_score"))
                    - (0.18 * feature_z("corr_state_corr_break"))
                    - (0.12 * feature_z("block_gap"))
                ),
                -1.0,
                1.0,
            )
            trend_score = _clip(
                math.tanh(
                    (0.42 * _clip(float(y_z[index]), -4.0, 4.0))
                    + (0.34 * _clip(float(y_slope[index]), -4.0, 4.0))
                    + (0.14 * feature_z("edge_bias"))
                    + (0.10 * feature_z("fair_value_gap_z"))
                ),
                -1.0,
                1.0,
            )
            stress_score = -_clip(
                math.tanh(
                    (0.42 * probability_map.get("stress", 0.0))
                    + (0.22 * probability_map.get("local_stress", 0.0))
                    + (0.36 * probability_map.get("dislocation", 0.0))
                    + (0.12 * (_safe_float(row.get("dislocation_score"), 0.0) or 0.0) / 100.0)
                    + (0.10 * math.tanh((_safe_float(row.get("outlier_score"), 0.0) or 0.0) / 3.0))
                ),
                0.0,
                1.0,
            )

            structure_score = _clip(
                (0.28 * legs_score)
                + (0.18 * flow_score)
                + (0.24 * local_score)
                + (0.18 * correlation_score)
                + (0.12 * trend_score),
                -1.0,
                1.0,
            )
            cross_alignment = _clip(1.0 - abs(state_score - structure_score), 0.0, 1.0)
            state_tail = _clip(
                probability_map.get("stress", 0.0)
                + probability_map.get("dislocation", 0.0)
                + (0.55 * probability_map.get("local_stress", 0.0)),
                0.0,
                1.0,
            )
            confirmation_gate = _clip(
                (0.42 * cross_alignment)
                + (0.20 * coherence)
                + (0.20 * abs(legs_score))
                + (0.10 * abs(flow_score))
                + (0.04 * abs(local_score))
                + (0.04 * abs(correlation_score))
                + (0.10 * (1.0 - state_tail)),
                0.0,
                1.0,
            )
            if use_legacy:
                raw_score = _clip(
                    (0.30 * state_score)
                    + (0.20 * legs_score)
                    + (0.14 * flow_score)
                    + (0.16 * local_score)
                    + (0.12 * correlation_score)
                    + (0.05 * trend_score)
                    + (0.03 * stress_score),
                    -1.0,
                    1.0,
                )
                smoothed_factor = 0.64
                markov_gate = state_score
            else:
                markov_gate = state_score * _clip(
                    0.24 + (0.64 * confirmation_gate) - (0.18 * state_tail),
                    0.20,
                    1.0,
                )
                raw_score = _clip(
                    (0.34 * markov_gate)
                    + (0.18 * legs_score)
                    + (0.12 * flow_score)
                    + (0.18 * local_score)
                    + (0.12 * correlation_score)
                    + (0.04 * trend_score)
                    + (0.02 * stress_score),
                    -1.0,
                    1.0,
                )
                smoothed_factor = _clip(
                    0.84 - (0.36 * confirmation_gate) + (0.16 * state_tail),
                    0.30,
                    0.90,
                )
            session_date = str(row.get("session_date") or "")
            previous_score = previous_score_by_session.get(session_date)
            smoothed_score = raw_score if previous_score is None else (
                (smoothed_factor * previous_score) + ((1.0 - smoothed_factor) * raw_score)
            )
            smoothed_score = _clip(smoothed_score, -1.0, 1.0)
            score = _clip(smoothed_score * 100.0, -100.0, 100.0)
            label, key, color = self._risk_thermometer_label(score)
            transition_hold = 0
            if not use_legacy:
                previous_key = previous_key_by_session.get(session_date)
                if previous_key and previous_key != key:
                    next_hold = pending_transition_by_session.get(session_date, 0) + 1
                    pending_transition_by_session[session_date] = next_hold
                    if confirmation_gate < 0.60 and next_hold < 2:
                        transition_hold = next_hold
                        score = _clip(previous_score * 100.0, -100.0, 100.0) if previous_score is not None else score
                        label, key, color = self._risk_thermometer_label(score)
                        smoothed_score = _clip(score / 100.0, -1.0, 1.0)
                    else:
                        pending_transition_by_session[session_date] = 0
                else:
                    pending_transition_by_session[session_date] = 0

            previous_score_by_session[session_date] = smoothed_score
            previous_key_by_session[session_date] = key

            finite_probs = np.asarray([max(float(value), 1e-12) for value in state_probs], dtype=float)
            entropy = -float(np.sum(finite_probs * np.log(finite_probs))) / max(math.log(len(finite_probs)), 1e-9)
            confidence = _clip(
                24.0
                + (34.0 * (1.0 - entropy))
                + (20.0 * coherence)
                + (14.0 * abs(breadth))
                - (18.0 * max(
                    probability_map.get("stress", 0.0),
                    probability_map.get("dislocation", 0.0),
                    probability_map.get("local_stress", 0.0) * 0.85,
                )),
                0.0,
                100.0,
            )
            row["feature_z_values"] = {
                key_name: _round_float(float(z_values[key_index]), 4)
                for key_index, key_name in enumerate(feature_keys)
            }
            row["risk_thermometer"] = {
                "score": round(score, 2),
                "risk_on_level": round((score + 100.0) / 2.0, 2),
                "risk_off_level": round((100.0 - score) / 2.0, 2),
                "label": label,
                "key": key,
                "color": color,
                "confidence": round(confidence, 2),
                "breadth": round(breadth, 4),
                "coherence": round(coherence, 4),
                "risk_on_probability": round(probability_map.get("risk_on", 0.0), 6),
                "risk_off_probability": round(
                    probability_map.get("risk_off", 0.0)
                    + probability_map.get("local_stress", 0.0)
                    + probability_map.get("stress", 0.0)
                    + probability_map.get("dislocation", 0.0),
                    6,
                ),
                "components": {
                    "markov": round(state_score * 100.0, 2),
                    "markov_gate": round(markov_gate * 100.0, 2),
                    "legs": round(legs_score * 100.0, 2),
                    "flow": round(flow_score * 100.0, 2),
                    "local": round(local_score * 100.0, 2),
                    "correlation": round(correlation_score * 100.0, 2),
                    "trend": round(trend_score * 100.0, 2),
                    "stress": round(stress_score * 100.0, 2),
                    "structure": round(structure_score * 100.0, 2),
                    "state_tail": round(state_tail, 4),
                    "cross_alignment": round(cross_alignment, 4),
                    "confirmation_gate": round(confirmation_gate, 4),
                },
                "decision": {
                    "legacy_mode": use_legacy,
                    "regime_mode": "legacy" if use_legacy else "smart",
                    "smoothed_factor": round(smoothed_factor, 4),
                    "transition_hold": int(transition_hold),
                    "accepted_transition": int(transition_hold) == 0,
                },
                "regime_mode": "legacy" if use_legacy else "smart",
            }

        return {
            "latest": deepcopy(rows[-1].get("risk_thermometer")) if rows else None,
            "model": "robust_markov_cross_asset_risk_thermometer",
            "score_range": [-100, 100],
            "positive_label": "Risk-on",
            "negative_label": "Risk-off",
            "components": component_meta,
            "methodology": (
                "Student-t Markov probabilities blended with robust-z FV leg breadth, "
                "local-vs-external block pressure, correlation-regime diagnostics and Theil-Sen slopes for DI/FX/credit "
                + (
                    "Smart regime mode active: Markov transitions are filtered by structural "
                    "alignment, correlation breaks and confidence-gated persistence."
                    if not use_legacy
                    else "Legacy mode active: fixed component blend and static hysteresis."
                )
                + " The final score is session-local hysteresis smoothed and clipped to [-100, 100]."
            ),
            "regime_mode": "legacy" if use_legacy else "smart",
        }

    def _build_rows(
        self,
        *,
        observations: list[dict[str, Any]],
        matrices: dict[str, Any],
        hmm: dict[str, Any],
        regressions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        probs = np.asarray(hmm["probabilities"], dtype=float)
        predictions = np.asarray(regressions["design_predictions"], dtype=float)
        expected_returns = np.sum(probs * predictions, axis=1)
        y = np.asarray(matrices["y"], dtype=float)
        residuals = y - expected_returns
        state_sigmas = np.asarray([model["sigma"] for model in regressions["models"]], dtype=float)
        blended_sigma = np.maximum(np.sum(probs * state_sigmas[None, :], axis=1), 1e-6)
        rows: list[dict[str, Any]] = []
        feature_keys = list(matrices["feature_keys"])
        x_raw = np.asarray(matrices["x_raw"], dtype=float)
        gap_index = feature_keys.index("fair_value_gap_z") if "fair_value_gap_z" in feature_keys else None
        rpc_index = feature_keys.index("rpc_pressure") if "rpc_pressure" in feature_keys else None
        dislocation_index = feature_keys.index("dislocation_pressure") if "dislocation_pressure" in feature_keys else None
        for index, obs in enumerate(observations):
            state_prob_values = probs[index, :]
            dominant_state = int(np.argmax(state_prob_values))
            gap_z = float(x_raw[index, gap_index]) if gap_index is not None else 0.0
            rpc_pressure = float(x_raw[index, rpc_index]) if rpc_index is not None else 0.0
            dislocation_pressure = float(x_raw[index, dislocation_index]) if dislocation_index is not None else 0.0
            residual_z = float(residuals[index] / blended_sigma[index])
            outlier_score = abs(residual_z)
            dislocation_score = math.tanh(
                (0.58 * outlier_score)
                + (0.21 * abs(gap_z))
                + (0.12 * abs(float(matrices["emission"][index, 2])))
                + (0.18 * max(dislocation_pressure, 0.0))
            ) * 100.0
            close = _safe_float(obs.get("close"), 0.0) or 0.0
            source_row = obs.get("source_row") if isinstance(obs.get("source_row"), dict) else {}
            row = {
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
                "return_decimal": _round_float(y[index], 8),
                "return_bps": _round_float(y[index] * 10_000.0, 3),
                "expected_return_decimal": _round_float(expected_returns[index], 8),
                "expected_return_bps": _round_float(expected_returns[index] * 10_000.0, 3),
                "expected_move_points": _round_float(close * expected_returns[index], 4),
                "residual_decimal": _round_float(residuals[index], 8),
                "residual_bps": _round_float(residuals[index] * 10_000.0, 3),
                "residual_z": _round_float(residual_z, 4),
                "outlier_score": _round_float(outlier_score, 4),
                "dislocation_score": _round_float(dislocation_score, 4),
                "dominant_state": dominant_state,
                "dominant_state_key": STATE_DEFINITIONS[dominant_state]["key"],
                "dominant_state_name": STATE_DEFINITIONS[dominant_state]["name"],
                "state_probabilities": [round(float(value), 6) for value in state_prob_values],
                "state_probability_map": {
                    str(STATE_DEFINITIONS[state_index]["key"]): round(float(value), 6)
                    for state_index, value in enumerate(state_prob_values)
                },
                "corr_regime": obs.get("corr_regime"),
                "corr_regime_key": obs.get("corr_regime_key"),
                "corr_regime_name": obs.get("corr_regime_name"),
                "corr_regime_color": obs.get("corr_regime_color"),
                "corr_state_probabilities": obs.get("corr_state_probabilities"),
                "corr_state_probability_map": obs.get("corr_state_probability_map"),
                "fair_value_gap_z": _round_float(gap_z, 4),
                "rpc_pressure": _round_float(rpc_pressure, 6),
                "model_signal_decimal": _round_float(obs.get("model_signal"), 8),
                "feature_values": {
                    key: _round_float(x_raw[index, feature_index], 8)
                    for feature_index, key in enumerate(feature_keys)
                },
            }
            rows.append(row)
        return rows

    @staticmethod
    def _trend_features(closes: list[float], index: int, window: int = 8) -> tuple[float, float]:
        if index <= 0:
            return 0.0, 0.0
        start = max(0, index - max(int(window or 8), 2))
        segment = [float(value) for value in closes[start:index + 1] if math.isfinite(float(value))]
        if len(segment) < 3:
            return 0.0, 0.0
        path = sum(abs(segment[item] - segment[item - 1]) for item in range(1, len(segment)))
        displacement = segment[-1] - segment[0]
        if path <= 1e-9:
            return 0.0, 0.0
        efficiency = abs(displacement) / path
        signed_efficiency = _clip(displacement / path, -1.0, 1.0)
        return _clip(efficiency, 0.0, 1.0), signed_efficiency

    @staticmethod
    def _tape_feature_definitions() -> list[dict[str, str]]:
        return [
            {"key": "return", "label": "XB1 return"},
            {"key": "abs_return", "label": "Abs return"},
            {"key": "true_range", "label": "True range"},
            {"key": "body", "label": "Candle body"},
            {"key": "trend_efficiency", "label": "Trend efficiency"},
            {"key": "signed_trend", "label": "Signed trend"},
            {"key": "wick_sweep", "label": "Wick/sweep"},
            {"key": "close_location", "label": "Close location"},
            {"key": "panic_pressure", "label": "Panic pressure"},
            {"key": "di_divergence", "label": "DI divergence"},
            {"key": "di_impulse", "label": "DI impulse"},
            {"key": "dislocation", "label": "Dislocation"},
            {"key": "outlier", "label": "Outlier"},
            {"key": "rpc_pressure", "label": "RPC pressure"},
        ]

    def _build_tape_feature_matrices(
        self,
        *,
        observations: list[dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        feature_defs = self._tape_feature_definitions()
        feature_keys = [item["key"] for item in feature_defs]
        closes = [_safe_float(obs.get("close"), 0.0) or 0.0 for obs in observations]
        raw_rows: list[list[float]] = []
        line_values: list[float | None] = []
        directions: list[str] = []
        previous_di_line: float | None = None

        for index, obs in enumerate(observations):
            source_row = obs.get("source_row") if isinstance(obs.get("source_row"), dict) else {}
            previous_source = obs.get("previous_source_row") if isinstance(obs.get("previous_source_row"), dict) else {}
            close = _safe_float(obs.get("close"), 0.0) or 0.0
            previous_close = max(abs(_safe_float(obs.get("previous_close"), close) or close), 1e-9)
            open_price = _safe_float(source_row.get("open"), close) or close
            high = max(_safe_float(source_row.get("high"), close) or close, open_price, close)
            low = min(_safe_float(source_row.get("low"), close) or close, open_price, close)
            previous_high = _safe_float(previous_source.get("high"))
            previous_low = _safe_float(previous_source.get("low"))
            candle_range = max(high - low, 1e-9)
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            ) / previous_close
            body = abs(close - open_price) / previous_close
            upper_wick = max(high - max(open_price, close), 0.0) / candle_range
            lower_wick = max(min(open_price, close) - low, 0.0) / candle_range
            close_location = ((close - low) / candle_range * 2.0) - 1.0
            swept_high = 1.0 if previous_high is not None and high > previous_high and close < previous_high else 0.0
            swept_low = 1.0 if previous_low is not None and low < previous_low and close > previous_low else 0.0
            wick_sweep = max(upper_wick, lower_wick) + (0.75 * max(swept_high, swept_low))
            trend_efficiency, signed_trend = self._trend_features(closes, index, window=8)
            return_decimal = _safe_float(obs.get("return_decimal"), 0.0) or 0.0
            row = rows[index] if index < len(rows) else {}
            rpc_pressure = _safe_float(row.get("rpc_pressure"), 0.0) or 0.0
            outlier = _safe_float(row.get("outlier_score"), 0.0) or 0.0
            dislocation = (_safe_float(row.get("dislocation_score"), 0.0) or 0.0) / 100.0
            di_line = _safe_float(source_row.get("leg_di"))
            if di_line is None:
                di_line = _safe_float(source_row.get("fair_value_core"))
            line_values.append(di_line)
            di_divergence = ((di_line - close) / previous_close) if di_line is not None else 0.0
            di_impulse = (
                ((di_line - previous_di_line) / previous_close)
                if di_line is not None and previous_di_line is not None
                else 0.0
            )
            if di_line is not None:
                previous_di_line = di_line
            panic_pressure = (
                max(-return_decimal, 0.0)
                + (0.34 * true_range)
                + (0.0025 * max(-rpc_pressure * 100.0, 0.0))
                + (0.0015 * max(outlier - 1.5, 0.0))
                + (0.0020 * max(dislocation * 100.0 - 55.0, 0.0))
            )
            direction_signal = (0.62 * signed_trend) + (0.38 * _clip(return_decimal / max(true_range, 1e-6), -1.0, 1.0))
            if direction_signal > 0.22:
                directions.append("up")
            elif direction_signal < -0.22:
                directions.append("down")
            else:
                directions.append("flat")
            raw_rows.append([
                _clip(return_decimal, -0.16, 0.16),
                _clip(abs(return_decimal), 0.0, 0.16),
                _clip(true_range, 0.0, 0.22),
                _clip(body, 0.0, 0.18),
                trend_efficiency,
                signed_trend,
                _clip(wick_sweep, 0.0, 2.0),
                _clip(close_location, -1.0, 1.0),
                _clip(panic_pressure, 0.0, 0.28),
                _clip(di_divergence, -0.12, 0.12),
                _clip(di_impulse, -0.12, 0.12),
                _clip(dislocation, 0.0, 1.25),
                _clip(outlier, 0.0, 8.0),
                _clip(rpc_pressure, -1.2, 1.2),
            ])

        raw_x = np.asarray(raw_rows, dtype=float)
        x_scaled, x_center, x_scale = self._center_scale_matrix(raw_x)
        emission_feature_keys = [
            "return",
            "abs_return",
            "true_range",
            "trend_efficiency",
            "signed_trend",
            "wick_sweep",
            "panic_pressure",
            "di_divergence",
            "dislocation",
            "outlier",
            "rpc_pressure",
        ]
        emission_indices = [feature_keys.index(key) for key in emission_feature_keys]
        emission = x_scaled[:, emission_indices]
        return {
            "feature_defs": feature_defs,
            "feature_keys": feature_keys,
            "raw_x": raw_x,
            "x_scaled": x_scaled,
            "x_center": x_center,
            "x_scale": x_scale,
            "emission": emission,
            "emission_feature_keys": emission_feature_keys,
            "emission_indices": emission_indices,
            "line_values": line_values,
            "directions": directions,
        }

    @staticmethod
    def _initial_tape_labels(tape_matrices: dict[str, Any]) -> np.ndarray:
        feature_keys = list(tape_matrices.get("feature_keys") or [])
        x_scaled = np.asarray(tape_matrices.get("x_scaled"), dtype=float)
        raw_x = np.asarray(tape_matrices.get("raw_x"), dtype=float)

        def scaled(index: int, key: str) -> float:
            return float(x_scaled[index, feature_keys.index(key)]) if key in feature_keys else 0.0

        def raw(index: int, key: str) -> float:
            return float(raw_x[index, feature_keys.index(key)]) if key in feature_keys else 0.0

        labels: list[int] = []
        for index in range(len(raw_x)):
            return_z = scaled(index, "return")
            abs_return_z = scaled(index, "abs_return")
            range_z = scaled(index, "true_range")
            trend_efficiency = raw(index, "trend_efficiency")
            signed_trend_z = scaled(index, "signed_trend")
            wick_z = scaled(index, "wick_sweep")
            panic_z = scaled(index, "panic_pressure")
            dislocation = raw(index, "dislocation")
            outlier = raw(index, "outlier")
            rpc_pressure = raw(index, "rpc_pressure")
            if (
                panic_z > 1.35
                or (return_z < -2.05 and range_z > 0.35)
                or (return_z < -1.25 and rpc_pressure < -0.42 and (outlier > 1.6 or dislocation > 0.58))
            ):
                labels.append(4)
            elif wick_z > 1.15 and trend_efficiency < 0.68 and abs_return_z > -0.15:
                labels.append(2)
            elif trend_efficiency > 0.60 and abs(signed_trend_z) > 0.55 and range_z > -0.35:
                labels.append(3)
            elif range_z > 0.72 or abs_return_z > 0.82 or outlier > 1.75:
                labels.append(0)
            else:
                labels.append(1)
        return np.asarray(labels, dtype=int)

    def _apply_tape_regime_layer(
        self,
        *,
        observations: list[dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if len(observations) < 12 or len(rows) != len(observations):
            return {
                "ok": False,
                "status": "insufficient_history",
                "states": TAPE_STATE_DEFINITIONS,
                "line": {"key": "leg_di", "label": "DI leg"},
            }
        tape = self._build_tape_feature_matrices(observations=observations, rows=rows)
        initial_labels = self._initial_tape_labels(tape)
        hmm = self._fit_hmm(
            np.asarray(tape["emission"], dtype=float),
            initial_labels,
            state_definitions=TAPE_STATE_DEFINITIONS,
            sticky_bias=13.5,
            iterations=7,
        )
        probs = np.asarray(hmm["probabilities"], dtype=float)
        transition = np.asarray(hmm["transition"], dtype=float)
        line_values = list(tape["line_values"])
        directions = list(tape["directions"])
        for index, row in enumerate(rows):
            state_probs = probs[index, :]
            state_index = int(np.argmax(state_probs))
            state = TAPE_STATE_DEFINITIONS[state_index]
            direction = directions[index] if index < len(directions) else "flat"
            row["tape_regime"] = state_index
            row["tape_regime_key"] = state["key"]
            row["tape_regime_name"] = state["name"]
            row["tape_regime_color"] = state["color"]
            row["tape_state_probabilities"] = [round(float(value), 6) for value in state_probs]
            row["tape_state_probability_map"] = {
                str(TAPE_STATE_DEFINITIONS[item]["key"]): round(float(value), 6)
                for item, value in enumerate(state_probs)
            }
            row["tape_direction"] = direction
            row["tape_line_key"] = "leg_di"
            row["tape_line_label"] = "DI leg"
            row["tape_line_value"] = _round_float(line_values[index], 4) if index < len(line_values) else None
            row["tape_features"] = {
                key: _round_float(float(tape["raw_x"][index, feature_index]), 8)
                for feature_index, key in enumerate(tape["feature_keys"])
            }

        return {
            "ok": True,
            "status": "ready",
            "model": "sticky_student_t_hsmm_inspired_xb1_tape_regime",
            "states": self._state_payloads(probs, transition, TAPE_STATE_DEFINITIONS),
            "transition_matrix": [
                [round(float(value), 6) for value in row]
                for row in transition
            ],
            "line": {
                "key": "leg_di",
                "label": "DI leg",
                "value_field": "tape_line_value",
                "color_field": "tape_regime_color",
                "regime_field": "tape_regime_key",
            },
            "feature_definitions": tape["feature_defs"],
            "methodology": {
                "state_model": "Sticky Student-t HMM with HSMM-style persistence bias over XB1 microstructure features.",
                "states": "Expansion, lateralidade, stop-hunt, tendencia clara e panico.",
                "stop_hunt": "Detected from wick/sweep, failed breakout and low directional efficiency.",
                "panic": "Detected from left-tail return, range expansion, negative RPC pressure, outlier and dislocation.",
                "line": "DI leg is plotted as a regime-colored state trace on the main chart.",
            },
            "model_spec": {
                "feature_keys": list(tape["feature_keys"]),
                "feature_definitions": tape["feature_defs"],
                "x_center": [float(value) for value in tape["x_center"]],
                "x_scale": [float(value) for value in tape["x_scale"]],
                "emission_feature_keys": list(tape["emission_feature_keys"]),
                "emission_indices": [int(value) for value in tape["emission_indices"]],
                "emission_means": np.asarray(hmm["means"]).tolist(),
                "emission_scales": np.asarray(hmm["scales"]).tolist(),
                "transition_matrix": transition.tolist(),
                "initial_probabilities": np.asarray(hmm["initial"]).tolist(),
            },
        }

    def _state_betas_payload(
        self,
        regressions: dict[str, Any],
        feature_defs: list[dict[str, str]],
        y_scale: float,
    ) -> dict[str, Any]:
        labels = {item["key"]: item.get("label") or item["key"] for item in feature_defs}
        output: dict[str, Any] = {}
        scale = max(abs(float(y_scale)), 1e-8)
        for model in regressions["models"]:
            beta_payload: dict[str, Any] = {}
            for key, value in model["beta"].items():
                beta_payload[key] = {
                    "label": labels.get(key, key),
                    "beta": _round_float(value, 10),
                    "beta_score": _round_float(value / scale, 6),
                }
            output[str(model["state_key"])] = {
                "alpha": _round_float(model["alpha"], 10),
                "sigma": _round_float(model["sigma"], 10),
                "effective_samples": _round_float(model["effective_samples"], 2),
                "features": beta_payload,
            }
        return output

    def _model_spec(
        self,
        *,
        matrices: dict[str, Any],
        hmm: dict[str, Any],
        regressions: dict[str, Any],
        feature_defs: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "feature_keys": list(matrices["feature_keys"]),
            "feature_definitions": feature_defs,
            "x_center": [float(value) for value in matrices["x_center"]],
            "x_scale": [float(value) for value in matrices["x_scale"]],
            "y_center": float(matrices["y_center"]),
            "y_scale": float(matrices["y_scale"]),
            "signal_center": float(matrices["signal_center"]),
            "signal_scale": float(matrices["signal_scale"]),
            "residual_center": float(matrices["residual_center"]),
            "residual_scale": float(matrices["residual_scale"]),
            "emission_feature_keys": list(matrices["emission_feature_keys"]),
            "emission_means": np.asarray(hmm["means"]).tolist(),
            "emission_scales": np.asarray(hmm["scales"]).tolist(),
            "transition_matrix": np.asarray(hmm["transition"]).tolist(),
            "base_transition_matrix": np.asarray(
                hmm.get("base_transition") if hmm.get("base_transition") is not None else hmm["transition"]
            ).tolist(),
            "initial_probabilities": np.asarray(hmm["initial"]).tolist(),
            "regression_models": deepcopy(regressions["models"]),
        }
