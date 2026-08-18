from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any

from ...config import Config
from .math_utils import clamp, percentile, weighted_average, weighted_quantile
from .types import MarketContext

NORMAL_DIST = NormalDist()
DEFAULT_BAND_QUANTILES = [
    {"level": 1, "label": "1sigma proxy", "lower_q": 0.16, "upper_q": 0.84},
    {"level": 2, "label": "2sigma proxy", "lower_q": 0.10, "upper_q": 0.90},
    {"level": 3, "label": "3sigma proxy", "lower_q": 0.05, "upper_q": 0.95},
    {"level": 4, "label": "4sigma proxy", "lower_q": 0.025, "upper_q": 0.975},
    {"level": 5, "label": "5sigma proxy", "lower_q": 0.01, "upper_q": 0.99},
    {"level": 6, "label": "6sigma proxy", "lower_q": 0.005, "upper_q": 0.995},
]
FALLBACK_SAMPLE_PROBS = [0.005, 0.01, 0.025, 0.05, 0.10, 0.16, 0.25, 0.50, 0.75, 0.84, 0.90, 0.95, 0.975, 0.99, 0.995]
IV_TRIM_LOWER_Q = 0.10
IV_TRIM_UPPER_Q = 0.90
ENVELOPE_BLEND_MIN = 0.18
ENVELOPE_BLEND_MAX = 0.55
ENVELOPE_BLEND_BASE = 0.22
ENVELOPE_BLEND_CLIP_WEIGHT = 0.38
ENVELOPE_BLEND_STRIKE_BONUS = 0.012


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _market_price(option: dict[str, Any], model_greeks: dict[str, Any]) -> float:
    mid = _safe_float(option.get("mid"), 0.0)
    bid = _safe_float(option.get("bid"), 0.0)
    ask = _safe_float(option.get("ask"), 0.0)
    px_last = _safe_float(option.get("px_last"), 0.0)
    if mid > 0:
        return mid
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if px_last > 0:
        return px_last
    return max(_safe_float(model_greeks.get("price"), 0.0), 0.0)


def _call_equivalent_price(option: dict[str, Any], model_greeks: dict[str, Any]) -> float:
    option_type = str(option.get("put_call") or "").strip().lower()
    observed_price = _market_price(option, model_greeks)
    if option_type.startswith("c"):
        return observed_price
    spot = _safe_float(option.get("spot_price"), 0.0)
    strike = _safe_float(option.get("strike"), 0.0)
    time_years = max(_safe_float(option.get("time_to_expiry_years"), 0.0), 1e-8)
    rate = _safe_float(option.get("interpolated_rate"), 0.0)
    carry = _safe_float(option.get("carry_dividend_proxy"), 0.0)
    discounted_spot = spot * math.exp(-carry * time_years)
    discounted_strike = strike * math.exp(-rate * time_years)
    return max(observed_price + discounted_spot - discounted_strike, 0.0)


def _surface_weight(option: dict[str, Any]) -> float:
    reliability = clamp(_safe_float(option.get("reliability_weight"), 0.0), 0.0, 1.0)
    liquidity = clamp(_safe_float(option.get("liquidity_weight"), 0.0), 0.0, 1.0)
    open_interest = max(_safe_float(option.get("open_int"), 0.0), 0.0)
    volume = max(_safe_float(option.get("px_volume"), 0.0), 0.0)
    return max(0.05, 0.55 * reliability + 0.45 * liquidity) * (1.0 + math.log1p(open_interest + 0.15 * volume))


def _trim_weighted_pairs(
    pairs: list[tuple[float, float]],
    *,
    lower_q: float = IV_TRIM_LOWER_Q,
    upper_q: float = IV_TRIM_UPPER_Q,
) -> list[tuple[float, float]]:
    clean = [
        (float(value), max(float(weight), 0.0))
        for value, weight in pairs
        if weight is not None and max(float(weight), 0.0) > 0 and math.isfinite(float(value))
    ]
    if len(clean) <= 2:
        return clean
    lower_bound = weighted_quantile(clean, lower_q, default=clean[0][0])
    upper_bound = weighted_quantile(clean, upper_q, default=clean[-1][0])
    if upper_bound < lower_bound:
        lower_bound, upper_bound = upper_bound, lower_bound
    trimmed = [(value, weight) for value, weight in clean if lower_bound <= value <= upper_bound]
    return trimmed or clean


def _distance_weight(strike: float, reference: float, base_weight: float) -> float:
    if base_weight <= 0:
        return 0.0
    distance = abs(strike - reference)
    return base_weight / (1.0 + (distance / 3500.0))


def _build_iv_envelope_state(rows: list[dict[str, Any]], forward_price: float) -> dict[str, float]:
    if not rows:
        return {
            "atm_iv": 0.20,
            "downside_iv": 0.20,
            "upside_iv": 0.20,
            "smile_skew": 0.0,
            "smile_width": 0.0,
        }

    atm_candidates = sorted(rows, key=lambda row: abs(float(row.get("strike") or 0.0) - forward_price))[:5]
    atm_pairs = _trim_weighted_pairs(
        [
            (
                max(float(candidate.get("selected_iv") or 0.0), 1e-4),
                _distance_weight(
                    float(candidate.get("strike") or 0.0),
                    forward_price,
                    max(float(candidate.get("surface_weight") or 0.0), 1e-4),
                ),
            )
            for candidate in atm_candidates
            if float(candidate.get("selected_iv") or 0.0) > 0
        ]
    )
    atm_iv = max(weighted_average(atm_pairs, default=0.20), 1e-4)

    downside_rows = [row for row in rows if float(row.get("strike") or 0.0) <= forward_price]
    upside_rows = [row for row in rows if float(row.get("strike") or 0.0) >= forward_price]

    downside_pairs = _trim_weighted_pairs(
        [
            (
                max(float(row.get("selected_iv") or 0.0), 1e-4),
                _distance_weight(
                    float(row.get("strike") or 0.0),
                    forward_price,
                    max(float(row.get("surface_weight") or 0.0), 1e-4),
                ),
            )
            for row in downside_rows
            if float(row.get("selected_iv") or 0.0) > 0
        ]
    )
    upside_pairs = _trim_weighted_pairs(
        [
            (
                max(float(row.get("selected_iv") or 0.0), 1e-4),
                _distance_weight(
                    float(row.get("strike") or 0.0),
                    forward_price,
                    max(float(row.get("surface_weight") or 0.0), 1e-4),
                ),
            )
            for row in upside_rows
            if float(row.get("selected_iv") or 0.0) > 0
        ]
    )

    downside_iv = max(weighted_average(downside_pairs, default=atm_iv), 1e-4)
    upside_iv = max(weighted_average(upside_pairs, default=atm_iv), 1e-4)

    vol_floor = max(atm_iv * 0.55, 0.04)
    vol_cap = max(atm_iv * 1.85, atm_iv + 0.12)
    downside_iv = clamp(downside_iv, vol_floor, vol_cap)
    upside_iv = clamp(upside_iv, vol_floor, vol_cap)

    return {
        "atm_iv": atm_iv,
        "downside_iv": downside_iv,
        "upside_iv": upside_iv,
        "smile_skew": (downside_iv - upside_iv) / max(atm_iv, 1e-4),
        "smile_width": abs(downside_iv - upside_iv),
    }


def _smooth_monotone_call_curve(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) <= 2:
        return rows
    smoothed_values: list[float] = []
    raw = [float(row.get("call_equivalent_price") or 0.0) for row in rows]
    for index, value in enumerate(raw):
        previous_value = raw[index - 1] if index > 0 else value
        next_value = raw[index + 1] if index < len(raw) - 1 else value
        smoothed_values.append(max((0.25 * previous_value) + (0.5 * value) + (0.25 * next_value), 0.0))
    monotone: list[float] = []
    for index, value in enumerate(smoothed_values):
        if index == 0:
            monotone.append(value)
            continue
        monotone.append(min(value, monotone[index - 1]))
    return [{**row, "call_price_smoothed": monotone[index]} for index, row in enumerate(rows)]


def _density_from_call_curve(rows: list[dict[str, Any]], rate: float) -> tuple[list[tuple[float, float]], int]:
    masses: list[tuple[float, float]] = []
    clipped_count = 0
    if len(rows) < 3:
        return masses, clipped_count
    growth = math.exp(rate * max(_safe_float(rows[0].get("time_years"), 0.0), 0.0))
    for index in range(1, len(rows) - 1):
        left = rows[index - 1]
        current = rows[index]
        right = rows[index + 1]
        k0, k1, k2 = float(left["strike"]), float(current["strike"]), float(right["strike"])
        c0 = float(left.get("call_price_smoothed") or left.get("call_equivalent_price") or 0.0)
        c1 = float(current.get("call_price_smoothed") or current.get("call_equivalent_price") or 0.0)
        c2 = float(right.get("call_price_smoothed") or right.get("call_equivalent_price") or 0.0)
        h_left = max(k1 - k0, 1.0)
        h_right = max(k2 - k1, 1.0)
        slope_left = (c1 - c0) / h_left
        slope_right = (c2 - c1) / h_right
        second = growth * (slope_right - slope_left) / max((k2 - k0) / 2.0, 1.0)
        if second < 0:
            clipped_count += 1
        density = max(second, 0.0)
        width = max((k2 - k0) / 2.0, 1.0)
        mass = density * width
        if mass > 0:
            masses.append((k1, mass))
    return masses, clipped_count


def _fallback_terminal_distribution(
    rows: list[dict[str, Any]],
    forward: float,
    time_years: float,
    *,
    iv_state: dict[str, float] | None = None,
) -> list[tuple[float, float]]:
    if not rows:
        return []
    state = iv_state or _build_iv_envelope_state(rows, forward)
    atm_vol = max(float(state.get("atm_iv") or 0.20), 1e-4)
    down_vol = max(float(state.get("downside_iv") or atm_vol), 1e-4)
    up_vol = max(float(state.get("upside_iv") or atm_vol), 1e-4)
    sqrt_t = math.sqrt(max(time_years, 1e-8))
    masses: list[tuple[float, float]] = []
    edges = [0.0, *[((FALLBACK_SAMPLE_PROBS[index] + FALLBACK_SAMPLE_PROBS[index + 1]) / 2.0) for index in range(len(FALLBACK_SAMPLE_PROBS) - 1)], 1.0]
    for index, probability in enumerate(FALLBACK_SAMPLE_PROBS):
        z_value = NORMAL_DIST.inv_cdf(probability)
        sigma = down_vol if probability < 0.5 else up_vol
        terminal = forward * math.exp((-0.5 * sigma * sigma * time_years) + (z_value * sigma * sqrt_t))
        weight = max(edges[index + 1] - edges[index], 1e-6)
        masses.append((terminal, weight))
    return masses


def _expiry_weight(expiry_slice: dict[str, Any]) -> float:
    time_years = max(_safe_float(expiry_slice.get("time_years"), 0.0), 1e-8)
    liquidity = clamp(_safe_float(expiry_slice.get("avg_liquidity_weight"), 0.0), 0.05, 1.0)
    oi_total = max(_safe_float(expiry_slice.get("oi_total"), 0.0), 0.0)
    gamma_total = max(abs(_safe_float(expiry_slice.get("gamma_total"), 0.0)), 0.0)
    oi_power = Config.OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_WEIGHT_OI_POWER
    gamma_power = Config.OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_WEIGHT_GAMMA_POWER
    kappa = Config.OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_DECAY_KAPPA
    return liquidity * ((oi_total + 1.0) ** oi_power) * ((gamma_total + 1.0) ** gamma_power) * math.exp(-kappa * time_years)


def _tactical_horizon_scale(days_to_expiry_business: float, target_horizon_days: float) -> float:
    horizon = max(target_horizon_days, 1e-6)
    tenor = max(days_to_expiry_business, horizon)
    return clamp(math.sqrt(horizon / tenor), 0.0, 1.0)


def _project_distribution_to_tactical_horizon(
    distribution: list[tuple[float, float]],
    *,
    forward_price: float,
    days_to_expiry_business: float,
    target_horizon_days: float,
) -> tuple[list[tuple[float, float]], float]:
    scale = _tactical_horizon_scale(days_to_expiry_business, target_horizon_days)
    projected = [
        (forward_price + ((terminal_price - forward_price) * scale), weight)
        for terminal_price, weight in distribution
        if weight > 0
    ]
    return projected, scale


def _blend_terminal_distributions(
    primary: list[tuple[float, float]],
    envelope: list[tuple[float, float]],
    *,
    strike_count: int,
    clipped_count: int,
) -> tuple[list[tuple[float, float]], dict[str, float]]:
    if not primary:
        return envelope, {"primary_weight": 0.0, "envelope_weight": 1.0}
    if not envelope:
        return primary, {"primary_weight": 1.0, "envelope_weight": 0.0}

    clip_ratio = clipped_count / max(strike_count - 2, 1)
    envelope_weight = clamp(
        ENVELOPE_BLEND_BASE
        + (clip_ratio * ENVELOPE_BLEND_CLIP_WEIGHT)
        - (min(strike_count, 12) * ENVELOPE_BLEND_STRIKE_BONUS),
        ENVELOPE_BLEND_MIN,
        ENVELOPE_BLEND_MAX,
    )
    primary_weight = 1.0 - envelope_weight
    blended = [(price, weight * primary_weight) for price, weight in primary]
    blended.extend((price, weight * envelope_weight) for price, weight in envelope)
    return blended, {
        "primary_weight": primary_weight,
        "envelope_weight": envelope_weight,
    }


def _apply_spot_horizon_to_distribution(
    distribution: list[tuple[float, float]],
    *,
    lower_bound: float | None,
    upper_bound: float | None,
) -> list[tuple[float, float]]:
    if lower_bound is None or upper_bound is None or upper_bound <= lower_bound:
        return distribution
    return [(clamp(price, lower_bound, upper_bound), weight) for price, weight in distribution if weight > 0]


def _clamp_to_horizon(value: float, *, lower_bound: float | None, upper_bound: float | None) -> float:
    if lower_bound is None or upper_bound is None or upper_bound <= lower_bound:
        return value
    return clamp(value, lower_bound, upper_bound)


def _normalize_weights(values: list[tuple[str, float]]) -> dict[str, float]:
    total = sum(max(weight, 0.0) for _, weight in values)
    if total <= 0:
        count = max(len(values), 1)
        return {key: 1.0 / count for key, _ in values}
    return {key: max(weight, 0.0) / total for key, weight in values}


def _atm_reference_move(expiry_slices: list[dict[str, Any]]) -> float:
    pairs: list[tuple[float, float]] = []
    for item in expiry_slices:
        atm_iv = _safe_float(item.get("atm_iv"), 0.0)
        forward = max(_safe_float(item.get("forward_price"), 0.0), 0.0)
        time_years = max(_safe_float(item.get("time_years"), 0.0), 1e-8)
        weight = max(_safe_float(item.get("weight"), 0.0), 0.0)
        if atm_iv <= 0 or forward <= 0 or weight <= 0:
            continue
        pairs.append((forward * atm_iv * math.sqrt(time_years), weight))
    return weighted_average(pairs, default=0.0)


def _apply_downside_guard(
    *,
    center: float,
    lower_raw: float,
    upper_raw: float,
    level: int,
    atm_reference_move: float,
) -> dict[str, float]:
    raw_lower_distance = max(center - lower_raw, 0.0)
    raw_upper_distance = max(upper_raw - center, 0.0)
    sigma_equivalent = abs(NORMAL_DIST.inv_cdf(clamp(DEFAULT_BAND_QUANTILES[level - 1]["upper_q"], 0.5001, 0.9999)))
    ratio_cap = Config.OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_RATIO_CAP_BASE + (level - 1) * Config.OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_RATIO_CAP_STEP
    floor_distance = atm_reference_move * max(sigma_equivalent, 1.0) * Config.OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_FLOOR_MULTIPLIER
    allowed_lower_distance = max(raw_upper_distance * ratio_cap, floor_distance)
    capped_lower_distance = min(raw_lower_distance, allowed_lower_distance)
    return {
        "raw_lower_distance": raw_lower_distance,
        "raw_upper_distance": raw_upper_distance,
        "allowed_lower_distance": allowed_lower_distance,
        "capped_lower_distance": capped_lower_distance,
        "ratio_cap": ratio_cap,
        "floor_distance": floor_distance,
        "applied": capped_lower_distance < raw_lower_distance,
    }


def _deformation_factors(
    level: int,
    exposures: dict[str, Any],
    pressure: dict[str, Any],
) -> tuple[float, float, dict[str, float]]:
    curve = pressure.get("curve") or []
    gex_scale = percentile((abs(_safe_float(point.get("gex"), 0.0)) for point in curve), 0.85, default=max(abs(_safe_float(exposures.get("gex_total"), 0.0)), 1.0))
    vex_scale = percentile((abs(_safe_float(point.get("vex"), 0.0)) for point in curve), 0.85, default=max(abs(_safe_float(exposures.get("vex_total"), 0.0)), 1.0))
    cex_scale = percentile((abs(_safe_float(point.get("cex"), 0.0)) for point in curve), 0.85, default=max(abs(_safe_float(exposures.get("cex_total"), 0.0)), 1.0))

    gex_norm = math.tanh(_safe_float(exposures.get("gex_total"), 0.0) / max(gex_scale, 1e-6))
    vex_norm = math.tanh(_safe_float(exposures.get("vex_total"), 0.0) / max(vex_scale, 1e-6))
    cex_norm = math.tanh(_safe_float(exposures.get("cex_total"), 0.0) / max(cex_scale, 1e-6))

    core_sensitivity = max(0.50, 1.0 - (level - 1) * 0.08)
    wing_sensitivity = 0.75 + (level - 1) * 0.06

    compression = 1.0 - (Config.OPTIONS_MODEL_RANGE_PROJECTION_GEX_DEFORM * gex_norm * core_sensitivity)
    tilt = (
        (Config.OPTIONS_MODEL_RANGE_PROJECTION_VEX_DEFORM * vex_norm)
        + (Config.OPTIONS_MODEL_RANGE_PROJECTION_CEX_DEFORM * cex_norm)
    ) * wing_sensitivity

    up_factor = clamp(compression + tilt, 0.35, 2.35)
    down_factor = clamp(compression - tilt, 0.35, 2.35)
    return up_factor, down_factor, {
        "gex_norm": gex_norm,
        "vex_norm": vex_norm,
        "cex_norm": cex_norm,
        "core_sensitivity": core_sensitivity,
        "wing_sensitivity": wing_sensitivity,
    }


def build_range_projection(
    *,
    underlying_security: str,
    market_context: MarketContext,
    prepared_options: list[dict[str, Any]],
    option_exposures: list[dict[str, Any]],
    summary: dict[str, Any],
    dealer_inference: dict[str, Any],
    pressure: dict[str, Any],
) -> dict[str, Any]:
    if not Config.OPTIONS_MODEL_RANGE_PROJECTION_ENABLE:
        return {"enabled": False, "reason": "disabled"}
    if not option_exposures:
        return {"enabled": False, "reason": "empty_option_exposures"}

    expiry_groups: dict[str, dict[str, Any]] = {}
    density_clip_count = 0
    fallback_expiries = 0
    min_strikes = max(int(Config.OPTIONS_MODEL_RANGE_PROJECTION_MIN_STRIKES_PER_EXPIRY), 3)
    tactical_horizon_days = float(Config.OPTIONS_MODEL_RANGE_PROJECTION_TACTICAL_HORIZON_DAYS)
    spot_reference = max(_safe_float(market_context.spot_price, market_context.forward_price or 0.0), 1.0)
    strike_horizon_points = max(_safe_float(Config.OPTIONS_MODEL_RANGE_PROJECTION_STRIKE_HORIZON_POINTS, 0.0), 0.0)
    spot_horizon_low = max(spot_reference - strike_horizon_points, 0.0) if strike_horizon_points > 0 else None
    spot_horizon_high = spot_reference + strike_horizon_points if strike_horizon_points > 0 else None
    filtered_outside_horizon_count = 0

    for item in option_exposures:
        option = item.get("option") or {}
        expiry = str(option.get("expiry_date") or "").strip()
        if not expiry:
            continue
        strike = round(_safe_float(option.get("strike"), 0.0), 6)
        if (
            spot_horizon_low is not None
            and spot_horizon_high is not None
            and (strike < spot_horizon_low or strike > spot_horizon_high)
        ):
            filtered_outside_horizon_count += 1
            continue
        group = expiry_groups.setdefault(
            expiry,
            {
                "expiry_date": expiry,
                "time_years": _safe_float(option.get("time_to_expiry_years"), 0.0),
                "days_to_expiry_business": option.get("days_to_expiry_business"),
                "forward_price": _safe_float(option.get("forward_price"), market_context.forward_price or market_context.spot_price),
                "interpolated_rate": _safe_float(option.get("interpolated_rate"), 0.0),
                "rows": {},
                "oi_total": 0.0,
                "gamma_total": 0.0,
                "avg_liquidity_weight": 0.0,
                "_liquidity_pairs": [],
            },
        )
        row = group["rows"].setdefault(
            strike,
            {
                "strike": strike,
                "call_equivalent_pairs": [],
                "iv_pairs": [],
                "oi_total": 0.0,
                "gamma_abs_total": 0.0,
                "surface_weight_total": 0.0,
            },
        )
        surface_weight = _surface_weight(option)
        call_equivalent = _call_equivalent_price(option, item.get("model_greeks") or {})
        row["call_equivalent_pairs"].append((call_equivalent, surface_weight))
        row["iv_pairs"].append((max(_safe_float(option.get("selected_iv"), 0.2), 1e-4), surface_weight))
        row["oi_total"] += max(_safe_float(option.get("open_int"), 0.0), 0.0)
        row["gamma_abs_total"] += abs(_safe_float((item.get("selected_greeks") or {}).get("gamma"), 0.0)) * max(_safe_float(option.get("open_int"), 0.0), 0.0)
        row["surface_weight_total"] += surface_weight
        group["oi_total"] += max(_safe_float(option.get("open_int"), 0.0), 0.0)
        group["gamma_total"] += abs(_safe_float((item.get("selected_greeks") or {}).get("gamma"), 0.0)) * max(_safe_float(option.get("open_int"), 0.0), 0.0)
        group["_liquidity_pairs"].append((clamp(_safe_float(option.get("liquidity_weight"), 0.0), 0.0, 1.0), surface_weight))

    expiry_slices: list[dict[str, Any]] = []
    mixed_distribution: list[tuple[float, float]] = []

    for expiry, group in expiry_groups.items():
        raw_rows = []
        for strike, row in sorted(group["rows"].items()):
            call_equivalent_price = weighted_average(row["call_equivalent_pairs"], default=0.0)
            selected_iv = weighted_average(_trim_weighted_pairs(row["iv_pairs"]), default=0.2)
            raw_rows.append(
                {
                    "strike": strike,
                    "call_equivalent_price": call_equivalent_price,
                    "selected_iv": selected_iv,
                    "surface_weight": row["surface_weight_total"],
                    "oi_total": row["oi_total"],
                    "gamma_abs_total": row["gamma_abs_total"],
                    "time_years": group["time_years"],
                }
            )

        if len(raw_rows) < min_strikes:
            continue

        smoothed_rows = _smooth_monotone_call_curve(raw_rows)
        forward_price = max(
            _safe_float(group.get("forward_price"), market_context.forward_price or market_context.spot_price),
            1.0,
        )
        iv_state = _build_iv_envelope_state(smoothed_rows, forward_price)
        density_masses, local_clip_count = _density_from_call_curve(
            smoothed_rows,
            rate=_safe_float(group.get("interpolated_rate"), 0.0),
        )
        density_clip_count += local_clip_count
        source_mode = "discrete_density_blended_with_asymmetric_iv_envelope"
        envelope_distribution = _fallback_terminal_distribution(
            smoothed_rows,
            forward=forward_price,
            time_years=max(_safe_float(group.get("time_years"), 0.0), 1e-8),
            iv_state=iv_state,
        )
        blend_metrics = {"primary_weight": 0.0, "envelope_weight": 1.0}
        working_distribution = density_masses
        if not density_masses:
            source_mode = "fallback_lognormal_proxy"
            fallback_expiries += 1
            working_distribution = envelope_distribution
        else:
            working_distribution, blend_metrics = _blend_terminal_distributions(
                density_masses,
                envelope_distribution,
                strike_count=len(smoothed_rows),
                clipped_count=local_clip_count,
            )

        days_to_expiry_business = max(
            _safe_float(group.get("days_to_expiry_business"), 0.0),
            max(_safe_float(group.get("time_years"), 0.0) * 252.0, 1.0),
        )
        tactical_distribution, tactical_horizon_scale = _project_distribution_to_tactical_horizon(
            working_distribution,
            forward_price=forward_price,
            days_to_expiry_business=days_to_expiry_business,
            target_horizon_days=tactical_horizon_days,
        )
        tactical_distribution = _apply_spot_horizon_to_distribution(
            tactical_distribution,
            lower_bound=spot_horizon_low,
            upper_bound=spot_horizon_high,
        )

        avg_liquidity = weighted_average(group["_liquidity_pairs"], default=0.0)
        atm_iv = iv_state.get("atm_iv", 0.0)
        expiry_slice = {
            "expiry_date": expiry,
            "days_to_expiry_business": group.get("days_to_expiry_business"),
            "time_years": group.get("time_years"),
            "forward_price": group.get("forward_price"),
            "oi_total": group.get("oi_total"),
            "gamma_total": group.get("gamma_total"),
            "avg_liquidity_weight": avg_liquidity,
            "distribution_source": source_mode,
            "strike_count": len(smoothed_rows),
            "distribution_points": len(working_distribution),
            "density_points": len(density_masses),
            "envelope_points": len(envelope_distribution),
            "distribution": tactical_distribution,
            "raw_distribution": working_distribution,
            "tactical_horizon_scale": tactical_horizon_scale,
            "tactical_horizon_days": tactical_horizon_days,
            "atm_iv": atm_iv,
            "downside_iv": iv_state.get("downside_iv", atm_iv),
            "upside_iv": iv_state.get("upside_iv", atm_iv),
            "smile_skew": iv_state.get("smile_skew", 0.0),
            "smile_width": iv_state.get("smile_width", 0.0),
            "density_blend_metrics": blend_metrics,
            "rnd_median": weighted_quantile(tactical_distribution, 0.50, default=forward_price),
            "lower_16": weighted_quantile(tactical_distribution, 0.16, default=forward_price),
            "upper_84": weighted_quantile(tactical_distribution, 0.84, default=forward_price),
            "raw_rnd_median": weighted_quantile(working_distribution, 0.50, default=forward_price),
            "raw_lower_16": weighted_quantile(working_distribution, 0.16, default=forward_price),
            "raw_upper_84": weighted_quantile(working_distribution, 0.84, default=forward_price),
        }
        expiry_slice["weight_raw"] = _expiry_weight(expiry_slice)
        expiry_slices.append(expiry_slice)

    expiry_slices = sorted(expiry_slices, key=lambda item: float(item.get("weight_raw") or 0.0), reverse=True)[: max(int(Config.OPTIONS_MODEL_RANGE_PROJECTION_MAX_EXPIRIES), 1)]
    if not expiry_slices:
        return {"enabled": False, "reason": "no_eligible_expiry_surface"}

    expiry_weight_map = _normalize_weights([(item["expiry_date"], float(item.get("weight_raw") or 0.0)) for item in expiry_slices])
    for expiry_slice in expiry_slices:
        expiry_slice["weight"] = expiry_weight_map.get(expiry_slice["expiry_date"], 0.0)
        for terminal_price, mass in expiry_slice["distribution"]:
            mixed_distribution.append((terminal_price, mass * expiry_slice["weight"]))

    mixed_distribution = [(price, weight) for price, weight in mixed_distribution if weight > 0]
    if not mixed_distribution:
        return {"enabled": False, "reason": "empty_mixed_distribution"}

    atm_reference_move = _atm_reference_move(expiry_slices)

    forward_reference = max(_safe_float(market_context.forward_price, market_context.spot_price), 1.0)
    dealer_reference = _safe_float((dealer_inference.get("comparison") or {}).get("reference_dealer_inference_value"), 0.0)
    if dealer_reference <= 0:
        dealer_reference = _safe_float(summary.get("zero_pressure"), forward_reference)
    rnd_center = weighted_quantile(mixed_distribution, 0.50, default=forward_reference)

    center_weight_forward = Config.OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_FORWARD
    center_weight_dealer = Config.OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_DEALER
    center_weight_rnd = Config.OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_RND
    center_weights = _normalize_weights(
        [
            ("forward", center_weight_forward),
            ("dealer", center_weight_dealer),
            ("rnd", center_weight_rnd),
        ]
    )

    hybrid_center = (
        forward_reference * center_weights["forward"]
        + dealer_reference * center_weights["dealer"]
        + rnd_center * center_weights["rnd"]
    )
    hybrid_center = _clamp_to_horizon(
        hybrid_center,
        lower_bound=spot_horizon_low,
        upper_bound=spot_horizon_high,
    )
    rnd_center = _clamp_to_horizon(
        rnd_center,
        lower_bound=spot_horizon_low,
        upper_bound=spot_horizon_high,
    )
    dealer_reference = _clamp_to_horizon(
        dealer_reference,
        lower_bound=spot_horizon_low,
        upper_bound=spot_horizon_high,
    )
    forward_reference = _clamp_to_horizon(
        forward_reference,
        lower_bound=spot_horizon_low,
        upper_bound=spot_horizon_high,
    )

    basis_points = _safe_float(market_context.future_basis_points, 0.0)
    band_rows: list[dict[str, Any]] = []

    exposure_totals = {
        "gex_total": _safe_float(summary.get("gex_total"), 0.0),
        "vex_total": _safe_float(summary.get("vex_total"), 0.0),
        "cex_total": _safe_float(summary.get("cex_total"), 0.0),
    }

    for band in DEFAULT_BAND_QUANTILES:
        lower_raw = weighted_quantile(mixed_distribution, band["lower_q"], default=hybrid_center)
        upper_raw = weighted_quantile(mixed_distribution, band["upper_q"], default=hybrid_center)
        downside_guard = _apply_downside_guard(
            center=hybrid_center,
            lower_raw=lower_raw,
            upper_raw=upper_raw,
            level=band["level"],
            atm_reference_move=atm_reference_move,
        )
        guarded_lower_raw = hybrid_center - downside_guard["capped_lower_distance"]
        up_factor, down_factor, deformation_metrics = _deformation_factors(band["level"], exposure_totals, pressure)
        lower_adjusted = hybrid_center + down_factor * (guarded_lower_raw - hybrid_center)
        upper_adjusted = hybrid_center + up_factor * (upper_raw - hybrid_center)
        lower_adjusted = min(
            hybrid_center,
            _clamp_to_horizon(lower_adjusted, lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
        )
        upper_adjusted = max(
            hybrid_center,
            _clamp_to_horizon(upper_adjusted, lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
        )
        lower_raw = _clamp_to_horizon(lower_raw, lower_bound=spot_horizon_low, upper_bound=spot_horizon_high)
        guarded_lower_raw = _clamp_to_horizon(guarded_lower_raw, lower_bound=spot_horizon_low, upper_bound=spot_horizon_high)
        upper_raw = _clamp_to_horizon(upper_raw, lower_bound=spot_horizon_low, upper_bound=spot_horizon_high)
        lower_future = lower_adjusted + basis_points
        upper_future = upper_adjusted + basis_points
        band_rows.append(
            {
                "level": band["level"],
                "label": band["label"],
                "lower_quantile": band["lower_q"],
                "upper_quantile": band["upper_q"],
                "raw_lower_spot": lower_raw,
                "guarded_lower_spot": guarded_lower_raw,
                "raw_upper_spot": upper_raw,
                "adjusted_lower_spot": lower_adjusted,
                "adjusted_upper_spot": upper_adjusted,
                "adjusted_lower_future": lower_future,
                "adjusted_upper_future": upper_future,
                "lower_distance_spot": lower_adjusted - hybrid_center,
                "upper_distance_spot": upper_adjusted - hybrid_center,
                "up_deformation_factor": up_factor,
                "down_deformation_factor": down_factor,
                "downside_guard": downside_guard,
                "deformation_metrics": deformation_metrics,
            }
        )

    return {
        "enabled": True,
        "mode": "surface_rnd_proxy_with_dealer_deformation",
        "methodology": (
            "Proxy institucional em 3 camadas: smile/surface limpa por vencimento, mistura de distribuições implícitas "
            "por quantis a partir de densidade discreta de calls suavizados com fallback lognormal assimétrico, e "
            "deformação final pelas exposições de dealer (GEX/VEX/CEX)."
        ),
        "underlying_security": underlying_security,
        "center": {
            "hybrid_center_spot": hybrid_center,
            "hybrid_center_future": hybrid_center + basis_points,
            "forward_observed": forward_reference,
            "dealer_reference": dealer_reference,
            "rnd_center": rnd_center,
            "weights": center_weights,
        },
        "basis": {
            "future_basis_points": basis_points,
            "future_basis_pct": _safe_float(market_context.future_basis_pct, 0.0),
        },
        "expiry_weights": [
            {
                "expiry_date": item["expiry_date"],
                "days_to_expiry_business": item["days_to_expiry_business"],
                "time_years": item["time_years"],
                "weight": item["weight"],
                "distribution_source": item["distribution_source"],
                "strike_count": item["strike_count"],
                "atm_iv": item["atm_iv"],
                "downside_iv": item["downside_iv"],
                "upside_iv": item["upside_iv"],
                "smile_skew": item["smile_skew"],
                "smile_width": item["smile_width"],
                "oi_total": item["oi_total"],
                "gamma_total": item["gamma_total"],
                "tactical_horizon_scale": item["tactical_horizon_scale"],
                "tactical_horizon_days": item["tactical_horizon_days"],
                "density_blend_metrics": item["density_blend_metrics"],
                "rnd_median": item["rnd_median"],
                "lower_16": item["lower_16"],
                "upper_84": item["upper_84"],
                "raw_rnd_median": item["raw_rnd_median"],
                "raw_lower_16": item["raw_lower_16"],
                "raw_upper_84": item["raw_upper_84"],
            }
            for item in expiry_slices
        ],
        "distribution_quantiles_spot": {
            "q005": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.005, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q010": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.01, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q025": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.025, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q050": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.05, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q100": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.10, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q160": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.16, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q500": rnd_center,
            "q840": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.84, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q900": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.90, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q950": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.95, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q975": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.975, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q990": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.99, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
            "q995": _clamp_to_horizon(weighted_quantile(mixed_distribution, 0.995, default=hybrid_center), lower_bound=spot_horizon_low, upper_bound=spot_horizon_high),
        },
        "bands": band_rows,
        "ladder": {
            "lower": [
                {
                    "level": item["level"],
                    "label": item["label"],
                    "spot": item["adjusted_lower_spot"],
                    "future": item["adjusted_lower_future"],
                }
                for item in band_rows
            ],
            "upper": [
                {
                    "level": item["level"],
                    "label": item["label"],
                    "spot": item["adjusted_upper_spot"],
                    "future": item["adjusted_upper_future"],
                }
                for item in band_rows
            ],
        },
        "diagnostics": {
            "expiry_count_used": len(expiry_slices),
            "distribution_points": len(mixed_distribution),
            "density_clip_count": density_clip_count,
            "fallback_expiry_count": fallback_expiries,
            "atm_reference_move_spot": atm_reference_move,
            "tactical_horizon_days": tactical_horizon_days,
            "strike_horizon_points": strike_horizon_points,
            "spot_horizon_low": spot_horizon_low,
            "spot_horizon_high": spot_horizon_high,
            "filtered_options_outside_horizon": filtered_outside_horizon_count,
            "prepared_option_count": len(prepared_options),
        },
    }
