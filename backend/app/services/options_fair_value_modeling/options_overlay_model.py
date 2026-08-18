from __future__ import annotations

import math
from typing import Any

from .types import FairValueRunConfig


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def build_options_overlay(
    current_future_price: float,
    structural_fair_value: float,
    current_sigma_points: float,
    options_model_run: dict[str, Any] | None,
    run_config: FairValueRunConfig,
) -> dict[str, Any]:
    payload = options_model_run or {}
    if not payload:
        return {
            "enabled": False,
            "state": "no_options_context",
            "confidence": 0.0,
            "fair_value_options_adjustment": 0.0,
        }

    summary = payload.get("summary") or {}
    market_context = payload.get("market_context") or {}
    pressure = payload.get("pressure") or {}
    dealer_inference = payload.get("dealer_inference") or {}
    comparison = dealer_inference.get("comparison") or summary.get("dealer_inference_comparison") or {}

    basis_points = _safe_float(market_context.get("future_basis_points"), 0.0)
    zero_pressure_future = _safe_float(((pressure.get("zero_pressure") or {}).get("spot")), 0.0) + basis_points
    acceleration_future = _safe_float(((pressure.get("max_acceleration") or {}).get("spot")), 0.0) + basis_points
    dealer_target_future = _safe_float(
        comparison.get("reference_dealer_inference_future_value"),
        zero_pressure_future,
    )
    pinning_band = pressure.get("pinning_band") or summary.get("pinning_band") or {}
    pin_low_future = _safe_float(pinning_band.get("low"), 0.0) + basis_points if pinning_band.get("low") is not None else 0.0
    pin_high_future = _safe_float(pinning_band.get("high"), 0.0) + basis_points if pinning_band.get("high") is not None else 0.0

    dealer_confidence = _safe_float(comparison.get("reference_confidence"), 0.0)
    gex_notional = abs(_safe_float(summary.get("gex_notional_future_total"), 0.0))
    gex_scale = min(max(math.log10(gex_notional + 1.0) / 18.0, 0.0), 1.0)
    confidence = min(0.98, max(0.05, (0.65 * dealer_confidence) + (0.35 * gex_scale)))

    within_pinning = pin_low_future > 0 and pin_high_future > 0 and pin_low_future <= current_future_price <= pin_high_future
    dominant_side = str(summary.get("dominant_side") or pressure.get("dominant_side") or "").lower()
    base_fair_value = structural_fair_value if structural_fair_value > 0 else current_future_price

    if within_pinning and confidence >= 0.2:
        state = "gamma_compression"
        strength = 0.45
        target_future = dealer_target_future if dealer_target_future > 0 else zero_pressure_future
    elif acceleration_future > 0 and current_future_price >= acceleration_future and "negative" in dominant_side:
        state = "gamma_release_up"
        strength = 0.18
        target_future = max(dealer_target_future, current_future_price)
    elif acceleration_future > 0 and current_future_price <= acceleration_future and "positive" in dominant_side:
        state = "gamma_release_down"
        strength = 0.18
        target_future = min(dealer_target_future, current_future_price)
    else:
        state = "neutral"
        strength = 0.10
        target_future = dealer_target_future if dealer_target_future > 0 else base_fair_value

    raw_adjustment = (target_future - base_fair_value) * strength * confidence * run_config.options_overlay_weight
    cap_points = max(current_sigma_points * run_config.options_max_sigma_mult, 120.0)
    adjustment_points = max(-cap_points, min(cap_points, raw_adjustment))

    return {
        "enabled": True,
        "state": state,
        "confidence": confidence,
        "dealer_target_future": dealer_target_future,
        "zero_pressure_future": zero_pressure_future,
        "acceleration_future": acceleration_future,
        "pinning_band_future": {"low": pin_low_future or None, "high": pin_high_future or None},
        "base_fair_value": base_fair_value,
        "fair_value_options_adjustment": adjustment_points,
        "raw_adjustment_points": raw_adjustment,
        "cap_points": cap_points,
    }
