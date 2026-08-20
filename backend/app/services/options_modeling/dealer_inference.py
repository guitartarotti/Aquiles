from __future__ import annotations

from typing import Any, cast

from ...config import Config
from .math_utils import clamp, percentile


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _weighted_avg(values: list[tuple[float, float]]) -> float | None:
    total_weight = sum(max(weight, 0.0) for _, weight in values)
    if total_weight <= 0:
        return None
    return sum(value * max(weight, 0.0) for value, weight in values) / total_weight


def _build_strike_sides(option_exposures: list[dict[str, Any]]) -> dict[float, dict[str, Any]]:
    strikes: dict[float, dict[str, Any]] = {}

    def side_bucket(strike_payload: dict[str, Any], side: str) -> dict[str, Any]:
        if side not in strike_payload:
            strike_payload[side] = {
                "contracts": 0,
                "oi": 0.0,
                "gex_abs": 0.0,
                "gamma_abs": 0.0,
                "iv_values": [],
                "liquidity_values": [],
                "reliability_values": [],
            }
        return cast(dict[str, Any], strike_payload[side])

    for item in option_exposures:
        option = item.get("option", {}) or {}
        strike = _safe_float(option.get("strike"))
        side = str(option.get("put_call") or "").strip()
        if strike is None or side not in {"Call", "Put"}:
            continue
        strike_payload = strikes.setdefault(strike, {"strike": strike})
        bucket = side_bucket(strike_payload, side)
        bucket["contracts"] += 1
        oi = max(_safe_float(option.get("open_int")) or 0.0, 0.0)
        bucket["oi"] += oi
        bucket["gex_abs"] += abs(_safe_float(item.get("gex")) or 0.0)
        selected_gamma = _safe_float((item.get("selected_greeks") or {}).get("gamma"))
        bucket["gamma_abs"] += abs(selected_gamma or 0.0)
        iv = _safe_float(option.get("selected_iv"))
        if iv is not None:
            weight = max(oi, 1.0) * max(_safe_float(option.get("liquidity_weight")) or 0.0, 0.05)
            bucket["iv_values"].append((iv, weight))
        bucket["liquidity_values"].append(max(_safe_float(option.get("liquidity_weight")) or 0.0, 0.0))
        bucket["reliability_values"].append(max(_safe_float(option.get("reliability_weight")) or 0.0, 0.0))

    for _strike, payload in strikes.items():
        for side in ("Call", "Put"):
            bucket = payload.get(side) or {
                "contracts": 0,
                "oi": 0.0,
                "gex_abs": 0.0,
                "gamma_abs": 0.0,
                "iv_values": [],
                "liquidity_values": [],
                "reliability_values": [],
            }
            payload[side] = bucket
            payload[f"oi_{side.lower()}"] = bucket["oi"]
            payload[f"gex_{side.lower()}"] = bucket["gex_abs"]
            payload[f"gamma_{side.lower()}"] = bucket["gamma_abs"]
            payload[f"iv_{side.lower()}"] = _weighted_avg(bucket["iv_values"])
            payload[f"liquidity_{side.lower()}"] = (
                sum(bucket["liquidity_values"]) / len(bucket["liquidity_values"])
                if bucket["liquidity_values"] else 0.0
            )
            payload[f"reliability_{side.lower()}"] = (
                sum(bucket["reliability_values"]) / len(bucket["reliability_values"])
                if bucket["reliability_values"] else 0.0
            )
        payload["pair_complete"] = payload["Call"]["contracts"] > 0 and payload["Put"]["contracts"] > 0
        payload["oi_total"] = payload["oi_call"] + payload["oi_put"]
    return strikes


def _compute_component_scores(
    strike_rows: list[dict[str, Any]],
    weights: dict[str, float],
    lambda_iv: float,
    lambda_oi: float,
    eps: float,
) -> list[dict[str, Any]]:
    gex_nets: list[float] = []
    gamma_nets: list[float] = []
    oi_totals: list[float] = []

    for row in strike_rows:
        row["gex_net"] = float(row.get("gex_call") or 0.0) - float(row.get("gex_put") or 0.0)
        row["gamma_net"] = float(row.get("gamma_call") or 0.0) - float(row.get("gamma_put") or 0.0)
        gex_nets.append(abs(row["gex_net"]))
        gamma_nets.append(abs(row["gamma_net"]))
        oi_totals.append(float(row.get("oi_total") or 0.0))

    gex_scale = max(percentile(gex_nets, 0.95, 1.0), eps)
    gamma_scale = max(percentile(gamma_nets, 0.95, 1.0), eps)
    oi_scale = max(percentile(oi_totals, 0.75, 1.0), eps)

    for row in strike_rows:
        pair_complete = bool(row.get("pair_complete"))
        iv_call = _safe_float(row.get("iv_call"))
        iv_put = _safe_float(row.get("iv_put"))
        oi_call = float(row.get("oi_call") or 0.0)
        oi_put = float(row.get("oi_put") or 0.0)
        valid_components: list[tuple[str, float, float]] = []

        if pair_complete and iv_call is not None and iv_put is not None:
            denominator = 0.5 * (iv_call + iv_put) + eps
            reliability_pair = (
                float(row.get("reliability_call") or 0.0) + float(row.get("reliability_put") or 0.0)
            ) / 2.0
            iv_score = __import__("math").tanh(lambda_iv * ((iv_call - iv_put) / denominator))
            row["iv_skew_score"] = iv_score
            row["iv_quality"] = clamp(reliability_pair, 0.25, 1.0)
            valid_components.append(("iv", iv_score, weights["iv"] * row["iv_quality"]))
        else:
            row["iv_skew_score"] = 0.0
            row["iv_quality"] = 0.2 if iv_call is not None or iv_put is not None else 0.0

        if pair_complete and (oi_call + oi_put) > 0:
            oi_score = __import__("math").tanh(lambda_oi * ((oi_call - oi_put) / (oi_call + oi_put + eps)))
            row["oi_imbalance_score"] = oi_score
            valid_components.append(("oi", oi_score, weights["oi"]))
        else:
            row["oi_imbalance_score"] = 0.0

        if pair_complete and abs(float(row.get("gex_net") or 0.0)) > 0:
            gex_score = __import__("math").tanh(float(row.get("gex_net") or 0.0) / (gex_scale + eps))
            row["gex_score"] = gex_score
            valid_components.append(("gex", gex_score, weights["gex"]))
        else:
            row["gex_score"] = 0.0

        if pair_complete and abs(float(row.get("gamma_net") or 0.0)) > 0:
            gamma_score = __import__("math").tanh(float(row.get("gamma_net") or 0.0) / (gamma_scale + eps))
            row["gamma_score"] = gamma_score
            valid_components.append(("gamma", gamma_score, weights["gamma"]))
        else:
            row["gamma_score"] = 0.0

        effective_weight = sum(weight for _, _, weight in valid_components)
        raw_score = sum(score * weight for _, score, weight in valid_components) / effective_weight if effective_weight > 0 else 0.0
        row["dealer_inference_raw_score"] = raw_score
        row["component_weight_sum"] = effective_weight
        row["oi_quality"] = clamp((oi_call + oi_put) / oi_scale, 0.0, 1.0)
        row["component_completeness"] = len(valid_components) / 4.0
    return strike_rows


def _compute_confidence(row: dict[str, Any]) -> float:
    pairing = 1.0 if row.get("pair_complete") else 0.15
    iv_quality = float(row.get("iv_quality") or 0.0)
    liquidity = (
        float(row.get("liquidity_call") or 0.0) + float(row.get("liquidity_put") or 0.0)
    ) / 2.0
    reliability = (
        float(row.get("reliability_call") or 0.0) + float(row.get("reliability_put") or 0.0)
    ) / 2.0
    oi_quality = float(row.get("oi_quality") or 0.0)
    completeness = float(row.get("component_completeness") or 0.0)
    confidence = min(
        1.0,
        0.28 * pairing
        + 0.18 * iv_quality
        + 0.18 * liquidity
        + 0.18 * oi_quality
        + 0.10 * reliability
        + 0.08 * completeness,
    )
    return clamp(confidence, 0.0, 1.0)


def _compute_reference_rank(
    row: dict[str, Any],
    *,
    spot_price: float | None,
    gex_scale: float,
    oi_scale: float,
    eps: float,
) -> float:
    confidence = float(row.get("dealer_inference_confidence") or 0.0)
    gex_signal = abs(float(row.get("gex_score") or 0.0))
    gamma_signal = abs(float(row.get("gamma_score") or 0.0))
    oi_total = float(row.get("oi_total") or 0.0)
    gex_net = abs(float(row.get("gex_net") or 0.0))
    completeness = float(row.get("component_completeness") or 0.0)

    materiality = (
        0.35 * gex_signal
        + 0.20 * gamma_signal
        + 0.20 * clamp(oi_total / max(oi_scale, eps), 0.0, 1.0)
        + 0.15 * clamp(gex_net / max(gex_scale, eps), 0.0, 1.0)
        + 0.10 * completeness
    )

    proximity = 1.0
    if spot_price is not None and spot_price > 0:
        distance_pct = abs(float(row.get("strike") or 0.0) - spot_price) / spot_price
        proximity = clamp(1.0 - (distance_pct / 0.35), 0.05, 1.0)

    return confidence * (0.30 + 0.70 * materiality) * proximity


def build_dealer_inference(
    option_exposures: list[dict[str, Any]],
    summary: dict[str, Any],
    pressure: dict[str, Any],
) -> dict[str, Any]:
    if not Config.OPTIONS_MODEL_DEALER_INFERENCE_ENABLE:
        return {
            "enabled": False,
            "rows": [],
            "comparison": {},
            "config": {},
        }

    weights = {
        "iv": float(Config.OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_IV),
        "oi": float(Config.OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_OI),
        "gex": float(Config.OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_GEX),
        "gamma": float(Config.OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_GAMMA),
    }
    strike_map = _build_strike_sides(option_exposures)
    strike_rows = sorted(strike_map.values(), key=lambda item: float(item["strike"]))
    strike_rows = _compute_component_scores(
        strike_rows,
        weights=weights,
        lambda_iv=float(Config.OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_IV),
        lambda_oi=float(Config.OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_OI),
        eps=float(Config.OPTIONS_MODEL_DEALER_INFERENCE_EPS),
    )

    range_points = float(Config.OPTIONS_MODEL_DEALER_INFERENCE_RANGE_POINTS)
    future_basis_points = float(_safe_float(summary.get("future_basis_points")) or 0.0)
    for row in strike_rows:
        shift = clamp(range_points * float(row.get("dealer_inference_raw_score") or 0.0), -range_points, range_points)
        confidence = _compute_confidence(row)
        row["dealer_inference_shift"] = shift
        row["dealer_inference_value"] = float(row["strike"]) + shift
        row["dealer_inference_future_value"] = float(row["dealer_inference_value"]) + future_basis_points
        row["dealer_inference_confidence"] = confidence

    eps = float(Config.OPTIONS_MODEL_DEALER_INFERENCE_EPS)
    gex_reference_scale = max(
        percentile((abs(float(row.get("gex_net") or 0.0)) for row in strike_rows), 0.85, 1.0),
        eps,
    )
    oi_reference_scale = max(
        percentile((float(row.get("oi_total") or 0.0) for row in strike_rows), 0.75, 1.0),
        eps,
    )
    spot_price = _safe_float(summary.get("spot_price"))
    for row in strike_rows:
        row["dealer_reference_rank"] = _compute_reference_rank(
            row,
            spot_price=spot_price,
            gex_scale=gex_reference_scale,
            oi_scale=oi_reference_scale,
            eps=eps,
        )

    ranked_rows = sorted(
        strike_rows,
        key=lambda item: (
            -float(item.get("dealer_inference_confidence") or 0.0),
            -abs(float(item.get("dealer_inference_shift") or 0.0)),
            -float(item.get("oi_total") or 0.0),
        )
    )

    reference_candidates = [
        row for row in strike_rows
        if float(row.get("oi_total") or 0.0) > 0 and abs(float(row.get("gex_net") or 0.0)) > 0
    ]
    reference_pool = reference_candidates or ranked_rows
    reference_row = max(
        reference_pool,
        key=lambda item: float(item.get("dealer_reference_rank") or 0.0),
        default={},
    )
    gex_center_of_mass = None
    denominator = sum(abs(float(row.get("gex_net") or 0.0)) for row in strike_rows)
    if denominator > 0:
        gex_center_of_mass = sum(float(row["strike"]) * abs(float(row.get("gex_net") or 0.0)) for row in strike_rows) / denominator

    zero_pressure_spot = (summary.get("zero_pressure") or {}).get("spot")
    max_acceleration_spot = (summary.get("max_acceleration") or {}).get("spot")
    nearest_full_strike_to_zero = None
    nearest_full_strike_to_accel = None
    if strike_rows and zero_pressure_spot is not None:
        nearest_full_strike_to_zero = min(strike_rows, key=lambda row: abs(float(row["strike"]) - float(zero_pressure_spot)))["strike"]
    if strike_rows and max_acceleration_spot is not None:
        nearest_full_strike_to_accel = min(strike_rows, key=lambda row: abs(float(row["strike"]) - float(max_acceleration_spot)))["strike"]

    ordered_rows = sorted(strike_rows, key=lambda item: float(item["strike"]))

    return {
        "enabled": True,
        "config": {
            "range_points": range_points,
            "weights": weights,
            "lambda_iv": float(Config.OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_IV),
            "lambda_oi": float(Config.OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_OI),
            "eps": float(Config.OPTIONS_MODEL_DEALER_INFERENCE_EPS),
        },
        "rows": [
            {
                "strike": float(row["strike"]),
                "dealer_inference_shift": float(row.get("dealer_inference_shift") or 0.0),
                "dealer_inference_value": float(row.get("dealer_inference_value") or row["strike"]),
                "dealer_inference_future_value": float(
                    row.get("dealer_inference_future_value") or row.get("dealer_inference_value") or row["strike"]
                ),
                "dealer_inference_confidence": float(row.get("dealer_inference_confidence") or 0.0),
                "dealer_reference_rank": float(row.get("dealer_reference_rank") or 0.0),
                "oi_total": float(row.get("oi_total") or 0.0),
                "iv_skew_score": float(row.get("iv_skew_score") or 0.0),
                "oi_imbalance_score": float(row.get("oi_imbalance_score") or 0.0),
                "gex_score": float(row.get("gex_score") or 0.0),
                "gamma_score": float(row.get("gamma_score") or 0.0),
                "gex_net": float(row.get("gex_net") or 0.0),
                "gamma_net": float(row.get("gamma_net") or 0.0),
                "oi_call": float(row.get("oi_call") or 0.0),
                "oi_put": float(row.get("oi_put") or 0.0),
                "iv_call": _safe_float(row.get("iv_call")),
                "iv_put": _safe_float(row.get("iv_put")),
            }
            for row in ordered_rows
        ],
        "comparison": {
            "reference_strike": float(reference_row["strike"]) if reference_row else None,
            "reference_dealer_inference_value": float(reference_row.get("dealer_inference_value") or 0.0) if reference_row else None,
            "reference_dealer_inference_future_value": (
                float(reference_row.get("dealer_inference_future_value") or 0.0) if reference_row else None
            ),
            "reference_confidence": float(reference_row.get("dealer_inference_confidence") or 0.0) if reference_row else None,
            "gex_center_of_mass": gex_center_of_mass,
            "zero_pressure_spot": zero_pressure_spot,
            "max_acceleration_spot": max_acceleration_spot,
            "nearest_full_strike_to_zero_pressure": nearest_full_strike_to_zero,
            "nearest_full_strike_to_max_acceleration": nearest_full_strike_to_accel,
        },
    }
