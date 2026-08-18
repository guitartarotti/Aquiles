from __future__ import annotations

import math
from typing import Any, Iterable

SQRT_2 = math.sqrt(2.0)
SQRT_2PI = math.sqrt(2.0 * math.pi)


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / SQRT_2))


def normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / SQRT_2PI


def normalize_rate(rate: float | None) -> float | None:
    if rate is None:
        return None
    if abs(rate) > 1.0:
        return rate / 100.0
    return rate


def normalize_vol(volatility: float | None) -> float | None:
    if volatility is None:
        return None
    if volatility > 3.0:
        return volatility / 100.0
    if volatility < 0:
        return None
    return volatility


def linear_interpolate(x: float, points: list[tuple[float, float]]) -> float:
    if not points:
        raise ValueError("Interpolation points are required")
    if len(points) == 1:
        return points[0][1]

    ordered = sorted(points, key=lambda item: item[0])
    if x <= ordered[0][0]:
        return ordered[0][1]
    if x >= ordered[-1][0]:
        return ordered[-1][1]

    for left, right in zip(ordered, ordered[1:]):
        x0, y0 = left
        x1, y1 = right
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            weight = (x - x0) / (x1 - x0)
            return y0 + weight * (y1 - y0)

    return ordered[-1][1]


def percentile(values: Iterable[float], quantile: float, default: float = 0.0) -> float:
    data = sorted(float(value) for value in values)
    if not data:
        return default
    q = clamp(float(quantile), 0.0, 1.0)
    if len(data) == 1:
        return data[0]
    position = q * (len(data) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return data[lower]
    weight = position - lower
    return data[lower] + weight * (data[upper] - data[lower])


def weighted_average(pairs: Iterable[tuple[float, float]], default: float = 0.0) -> float:
    total_weight = 0.0
    total_value = 0.0
    for value, weight in pairs:
        total_value += value * weight
        total_weight += weight
    if total_weight <= 0:
        return default
    return total_value / total_weight


def weighted_quantile(
    pairs: Iterable[tuple[float, float]],
    quantile: float,
    default: float = 0.0,
) -> float:
    ordered = sorted(
        (float(value), max(float(weight), 0.0))
        for value, weight in pairs
        if weight is not None and float(weight) > 0
    )
    if not ordered:
        return default
    target = clamp(float(quantile), 0.0, 1.0)
    total_weight = sum(weight for _, weight in ordered)
    if total_weight <= 0:
        return default
    cumulative = 0.0
    threshold = total_weight * target
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def argmax_abs(values: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not values:
        return None
    return max(values, key=lambda item: abs(item[1]))
