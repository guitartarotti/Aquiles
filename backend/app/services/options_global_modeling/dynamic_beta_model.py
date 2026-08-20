from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import pstdev
from typing import Any

from .types import GlobalTriangulationConfig


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _normalize_bucket_timestamp(timestamp: Any, bucket_minutes: int) -> str:
    if isinstance(timestamp, datetime):
        dt = timestamp.astimezone(timezone.utc)
    else:
        text = str(timestamp or "").strip()
        if not text:
            return ""
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        except Exception:
            return text
    minute_bucket = (dt.minute // max(bucket_minutes, 1)) * max(bucket_minutes, 1)
    bucketed = dt.replace(minute=minute_bucket, second=0, microsecond=0)
    return bucketed.isoformat()


def _series_to_map(series: list[tuple[Any, float]], bucket_minutes: int) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for ts, value in series:
        bucket = _normalize_bucket_timestamp(ts, bucket_minutes)
        if bucket:
            normalized[bucket] = float(value)
    return normalized


def _aligned_vectors(local_series: list[tuple[Any, float]], asset_series: list[tuple[Any, float]], bucket_minutes: int) -> tuple[list[float], list[float], list[str]]:
    local_map = _series_to_map(local_series, bucket_minutes)
    asset_map = _series_to_map(asset_series, bucket_minutes)
    common = sorted(set(local_map.keys()) & set(asset_map.keys()))
    return [local_map[key] for key in common], [asset_map[key] for key in common], common


def _ewma_mean(values: list[float], alpha: float) -> float:
    if not values:
        return 0.0
    mean = values[0]
    for value in values[1:]:
        mean = (alpha * value) + ((1.0 - alpha) * mean)
    return mean


def _ewma_covariance(x_values: list[float], y_values: list[float], alpha: float) -> float:
    if not x_values or not y_values or len(x_values) != len(y_values):
        return 0.0
    mean_x = x_values[0]
    mean_y = y_values[0]
    cov = 0.0
    for x_value, y_value in zip(x_values, y_values, strict=False):
        mean_x = (alpha * x_value) + ((1.0 - alpha) * mean_x)
        mean_y = (alpha * y_value) + ((1.0 - alpha) * mean_y)
        cov = (alpha * ((x_value - mean_x) * (y_value - mean_y))) + ((1.0 - alpha) * cov)
    return cov


def _pearson_corr(x_values: list[float], y_values: list[float]) -> float:
    if len(x_values) < 2 or len(y_values) < 2 or len(x_values) != len(y_values):
        return 0.0
    mean_x = sum(x_values) / len(x_values)
    mean_y = sum(y_values) / len(y_values)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values, strict=False))
    var_x = sum((x - mean_x) ** 2 for x in x_values)
    var_y = sum((y - mean_y) ** 2 for y in y_values)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def _quality_from_points(point_count: int, minimum: int) -> float:
    return min(max(point_count / max(minimum, 1), 0.0), 1.0)


def build_dynamic_beta_model(
    prepared_inputs: dict[str, Any],
    run_config: GlobalTriangulationConfig,
) -> dict[str, Any]:
    assets = prepared_inputs.get("assets") or []
    local_asset = next((asset for asset in assets if asset.get("slug") == "local_index"), None)
    if not local_asset:
        raise ValueError("Global triangulation requires a local_index asset config")

    local_series = local_asset.get("return_series") or []
    local_latest_return = _safe_float(local_asset.get("latest_return"), 0.0)
    local_current_price = _safe_float(local_asset.get("current_price"), 0.0)
    local_previous_price = _safe_float(local_asset.get("previous_price"), local_current_price)

    relationships: list[dict[str, Any]] = []
    active_weights: list[tuple[int, float]] = []

    for asset in assets:
        if asset is local_asset:
            continue
        asset_series = asset.get("return_series") or []
        local_values, asset_values, common_keys = _aligned_vectors(local_series, asset_series, run_config.bar_interval_minutes)
        point_count = len(common_keys)
        quality = _quality_from_points(point_count, run_config.min_points) * float(asset.get("state_quality_score") or 0.0)
        if point_count < run_config.min_points:
            relationships.append(
                {
                    "slug": asset.get("slug"),
                    "label": asset.get("label"),
                    "security": asset.get("selected_security"),
                    "point_count": point_count,
                    "quality": quality,
                    "active": False,
                    "beta": 0.0,
                    "alpha": 0.0,
                    "corr_short": 0.0,
                    "corr_smoothed": 0.0,
                    "latest_return": _safe_float(asset.get("latest_return"), 0.0),
                    "intraday_return": _safe_float(asset.get("intraday_return"), 0.0),
                    "expected_contribution": 0.0,
                }
            )
            continue

        cov_l_a = _ewma_covariance(local_values, asset_values, run_config.ewma_alpha)
        var_a = max(_ewma_covariance(asset_values, asset_values, run_config.ewma_alpha), 1e-10)
        beta = cov_l_a / var_a
        local_mean = _ewma_mean(local_values, run_config.ewma_alpha)
        asset_mean = _ewma_mean(asset_values, run_config.ewma_alpha)
        alpha = local_mean - (beta * asset_mean)
        corr_smoothed = cov_l_a / math.sqrt(max(_ewma_covariance(local_values, local_values, run_config.ewma_alpha), 1e-10) * var_a)
        short_window = min(run_config.corr_short_window, point_count)
        corr_short = _pearson_corr(local_values[-short_window:], asset_values[-short_window:])
        latest_return = _safe_float(asset.get("latest_return"), 0.0)
        expected_contribution = alpha + (beta * latest_return)
        active = quality > 0.1

        relationships.append(
            {
                "slug": asset.get("slug"),
                "label": asset.get("label"),
                "security": asset.get("selected_security"),
                "point_count": point_count,
                "quality": quality,
                "active": active,
                "beta": beta,
                "alpha": alpha,
                "corr_short": corr_short,
                "corr_smoothed": corr_smoothed,
                "latest_return": latest_return,
                "intraday_return": _safe_float(asset.get("intraday_return"), 0.0),
                "expected_contribution": expected_contribution,
                "weight_raw": max(_safe_float(asset.get("weight"), 0.0), 0.0) * max(abs(corr_smoothed), 0.05) * max(quality, 0.05),
            }
        )
        if active:
            active_weights.append((len(relationships) - 1, relationships[-1]["weight_raw"]))

    total_weight = sum(weight for _, weight in active_weights)
    for index, _ in active_weights:
        relationships[index]["weight"] = relationships[index]["weight_raw"] / total_weight if total_weight > 0 else 0.0
    for relationship in relationships:
        relationship.setdefault("weight", 0.0)

    basket_expected_return = sum(
        relationship["weight"] * relationship["expected_contribution"]
        for relationship in relationships
        if relationship.get("active")
    )
    basket_alpha = sum(
        relationship["weight"] * relationship["alpha"]
        for relationship in relationships
        if relationship.get("active")
    )

    local_map = _series_to_map(local_series, run_config.bar_interval_minutes)
    asset_maps = {
        relationship["slug"]: _series_to_map(
            next((asset.get("return_series") for asset in assets if asset.get("slug") == relationship["slug"]), []) or [],
            run_config.bar_interval_minutes,
        )
        for relationship in relationships
    }
    common_timestamps = sorted(local_map.keys())
    residual_series: list[tuple[str, float]] = []
    for timestamp in common_timestamps:
        contributions = []
        for relationship in relationships:
            if not relationship.get("active"):
                continue
            asset_map = asset_maps.get(relationship["slug"]) or {}
            if timestamp not in asset_map:
                continue
            contributions.append(
                (
                    relationship["weight"],
                    relationship["alpha"] + (relationship["beta"] * asset_map[timestamp]),
                )
            )
        if not contributions:
            continue
        weight_sum = sum(item[0] for item in contributions)
        expected = sum(weight * contribution for weight, contribution in contributions) / max(weight_sum, 1e-10)
        residual_series.append((timestamp, local_map[timestamp] - expected))

    residual_values = [value for _, value in residual_series]
    residual_sigma = pstdev(residual_values) if len(residual_values) >= 2 else abs(residual_values[-1]) if residual_values else 0.0
    residual_return = local_latest_return - basket_expected_return
    global_beta_now = sum(
        relationship["weight"] * relationship["beta"]
        for relationship in relationships
        if relationship.get("active")
    )
    global_corr_short = sum(
        relationship["weight"] * relationship["corr_short"]
        for relationship in relationships
        if relationship.get("active")
    )
    global_corr_smoothed = sum(
        relationship["weight"] * relationship["corr_smoothed"]
        for relationship in relationships
        if relationship.get("active")
    )
    top_explaining_assets = sorted(
        [
            {
                "slug": relationship["slug"],
                "label": relationship["label"],
                "security": relationship["security"],
                "beta": relationship["beta"],
                "corr_smoothed": relationship["corr_smoothed"],
                "latest_return": relationship["latest_return"],
                "expected_contribution": relationship["weight"] * relationship["expected_contribution"],
            }
            for relationship in relationships
            if relationship.get("active")
        ],
        key=lambda item: abs(item["expected_contribution"]),
        reverse=True,
    )[:4]

    return {
        "local_asset_slug": local_asset.get("slug"),
        "local_security": local_asset.get("selected_security"),
        "local_return": local_latest_return,
        "local_current_price": local_current_price,
        "local_previous_price": local_previous_price,
        "basket_expected_return": basket_expected_return,
        "basket_alpha": basket_alpha,
        "residual_return": residual_return,
        "residual_sigma": residual_sigma,
        "global_beta_now": global_beta_now,
        "global_corr_short": global_corr_short,
        "global_corr_smoothed": global_corr_smoothed,
        "relationships": relationships,
        "residual_series": residual_series,
        "top_explaining_assets": top_explaining_assets,
    }
