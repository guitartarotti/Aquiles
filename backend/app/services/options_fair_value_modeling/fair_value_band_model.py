from __future__ import annotations

from typing import Any

from .types import FairValueRunConfig


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def build_fair_value_band(
    fair_value_final: float,
    structural_sigma_points: float,
    realized_vol_points: float,
    options_overlay: dict[str, Any],
    global_overlay: dict[str, Any],
    regime: dict[str, Any],
    us_rates_context: dict[str, Any] | None,
    options_model_run: dict[str, Any] | None,
    run_config: FairValueRunConfig,
) -> dict[str, Any]:
    base_width = max(
        structural_sigma_points * run_config.band_sigma_multiplier,
        realized_vol_points * run_config.band_vol_weight,
        run_config.band_floor_points,
    )

    regime_label = str(regime.get("market_regime") or "")
    width_multiplier = 1.0
    if regime_label == "compressed_gamma_regime" or options_overlay.get("state") == "gamma_compression":
        width_multiplier *= 0.78
    if regime_label in {"release_regime", "stress_brasil", "risk_off_global"} or str(global_overlay.get("state") or "").startswith("global_breakout"):
        width_multiplier *= 1.20
    us_rates_context = us_rates_context or {}
    width_multiplier *= max(float(us_rates_context.get("band_width_multiplier") or 1.0), 0.75)

    current_band = base_width * width_multiplier

    asymmetry = 0.0
    range_projection = (options_model_run or {}).get("range_projection") or {}
    bands = range_projection.get("bands") or []
    if bands:
        first_band = bands[0]
        center = _safe_float(range_projection.get("hybrid_center_future") or range_projection.get("hybrid_center_spot"))
        low = _safe_float(first_band.get("adjusted_lower_future") or first_band.get("adjusted_lower_spot"))
        high = _safe_float(first_band.get("adjusted_upper_future") or first_band.get("adjusted_upper_spot"))
        down_distance = max(center - low, 0.0)
        up_distance = max(high - center, 0.0)
        total = down_distance + up_distance
        if total > 1e-9:
            asymmetry = (up_distance - down_distance) / total

    high_width = current_band * (1.0 + max(asymmetry, 0.0))
    low_width = current_band * (1.0 + max(-asymmetry, 0.0))

    return {
        "fair_value_band_low": fair_value_final - low_width,
        "fair_value_band_high": fair_value_final + high_width,
        "band_half_width_points": current_band,
        "band_low_width_points": low_width,
        "band_high_width_points": high_width,
        "fair_value_band_regime": regime_label or "neutral",
        "band_asymmetry": asymmetry,
        "band_width_multiplier": width_multiplier,
    }
