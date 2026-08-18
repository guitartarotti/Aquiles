from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if parsed == parsed else default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_market_state(
    *,
    dominant_price_making_score: float,
    dominant_theoretical_strength: float,
    xb1_momentum_score: float,
    dependence_increase: float,
    band_acceptance_score: float,
    flow_confirmation_score: float,
    persistence_score: float,
    decline_in_price_making_score: float,
    decline_in_elasticity: float,
    failed_breakout_score: float,
    volume_without_progress: float,
    extreme_dislocation_score: float,
    low_price_response: float,
    proximity_to_fv_band_or_gamma: float,
    failed_continuation: float,
    low_factor_alignment: float,
    low_realized_volatility: float,
    no_dominant_price_maker: float,
    mixed_leg_signals: float,
    shadow_against_core: float,
    fv_or_vwap_recross: float,
    new_opposite_price_maker: float,
    flow_reversal: float,
    divergence_pressure: float,
    latent_stress_pressure: float,
) -> dict[str, Any]:
    acceleration_score = _clamp(
        0.25 * dominant_price_making_score
        + 0.20 * xb1_momentum_score
        + 0.15 * dependence_increase
        + 0.15 * band_acceptance_score
        + 0.15 * flow_confirmation_score
        + 0.10 * persistence_score,
        0.0,
        1.0,
    )
    exhaustion_score = _clamp(
        0.25 * dominant_theoretical_strength
        + 0.25 * decline_in_price_making_score
        + 0.20 * decline_in_elasticity
        + 0.15 * failed_breakout_score
        + 0.10 * volume_without_progress
        + 0.05 * extreme_dislocation_score,
        0.0,
        1.0,
    )
    absorption_score = _clamp(
        0.25 * dominant_theoretical_strength
        + 0.20 * low_price_response
        + 0.15 * proximity_to_fv_band_or_gamma
        + 0.15 * flow_confirmation_score
        + 0.15 * failed_continuation
        + 0.10 * persistence_score,
        0.0,
        1.0,
    )
    consolidation_score = _clamp(
        0.25 * low_factor_alignment
        + 0.20 * low_realized_volatility
        + 0.20 * no_dominant_price_maker
        + 0.15 * band_acceptance_score
        + 0.10 * (1.0 - dependence_increase)
        + 0.10 * mixed_leg_signals,
        0.0,
        1.0,
    )
    reversal_score = _clamp(
        0.20 * exhaustion_score
        + 0.20 * shadow_against_core
        + 0.15 * fv_or_vwap_recross
        + 0.15 * failed_breakout_score
        + 0.15 * new_opposite_price_maker
        + 0.15 * flow_reversal,
        0.0,
        1.0,
    )
    divergence_score = _clamp(
        0.45 * divergence_pressure
        + 0.25 * shadow_against_core
        + 0.15 * mixed_leg_signals
        + 0.15 * failed_continuation,
        0.0,
        1.0,
    )
    latent_stress_score = _clamp(
        0.45 * latent_stress_pressure
        + 0.20 * shadow_against_core
        + 0.20 * proximity_to_fv_band_or_gamma
        + 0.15 * low_price_response,
        0.0,
        1.0,
    )

    score_map = {
        "acceleration": acceleration_score,
        "exhaustion": exhaustion_score,
        "absorption": absorption_score,
        "consolidation": consolidation_score,
        "reversal": reversal_score,
        "divergence": divergence_score,
        "latent_stress": latent_stress_score,
        "neutral": 0.12,
    }
    selected_state = max(score_map.items(), key=lambda item: item[1])[0]
    selected_confidence = score_map[selected_state]
    direction = "neutral"
    if selected_state in {"acceleration", "recovery_candidate"}:
        direction = "bullish"
    elif selected_state in {"exhaustion", "absorption", "latent_stress", "reversal"}:
        direction = "bearish"
    reason = (
        f"Estado {selected_state} com score {selected_confidence:.2f}; "
        f"dominant_price_making={dominant_price_making_score:.2f}, "
        f"divergence={divergence_score:.2f}, latent_stress={latent_stress_score:.2f}."
    )
    return {
        "acceleration_score": round(acceleration_score, 6),
        "exhaustion_score": round(exhaustion_score, 6),
        "absorption_score": round(absorption_score, 6),
        "consolidation_score": round(consolidation_score, 6),
        "reversal_score": round(reversal_score, 6),
        "divergence_score": round(divergence_score, 6),
        "latent_stress_score": round(latent_stress_score, 6),
        "selected_state": selected_state,
        "confidence": round(_clamp(selected_confidence, 0.05, 0.98), 6),
        "direction": direction,
        "reason": reason,
    }
