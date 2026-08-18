from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import median
from typing import Any


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def _asset_direction_multiplier(expected_direction: str, fallback_score: float = 0.0) -> float:
    key = str(expected_direction or "").strip().lower()
    if key in {"positive_when_rising", "positive_when_falling_negative"}:
        return 1.0
    if key in {"negative_when_rising", "positive_when_falling", "negative_when_steepening"}:
        return -1.0
    if key in {"positive_when_dovish", "positive_when_falling"}:
        return -1.0
    if key in {"negative_when_falling"}:
        return 1.0
    return 1.0 if fallback_score >= 0 else -1.0


def _signed_metric(row: dict[str, Any], direction_multiplier: float) -> float:
    raw_candidates = [
        _safe_float(row.get("daily_change_pct")),
        _safe_float(row.get("feature_value")),
        _safe_float(row.get("raw_value")),
        _safe_float(row.get("feature_zscore")),
    ]
    for value in raw_candidates:
        if value is None:
            continue
        scale = 1.0
        if abs(value) > 30:
            scale = 0.01
        return direction_multiplier * value * scale
    return 0.0


def _robust_sigma(values: list[float]) -> float:
    clean = [float(value) for value in values if math.isfinite(value)]
    if len(clean) < 3:
        return max(abs(clean[0]) if clean else 0.05, 0.05)
    med = median(clean)
    mad = median([abs(value - med) for value in clean])
    sigma = mad * 1.4826
    if sigma <= 1e-9:
        sigma = median([abs(value) for value in clean]) or 0.05
    return max(float(sigma), 0.05)


def _ewma(values: list[float], alpha: float = 0.35) -> float:
    if not values:
        return 0.0
    acc = values[0]
    for value in values[1:]:
        acc = (alpha * value) + ((1.0 - alpha) * acc)
    return acc


def _persistence(values: list[float]) -> float:
    clean = [value for value in values if abs(value) > 1e-9]
    if not clean:
        return 0.0
    target_sign = 1 if clean[-1] > 0 else -1
    aligned = [value for value in clean if (1 if value > 0 else -1) == target_sign]
    return len(aligned) / max(len(clean), 1)


def _freshness(timestamp: Any, max_minutes: float = 30.0) -> tuple[float, bool]:
    parsed = _parse_iso(timestamp)
    if parsed is None:
        return 0.15, True
    minutes = max((datetime.now(timezone.utc) - parsed).total_seconds() / 60.0, 0.0)
    freshness = _clamp(1.0 - (minutes / max_minutes), 0.05, 1.0)
    return freshness, minutes > max_minutes


def _classify_asset_regime(
    *,
    z_score: float,
    persistence: float,
    volatility: float,
    stale: bool,
    divergent: bool,
) -> str:
    if stale:
        return "stale"
    if divergent:
        return "divergent"
    if z_score >= 2.0 and volatility > 0.6:
        return "shock_up"
    if z_score <= -2.0 and volatility > 0.6:
        return "shock_down"
    if z_score >= 0.8 and persistence >= 0.55:
        return "bullish_pressure"
    if z_score <= -0.8 and persistence >= 0.55:
        return "bearish_pressure"
    return "neutral"


def build_asset_regimes(
    *,
    current_rows: list[dict[str, Any]],
    history_by_factor: dict[str, list[dict[str, Any]]],
    factor_definitions: dict[str, dict[str, Any]],
    xb1_signed_return: float,
) -> dict[str, Any]:
    rows_by_factor = {
        str(item.get("factor") or "").strip(): dict(item or {})
        for item in (current_rows or [])
        if str(item.get("factor") or "").strip()
    }
    asset_rows: list[dict[str, Any]] = []
    asset_map: dict[str, dict[str, Any]] = {}

    for factor, row in rows_by_factor.items():
        definition = dict(factor_definitions.get(factor) or {})
        fallback_score = _safe_float(row.get("feature_zscore"), 0.0) or 0.0
        direction_multiplier = _asset_direction_multiplier(
            str(definition.get("expected_direction_to_ibov") or ""),
            fallback_score=fallback_score,
        )
        historical_rows = [dict(item or {}) for item in (history_by_factor.get(factor) or [])]
        historical_series = [
            _signed_metric(item, direction_multiplier)
            for item in historical_rows
        ]
        current_value = _signed_metric(row, direction_multiplier)
        series = [value for value in historical_series if math.isfinite(value)]
        if not series:
            series = [current_value]
        sigma = _robust_sigma(series)
        z_score = current_value / max(sigma, 0.05)
        momentum = _ewma(series[-12:])
        previous_momentum = _ewma(series[-13:-1] or series[-12:])
        acceleration = momentum - previous_momentum
        volatility = _ewma([abs(value) for value in series[-20:]])
        persistence = _persistence(series[-20:])
        freshness_score, stale = _freshness(row.get("timestamp"))
        shock_score = abs(z_score)
        data_quality = _clamp((0.55 * freshness_score) + (0.45 * (1.0 if sigma > 0.05 else 0.45)), 0.05, 1.0)
        divergent = abs(z_score) > 0.7 and (math.copysign(1.0, z_score) != math.copysign(1.0, xb1_signed_return)) and abs(xb1_signed_return) > 0.15
        asset_regime = _classify_asset_regime(
            z_score=z_score,
            persistence=persistence,
            volatility=volatility,
            stale=stale,
            divergent=divergent,
        )
        snapshot = {
            "timestamp": row.get("timestamp"),
            "ticker": factor,
            "label": row.get("label") or definition.get("label") or factor,
            "economic_name": definition.get("economic_name") or row.get("label") or factor,
            "signed_return": round(current_value, 6),
            "z_score": round(z_score, 6),
            "momentum": round(momentum, 6),
            "acceleration": round(acceleration, 6),
            "volatility": round(volatility, 6),
            "persistence": round(persistence, 6),
            "shock_score": round(shock_score, 6),
            "freshness": round(freshness_score, 6),
            "data_quality": round(data_quality, 6),
            "asset_regime": asset_regime,
            "confidence": round(_clamp((0.42 * freshness_score) + (0.28 * min(shock_score / 2.0, 1.0)) + (0.30 * persistence), 0.05, 0.98), 6),
            "direction_multiplier": direction_multiplier,
            "expected_direction_to_ibov": definition.get("expected_direction_to_ibov"),
            "stale": stale,
            "divergent": divergent,
        }
        asset_rows.append(snapshot)
        asset_map[factor] = snapshot

    asset_rows.sort(key=lambda item: abs(float(item.get("z_score") or 0.0)), reverse=True)
    return {
        "asset_regime_map": asset_map,
        "asset_regime_snapshots": asset_rows,
    }
