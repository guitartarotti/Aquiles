from __future__ import annotations

from statistics import median
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _median_score(rows: list[dict[str, Any]], key: str) -> float:
    values = [_safe_float(row.get(key), 0.0) for row in rows]
    values = [value for value in values if value != 0.0]
    return float(median(values)) if values else 0.0


def _derive_skew_state(value: float) -> str:
    if value <= -0.15:
        return "downside_heavy"
    if value >= 0.15:
        return "upside_heavy"
    return "balanced"


def _extract_level_a_state(asset: dict[str, Any], model_run: dict[str, Any]) -> dict[str, Any]:
    summary = model_run.get("summary") or {}
    pressure = model_run.get("pressure") or {}
    dealer = model_run.get("dealer_inference") or {}
    comparison = dealer.get("comparison") or summary.get("dealer_inference_comparison") or {}
    dealer_rows = dealer.get("rows") or []
    basis = _safe_float(summary.get("future_basis_points"), 0.0) if asset.get("use_future_space") else 0.0

    current_price = _safe_float(asset.get("current_price"), 0.0)
    dealer_core = _safe_float(
        comparison.get("reference_dealer_inference_future_value" if asset.get("use_future_space") else "reference_dealer_inference_value"),
        0.0,
    )
    if dealer_core <= 0:
        dealer_core = _safe_float(summary.get("forward_price" if asset.get("use_future_space") else "spot_price"), current_price)

    pinning = pressure.get("pinning_band") or {}
    acceleration = pressure.get("max_acceleration") or {}
    zero_pressure = pressure.get("zero_pressure") or {}
    pin_low = _safe_float(pinning.get("low"), 0.0) + basis
    pin_high = _safe_float(pinning.get("high"), 0.0) + basis
    acceleration_level = _safe_float(acceleration.get("spot"), 0.0) + basis
    zero_pressure_level = _safe_float(zero_pressure.get("spot"), 0.0) + basis
    gex_total = _safe_float(summary.get("gex_total"), 0.0)
    vex_total = _safe_float(summary.get("vex_total"), 0.0)
    cex_total = _safe_float(summary.get("cex_total"), 0.0)

    pin_width = max(pin_high - pin_low, max(current_price * 0.0025, 1.0))
    inside_pinning = pin_low > 0 and pin_high > 0 and pin_low <= current_price <= pin_high
    dist_to_core = abs(current_price - dealer_core)
    dist_to_accel = abs(current_price - acceleration_level) if acceleration_level > 0 else current_price
    core_score = 1.0 if inside_pinning else _clamp(1.0 - (dist_to_core / max(pin_width * 1.5, 1.0)), 0.0, 1.0)
    accel_score = _clamp(1.0 - (dist_to_accel / max(pin_width * 2.0, 1.0)), 0.0, 1.0)
    iv_skew_score = _median_score(dealer_rows, "iv_skew_score")
    skew_state = _derive_skew_state(iv_skew_score)
    latest_return_abs = abs(_safe_float(asset.get("latest_return"), 0.0))
    realized_vol = max(_safe_float(asset.get("realized_vol_intraday"), 0.0), 1e-8)
    vol_deviation_score = _clamp((latest_return_abs / realized_vol) / 2.0, 0.0, 1.0)

    absorption_score = _clamp(
        (0.45 * core_score)
        + (0.30 * (1.0 if gex_total > 0 else 0.25))
        + (0.15 * (1.0 if skew_state == "downside_heavy" else 0.7))
        + (0.10 * (1.0 if zero_pressure_level > 0 and abs(current_price - zero_pressure_level) <= pin_width * 1.5 else 0.45)),
        0.0,
        1.0,
    )
    breakout_score = _clamp(
        (0.40 * accel_score)
        + (0.30 * (1.0 if gex_total < 0 else 0.30))
        + (0.15 * (1.0 if abs(_safe_float(asset.get("latest_return"), 0.0)) > max(_safe_float(asset.get("realized_vol_intraday"), 0.0), 1e-6) else 0.4))
        + (0.15 * (1.0 if skew_state in {"balanced", "upside_heavy"} else 0.55)),
        0.0,
        1.0,
    )

    if gex_total > 0 and inside_pinning:
        dealer_regime_state = "compression"
    elif gex_total > 0:
        dealer_regime_state = "absorption"
    elif accel_score > 0.75:
        dealer_regime_state = "release"
    else:
        dealer_regime_state = "fragility"

    confidence = _clamp(
        (0.45 * _safe_float(comparison.get("reference_confidence"), 0.0))
        + (0.30 * _safe_float(asset.get("state_quality_score"), 0.0))
        + (0.25 * (1.0 if dealer_core > 0 and pin_low > 0 and pin_high > 0 else 0.4)),
        0.0,
        1.0,
    )

    return {
        "dealer_core": dealer_core or None,
        "pinning_band_low": pin_low or None,
        "pinning_band_high": pin_high or None,
        "acceleration_level": acceleration_level or None,
        "zero_pressure": zero_pressure_level or None,
        "gex_total": gex_total,
        "vex_total": vex_total,
        "cex_total": cex_total,
        "iv_skew_state": skew_state,
        "iv_skew_numeric": iv_skew_score,
        "vol_deviation_score": vol_deviation_score,
        "dealer_regime_state": dealer_regime_state,
        "dealer_regime_confidence": confidence,
        "local_absorption_score": absorption_score,
        "local_breakout_score": breakout_score,
    }


def _extract_price_only_state(asset: dict[str, Any]) -> dict[str, Any]:
    latest_return = abs(_safe_float(asset.get("latest_return"), 0.0))
    realized_vol = max(_safe_float(asset.get("realized_vol_intraday"), 0.0), 1e-8)
    intraday_return = abs(_safe_float(asset.get("intraday_return"), 0.0))
    burst = latest_return / realized_vol
    intraday_stretch = intraday_return / max(realized_vol * 4.0, 1e-8)
    breakout_score = _clamp((burst - 0.45) / 1.4, 0.0, 1.0)
    absorption_score = _clamp((1.0 - min(burst, 1.2) / 1.2) * (1.0 - min(intraday_stretch, 1.0)), 0.0, 1.0)
    if breakout_score >= 0.65:
        regime = "breakout"
    elif absorption_score >= 0.60:
        regime = "absorption"
    else:
        regime = "neutral"
    confidence = _clamp((0.55 * _safe_float(asset.get("state_quality_score"), 0.0)) + (0.45 * min(abs(intraday_return) / max(realized_vol, 1e-8), 1.0)), 0.0, 1.0)
    return {
        "dealer_core": None,
        "pinning_band_low": None,
        "pinning_band_high": None,
        "acceleration_level": None,
        "zero_pressure": None,
        "gex_total": None,
        "vex_total": None,
        "cex_total": None,
        "iv_skew_state": "unavailable",
        "iv_skew_numeric": 0.0,
        "vol_deviation_score": _clamp(max(burst, intraday_stretch) / 2.0, 0.0, 1.0),
        "dealer_regime_state": regime,
        "dealer_regime_confidence": confidence,
        "local_absorption_score": absorption_score,
        "local_breakout_score": breakout_score,
    }


def extract_asset_states(prepared_inputs: dict[str, Any]) -> list[dict[str, Any]]:
    asset_states: list[dict[str, Any]] = []
    for asset in prepared_inputs.get("assets") or []:
        support_level = str(asset.get("support_level") or "C").upper()
        model_run = asset.get("options_model_run") or {}
        if support_level == "A" and model_run:
            derived = _extract_level_a_state(asset, model_run)
        else:
            derived = _extract_price_only_state(asset)

        asset_states.append(
            {
                "asset": asset.get("slug"),
                "label": asset.get("label"),
                "region": asset.get("region"),
                "support_level": support_level,
                "state_quality_score": _safe_float(asset.get("state_quality_score"), 0.0),
                "security": asset.get("selected_security"),
                "trade_symbol": asset.get("trade_symbol"),
                "model_underlying": asset.get("model_underlying"),
                "dealer_zone_source_underlying": asset.get("dealer_zone_source_underlying"),
                "dealer_zone_source_security": asset.get("dealer_zone_source_security"),
                "dealer_zone_source_mode": asset.get("dealer_zone_source_mode"),
                "spot": asset.get("current_price"),
                "return_intraday": _safe_float(asset.get("intraday_return"), 0.0),
                "latest_return": _safe_float(asset.get("latest_return"), 0.0),
                "realized_vol_intraday": _safe_float(asset.get("realized_vol_intraday"), 0.0),
                **derived,
            }
        )
    return asset_states
