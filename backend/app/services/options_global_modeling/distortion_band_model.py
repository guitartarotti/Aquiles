from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def build_distortion_band(dynamic_model: dict[str, Any], sigma_multiplier: float) -> dict[str, Any]:
    previous_price = _safe_float(dynamic_model.get("local_previous_price"), 0.0)
    current_price = _safe_float(dynamic_model.get("local_current_price"), 0.0)
    local_return = _safe_float(dynamic_model.get("local_return"), 0.0)
    expected_return = _safe_float(dynamic_model.get("basket_expected_return"), 0.0)
    residual_return = _safe_float(dynamic_model.get("residual_return"), 0.0)
    residual_sigma = max(_safe_float(dynamic_model.get("residual_sigma"), 0.0), 1e-8)
    zscore = residual_return / residual_sigma

    expected_price = previous_price * (1.0 + expected_return) if previous_price > 0 else current_price
    sigma_price = previous_price * residual_sigma if previous_price > 0 else abs(current_price * residual_sigma)
    band_low = expected_price - (sigma_multiplier * sigma_price)
    band_high = expected_price + (sigma_multiplier * sigma_price)
    distortion_value = current_price - expected_price

    abs_z = abs(zscore)
    if abs_z < 1.0:
        regime = "normal"
    elif abs_z < 2.0:
        regime = "attention"
    elif abs_z < 3.0:
        regime = "strong_distortion"
    else:
        regime = "extreme_distortion"

    if abs_z < 0.85:
        local_fairness = "justo"
    elif zscore > 0:
        local_fairness = "adiantado"
    else:
        local_fairness = "atrasado"

    return {
        "expected_return": expected_return,
        "local_return": local_return,
        "distortion_value": distortion_value,
        "distortion_sigma": sigma_price,
        "distortion_zscore": zscore,
        "distortion_band_low": band_low,
        "distortion_band_high": band_high,
        "distortion_regime": regime,
        "expected_price": expected_price,
        "actual_price": current_price,
        "local_fairness": local_fairness,
    }
