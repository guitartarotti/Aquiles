from __future__ import annotations

import math
from typing import Any

import numpy as np

from .fair_value_markov_contracts import STUDENT_T_NU


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)


def _round_float(value: Any, digits: int = 6) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return round(parsed, digits)


def _median(values: list[float]) -> float:
    clean = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not clean:
        return 0.0
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def _mad(values: list[float], center: float | None = None) -> float:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return 1.0
    resolved_center = _median(clean) if center is None else float(center)
    deviations = [abs(value - resolved_center) for value in clean]
    return max(_median(deviations) * 1.4826, 1e-9)


def _weighted_average(values: np.ndarray, weights: np.ndarray, default: float = 0.0) -> float:
    weights = np.asarray(weights, dtype=float)
    values = np.asarray(values, dtype=float)
    total = float(np.sum(weights))
    if total <= 1e-12:
        return default
    return float(np.sum(values * weights) / total)


def _weighted_sigma(values: np.ndarray, weights: np.ndarray, center: float | None = None) -> float:
    weights = np.asarray(weights, dtype=float)
    values = np.asarray(values, dtype=float)
    total = float(np.sum(weights))
    if total <= 1e-12:
        return max(float(np.std(values)) if values.size else 0.0, 1e-6)
    resolved_center = _weighted_average(values, weights) if center is None else float(center)
    variance = float(np.sum(weights * ((values - resolved_center) ** 2)) / total)
    return max(math.sqrt(max(variance, 0.0)), 1e-6)


def _logsumexp(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    max_value = float(np.max(values))
    if not math.isfinite(max_value):
        return max_value
    return max_value + math.log(float(np.sum(np.exp(values - max_value))))


def _student_t_logpdf(value: float, mean: float, scale: float, nu: float = STUDENT_T_NU) -> float:
    resolved_scale = max(float(scale), 1e-6)
    z = (float(value) - float(mean)) / resolved_scale
    return (
        math.lgamma((nu + 1.0) / 2.0)
        - math.lgamma(nu / 2.0)
        - (0.5 * math.log(nu * math.pi))
        - math.log(resolved_scale)
        - (((nu + 1.0) / 2.0) * math.log1p((z * z) / nu))
    )


def _normalize_probabilities(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    values = np.where(np.isfinite(values), values, 0.0)
    total = float(np.sum(values))
    if total <= 1e-12:
        return np.full(values.shape, 1.0 / max(values.size, 1))
    return values / total


def _fisher_z(value: float) -> float:
    clipped = _clip(float(value), -0.98, 0.98)
    return float(np.arctanh(clipped))


def _rolling_corr(left: list[float], right: list[float], window: int) -> float:
    resolved_window = max(int(window or 1), 3)
    if len(left) < resolved_window or len(right) < resolved_window:
        return 0.0
    left_window = np.asarray(left[-resolved_window:], dtype=float)
    right_window = np.asarray(right[-resolved_window:], dtype=float)
    if left_window.size < 3 or right_window.size < 3:
        return 0.0
    if float(np.std(left_window)) <= 1e-9 or float(np.std(right_window)) <= 1e-9:
        return 0.0
    corr = np.corrcoef(left_window, right_window)[0, 1]
    if not math.isfinite(float(corr)):
        return 0.0
    return _clip(float(corr), -0.995, 0.995)


def _delta_from_history(values: list[float], index: int, steps: int) -> float:
    resolved_steps = max(int(steps or 1), 1)
    previous_index = max(index - resolved_steps, 0)
    return float(values[index] - values[previous_index])

