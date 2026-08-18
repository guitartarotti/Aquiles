from __future__ import annotations

from typing import Any

from .math_utils import percentile
from .types import ModelRunConfig


def _derive_pressure_point(point: dict[str, Any], run_config: ModelRunConfig) -> dict[str, Any]:
    hp = (
        run_config.gex_weight * float(point.get("gex") or 0.0)
        + run_config.vex_weight * float(point.get("vex") or 0.0)
        + run_config.cex_weight * float(point.get("cex") or 0.0)
    )
    enriched = dict(point)
    enriched["hp"] = hp
    return enriched


def _derivative(curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if len(curve) < 2:
        return results
    for index, point in enumerate(curve):
        if index == 0:
            next_point = curve[index + 1]
            slope = (float(next_point["hp"]) - float(point["hp"])) / (float(next_point["spot"]) - float(point["spot"]))
        elif index == len(curve) - 1:
            prev_point = curve[index - 1]
            slope = (float(point["hp"]) - float(prev_point["hp"])) / (float(point["spot"]) - float(prev_point["spot"]))
        else:
            prev_point = curve[index - 1]
            next_point = curve[index + 1]
            slope = (float(next_point["hp"]) - float(prev_point["hp"])) / (float(next_point["spot"]) - float(prev_point["spot"]))
        results.append({"spot": point["spot"], "d_hp_d_s": slope})
    return results


def _find_zero_pressure(curve: list[dict[str, Any]]) -> dict[str, Any]:
    if not curve:
        return {"spot": None, "method": "empty"}
    nearest = min(curve, key=lambda item: abs(float(item.get("hp") or 0.0)))
    for index in range(len(curve) - 1):
        left = curve[index]
        right = curve[index + 1]
        left_hp = float(left.get("hp") or 0.0)
        right_hp = float(right.get("hp") or 0.0)
        if left_hp == 0:
            return {"spot": left["spot"], "method": "exact"}
        if left_hp * right_hp < 0:
            left_spot = float(left["spot"])
            right_spot = float(right["spot"])
            weight = abs(left_hp) / (abs(left_hp) + abs(right_hp))
            return {
                "spot": left_spot + (right_spot - left_spot) * weight,
                "method": "interpolated_crossing",
                "left_spot": left_spot,
                "right_spot": right_spot,
            }
    return {"spot": nearest["spot"], "method": "nearest_abs_hp"}


def _band_from_mask(curve: list[dict[str, Any]], mask: list[bool], anchor_index: int) -> dict[str, Any]:
    if not curve or anchor_index < 0 or anchor_index >= len(curve):
        return {"low": None, "high": None}
    left = anchor_index
    right = anchor_index
    while left - 1 >= 0 and mask[left - 1]:
        left -= 1
    while right + 1 < len(curve) and mask[right + 1]:
        right += 1
    return {"low": curve[left]["spot"], "high": curve[right]["spot"]}


def analyze_pressure_curve(
    grid_result: dict[str, Any],
    run_config: ModelRunConfig,
    spot_price: float,
) -> dict[str, Any]:
    raw_curve = grid_result.get("curve") or []
    curve = [_derive_pressure_point(point, run_config) for point in raw_curve]
    derivatives = _derivative(curve)
    zero_pressure = _find_zero_pressure(curve)

    hp_values = [abs(float(point.get("hp") or 0.0)) for point in curve]
    hp_threshold = percentile(hp_values, 0.20) if hp_values else 0.0
    derivative_values = [abs(float(point.get("d_hp_d_s") or 0.0)) for point in derivatives]
    accel_threshold = percentile(derivative_values, 0.80) if derivative_values else 0.0
    accel_index = max(range(len(derivative_values)), key=lambda idx: abs(derivative_values[idx])) if derivative_values else None
    hp_index = min(range(len(curve)), key=lambda idx: abs(float(curve[idx].get("spot") or 0.0) - spot_price)) if curve else None

    pinning_mask = [abs(float(point.get("hp") or 0.0)) <= hp_threshold for point in curve]
    accel_mask = [abs(float(point.get("d_hp_d_s") or 0.0)) >= accel_threshold for point in derivatives]

    pinning_anchor = hp_index if hp_index is not None and pinning_mask[hp_index] else min(range(len(curve)), key=lambda idx: abs(float(curve[idx].get("spot") or 0.0) - float(zero_pressure.get("spot") or spot_price))) if curve else 0
    acceleration_anchor = accel_index if accel_index is not None else 0

    pinning_band = _band_from_mask(curve, pinning_mask, pinning_anchor) if curve else {"low": None, "high": None}
    acceleration_band = _band_from_mask(derivatives, accel_mask, acceleration_anchor) if derivatives else {"low": None, "high": None}

    hp_total = sum(abs(float(point.get("hp") or 0.0)) for point in curve)
    center_of_mass = None
    if hp_total > 0:
        center_of_mass = sum(float(point["spot"]) * abs(float(point.get("hp") or 0.0)) for point in curve) / hp_total

    current_point = min(curve, key=lambda item: abs(float(item.get("spot") or 0.0) - spot_price)) if curve else None
    dominant_side = "balanced"
    if current_point:
        if float(current_point.get("hp") or 0.0) > 0:
            dominant_side = "positive_hedge_pressure"
        elif float(current_point.get("hp") or 0.0) < 0:
            dominant_side = "negative_hedge_pressure"

    max_acceleration = derivatives[accel_index] if accel_index is not None and derivatives else {"spot": None, "d_hp_d_s": None}
    decompression_band = {
        "low": acceleration_band.get("high"),
        "high": curve[-1]["spot"] if curve else None,
    } if acceleration_band.get("high") and curve else {"low": None, "high": None}

    return {
        "curve": curve,
        "derivatives": derivatives,
        "zero_pressure": zero_pressure,
        "max_acceleration": max_acceleration,
        "center_of_mass": center_of_mass,
        "pinning_band": pinning_band,
        "acceleration_band": acceleration_band,
        "decompression_band": decompression_band,
        "dominant_side": dominant_side,
        "current_point": current_point,
    }
