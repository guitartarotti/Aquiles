from __future__ import annotations

import math
from typing import Any


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _minutes_from_hhmm(value: str, fallback: int) -> int:
    try:
        hour, minute = str(value or "").strip().split(":", 1)
        return max(0, min((int(hour) * 60) + int(minute), 24 * 60 - 1))
    except Exception:
        return fallback


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float | None:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _median(values: list[float]) -> float | None:
    clean = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2.0


def _sign(value: float | None, threshold: float = 1e-9) -> int:
    parsed = _safe_float(value, 0.0) or 0.0
    if parsed > threshold:
        return 1
    if parsed < -threshold:
        return -1
    return 0


def _sentiment_regime(score: float) -> str:
    if score >= 65.0:
        return "Bull regime"
    if score >= 28.0:
        return "Bull impulse"
    if score >= 10.0:
        return "Bull watch"
    if score <= -65.0:
        return "Bear regime"
    if score <= -28.0:
        return "Bear impulse"
    if score <= -10.0:
        return "Bear watch"
    return "Transition"


def _bias_label(score: float, active_bias: int) -> str:
    if active_bias > 0:
        if score >= 62.0:
            return "Long edge"
        if score >= 30.0:
            return "Long bias"
        return "Long fading"
    if active_bias < 0:
        if score <= -62.0:
            return "Short edge"
        if score <= -30.0:
            return "Short bias"
        return "Short fading"
    if score >= 22.0:
        return "Long watch"
    if score <= -22.0:
        return "Short watch"
    return "Neutral"


def _rpc_regime(score: float, slope: float, acceleration: float) -> str:
    if score <= -58.0 and slope < -4.0:
        return "Stress impulse"
    if score <= -34.0:
        return "Risk-off pressure"
    if score >= 58.0 and slope > 4.0:
        return "Risk-on impulse"
    if score >= 34.0:
        return "Risk-on relief"
    if slope < -12.0 and acceleration < 0.0:
        return "Pressure building"
    if slope > 12.0 and acceleration > 0.0:
        return "Pressure fading"
    return "Neutral"


def _pearson_corr(left: list[float], right: list[float]) -> float | None:
    pairs = [
        (float(a), float(b))
        for a, b in zip(left, right)
        if math.isfinite(float(a)) and math.isfinite(float(b))
    ]
    if len(pairs) < 4:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    var_x = sum((value - mean_x) ** 2 for value in xs)
    var_y = sum((value - mean_y) ** 2 for value in ys)
    if var_x <= 1e-18 or var_y <= 1e-18:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    return cov / math.sqrt(var_x * var_y)
