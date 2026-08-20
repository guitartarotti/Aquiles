from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Any, TypedDict


class ReferenceAsset(TypedDict):
    security: str
    label: str
    tenor: float

DI_CURVE_REFERENCE_ASSETS: tuple[ReferenceAsset, ...] = (
    {"security": "ODF27 Comdty", "label": "F27", "tenor": 27.0},
    {"security": "ODF28 Comdty", "label": "F28", "tenor": 28.0},
    {"security": "ODF29 Comdty", "label": "F29", "tenor": 29.0},
    {"security": "ODF30 Comdty", "label": "F30", "tenor": 30.0},
    {"security": "ODF31 Comdty", "label": "F31", "tenor": 31.0},
    {"security": "ODF32 Comdty", "label": "F32", "tenor": 32.0},
    {"security": "ODF33 Comdty", "label": "F33", "tenor": 33.0},
    {"security": "ODF35 Comdty", "label": "F35", "tenor": 35.0},
)

BR_IMPLIED_INFLATION_REFERENCE_ASSETS: tuple[ReferenceAsset, ...] = (
    {"security": ".BRII1Y Index", "label": "BRII 1Y", "tenor": 1.0},
    {"security": ".BRII2Y Index", "label": "BRII 2Y", "tenor": 2.0},
    {"security": ".BRII5Y Index", "label": "BRII 5Y", "tenor": 5.0},
    {"security": ".BRII10Y Index", "label": "BRII 10Y", "tenor": 10.0},
)


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


def _sign_label(value: float, bullish_positive: bool = True) -> str:
    threshold = 0.08
    if abs(value) < threshold:
        return "neutral"
    bullish = value > 0 if bullish_positive else value < 0
    return "bullish" if bullish else "bearish"


def _strength_from_score(value: float) -> float:
    return _clamp(abs(value) * 40.0, 0.0, 100.0)


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _row_map(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("factor") or "").strip(): dict(item or {})
        for item in (rows or [])
        if str(item.get("factor") or "").strip()
    }


def _avg(values: list[float]) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _max_abs(values: list[float]) -> float:
    clean = [abs(value) for value in values if math.isfinite(value)]
    return max(clean) if clean else 0.0


def _has_factor_data(rows_by_factor: dict[str, dict[str, Any]], factor_names: list[str]) -> bool:
    return any(
        (rows_by_factor.get(name) or {}).get("timestamp")
        or (rows_by_factor.get(name) or {}).get("raw_value") is not None
        or (rows_by_factor.get(name) or {}).get("daily_change_pct") is not None
        for name in factor_names
    )


def _score_from_row(row: dict[str, Any] | None, *, invert_daily: bool = False) -> float:
    row = row or {}
    z_value = _safe_float(row.get("feature_zscore"), default=float("nan"))
    daily_value = row.get("daily_change_pct")
    daily_score: float | None = None
    if daily_value is not None:
        daily_numeric = _safe_float(daily_value, default=float("nan"))
        if math.isfinite(daily_numeric):
            if invert_daily:
                daily_numeric *= -1.0
            daily_score = _clamp(2.2 * math.tanh(daily_numeric / 2.5), -2.75, 2.75)
    if daily_score is not None and math.isfinite(z_value):
        if abs(z_value) < 0.12 or math.copysign(1.0, daily_score) == math.copysign(1.0, z_value):
            return (0.65 * daily_score) + (0.35 * z_value)
        return (0.82 * daily_score) + (0.18 * z_value)
    if daily_score is not None:
        return daily_score
    if math.isfinite(z_value):
        return z_value
    return 0.0


def _feature_delta_from_row(row: dict[str, Any] | None) -> float | None:
    row = row or {}
    for key in ("feature_value", "raw_value", "daily_change_pct"):
        value = row.get(key)
        if value is None:
            continue
        parsed = _safe_float(value, default=float("nan"))
        if math.isfinite(parsed):
            return parsed
    return None


def _reference_row_value(reference_rows: dict[str, dict[str, Any]] | None, security: str, key: str) -> float | None:
    row = (reference_rows or {}).get(security) or {}
    value = row.get(key)
    if value is None and key == "daily_change_pct":
        value = ((row.get("fields") or {}).get("CHG_PCT_1D"))
    if value is None and key == "price":
        value = ((row.get("fields") or {}).get("PX_LAST"))
    parsed = _safe_float(value, default=float("nan"))
    return parsed if math.isfinite(parsed) else None


def _mean_optional(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _factor_score(
    rows_by_factor: dict[str, dict[str, Any]],
    factor_name: str,
    *,
    sign: float = 1.0,
) -> float:
    return _score_from_row(rows_by_factor.get(factor_name)) * sign


def _default_score_sign(row: dict[str, Any] | None) -> float:
    expected_direction = str((row or {}).get("expected_direction_to_ibov") or "").strip().lower()
    if expected_direction in {
        "negative_when_rising",
        "positive_when_falling",
        "negative_when_steepening",
        "negative_when_widening",
    }:
        return -1.0
    return 1.0


def _derive_score_return_scale(
    rows_by_factor: dict[str, dict[str, Any]],
    contributions_by_factor: dict[str, dict[str, Any]],
    *,
    anchor_price: float,
) -> float:
    ratios: list[float] = []
    if anchor_price <= 0:
        return 0.00045
    for name, payload in (contributions_by_factor or {}).items():
        row = rows_by_factor.get(name) or {}
        signed_score = _score_from_row(row) * _default_score_sign(row)
        if abs(signed_score) < 0.05:
            continue
        cumulative_return = _safe_float(
            payload.get("cumulative_contribution_return"),
            default=float("nan"),
        )
        if not math.isfinite(cumulative_return):
            contribution_points = _safe_float(
                payload.get("contribution_points"),
                default=float("nan"),
            )
            if not math.isfinite(contribution_points):
                continue
            cumulative_return = math.log1p(contribution_points / anchor_price)
        ratio = abs(cumulative_return / signed_score)
        if math.isfinite(ratio) and 1e-6 <= ratio <= 0.02:
            ratios.append(ratio)
    if not ratios:
        return 0.00045
    return float(statistics.median(ratios))


def _curve_regime_label(state: str) -> str:
    labels = {
        "bull_steepening": "bull steepening",
        "bull_flattening": "bull flattening",
        "bear_steepening": "bear steepening",
        "bear_flattening": "bear flattening",
        "parallel_easing": "parallel easing",
        "parallel_tightening": "parallel tightening",
        "steepening_bias": "bias de steepening",
        "flattening_bias": "bias de flattening",
        "mixed_curve": "curva mista",
    }
    return labels.get(str(state or "").strip(), "curva mista")


def _curve_move_sign(value: float | None, threshold: float = 0.002) -> int:
    numeric = _safe_float(value, default=0.0)
    if numeric > threshold:
        return 1
    if numeric < -threshold:
        return -1
    return 0


def _build_curve_regime_summary(
    *,
    rows_by_factor: dict[str, dict[str, Any]],
    core_legs: dict[str, dict[str, Any]],
    live_reference_rows: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    curve_points: list[dict[str, Any]] = []
    for item in DI_CURVE_REFERENCE_ASSETS:
        security = str(item["security"])
        curve_points.append({
            "security": security,
            "label": str(item["label"]),
            "tenor": float(item["tenor"]),
            "price": _reference_row_value(live_reference_rows, security, "price"),
            "daily_change_pct": _reference_row_value(live_reference_rows, security, "daily_change_pct"),
        })

    inflation_points: list[dict[str, Any]] = []
    for item in BR_IMPLIED_INFLATION_REFERENCE_ASSETS:
        security = str(item["security"])
        point = {
            "security": security,
            "label": str(item["label"]),
            "tenor": float(item["tenor"]),
            "price": _reference_row_value(live_reference_rows, security, "price"),
            "daily_change_pct": _reference_row_value(live_reference_rows, security, "daily_change_pct"),
        }
        if point["price"] is not None or point["daily_change_pct"] is not None:
            inflation_points.append(point)

    short_change = _mean_optional([point.get("daily_change_pct") for point in curve_points[:2]])
    belly_change = _mean_optional([point.get("daily_change_pct") for point in curve_points[2:6]])
    long_change = _mean_optional([point.get("daily_change_pct") for point in curve_points[-2:]])
    level_change = _mean_optional([point.get("daily_change_pct") for point in curve_points])
    medium_long_change = _mean_optional([point.get("daily_change_pct") for point in curve_points[-3:]])
    slope_change = (
        (long_change - short_change)
        if short_change is not None and long_change is not None
        else _feature_delta_from_row(rows_by_factor.get("di_slope"))
    )
    curve_edge_change = _mean_optional([short_change, long_change])
    twist_change = (
        belly_change - curve_edge_change
        if belly_change is not None and curve_edge_change is not None
        else _feature_delta_from_row(rows_by_factor.get("di_twist"))
    )
    fiscal_change = (
        (long_change - level_change)
        if long_change is not None and level_change is not None
        else _feature_delta_from_row(rows_by_factor.get("di_fiscal_pressure"))
    )
    duration_change = (
        (medium_long_change - belly_change)
        if medium_long_change is not None and belly_change is not None
        else _feature_delta_from_row(rows_by_factor.get("di_duration_pressure"))
    )

    short_level = _mean_optional([point.get("price") for point in curve_points[:2]])
    long_level = _mean_optional([point.get("price") for point in curve_points[-2:]])
    _mean_optional([point.get("price") for point in curve_points[2:6]])
    geometric_slope = (long_level - short_level) if short_level is not None and long_level is not None else None
    geometric_angle_degrees = (
        math.degrees(math.atan((geometric_slope or 0.0) / max(len(curve_points) - 1, 1)))
        if geometric_slope is not None
        else None
    )

    infl_short_change = _mean_optional([point.get("daily_change_pct") for point in inflation_points[:2]])
    infl_long_change = _mean_optional([point.get("daily_change_pct") for point in inflation_points[-2:]])
    infl_level_change = _mean_optional([point.get("daily_change_pct") for point in inflation_points])
    infl_curve_change = (
        (infl_long_change - infl_short_change)
        if infl_short_change is not None and infl_long_change is not None
        else None
    )

    short_sign = _curve_move_sign(short_change, threshold=0.03)
    long_sign = _curve_move_sign(long_change, threshold=0.03)
    level_sign = _curve_move_sign(level_change, threshold=0.03)
    slope_sign = _curve_move_sign(slope_change, threshold=0.03)

    if short_sign < 0 and long_sign < 0:
        state = "bull_steepening" if slope_sign > 0 else "bull_flattening" if slope_sign < 0 else "parallel_easing"
    elif short_sign > 0 and long_sign > 0:
        state = "bear_steepening" if slope_sign > 0 else "bear_flattening" if slope_sign < 0 else "parallel_tightening"
    elif level_sign < 0 and slope_sign == 0:
        state = "parallel_easing"
    elif level_sign > 0 and slope_sign == 0:
        state = "parallel_tightening"
    elif slope_sign > 0:
        state = "steepening_bias"
    elif slope_sign < 0:
        state = "flattening_bias"
    else:
        state = "mixed_curve"

    fiscal_score = _score_from_row(rows_by_factor.get("di_fiscal_pressure"))
    duration_score = _score_from_row(rows_by_factor.get("di_duration_pressure"))
    medium_long_score = _score_from_row(rows_by_factor.get("di_medium_long"))
    level_score = _score_from_row(rows_by_factor.get("di_level"))
    slope_score = _score_from_row(rows_by_factor.get("di_slope"))
    twist_score = _score_from_row(rows_by_factor.get("di_twist"))
    curve_leg = core_legs.get("curve_medium_long") or {}
    rates_leg = core_legs.get("rates") or {}
    contribution_points = _safe_float(curve_leg.get("contribution_points"))
    rates_points = _safe_float(rates_leg.get("contribution_points"))

    fiscal_risk_score = _clamp(
        max(fiscal_score, 0.0) * 36.0
        + max(duration_score, 0.0) * 28.0
        + max(slope_score, 0.0) * 16.0,
        0.0,
        100.0,
    )
    duration_pressure_score = _clamp(
        max(duration_score, 0.0) * 42.0
        + max(medium_long_score, 0.0) * 26.0
        + max(twist_score, 0.0) * 14.0,
        0.0,
        100.0,
    )
    day_shape_intensity = _clamp(abs(_safe_float(slope_change, 0.0)) * 220.0, 0.0, 100.0)
    geometric_intensity = _clamp(abs(_safe_float(geometric_slope, 0.0)) * 150.0, 0.0, 100.0)
    inclination_score = _clamp((0.55 * day_shape_intensity) + (0.45 * geometric_intensity), 0.0, 100.0)
    state_confidence = _clamp(
        0.34
        + min(abs(_safe_float(short_change)), 0.90) * 0.18
        + min(abs(_safe_float(long_change)), 0.90) * 0.18
        + min(abs(_safe_float(slope_change)), 0.40) * 0.55,
        0.10,
        0.95,
    )
    medium_long_bias = "bullish" if contribution_points > 10 else "bearish" if contribution_points < -10 else "neutral"
    fiscal_risk_flag = bool(
        fiscal_risk_score >= 58.0
        or (state == "bear_steepening" and max(fiscal_score, 0.0) > 0.35)
    )
    if inclination_score >= 78:
        inclination_label = "extremamente inclinada"
    elif inclination_score >= 55:
        inclination_label = "bem inclinada"
    elif inclination_score >= 32:
        inclination_label = "moderadamente inclinada"
    else:
        inclination_label = "quase neutra"

    belly_pressure = max(_safe_float(belly_change) - _safe_float(long_change), 0.0)
    front_pressure = max(_safe_float(short_change) - _safe_float(long_change), 0.0)
    inflationary_raw = (
        max(_safe_float(level_change), 0.0) * 0.42
        + max(_safe_float(belly_change), 0.0) * 0.26
        + max(_safe_float(infl_level_change), 0.0) * 0.22
        + max(_safe_float(infl_curve_change), 0.0) * 0.10
    )
    fiscal_raw = (
        max(_safe_float(long_change), 0.0) * 0.34
        + max(_safe_float(slope_change), 0.0) * 0.28
        + max(_safe_float(duration_change), 0.0) * 0.18
        + max(_safe_float(infl_curve_change), 0.0) * 0.20
    )
    contraction_raw = (
        max(_safe_float(level_change), 0.0) * 0.32
        + max(_safe_float(belly_change), 0.0) * 0.28
        + belly_pressure * 0.25
        + front_pressure * 0.15
    )
    easing_raw = (
        max(-_safe_float(level_change), 0.0) * 0.50
        + max(-_safe_float(long_change), 0.0) * 0.20
        + max(-_safe_float(infl_level_change), 0.0) * 0.30
    )
    mixed_raw = 0.12 + max(abs(_safe_float(twist_change)) - 0.03, 0.0) * 0.40

    regime_raw = {
        "inflacionario": inflationary_raw,
        "fiscal": fiscal_raw,
        "contracao": contraction_raw,
        "desinflacionario": easing_raw,
        "misto": mixed_raw,
    }
    total_regime_raw = sum(max(value, 0.0) for value in regime_raw.values())
    regime_probabilities = {
        key: round(((max(value, 0.0) / total_regime_raw) * 100.0) if total_regime_raw > 0 else (100.0 if key == "misto" else 0.0), 2)
        for key, value in regime_raw.items()
    }
    dominant_regime_key = max(regime_probabilities.items(), key=lambda item: item[1])[0]
    second_regime_key = sorted(regime_probabilities.items(), key=lambda item: item[1], reverse=True)[1][0]
    macro_regime_map = {
        "inflacionario": "inflacionario",
        "fiscal": "risco fiscal / duration",
        "contracao": "contracao / aperto monetario",
        "desinflacionario": "desinflacionario / alivio",
        "misto": "misto / sem vetor unico",
    }
    macro_regime = macro_regime_map.get(dominant_regime_key, "misto / sem vetor unico")
    probable_driver = (
        "belly liderando a alta das taxas"
        if belly_pressure >= 0.06
        else "ponta longa puxando duration/fiscal"
        if max(_safe_float(long_change) - _safe_float(short_change), 0.0) >= 0.05
        else "ponta curta pressionando aperto"
        if front_pressure >= 0.05
        else "movimento mais paralelo da curva"
    )
    absolute_shape = (
        "invertida"
        if geometric_slope is not None and geometric_slope < -0.05
        else "positiva"
        if geometric_slope is not None and geometric_slope > 0.05
        else "flat"
    )
    summary = (
        f"{_curve_regime_label(state)} com {macro_regime}; curta {(_safe_float(short_change)):+.2f}%, "
        f"belly {(_safe_float(belly_change)):+.2f}% e longa {(_safe_float(long_change)):+.2f}%."
    )
    fiscal_message = (
        f"Leitura dominante do dia: {macro_regime} ({regime_probabilities.get(dominant_regime_key, 0.0):.0f}%), "
        f"com vetor secundario {macro_regime_map.get(second_regime_key, second_regime_key)} "
        f"({regime_probabilities.get(second_regime_key, 0.0):.0f}%). Motivo provavel: {probable_driver}."
    )

    return {
        "state": state,
        "label": _curve_regime_label(state),
        "macro_regime": macro_regime,
        "macro_regime_key": dominant_regime_key,
        "regime_probabilities": regime_probabilities,
        "probable_driver": probable_driver,
        "absolute_curve_shape": absolute_shape,
        "summary": summary,
        "fiscal_message": fiscal_message,
        "state_confidence": state_confidence,
        "short_change": short_change,
        "long_change": long_change,
        "level_change": level_change,
        "belly_change": belly_change,
        "slope_change": slope_change,
        "twist_change": twist_change,
        "medium_long_change": medium_long_change,
        "fiscal_change": fiscal_change,
        "duration_change": duration_change,
        "short_day_change_pct": short_change,
        "belly_day_change_pct": belly_change,
        "long_day_change_pct": long_change,
        "level_day_change_pct": level_change,
        "inflation_day_change_pct": infl_level_change,
        "inflation_curve_change_pct": infl_curve_change,
        "curve_points": curve_points,
        "inflation_points": inflation_points,
        "geometric_slope": geometric_slope,
        "geometric_angle_degrees": geometric_angle_degrees,
        "short_score": _score_from_row(rows_by_factor.get("di_short")),
        "long_score": _score_from_row(rows_by_factor.get("di_long")),
        "level_score": level_score,
        "belly_score": _score_from_row(rows_by_factor.get("di_belly")),
        "slope_score": slope_score,
        "twist_score": twist_score,
        "medium_long_score": medium_long_score,
        "fiscal_score": fiscal_score,
        "duration_score": duration_score,
        "fiscal_risk_score": fiscal_risk_score,
        "duration_pressure_score": duration_pressure_score,
        "inclination_score": inclination_score,
        "inclination_label": inclination_label,
        "medium_long_bias": medium_long_bias,
        "curve_contribution_points": contribution_points,
        "rates_contribution_points": rates_points,
        "fiscal_risk_flag": fiscal_risk_flag,
    }


def _build_core_leg(
    *,
    key: str,
    label: str,
    factor_names: list[str],
    rows_by_factor: dict[str, dict[str, Any]],
    contributions_by_factor: dict[str, dict[str, Any]],
    proxy_contributions_by_factor: dict[str, dict[str, Any]] | None,
    anchor_price: float,
    base_reference_price: float,
    stale_penalty: float,
    fallback_scale: float,
    fallback_return_scale: float,
    explanation_hint: str,
    score_signs: dict[str, float] | None = None,
    score_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    supporting_rows = [
        rows_by_factor.get(name) or {}
        for name in factor_names
    ]
    has_supporting_data = any(
        row.get("timestamp") or row.get("raw_value") is not None or row.get("daily_change_pct") is not None
        for row in supporting_rows
    )
    signed_scores: list[float] = []
    weighted_score_total = 0.0
    weight_total = 0.0
    contribution_points = 0.0
    contribution_breakdown: list[dict[str, Any]] = []
    has_model_contribution = False
    for name in factor_names:
        row = rows_by_factor.get(name) or {}
        score_sign = float((score_signs or {}).get(name, 1.0))
        if name not in (score_signs or {}):
            score_sign = _default_score_sign(row)
        row_weight = _safe_float(row.get("weight"), 1.0)
        score_weight = max(float((score_weights or {}).get(name, row_weight if row_weight > 0 else 1.0)), 0.0)
        score = _score_from_row(row) * score_sign
        signed_scores.append(score)
        weighted_score_total += score * score_weight
        weight_total += score_weight
        factor_contribution_payload = contributions_by_factor.get(name) or {}
        contribution_source = "structural_model"
        raw_contribution_points = factor_contribution_payload.get("contribution_points")
        if raw_contribution_points is None:
            factor_contribution_payload = (proxy_contributions_by_factor or {}).get(name) or {}
            raw_contribution_points = factor_contribution_payload.get("contribution_points")
            contribution_source = str(factor_contribution_payload.get("contribution_source") or "proxy_regression")
        factor_contribution_points = _safe_float(raw_contribution_points, default=float("nan"))
        if math.isfinite(factor_contribution_points):
            contribution_points += factor_contribution_points
            has_model_contribution = True
            contribution_breakdown.append({
                "factor": name,
                "label": row.get("label") or factor_contribution_payload.get("label") or name,
                "contribution_points": factor_contribution_points,
                "source": contribution_source,
            })
    contribution_source = "model_anchor"
    if not has_model_contribution:
        score = (weighted_score_total / weight_total) if weight_total > 0 else _avg(signed_scores)
        proxy_leg_return = score * fallback_return_scale * max(fallback_scale / 160.0, 0.35)
        anchor_base = anchor_price if anchor_price > 0 else base_reference_price
        contribution_points = anchor_base * (math.exp(proxy_leg_return) - 1.0)
        contribution_source = "anchor_score_proxy"
    score = (weighted_score_total / weight_total) if weight_total > 0 else _avg(signed_scores)
    if has_model_contribution and abs(score) >= 0.12 and abs(contribution_points) > 1e-6:
        same_sign = math.copysign(1.0, score) == math.copysign(1.0, contribution_points)
        if not same_sign:
            anchor_base = anchor_price if anchor_price > 0 else base_reference_price
            proxy_leg_return = score * fallback_return_scale * max(fallback_scale / 160.0, 0.35)
            proxy_points = anchor_base * (math.exp(proxy_leg_return) - 1.0)
            blend_weight = 0.72 if abs(contribution_points) <= abs(proxy_points) * 1.5 else 0.58
            contribution_points = ((1.0 - blend_weight) * contribution_points) + (blend_weight * proxy_points)
            contribution_source = "model_anchor_realigned"
    confidence = _clamp(0.42 + (_strength_from_score(score) / 170.0) - stale_penalty - (0.18 if not has_supporting_data else 0.0), 0.08, 0.95)
    direction = _sign_label(score)
    return {
        "enabled": has_supporting_data,
        "name": key,
        "label": label,
        "type": "core",
        "score": score,
        "direction": direction,
        "strength": _strength_from_score(score),
        "contribution_points": contribution_points,
        "implied_fair_value_xb1": base_reference_price + contribution_points,
        "contribution_source": contribution_source,
        "contribution_breakdown": contribution_breakdown,
        "confidence": confidence,
        "explanation": (
            f"{label} {direction}: {explanation_hint}"
            if has_supporting_data
            else f"{label} sem dados suficientes; contribution e confidence foram degradados."
        ),
    }


def _build_shadow_leg(
    *,
    key: str,
    label: str,
    score: float,
    base_reference_price: float,
    quality_impact_scale: float,
    band_impact_scale: float,
    convergence_impact_scale: float,
    stale_penalty: float,
    enabled: bool,
    explanation: str,
) -> dict[str, Any]:
    quality_impact = -score * quality_impact_scale
    band_impact = max(score, 0.0) * band_impact_scale
    convergence_impact = -score * convergence_impact_scale
    implied_fv = base_reference_price + (quality_impact * 0.65)
    confidence = _clamp(0.40 + (_strength_from_score(score) / 180.0) - stale_penalty - (0.18 if not enabled else 0.0), 0.06, 0.93)
    return {
        "enabled": enabled,
        "name": key,
        "label": label,
        "type": "shadow",
        "score": score,
        "direction": _sign_label(score, bullish_positive=False),
        "strength": _strength_from_score(score),
        "quality_impact": quality_impact,
        "band_impact": band_impact,
        "convergence_impact": convergence_impact,
        "implied_fair_value_xb1": implied_fv,
        "confidence": confidence,
        "explanation": explanation if enabled else f"{label} sem dado suficiente; quality impact mantido apenas como fallback fraco.",
    }


def _clamp_quality_adjusted_fair_value(
    *,
    core_fair_value_xb1: float,
    proposed_value: float,
    band_half_width_points: float,
) -> float:
    band_half_width_points = max(band_half_width_points, 35.0)
    lower_bound = core_fair_value_xb1 - (band_half_width_points * 0.60)
    upper_bound = core_fair_value_xb1 + (band_half_width_points * 0.60)
    return _clamp(proposed_value, lower_bound, upper_bound)


def _adverse_impact_points(value: float, *, core_direction: str) -> float:
    if core_direction == "bullish":
        return max(-value, 0.0)
    if core_direction == "bearish":
        return max(value, 0.0)
    return abs(value)


def _build_blocker_message(*, label: str, leg_type: str, core_direction: str) -> str:
    if core_direction == "bullish":
        return (
            f"{label} ainda tira qualidade do upside e segura a convergencia."
            if leg_type == "shadow"
            else f"{label} ainda faz preco contra o vetor comprador do core."
        )
    if core_direction == "bearish":
        return (
            f"{label} ainda alivia a perna de baixa e corta a assimetria vendedora."
            if leg_type == "shadow"
            else f"{label} ainda devolve suporte ao preco contra o vetor vendedor do core."
        )
    return f"{label} segue relevante e impede uma leitura limpa de convergencia."


def _build_confirmation_trigger(*, key: str, label: str, core_direction: str) -> dict[str, str]:
    bullish_templates = {
        "rates": "DI curta, belly e slope precisam parar de subir para o core comprador ganhar tracao.",
        "curve_medium_long": "Trecho medio-longo, fiscal e duration precisam aliviar para o upside destravar.",
        "us_rates": "Treasuries, OIS e real yields dos EUA precisam perder pressao para o beta local respirar.",
        "fx": "WDO e dolar global precisam aliviar para reduzir o freio cambial no indice.",
        "credit": "CDS e credito EM/Brasil precisam melhorar para o risco local voltar a ser aceito.",
        "credit_brazil": "Brazil CDS, bonds soberanos e credito corporativo local precisam confirmar alivio.",
        "equity_brazil": "EWZ, financeiro, consumo e small caps precisam confirmar melhor a leitura global.",
        "equity": "O suporte de equity global e EM precisa seguir firme para sustentar o gap bruto.",
        "commodities": "China e commodities precisam manter suporte para o core nao perder tracao.",
        "funding": "Funding global e carry stress precisam aliviar para o shadow parar de cortar conviccao.",
        "volatility": "VIX, MOVE e VXBR precisam estabilizar para a convergencia ficar mais limpa.",
        "credit_shadow": "Credito shadow precisa sair do modo defensivo para o haircut diminuir.",
        "bond_quality": "Bonds BR soberanos/corporativos precisam melhorar para validar a alta local.",
        "corporate_credit": "Credito corporativo global precisa seguir fechando para reforcar a leitura construtiva.",
        "em_stress": "Stress EM precisa aliviar para o risk-on fragil virar risk-on mais aceito.",
        "brazil_relative": "Brasil precisa parar de piorar contra EM para o preco aceitar o fair value.",
        "sovereign_credit": "Risco soberano do Brasil precisa aliviar para destravar a convergencia positiva.",
    }
    bearish_templates = {
        "rates": "DI curta, belly e slope precisam retomar abertura para a perna de baixa ganhar tracao.",
        "curve_medium_long": "Trecho medio-longo, fiscal e duration precisam voltar a pressionar para confirmar a venda.",
        "us_rates": "Treasuries, OIS e real yields dos EUA precisam voltar a apertar para reforcar o downside.",
        "fx": "WDO e dolar global precisam voltar a pressionar para o indice ceder com mais facilidade.",
        "credit": "CDS e credito EM/Brasil precisam piorar novamente para validar o vetor vendedor.",
        "credit_brazil": "Brazil CDS e bonds BR precisam voltar a deteriorar para o downside ganhar aceitação.",
        "equity_brazil": "EWZ, financeiro, consumo e small caps precisam perder suporte para o preco convergir para baixo.",
        "equity": "Equity global e EM precisam perder folego para o preco aceitar o fair value vendedor.",
        "commodities": "Commodities e China precisam esfriar para tirar o suporte residual do indice.",
        "funding": "Funding global precisa voltar a apertar para o shadow reforcar a leitura defensiva.",
        "volatility": "VIX, MOVE e VXBR precisam reacelerar para ampliar a assimetria de baixa.",
        "credit_shadow": "Credito shadow precisa voltar a estressar para o haircut parar de aliviar o downside.",
        "bond_quality": "Bonds BR precisam voltar a deteriorar para a venda local ganhar confirmacao.",
        "corporate_credit": "Credito corporativo global precisa piorar para reforcar o movimento vendedor.",
        "em_stress": "Stress EM precisa reacelerar para o mercado aceitar mais desconto.",
        "brazil_relative": "Brasil precisa voltar a piorar contra EM para a convergencia de baixa destravar.",
        "sovereign_credit": "Risco soberano do Brasil precisa reacelerar para confirmar o vetor vendedor.",
    }
    templates = bullish_templates if core_direction == "bullish" else bearish_templates
    return {
        "key": key,
        "label": label,
        "message": templates.get(key, f"{label} precisa sair do caminho para a convergencia ficar mais limpa."),
    }


def _build_dominant_blockers(
    *,
    core_legs: dict[str, dict[str, Any]],
    shadow_legs: dict[str, dict[str, Any]],
    core_direction: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for key, leg in core_legs.items():
        if not isinstance(leg, dict) or leg.get("enabled") is False:
            continue
        impact_points = _safe_float(leg.get("contribution_points"))
        adverse_points = _adverse_impact_points(impact_points, core_direction=core_direction)
        if adverse_points < 8.0:
            continue
        blockers.append({
            "key": key,
            "label": str(leg.get("label") or key),
            "type": "core",
            "impact_points": impact_points,
            "adverse_points": adverse_points,
            "confidence": _safe_float(leg.get("confidence")),
            "message": _build_blocker_message(
                label=str(leg.get("label") or key),
                leg_type="core",
                core_direction=core_direction,
            ),
        })
    for key, leg in shadow_legs.items():
        if not isinstance(leg, dict) or leg.get("enabled") is False:
            continue
        impact_points = _safe_float(leg.get("quality_impact"))
        adverse_points = _adverse_impact_points(impact_points, core_direction=core_direction)
        if adverse_points < 6.0:
            continue
        blockers.append({
            "key": key,
            "label": str(leg.get("label") or key),
            "type": "shadow",
            "impact_points": impact_points,
            "adverse_points": adverse_points,
            "confidence": _safe_float(leg.get("confidence")),
            "message": _build_blocker_message(
                label=str(leg.get("label") or key),
                leg_type="shadow",
                core_direction=core_direction,
            ),
        })
    blockers.sort(key=lambda item: _safe_float(item.get("adverse_points")), reverse=True)
    return blockers[:5]


def build_fair_value_quality_package(
    *,
    current_future_price: float,
    core_fair_value_xb1: float,
    band_half_width_points: float,
    live_factor_rows: list[dict[str, Any]] | None,
    live_reference_rows: dict[str, dict[str, Any]] | None,
    structural_model: dict[str, Any],
    proxy_contributions_by_factor: dict[str, dict[str, Any]] | None = None,
    options_overlay: dict[str, Any],
    global_overlay: dict[str, Any],
    regime: dict[str, Any],
    us_rates_context: dict[str, Any] | None,
    base_confidence: float,
    base_risk_quality_score: float,
    convergence_probability: float,
) -> dict[str, Any]:
    us_rates_context = us_rates_context or {}
    rows_by_factor = _row_map(live_factor_rows)
    contributions_by_factor = structural_model.get("factor_contributions_now") or {}
    now = datetime.now(timezone.utc)
    stale_scores = []
    for row in rows_by_factor.values():
        ts = _parse_iso(row.get("timestamp"))
        if ts is None:
            continue
        minutes = max((now - ts).total_seconds() / 60.0, 0.0)
        stale_scores.append(_clamp((minutes - 8.0) / 60.0, 0.0, 0.55))
    stale_penalty = max(stale_scores) if stale_scores else 0.0
    reference_fair_value = core_fair_value_xb1 if core_fair_value_xb1 > 0 else current_future_price
    anchor_reference_price = _safe_float(
        structural_model.get("anchor_xb1"),
        _safe_float(structural_model.get("fair_value_intraday_anchor"), reference_fair_value),
    )
    fallback_return_scale = _derive_score_return_scale(
        rows_by_factor,
        contributions_by_factor,
        anchor_price=anchor_reference_price if anchor_reference_price > 0 else reference_fair_value,
    )

    core_legs = {
        "rates": _build_core_leg(
            key="rates",
            label="Core Rates",
            factor_names=[
                "di_short",
                "di_level",
                "di_slope",
                "di_belly",
                "di_twist",
                "brii1_real_yield",
                "brii2_real_yield",
                "brii5_real_yield",
                "brii10_real_yield",
            ],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=180.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="curva local e prêmio de prazo no Brasil.",
        ),
        "equity": _build_core_leg(
            key="equity",
            label="Core Equity",
            factor_names=["spx_proxy", "russell", "developed_markets", "em_future", "ewz", "eem"],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=210.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="equity global, EM e confirmação offshore de Brasil.",
        ),
        "credit": _build_core_leg(
            key="credit",
            label="Core Credit",
            factor_names=["cdx_em", "cdx_hy", "brazil_cds", "embiv"],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=165.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="stress ou alívio em CDS e bonds EM/Brasil.",
        ),
        "fx": _build_core_leg(
            key="fx",
            label="Core FX",
            factor_names=["usdbrl", "dxy_index"],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=160.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="pressão cambial local e dólar global.",
        ),
        "commodities": _build_core_leg(
            key="commodities",
            label="Core Commodities",
            factor_names=["oil", "coal", "copper", "iron_ore"],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=155.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="suporte ou arrasto de commodities relevantes para Brasil.",
        ),
        "us_rates": _build_core_leg(
            key="us_rates",
            label="Core US Rates",
            factor_names=[
                "usgg2_treasury",
                "usgg10_treasury",
                "us_ois_short_factor",
                "us_ois_long_factor",
                "us_monetary_policy_factor",
                "us_term_premium_factor",
            ],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=150.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="Treasuries, OIS e política monetária implícita americana.",
        ),
        "curve_medium_long": _build_core_leg(
            key="curve_medium_long",
            label="Core Curve Medium Long",
            factor_names=[
                "di_medium_long",
                "di_fiscal_pressure",
                "di_duration_pressure",
                "brii5_real_yield",
                "brii10_real_yield",
            ],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=145.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="trecho medio-longo da curva DI e seus proxies de fiscal/duration.",
            score_signs={
                "di_medium_long": -1.0,
                "di_fiscal_pressure": -1.0,
                "di_duration_pressure": -1.0,
                "brii5_real_yield": -1.0,
                "brii10_real_yield": -1.0,
            },
            score_weights={
                "di_medium_long": 1.0,
                "di_fiscal_pressure": 0.90,
                "di_duration_pressure": 0.80,
                "brii5_real_yield": 0.70,
                "brii10_real_yield": 0.80,
            },
        ),
        "credit_brazil": _build_core_leg(
            key="credit_brazil",
            label="Core Brazil Credit",
            factor_names=[
                "brazil_cds",
                "brazil_cds_3y",
                "brazil_bond_price",
                "brazil_corporate_bond_price",
            ],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=140.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="credito soberano, bonds Brasil e corporativo local.",
            score_signs={
                "brazil_cds": -1.0,
                "brazil_cds_3y": -1.0,
                "brazil_bond_price": 1.0,
                "brazil_corporate_bond_price": 1.0,
            },
            score_weights={
                "brazil_cds": 1.0,
                "brazil_cds_3y": 0.75,
                "brazil_bond_price": 0.85,
                "brazil_corporate_bond_price": 0.75,
            },
        ),
        "equity_brazil": _build_core_leg(
            key="equity_brazil",
            label="Core Brazil Equity",
            factor_names=[
                "brazil_financials",
                "brazil_materials",
                "brazil_consumption",
                "brazil_small_caps",
                "brazil_dividends",
                "vale3_local",
                "petr4_local",
            ],
            rows_by_factor=rows_by_factor,
            contributions_by_factor=contributions_by_factor,
            proxy_contributions_by_factor=proxy_contributions_by_factor,
            anchor_price=anchor_reference_price,
            base_reference_price=reference_fair_value,
            stale_penalty=stale_penalty,
            fallback_scale=170.0,
            fallback_return_scale=fallback_return_scale,
            explanation_hint="setores domesticos, breadth local e heavyweights do indice.",
            score_weights={
                "brazil_financials": 1.0,
                "brazil_materials": 0.95,
                "brazil_consumption": 0.75,
                "brazil_small_caps": 0.65,
                "brazil_dividends": 0.55,
                "vale3_local": 0.90,
                "petr4_local": 0.90,
            },
        ),
    }

    curve_conditions = _build_curve_regime_summary(
        rows_by_factor=rows_by_factor,
        core_legs=core_legs,
        live_reference_rows=live_reference_rows,
    )

    volatility_score = _avg([
        _score_from_row(rows_by_factor.get("vix_index")),
        _score_from_row(rows_by_factor.get("move_index")),
        _score_from_row(rows_by_factor.get("vxbr_index")),
    ])
    funding_score = _safe_float(((us_rates_context.get("funding_stress_factor") or {}).get("score")), 0.0)
    em_stress_score = _avg([
        _score_from_row(rows_by_factor.get("cdx_em")),
        _score_from_row(rows_by_factor.get("embiv")),
    ])
    corporate_credit_score = _score_from_row(rows_by_factor.get("cdx_hy"))
    sovereign_credit_score = _avg([
        _score_from_row(rows_by_factor.get("brazil_cds")),
        _score_from_row(rows_by_factor.get("brazil_cds_3y")),
    ])
    bond_quality_score = _avg([
        _score_from_row(rows_by_factor.get("embiv")),
        _score_from_row(rows_by_factor.get("brazil_cds")),
    ])
    brazil_bond_relief_score = _avg([
        _factor_score(rows_by_factor, "brazil_bond_price", sign=-1.0),
        _factor_score(rows_by_factor, "brazil_corporate_bond_price", sign=-1.0),
    ])
    bond_quality_score = _avg([bond_quality_score, brazil_bond_relief_score])
    brazil_relative_score = sovereign_credit_score - em_stress_score

    shadow_legs = {
        "credit_shadow": _build_shadow_leg(
            key="credit_shadow",
            label="Shadow Credit",
            score=_avg([corporate_credit_score, sovereign_credit_score, em_stress_score]),
            base_reference_price=reference_fair_value,
            quality_impact_scale=110.0,
            band_impact_scale=0.18,
            convergence_impact_scale=0.14,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["cdx_hy", "brazil_cds", "brazil_cds_3y", "cdx_em", "embiv"]),
            explanation="Lê a qualidade do movimento a partir de CDS soberano, HY e EM.",
        ),
        "bond_quality": _build_shadow_leg(
            key="bond_quality",
            label="Shadow Bonds BR",
            score=bond_quality_score,
            base_reference_price=reference_fair_value,
            quality_impact_scale=85.0,
            band_impact_scale=0.11,
            convergence_impact_scale=0.08,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["embiv", "brazil_cds", "brazil_bond_price", "brazil_corporate_bond_price"]),
            explanation="Qualidade implícita de bonds Brasil soberanos/corporativos e EMBI/EMBIV.",
        ),
        "corporate_credit": _build_shadow_leg(
            key="corporate_credit",
            label="Shadow Corporate Credit",
            score=corporate_credit_score,
            base_reference_price=reference_fair_value,
            quality_impact_scale=72.0,
            band_impact_scale=0.10,
            convergence_impact_scale=0.08,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["cdx_hy"]),
            explanation="Stress ou alívio de crédito corporativo global / high yield.",
        ),
        "em_stress": _build_shadow_leg(
            key="em_stress",
            label="Shadow EM Stress",
            score=em_stress_score,
            base_reference_price=reference_fair_value,
            quality_impact_scale=76.0,
            band_impact_scale=0.12,
            convergence_impact_scale=0.10,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["cdx_em", "embiv"]),
            explanation="Stress relativo de emergentes e crédito EM.",
        ),
        "funding": _build_shadow_leg(
            key="funding",
            label="Shadow Funding",
            score=funding_score,
            base_reference_price=reference_fair_value,
            quality_impact_scale=125.0,
            band_impact_scale=0.21,
            convergence_impact_scale=0.17,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["us_ois_short_factor", "us_ois_long_factor", "move_index", "dxy_index", "jpy_basket"]),
            explanation="Funding global via OIS, MOVE, DXY e stress de carry.",
        ),
        "volatility": _build_shadow_leg(
            key="volatility",
            label="Shadow Volatility",
            score=volatility_score,
            base_reference_price=reference_fair_value,
            quality_impact_scale=92.0,
            band_impact_scale=0.16,
            convergence_impact_scale=0.12,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["vix_index", "move_index", "vxbr_index"]),
            explanation="Volatilidade global e local usada como filtro de qualidade.",
        ),
        "brazil_relative": _build_shadow_leg(
            key="brazil_relative",
            label="Shadow Brazil Relative",
            score=brazil_relative_score,
            base_reference_price=reference_fair_value,
            quality_impact_scale=68.0,
            band_impact_scale=0.08,
            convergence_impact_scale=0.06,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["brazil_cds", "brazil_cds_3y", "cdx_em", "embiv"]),
            explanation="Divergência de Brasil contra o pacote EM/Global.",
        ),
        "sovereign_credit": _build_shadow_leg(
            key="sovereign_credit",
            label="Shadow Sovereign Credit",
            score=sovereign_credit_score,
            base_reference_price=reference_fair_value,
            quality_impact_scale=74.0,
            band_impact_scale=0.10,
            convergence_impact_scale=0.08,
            stale_penalty=stale_penalty,
            enabled=_has_factor_data(rows_by_factor, ["brazil_cds", "brazil_cds_3y"]),
            explanation="Stress soberano de Brasil no curto e 5 anos.",
        ),
    }

    core_scores = [float(item.get("score") or 0.0) for item in core_legs.values()]
    shadow_scores = [float(item.get("score") or 0.0) for item in shadow_legs.values()]
    core_direction_score = _avg(core_scores)
    shadow_direction_score = -_avg(shadow_scores)
    alignment = 1.0 - min(abs(core_direction_score - shadow_direction_score) / 3.0, 1.0)
    divergence_score = min(abs(core_direction_score - shadow_direction_score) / 2.5, 1.0)
    coherence_score = _clamp(
        (alignment * 0.55)
        + ((1.0 - divergence_score) * 0.20)
        + (base_confidence * 0.25),
        0.0,
        1.0,
    )

    shadow_net_quality = sum(_safe_float(item.get("quality_impact")) for item in shadow_legs.values())
    shadow_band_pressure = sum(_safe_float(item.get("band_impact")) for item in shadow_legs.values())
    shadow_convergence_pressure = sum(_safe_float(item.get("convergence_impact")) for item in shadow_legs.values())

    mispricing = current_future_price - core_fair_value_xb1
    core_direction = "bullish" if core_fair_value_xb1 > current_future_price else "bearish" if core_fair_value_xb1 < current_future_price else "neutral"
    quality_multiplier = _clamp(
        0.45 + (base_confidence * 0.30) + (alignment * 0.22) - (divergence_score * 0.25),
        0.18,
        1.05,
    )
    shadow_quality_shift = _clamp(
        shadow_net_quality * 0.035,
        -(band_half_width_points * 0.40),
        band_half_width_points * 0.40,
    )
    quality_adjusted_fair_value_xb1 = core_fair_value_xb1 + (shadow_quality_shift * quality_multiplier)
    quality_adjusted_fair_value_xb1 = _clamp_quality_adjusted_fair_value(
        core_fair_value_xb1=core_fair_value_xb1,
        proposed_value=quality_adjusted_fair_value_xb1,
        band_half_width_points=band_half_width_points,
    )
    shadow_haircut_points = quality_adjusted_fair_value_xb1 - core_fair_value_xb1

    if core_direction == "bullish" and shadow_direction_score > 0.15:
        implicit_sentiment = "bullish_confirmed"
    elif core_direction == "bullish" and shadow_direction_score <= 0.15:
        implicit_sentiment = "bullish_fragile"
    elif core_direction == "bearish" and shadow_direction_score < -0.15:
        implicit_sentiment = "bearish_confirmed"
    elif core_direction == "bearish" and shadow_direction_score >= -0.15:
        implicit_sentiment = "bearish_fragile"
    elif divergence_score > 0.55:
        implicit_sentiment = "divergent"
    else:
        implicit_sentiment = "neutral"

    if funding_score > 0.45:
        implicit_sentiment = "stress_risk"
    elif _safe_float(((us_rates_context.get("funding_stress_factor") or {}).get("score")), 0.0) > 0.30 and _score_from_row(rows_by_factor.get("jpy_basket")) > 0.40:
        implicit_sentiment = "carry_unwind_risk"
    elif shadow_legs["volatility"]["score"] > 0.50 and core_direction == "bullish":
        implicit_sentiment = "bullish_fragile"
    elif shadow_legs["volatility"]["score"] > 0.50 and core_direction == "bearish":
        implicit_sentiment = "bearish_confirmed"
    elif mispricing > band_half_width_points * 0.75 and shadow_direction_score <= 0:
        implicit_sentiment = "overextended_fragile"
    elif mispricing < -band_half_width_points * 0.75 and shadow_direction_score > 0:
        implicit_sentiment = "recovery_candidate"
    elif core_direction == "neutral" and shadow_direction_score < -0.15:
        implicit_sentiment = "latent_stress"
    elif shadow_legs["funding"]["score"] > 0.65 and shadow_legs["volatility"]["score"] > 0.45:
        implicit_sentiment = "squeeze_risk"

    sentiment_confidence = _clamp(
        0.32 + (base_confidence * 0.28) + (coherence_score * 0.24) + (_max_abs(core_scores + shadow_scores) * 0.08),
        0.10,
        0.96,
    )

    upside_bias = _clamp(max(core_direction_score, 0.0) * 0.45 + max(shadow_direction_score, 0.0) * 0.35 - max(shadow_scores[4] if len(shadow_scores) > 4 else 0.0, 0.0) * 0.20, -1.0, 1.0)
    downside_bias = _clamp(max(-core_direction_score, 0.0) * 0.45 + max(-shadow_direction_score, 0.0) * 0.35 + max(funding_score, 0.0) * 0.20, -1.0, 1.0)
    ribbon_multiplier = _clamp(
        0.72
        + ((1.0 - base_confidence) * 0.55)
        + ((1.0 - base_risk_quality_score) * 0.42)
        + (divergence_score * 0.38)
        + shadow_band_pressure,
        0.55,
        2.2,
    )
    ribbon_width = max(band_half_width_points * ribbon_multiplier, 35.0)
    ribbon_upper = core_fair_value_xb1 + (ribbon_width * (1.0 + max(upside_bias, 0.0) * 0.55))
    ribbon_lower = core_fair_value_xb1 - (ribbon_width * (1.0 + max(downside_bias, 0.0) * 0.55))
    quality_ribbon = {
        "upper": ribbon_upper,
        "lower": ribbon_lower,
        "width": ribbon_upper - ribbon_lower,
        "asymmetry": (ribbon_upper - core_fair_value_xb1) - (core_fair_value_xb1 - ribbon_lower),
        "reason": (
            "Faixa estreita e simétrica: boa coerência de Core/Shadow."
            if ribbon_multiplier < 0.9 and divergence_score < 0.25
            else "Faixa ampliada por divergência Core/Shadow, funding/volatilidade e stress de qualidade."
        ),
    }

    bullish_forces = [
        f"{leg['label']} {leg['contribution_points']:+.0f} pts"
        for leg in core_legs.values()
        if _safe_float(leg.get("contribution_points")) > 0
    ][:4]
    bearish_forces = [
        f"{leg['label']} {leg['contribution_points']:+.0f} pts"
        for leg in core_legs.values()
        if _safe_float(leg.get("contribution_points")) < 0
    ][:4]
    divergences = []
    if divergence_score > 0.35:
        divergences.append("Core e Shadow divergem materialmente em direção/qualidade.")
    if abs(core_legs["equity"]["score"] - shadow_legs["volatility"]["score"]) > 0.8:
        divergences.append("Equity core e volatility shadow contam histórias diferentes.")
    if abs(core_legs["credit"]["score"] - shadow_legs["em_stress"]["score"]) > 0.75:
        divergences.append("Crédito core e stress EM shadow mostram desalinhamento.")
    warnings = []
    if stale_penalty > 0.10:
        warnings.append("Parte das pernas está stale; confidence foi penalizada.")
    if funding_score > 0.45:
        warnings.append("Funding stress elevado amplia bandas e reduz probabilidade de convergência.")
    if shadow_legs["volatility"]["score"] > 0.45:
        warnings.append("Volatilidade shadow deteriorada reduz a qualidade do Fair Value.")

    quality_gauge = _clamp(base_risk_quality_score * 100.0, 0.0, 100.0)
    ranking_up = sorted(core_legs.values(), key=lambda item: _safe_float(item.get("contribution_points")), reverse=True)[:4]
    ranking_down = sorted(core_legs.values(), key=lambda item: _safe_float(item.get("contribution_points")))[:4]
    dominant_blockers = _build_dominant_blockers(
        core_legs=core_legs,
        shadow_legs=shadow_legs,
        core_direction=core_direction,
    )
    confirmation_triggers = [
        _build_confirmation_trigger(
            key=str(item.get("key") or ""),
            label=str(item.get("label") or item.get("key") or ""),
            core_direction=core_direction,
        )
        for item in dominant_blockers
    ]

    return {
        "core_fair_value_xb1": core_fair_value_xb1,
        "quality_adjusted_fair_value_xb1": quality_adjusted_fair_value_xb1,
        "shadow_haircut_points": shadow_haircut_points,
        "curve_conditions": curve_conditions,
        "implicit_sentiment": implicit_sentiment,
        "sentiment_confidence": sentiment_confidence,
        "core_shadow_alignment": alignment,
        "divergence_score": divergence_score,
        "coherence_score": coherence_score,
        "convergence_probability": _clamp(convergence_probability - shadow_convergence_pressure, 0.02, 0.98),
        "regime_break_probability": _clamp(divergence_score * 0.55 + max(funding_score, 0.0) * 0.30 + max(shadow_legs["volatility"]["score"], 0.0) * 0.20, 0.02, 0.98),
        "quality_ribbon": quality_ribbon,
        "core_legs": core_legs,
        "shadow_legs": shadow_legs,
        "quality_gauge": quality_gauge,
        "ranking_up": ranking_up,
        "ranking_down": ranking_down,
        "explanation": {
            "summary": (
                f"Core FV em {core_direction}; gap bruto {core_fair_value_xb1 - current_future_price:+.0f} pts, "
                f"shadow {'corta' if _adverse_impact_points(shadow_haircut_points, core_direction=core_direction) > 0 else 'reforca'} "
                f"{shadow_haircut_points:+.0f} pts e deixa gap liquido {quality_adjusted_fair_value_xb1 - current_future_price:+.0f} pts. "
                f"Curva local: {curve_conditions.get('label') or 'curva mista'}."
            ),
            "core_message": f"Core Fair Value aponta {core_direction} com coerência {coherence_score:.2f}.",
            "shadow_message": f"Shadow Risk classifica o cenário como {implicit_sentiment}.",
            "bullish_forces": bullish_forces,
            "bearish_forces": bearish_forces,
            "shadow_haircut_points": shadow_haircut_points,
            "dominant_blockers": dominant_blockers,
            "confirmation_triggers": confirmation_triggers,
            "divergences": divergences,
            "warnings": warnings,
        },
    }
