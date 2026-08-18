from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

WINDOW_SPECS = {
    "30m": timedelta(minutes=30),
    "2h": timedelta(hours=2),
    "1d": timedelta(days=1),
    "5d": timedelta(days=5),
    "20d": timedelta(days=20),
}

LAG_MINUTES = [-15, -5, -2, 0, 2, 5, 15]


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


def _series_from_observations(
    observations: list[dict[str, Any]],
    leg_path: tuple[str, str],
) -> tuple[pd.Series, pd.Series]:
    timestamps: list[datetime] = []
    xb1_values: list[float] = []
    leg_values: list[float] = []
    bucket_name, metric_key = leg_path
    for item in observations:
        ts = _parse_iso(item.get("timestamp"))
        if ts is None:
            continue
        xb1_value = _safe_float(item.get("xb1_return"), default=float("nan"))
        if not math.isfinite(xb1_value):
            continue
        leg_bucket = ((item.get(bucket_name) or {}).get(item.get("leg_key")) or {})
        leg_value = _safe_float(leg_bucket.get(metric_key), default=float("nan"))
        if not math.isfinite(leg_value):
            continue
        timestamps.append(ts)
        xb1_values.append(xb1_value)
        leg_values.append(leg_value)
    if not timestamps:
        empty = pd.Series(dtype="float64")
        return empty, empty
    index = pd.to_datetime(timestamps, utc=True)
    return pd.Series(xb1_values, index=index), pd.Series(leg_values, index=index)


def _distance_correlation(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or len(y) < 3:
        return 0.0
    x = x.reshape(-1, 1)
    y = y.reshape(-1, 1)
    a = np.abs(x - x.T)
    b = np.abs(y - y.T)
    A = a - a.mean(axis=0)[None, :] - a.mean(axis=1)[:, None] + a.mean()
    B = b - b.mean(axis=0)[None, :] - b.mean(axis=1)[:, None] + b.mean()
    dcov = np.sqrt(max(np.mean(A * B), 0.0))
    dvar_x = np.sqrt(max(np.mean(A * A), 0.0))
    dvar_y = np.sqrt(max(np.mean(B * B), 0.0))
    if dvar_x <= 1e-12 or dvar_y <= 1e-12:
        return 0.0
    return float(_clamp(dcov / math.sqrt(dvar_x * dvar_y), 0.0, 1.0))


def _tail_dependence(x: np.ndarray, y: np.ndarray, threshold: float = 1.5) -> float:
    if len(x) < 8 or len(y) < 8:
        return 0.0
    x_std = np.std(x)
    y_std = np.std(y)
    if x_std <= 1e-12 or y_std <= 1e-12:
        return 0.0
    x_z = (x - np.mean(x)) / x_std
    y_z = (y - np.mean(y)) / y_std
    mask_x = np.abs(x_z) >= threshold
    if not mask_x.any():
        return 0.0
    conditional = np.abs(y_z[mask_x]) >= threshold
    return float(_clamp(np.mean(conditional), 0.0, 1.0))


def _quantile_beta(x: np.ndarray, y: np.ndarray, quantile: float = 0.8) -> float:
    if len(x) < 8 or len(y) < 8:
        return 0.0
    threshold = np.quantile(np.abs(x), quantile)
    mask = np.abs(x) >= threshold
    if mask.sum() < 3:
        return 0.0
    denominator = np.var(x[mask])
    if denominator <= 1e-12:
        return 0.0
    covariance = np.cov(x[mask], y[mask])[0, 1]
    return float(covariance / denominator)


def _lead_lag_score(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    if len(x) < 6 or len(y) < 6:
        return 0.0, 0
    best_score = 0.0
    best_lag = 0
    for lag in LAG_MINUTES:
        shifted = x.copy()
        if lag:
            shifted.index = shifted.index + pd.to_timedelta(lag, unit="m")
        merged = pd.concat([shifted.rename("leg"), y.rename("xb1")], axis=1).dropna()
        if len(merged) < 6:
            continue
        corr = abs(float(merged["leg"].corr(merged["xb1"], method="pearson") or 0.0))
        sample_score = min(len(merged) / 24.0, 1.0)
        score = corr * sample_score
        if score >= best_score:
            best_score = score
            best_lag = lag
    return float(_clamp(best_score, 0.0, 1.0)), best_lag


def _window_metrics(x: pd.Series, y: pd.Series, window_name: str, delta: timedelta) -> dict[str, Any]:
    if x.empty or y.empty:
        return {"window": window_name, "sample_size": 0}
    latest_ts = min(x.index.max(), y.index.max())
    cutoff = latest_ts - delta
    merged = pd.concat([x.rename("leg"), y.rename("xb1")], axis=1).dropna()
    merged = merged.loc[merged.index >= cutoff]
    sample_size = len(merged)
    if sample_size < 4:
        return {"window": window_name, "sample_size": sample_size}

    leg = merged["leg"].astype(float)
    xb1 = merged["xb1"].astype(float)
    if leg.std(ddof=0) <= 1e-12 or xb1.std(ddof=0) <= 1e-12:
        lag_score, best_lag = _lead_lag_score(leg, xb1)
        sample_size_score = _clamp(sample_size / 40.0, 0.1, 1.0)
        return {
            "window": window_name,
            "sample_size": sample_size,
            "pearson_corr": 0.0,
            "spearman_corr": 0.0,
            "kendall_tau": 0.0,
            "distance_corr": 0.0,
            "tail_dependence": 0.0,
            "quantile_beta": 0.0,
            "lead_lag_score": lag_score,
            "best_lag_minutes": best_lag,
            "linear_score": 0.0,
            "monotonic_score": 0.0,
            "nonlinear_dependence_score": 0.0,
            "dependence_score": lag_score * 0.10,
            "dependence_confidence": _clamp(sample_size_score * 0.15, 0.02, 0.35),
        }
    pearson = float(leg.corr(xb1, method="pearson") or 0.0)
    spearman = float(leg.corr(xb1, method="spearman") or 0.0)
    kendall = float(leg.corr(xb1, method="kendall") or 0.0)
    dcor = _distance_correlation(leg.to_numpy(), xb1.to_numpy())
    tail = _tail_dependence(leg.to_numpy(), xb1.to_numpy())
    qbeta = _quantile_beta(leg.to_numpy(), xb1.to_numpy())
    lag_score, best_lag = _lead_lag_score(leg, xb1)
    linear_score = abs(pearson)
    monotonic_score = (0.6 * abs(spearman)) + (0.4 * abs(kendall))
    dependence_score = _clamp(
        (0.30 * linear_score)
        + (0.20 * monotonic_score)
        + (0.25 * dcor)
        + (0.15 * tail)
        + (0.10 * lag_score),
        0.0,
        1.0,
    )
    sample_size_score = _clamp(sample_size / 40.0, 0.1, 1.0)
    stability_score = _clamp(1.0 - abs(abs(pearson) - abs(spearman)), 0.1, 1.0)
    confidence = _clamp(dependence_score * stability_score * sample_size_score, 0.02, 0.98)
    return {
        "window": window_name,
        "sample_size": sample_size,
        "pearson_corr": pearson,
        "spearman_corr": spearman,
        "kendall_tau": kendall,
        "distance_corr": dcor,
        "tail_dependence": tail,
        "quantile_beta": qbeta,
        "lead_lag_score": lag_score,
        "best_lag_minutes": best_lag,
        "linear_score": linear_score,
        "monotonic_score": monotonic_score,
        "nonlinear_dependence_score": dcor,
        "dependence_score": dependence_score,
        "dependence_confidence": confidence,
    }


def build_nonlinear_dependence(
    *,
    observations: list[dict[str, Any]],
    leg_key: str,
    leg_type: str,
) -> dict[str, Any]:
    bucket_name = "core_legs" if leg_type == "core" else "shadow_legs"
    metric_key = "contribution_points" if leg_type == "core" else "quality_impact"
    enriched_observations = []
    for item in observations:
        enriched = dict(item)
        enriched["leg_key"] = leg_key
        enriched_observations.append(enriched)
    xb1_series, leg_series = _series_from_observations(enriched_observations, (bucket_name, metric_key))
    windows = {
        window_name: _window_metrics(leg_series, xb1_series, window_name, delta)
        for window_name, delta in WINDOW_SPECS.items()
    }
    weighted_metrics = [item for item in windows.values() if int(item.get("sample_size") or 0) >= 4]
    if not weighted_metrics:
        return {
            "windows": windows,
            "pearson_corr": 0.0,
            "spearman_corr": 0.0,
            "kendall_tau": 0.0,
            "distance_corr": 0.0,
            "tail_dependence": 0.0,
            "quantile_beta": 0.0,
            "best_lag_minutes": 0,
            "lead_lag_score": 0.0,
            "nonlinear_dependence_score": 0.0,
            "dependence_confidence": 0.05,
        }

    total_weight = 0.0
    aggregate = {
        "pearson_corr": 0.0,
        "spearman_corr": 0.0,
        "kendall_tau": 0.0,
        "distance_corr": 0.0,
        "tail_dependence": 0.0,
        "quantile_beta": 0.0,
        "lead_lag_score": 0.0,
        "nonlinear_dependence_score": 0.0,
        "dependence_confidence": 0.0,
    }
    best_lag_minutes = 0
    best_lag_score = -1.0
    for metric in weighted_metrics:
        weight = max(float(metric.get("dependence_confidence") or 0.0), 0.05)
        total_weight += weight
        for key in aggregate.keys():
            aggregate[key] += weight * float(metric.get(key) or 0.0)
        if float(metric.get("lead_lag_score") or 0.0) >= best_lag_score:
            best_lag_score = float(metric.get("lead_lag_score") or 0.0)
            best_lag_minutes = int(metric.get("best_lag_minutes") or 0)
    for key in aggregate.keys():
        aggregate[key] = aggregate[key] / max(total_weight, 1e-9)
    aggregate["best_lag_minutes"] = best_lag_minutes
    aggregate["windows"] = windows
    return aggregate
