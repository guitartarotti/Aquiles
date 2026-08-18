from __future__ import annotations

import math
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _direction_label(value: float) -> str:
    if value > 0.06:
        return "bullish"
    if value < -0.06:
        return "bearish"
    return "neutral"


def _state_from_scores(
    *,
    theoretical_strength: float,
    alignment: float,
    elasticity: float,
    price_making_score: float,
    divergence_score: float,
    proximity_to_band: float,
) -> str:
    if price_making_score >= 72 and alignment > 0.20 and elasticity > 0.20:
        return "acceleration"
    if theoretical_strength > 0.65 and price_making_score < 45 and proximity_to_band > 0.55:
        return "absorption"
    if theoretical_strength > 0.65 and divergence_score > 0.45:
        return "exhaustion"
    if divergence_score > 0.65:
        return "divergence"
    if abs(alignment) < 0.08 and price_making_score < 42:
        return "consolidation"
    if alignment < -0.12:
        return "reversal"
    return "neutral"


def _status_from_scores(
    *,
    theoretical_strength: float,
    alignment: float,
    price_making_score: float,
    lead_lag_minutes: int,
    state: str,
) -> str:
    if theoretical_strength >= 0.45 and price_making_score >= 65 and alignment > 0.15:
        return "making_price"
    if theoretical_strength >= 0.45 and alignment < -0.10:
        return "diverging"
    if theoretical_strength >= 0.45 and price_making_score < 40:
        return "ignored"
    if lead_lag_minutes < 0 and price_making_score >= 50:
        return "leading"
    if lead_lag_minutes > 0 and price_making_score >= 45:
        return "lagging"
    if state == "absorption":
        return "absorbed"
    if state == "exhaustion":
        return "exhausted"
    return "confirming_only"


def build_leg_price_making(
    *,
    leg_key: str,
    leg_type: str,
    leg_payload: dict[str, Any],
    dependence: dict[str, Any],
    xb1_return_z: float,
    dislocation_zscore: float,
    price_vs_core_fv: float,
    price_vs_quality_fv: float,
    price_vs_band: float,
    microstructure_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    microstructure_context = microstructure_context or {}
    contribution_points = _safe_float(leg_payload.get("contribution_points"))
    if leg_type == "shadow":
        contribution_points = _safe_float(leg_payload.get("quality_impact"))
    pressure_score = _safe_float(leg_payload.get("score"))
    implied_fair_value = _safe_float(leg_payload.get("implied_fair_value_xb1"))
    confidence = _clamp(_safe_float(leg_payload.get("confidence"), 0.35), 0.05, 0.98)
    theoretical_strength = _clamp(max(abs(contribution_points), abs(pressure_score) * 125.0) / 600.0, 0.0, 1.0)
    expected_direction = 1.0 if contribution_points >= 0 else -1.0
    alignment = expected_direction * xb1_return_z
    explained_move = _safe_float(dependence.get("quantile_beta")) * pressure_score
    residual_after_leg = xb1_return_z - explained_move
    residual_explanation = _clamp(1.0 - min(abs(residual_after_leg) / max(abs(xb1_return_z), 0.25), 1.5), 0.0, 1.0)
    beta_significance = _clamp(abs(_safe_float(dependence.get("pearson_corr"))) * confidence, 0.0, 1.0)
    lead_lag_score = _clamp(_safe_float(dependence.get("lead_lag_score")), 0.0, 1.0)
    dependence_confidence = _clamp(_safe_float(dependence.get("dependence_confidence")), 0.0, 1.0)
    persistence = _clamp(abs(pressure_score) * 0.55, 0.0, 1.0)
    price_elasticity = xb1_return_z / max(abs(pressure_score), 0.12)
    flow_confirmation = _safe_float(microstructure_context.get("flow_confirmation"), 0.4)
    price_making_score = _clamp(
        (
            0.25 * dependence_confidence
            + 0.20 * max(0.0, alignment)
            + 0.20 * beta_significance
            + 0.15 * lead_lag_score
            + 0.10 * persistence
            + 0.10 * residual_explanation
        ) * 100.0,
        0.0,
        100.0,
    )
    divergence_score = _clamp(
        abs(price_vs_core_fv - price_vs_quality_fv) * 0.3
        + max(0.0, -alignment) * 0.4
        + abs(dislocation_zscore) * 0.1,
        0.0,
        1.0,
    )
    proximity_to_band = _clamp(abs(price_vs_band), 0.0, 1.0)
    state = _state_from_scores(
        theoretical_strength=theoretical_strength,
        alignment=alignment,
        elasticity=abs(price_elasticity),
        price_making_score=price_making_score / 100.0,
        divergence_score=divergence_score,
        proximity_to_band=proximity_to_band,
    )
    status = _status_from_scores(
        theoretical_strength=theoretical_strength,
        alignment=alignment,
        price_making_score=price_making_score,
        lead_lag_minutes=int(dependence.get("best_lag_minutes") or 0),
        state=state,
    )
    explanation = (
        f"{leg_payload.get('label') or leg_payload.get('name') or leg_key}: pressão teórica "
        f"{contribution_points:+.1f} pts, alignment {alignment:+.2f}, "
        f"dependência {dependence_confidence:.2f} e elasticidade {price_elasticity:+.2f}."
    )
    return {
        "pressure_score": round(pressure_score, 6),
        "contribution_points": round(contribution_points, 4),
        "implied_fair_value_xb1": implied_fair_value,
        "linear_corr": round(_safe_float(dependence.get("pearson_corr")), 6),
        "spearman_corr": round(_safe_float(dependence.get("spearman_corr")), 6),
        "distance_corr": round(_safe_float(dependence.get("distance_corr")), 6),
        "tail_dependence": round(_safe_float(dependence.get("tail_dependence")), 6),
        "nonlinear_dependence_score": round(_safe_float(dependence.get("nonlinear_dependence_score")), 6),
        "rolling_beta": round(_safe_float(dependence.get("quantile_beta")), 6),
        "lead_lag_minutes": int(dependence.get("best_lag_minutes") or 0),
        "lead_lag_score": round(lead_lag_score, 6),
        "price_making_score": round(price_making_score, 4),
        "price_elasticity": round(price_elasticity, 6),
        "status": status,
        "state": state,
        "direction": _direction_label(contribution_points),
        "confidence": round(_clamp((0.45 * confidence) + (0.35 * dependence_confidence) + (0.20 * flow_confirmation), 0.05, 0.98), 6),
        "alignment": round(alignment, 6),
        "residual_after_leg": round(residual_after_leg, 6),
        "residual_explanation": round(residual_explanation, 6),
        "theoretical_strength": round(theoretical_strength, 6),
        "explanation": explanation,
        "dependence_windows": dependence.get("windows") or {},
    }
