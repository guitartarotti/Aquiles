from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from ...utils.logger import get_logger
from .types import FairValueRunConfig

logger = get_logger("aquiles.options_fair_value.dynamic_model")


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _safe_exp_log_price(value: float) -> float:
    return math.log(max(float(value), 1e-9))


def _cumulative_by_session(
    values: np.ndarray,
    session_keys: np.ndarray,
    *,
    subtract_first_step: bool,
) -> np.ndarray:
    result = np.zeros(len(values), dtype=float)
    running = 0.0
    first_step = 0.0
    current_session: str | None = None

    for idx, key in enumerate(session_keys):
        session_key = str(key)
        if session_key != current_session:
            current_session = session_key
            running = float(values[idx])
            first_step = float(values[idx])
        else:
            running += float(values[idx])
        result[idx] = running - first_step if subtract_first_step else running
    return result


def _session_minutes_from_start(index: pd.Index, session_keys: np.ndarray) -> np.ndarray:
    minutes = np.zeros(len(index), dtype=float)
    session_start = None
    current_session: str | None = None

    for idx, key in enumerate(session_keys):
        session_key = str(key)
        timestamp = index[idx]
        if session_key != current_session:
            current_session = session_key
            session_start = timestamp
        if session_start is None:
            continue
        delta = timestamp - session_start
        minutes[idx] = max(float(delta.total_seconds()) / 60.0, 0.0)
    return minutes


def _session_increments_from_cumulative(cumulative: np.ndarray, session_keys: np.ndarray) -> np.ndarray:
    increments = np.zeros(len(cumulative), dtype=float)
    previous = 0.0
    current_session: str | None = None

    for idx, key in enumerate(session_keys):
        session_key = str(key)
        if session_key != current_session:
            current_session = session_key
            previous = 0.0
        current_value = float(cumulative[idx])
        increments[idx] = current_value - previous
        previous = current_value
    return increments


def _state_space_path(
    *,
    fair_anchor_prices: np.ndarray,
    predicted_returns: np.ndarray,
    observed_prices: np.ndarray,
    residual_sigma_return: float,
    run_config: FairValueRunConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    process_var = max(float(run_config.state_space_process_noise), 1e-8)
    measurement_var = max(
        (max(float(residual_sigma_return), 1e-6) ** 2) * max(float(run_config.state_space_measurement_noise), 1.0),
        process_var * 4.0,
        1e-8,
    )

    history = np.zeros(len(predicted_returns), dtype=float)
    gains = np.zeros(len(predicted_returns), dtype=float)
    innovations = np.zeros(len(predicted_returns), dtype=float)

    anchor0 = fair_anchor_prices[0] if fair_anchor_prices[0] > 0 else observed_prices[0]
    state_post = _safe_exp_log_price(anchor0 if anchor0 > 0 else observed_prices[0])
    variance_post = measurement_var

    for idx in range(len(predicted_returns)):
        state_prior = state_post + float(predicted_returns[idx])
        variance_prior = variance_post + process_var
        observed_log_price = _safe_exp_log_price(observed_prices[idx])
        innovation = observed_log_price - state_prior
        gain = variance_prior / max(variance_prior + measurement_var, 1e-9)
        state_post = state_prior + (gain * innovation)
        variance_post = max((1.0 - gain) * variance_prior, 1e-10)

        history[idx] = math.exp(state_post)
        gains[idx] = gain
        innovations[idx] = innovation

    return history, gains, innovations


def run_dynamic_structural_model(
    frame: pd.DataFrame,
    feature_meta: dict[str, dict[str, Any]],
    feature_universe_meta: dict[str, dict[str, Any]] | None,
    run_config: FairValueRunConfig,
) -> dict[str, Any]:
    if frame.empty:
        raise ValueError("Factor frame is empty")

    feature_names = list(feature_meta.keys())
    feature_universe_meta = feature_universe_meta or feature_meta
    universe_feature_names = list(feature_universe_meta.keys())
    z_columns = [feature_meta[name].get("model_column") or feature_meta[name]["z_column"] for name in feature_names]
    model_frame = frame.dropna(
        subset=[
            "target_log_return",
            "local_future_close",
            "structural_anchor_price",
            "fair_value_anchor_price",
            "session_date",
        ]
    ).copy()
    if len(model_frame) < run_config.min_points:
        raise ValueError(
            f"Not enough fair value observations after preparation: {len(model_frame)} < {run_config.min_points}"
        )

    x_matrix = model_frame[z_columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    y_vector = model_frame["target_log_return"].to_numpy(dtype=float)
    prior_prices = model_frame["structural_anchor_price"].to_numpy(dtype=float)
    current_prices = model_frame["local_future_close"].to_numpy(dtype=float)
    fair_anchor_prices = model_frame["fair_value_anchor_price"].to_numpy(dtype=float)
    session_keys = model_frame["session_date"].astype(str).to_numpy()
    selected_blocks = sorted({str(meta.get("block") or "other") for meta in feature_meta.values()})
    universe_blocks = sorted({str(meta.get("block") or "other") for meta in feature_universe_meta.values()})

    universe_feature_ratio = len(feature_names) / max(len(universe_feature_names), 1)
    universe_block_ratio = len(selected_blocks) / max(len(universe_blocks), 1)
    selection_breadth_score = max(
        0.0,
        min(
            1.0,
            (0.55 * universe_feature_ratio) + (0.45 * universe_block_ratio),
        ),
    )

    x_mean = np.nanmean(x_matrix[:-1], axis=0) if len(x_matrix) > 1 else np.nanmean(x_matrix, axis=0)
    x_std = np.nanstd(x_matrix[:-1], axis=0) if len(x_matrix) > 1 else np.nanstd(x_matrix, axis=0)
    x_std = np.where(np.isfinite(x_std) & (x_std > 1e-9), x_std, 1.0)
    x_norm = np.nan_to_num((x_matrix - x_mean) / x_std, nan=0.0, posinf=0.0, neginf=0.0)
    block_counts: dict[str, int] = {}
    for name in feature_names:
        block = str(feature_meta[name].get("block") or "other")
        block_counts[block] = block_counts.get(block, 0) + 1
    block_input_scales: dict[str, float] = {}
    for idx, name in enumerate(feature_names):
        block = str(feature_meta[name].get("block") or "other")
        block_scale = 1.0 if block == "local_brazil" else (0.55 / math.sqrt(max(block_counts.get(block, 1), 1)))
        x_norm[:, idx] = x_norm[:, idx] * block_scale
        block_input_scales[name] = float(block_scale)

    observations = len(model_frame)
    n_features = x_norm.shape[1] + 1
    theta = np.zeros(n_features, dtype=float)
    covariance = np.eye(n_features, dtype=float) * max(run_config.rls_init_covariance, 1.0)

    predictions = np.zeros(observations, dtype=float)
    residuals = np.zeros(observations, dtype=float)
    theta_history = np.zeros((observations, n_features), dtype=float)

    forgetting = min(max(run_config.rls_forgetting, 0.85), 0.9995)

    for idx in range(observations):
        x_row = np.concatenate(([1.0], x_norm[idx]))
        theta_pre = theta.copy()
        pred = float(theta_pre @ x_row)
        err = float(y_vector[idx] - pred)

        predictions[idx] = pred
        residuals[idx] = err
        theta_history[idx] = theta_pre

        denom = forgetting + float(x_row @ covariance @ x_row)
        gain = (covariance @ x_row) / max(denom, 1e-9)
        theta = theta_pre + gain * err
        covariance = (covariance - np.outer(gain, x_row) @ covariance) / forgetting

    latest_idx = observations - 1
    latest_theta = theta_history[latest_idx]
    latest_x_row = np.concatenate(([1.0], x_norm[latest_idx]))
    session_elapsed_minutes = _session_minutes_from_start(model_frame.index, session_keys)
    warmup_progress = np.clip(
        session_elapsed_minutes / max(float(run_config.breadth_warmup_minutes), 5.0),
        0.0,
        1.0,
    )
    breadth_score_history = np.clip(
        (0.60 * selection_breadth_score) + (0.40 * warmup_progress),
        0.0,
        1.0,
    )
    prediction_scales = np.clip(
        float(run_config.breadth_scale_floor)
        + ((1.0 - float(run_config.breadth_scale_floor)) * breadth_score_history),
        float(run_config.breadth_scale_floor),
        1.0,
    )
    scaled_predictions = predictions * prediction_scales
    float(prior_prices[latest_idx])
    actual_price = float(current_prices[latest_idx])

    alpha = math.exp(math.log(0.5) / max(run_config.residual_sigma_halflife, 1.0))
    ewma_var = 0.0
    warm = False
    subtract_first_step = str(run_config.intraday_anchor_type or "previous_close").strip().lower() == "session_open"
    raw_cumulative_predicted_log_returns = _cumulative_by_session(
        scaled_predictions,
        session_keys,
        subtract_first_step=subtract_first_step,
    )
    realized_cumulative_var = _cumulative_by_session(
        np.square(y_vector),
        session_keys,
        subtract_first_step=subtract_first_step,
    )
    realized_cumulative_sigma = np.sqrt(np.maximum(realized_cumulative_var, 0.0))
    cumulative_return_budget = np.clip(
        realized_cumulative_sigma * (1.15 + (0.45 * selection_breadth_score)),
        0.0035,
        0.0150,
    )
    cumulative_predicted_log_returns = np.clip(
        raw_cumulative_predicted_log_returns,
        -cumulative_return_budget,
        cumulative_return_budget,
    )
    effective_predictions = _session_increments_from_cumulative(
        cumulative_predicted_log_returns,
        session_keys,
    )
    clamp_ratio = np.divide(
        effective_predictions,
        scaled_predictions,
        out=np.ones_like(effective_predictions),
        where=np.abs(scaled_predictions) > 1e-10,
    )
    effective_residuals = y_vector - effective_predictions
    predicted_return_now = float(effective_predictions[latest_idx])
    for value in effective_residuals[:-1] if observations > 1 else effective_residuals:
        if not warm:
            ewma_var = float(value * value)
            warm = True
        else:
            ewma_var = (alpha * ewma_var) + ((1.0 - alpha) * float(value * value))
    residual_sigma_return = math.sqrt(max(ewma_var, 1e-12))
    cumulative_intercept_log_returns = _cumulative_by_session(
        theta_history[:, 0] * prediction_scales * clamp_ratio,
        session_keys,
        subtract_first_step=subtract_first_step,
    )
    intraday_fair_values = fair_anchor_prices * np.exp(cumulative_predicted_log_returns)

    state_space_history, state_space_gains, state_space_innovations = _state_space_path(
        fair_anchor_prices=fair_anchor_prices,
        predicted_returns=effective_predictions,
        observed_prices=current_prices,
        residual_sigma_return=residual_sigma_return,
        run_config=run_config,
    )

    active_mode = str(run_config.engine_mode or "intraday_anchor").strip().lower()
    if active_mode not in {"intraday_anchor", "state_space"}:
        active_mode = "intraday_anchor"
    active_anchor_type = "state_space" if active_mode == "state_space" else str(run_config.intraday_anchor_type or "previous_close")
    active_fair_history = state_space_history if active_mode == "state_space" else intraday_fair_values
    fair_value_structural = float(active_fair_history[latest_idx])
    anchor_price = float(fair_anchor_prices[latest_idx])
    structural_residual_points = actual_price - fair_value_structural
    structural_residual_return = y_vector[latest_idx] - predicted_return_now
    residual_sigma_points = max(anchor_price * residual_sigma_return, 1.0)

    factor_betas_now: dict[str, float] = {}
    factor_contributions_now: dict[str, dict[str, Any]] = {}
    factor_expected_returns: dict[str, float] = {
        "alpha": float(latest_theta[0] * prediction_scales[latest_idx] * clamp_ratio[latest_idx])
    }
    factor_cumulative_contributions_from_anchor: dict[str, float] = {}
    block_contributions: dict[str, float] = {}
    factor_return_history = theta_history[:, 1:] * x_norm * prediction_scales[:, None] * clamp_ratio[:, None]
    cumulative_factor_returns: dict[str, np.ndarray] = {}

    intercept_contribution_return = float(latest_theta[0] * prediction_scales[latest_idx] * clamp_ratio[latest_idx])
    intercept_cumulative_return = float(cumulative_intercept_log_returns[latest_idx])
    intercept_contribution_points = anchor_price * (math.exp(intercept_cumulative_return) - 1.0)

    for index, name in enumerate(feature_names, start=1):
        meta = feature_meta[name]
        expected_return = float(
            latest_theta[index]
            * latest_x_row[index]
            * prediction_scales[latest_idx]
            * clamp_ratio[latest_idx]
        )
        cumulative_returns = _cumulative_by_session(
            factor_return_history[:, index - 1],
            session_keys,
            subtract_first_step=subtract_first_step,
        )
        cumulative_factor_returns[name] = cumulative_returns
        cumulative_return_now = float(cumulative_returns[latest_idx])
        cumulative_points = anchor_price * (math.exp(cumulative_return_now) - 1.0)
        factor_betas_now[name] = float(latest_theta[index])
        factor_expected_returns[name] = expected_return
        factor_cumulative_contributions_from_anchor[name] = cumulative_points
        factor_contributions_now[name] = {
            "label": meta["label"],
            "block": meta["block"],
            "beta": float(latest_theta[index]),
            "feature_value": float(model_frame.iloc[latest_idx][meta["feature_column"]]),
            "feature_zscore": float(model_frame.iloc[latest_idx][meta["z_column"]]),
            "model_input_zscore": float(model_frame.iloc[latest_idx][meta.get("model_column") or meta["z_column"]]),
            "block_input_scale": float(block_input_scales.get(name, 1.0)),
            "weight": float(meta.get("weight") or 1.0),
            "model_layer": str(meta.get("model_layer") or "core"),
            "contribution_return": expected_return,
            "cumulative_contribution_return": cumulative_return_now,
            "contribution_points": cumulative_points,
            "anchor_xb1": anchor_price,
        }
        block = str(meta["block"])
        block_contributions[block] = block_contributions.get(block, 0.0) + cumulative_points

    rmse = float(np.sqrt(np.mean(np.square(effective_residuals))))
    mae = float(np.mean(np.abs(effective_residuals)))
    directional_accuracy = float(np.mean(np.sign(effective_predictions) == np.sign(y_vector)))

    history = []
    for idx in range(observations):
        anchor_row = float(fair_anchor_prices[idx])
        intraday_fair_value = float(intraday_fair_values[idx])
        state_space_fair_value = float(state_space_history[idx])
        active_fair_value = float(active_fair_history[idx])
        history.append(
            {
                "timestamp": model_frame.index[idx].isoformat(),
                "session_date": str(session_keys[idx]),
                "anchor_xb1": anchor_row,
                "anchor_type": active_anchor_type,
                "intraday_anchor_type": str(run_config.intraday_anchor_type or "previous_close"),
                "prior_price": float(prior_prices[idx]),
                "actual_price": float(current_prices[idx]),
                "actual_return": float(y_vector[idx]),
                "predicted_return_raw": float(predictions[idx]),
                "predicted_return_pre_cap": float(scaled_predictions[idx]),
                "predicted_return": float(effective_predictions[idx]),
                "prediction_scale": float(prediction_scales[idx]),
                "prediction_clamp_ratio": float(clamp_ratio[idx]),
                "breadth_score": float(breadth_score_history[idx]),
                "session_elapsed_minutes": float(session_elapsed_minutes[idx]),
                "residual_return": float(effective_residuals[idx]),
                "cumulative_return_budget": float(cumulative_return_budget[idx]),
                "cumulative_predicted_return_from_anchor": float(cumulative_predicted_log_returns[idx]),
                "fair_value_intraday_anchor": intraday_fair_value,
                "fair_value_state_space": state_space_fair_value,
                "fair_value_structural": active_fair_value,
                "mispricing_points": float(current_prices[idx] - active_fair_value),
                "state_space_kalman_gain": float(state_space_gains[idx]),
                "state_space_innovation": float(state_space_innovations[idx]),
            }
        )

    rank = sorted(
        (
            {
                "factor": name,
                "label": payload["label"],
                "block": payload["block"],
                "contribution_points": payload["contribution_points"],
            }
            for name, payload in factor_contributions_now.items()
        ),
        key=lambda item: abs(item["contribution_points"]),
        reverse=True,
    )

    residual_score = abs(structural_residual_points) / max(residual_sigma_points, 1.0)
    structural_confidence = max(
        0.15,
        min(
            0.95,
            (
                0.28
                + (0.35 * directional_accuracy)
                + (0.17 * _sigmoid(2.0 - residual_score))
                + (0.20 * selection_breadth_score)
            ),
        ),
    )

    return {
        "fair_value_structural": fair_value_structural,
        "fair_value_intraday_anchor": float(intraday_fair_values[latest_idx]),
        "fair_value_state_space": float(state_space_history[latest_idx]),
        "predicted_return_now": predicted_return_now,
        "predicted_return_raw_now": float(predictions[latest_idx]),
        "predicted_return_pre_cap_now": float(scaled_predictions[latest_idx]),
        "prediction_scale": float(prediction_scales[latest_idx]),
        "prediction_clamp_ratio": float(clamp_ratio[latest_idx]),
        "anchor_price": anchor_price,
        "anchor_xb1": anchor_price,
        "session_anchor_xb1": anchor_price,
        "anchor_type": active_anchor_type,
        "intraday_anchor_type": str(run_config.intraday_anchor_type or "previous_close"),
        "engine_mode": active_mode,
        "current_price": actual_price,
        "structural_residual_points": structural_residual_points,
        "structural_residual_return": structural_residual_return,
        "residual_sigma_return": residual_sigma_return,
        "residual_sigma_points": residual_sigma_points,
        "factor_betas_now": factor_betas_now,
        "factor_expected_returns": factor_expected_returns,
        "factor_cumulative_contributions_from_anchor": factor_cumulative_contributions_from_anchor,
        "factor_contributions_now": factor_contributions_now,
        "intercept_contribution_return": intercept_contribution_return,
        "intercept_cumulative_return": intercept_cumulative_return,
        "intercept_contribution_points": intercept_contribution_points,
        "cumulative_fair_return_from_anchor": float(cumulative_predicted_log_returns[latest_idx]),
        "selection_breadth_score": float(selection_breadth_score),
        "selected_feature_ratio": float(universe_feature_ratio),
        "selected_block_ratio": float(universe_block_ratio),
        "breadth_score": float(breadth_score_history[latest_idx]),
        "session_elapsed_minutes": float(session_elapsed_minutes[latest_idx]),
        "cumulative_return_budget": float(cumulative_return_budget[latest_idx]),
        "cumulative_fair_return_from_anchor_raw": float(raw_cumulative_predicted_log_returns[latest_idx]),
        "block_contributions_points": block_contributions,
        "ranking": rank,
        "validation": {
            "observation_count": observations,
            "rmse_return": rmse,
            "mae_return": mae,
            "directional_accuracy": directional_accuracy,
        },
        "history": history,
        "confidence": structural_confidence,
        "normalization": {
            "feature_order": feature_names,
            "mean": {name: float(x_mean[idx]) for idx, name in enumerate(feature_names)},
            "std": {name: float(x_std[idx]) for idx, name in enumerate(feature_names)},
        },
        "state_space": {
            "fair_value": float(state_space_history[latest_idx]),
            "kalman_gain": float(state_space_gains[latest_idx]),
            "innovation": float(state_space_innovations[latest_idx]),
            "measurement_noise": max(float(run_config.state_space_measurement_noise), 1.0),
            "process_noise": max(float(run_config.state_space_process_noise), 1e-8),
        },
    }
