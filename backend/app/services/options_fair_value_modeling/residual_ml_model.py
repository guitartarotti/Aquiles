from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .types import FairValueRunConfig


def build_residual_ml_adjustment(
    frame: pd.DataFrame,
    structural_model: dict[str, Any],
    feature_meta: dict[str, dict[str, Any]],
    run_config: FairValueRunConfig,
) -> dict[str, Any]:
    history = structural_model.get("history") or []
    if len(history) < max(run_config.min_points, 90):
        return {
            "enabled": False,
            "status": "insufficient_history",
            "fair_value_residual_adjustment": 0.0,
            "confidence": 0.0,
            "validation": {"observation_count": len(history)},
        }

    history_frame = pd.DataFrame(history)
    history_frame["timestamp"] = pd.to_datetime(history_frame["timestamp"], utc=True)
    history_frame = history_frame.set_index("timestamp").sort_index()
    model_frame = frame.join(history_frame[["residual_return", "predicted_return"]], how="inner")
    feature_columns = [meta["z_column"] for meta in feature_meta.values()]
    model_frame["abs_predicted_return"] = model_frame["predicted_return"].abs()
    target_return_column = "target_log_return" if "target_log_return" in model_frame.columns else "target_return"
    model_frame["abs_target_return"] = model_frame[target_return_column].abs()
    model_frame["residual_lag_1"] = model_frame["residual_return"].shift(1)
    model_frame["residual_lag_2"] = model_frame["residual_return"].shift(2)
    model_frame["realized_vol_lag"] = model_frame["realized_vol_rolling"].shift(1)
    ml_feature_columns = feature_columns + [
        "predicted_return",
        "abs_predicted_return",
        "abs_target_return",
        "residual_lag_1",
        "residual_lag_2",
        "realized_vol_lag",
    ]
    model_frame = model_frame.dropna(subset=ml_feature_columns + ["residual_return"])
    if len(model_frame) < max(run_config.min_points, 90):
        return {
            "enabled": False,
            "status": "insufficient_ml_rows",
            "fair_value_residual_adjustment": 0.0,
            "confidence": 0.0,
            "validation": {"observation_count": int(len(model_frame))},
        }

    split_index = max(int(len(model_frame) * 0.8), 40)
    train = model_frame.iloc[:split_index]
    test = model_frame.iloc[split_index:] if split_index < len(model_frame) else model_frame.iloc[0:0]

    x_train = train[ml_feature_columns].to_numpy(dtype=float)
    y_train = train["residual_return"].to_numpy(dtype=float)
    x_latest = model_frame[ml_feature_columns].iloc[[-1]].to_numpy(dtype=float)

    model = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_depth=3,
        max_iter=120,
        min_samples_leaf=8,
        l2_regularization=0.1,
        random_state=42,
    )
    model.fit(x_train, y_train)

    latest_residual_return = float(model.predict(x_latest)[0])
    anchor_price = float(
        structural_model.get("fair_value_structural")
        or structural_model.get("anchor_price")
        or model_frame["fair_value_anchor_price"].iloc[-1]
        or model_frame["structural_anchor_price"].iloc[-1]
    )
    current_sigma_points = float(structural_model.get("residual_sigma_points") or 1.0)
    raw_adjustment_points = anchor_price * latest_residual_return
    cap_points = max(current_sigma_points * run_config.residual_max_sigma_mult, 150.0)
    adjustment_points = float(np.clip(raw_adjustment_points, -cap_points, cap_points))

    validation = {"observation_count": int(len(model_frame))}
    if len(test) >= 10:
        x_test = test[ml_feature_columns].to_numpy(dtype=float)
        y_test = test["residual_return"].to_numpy(dtype=float)
        preds = model.predict(x_test)
        validation.update(
            {
                "rmse_return": float(np.sqrt(np.mean(np.square(y_test - preds)))),
                "mae_return": float(np.mean(np.abs(y_test - preds))),
                "directional_accuracy": float(np.mean(np.sign(y_test) == np.sign(preds))),
            }
        )

    confidence = 0.0
    if validation.get("directional_accuracy") is not None:
        confidence = max(0.15, min(0.85, 0.25 + (0.65 * float(validation["directional_accuracy"]))))

    return {
        "enabled": True,
        "status": "trained",
        "fair_value_residual_adjustment": adjustment_points,
        "predicted_residual_return": latest_residual_return,
        "raw_adjustment_points": raw_adjustment_points,
        "cap_points": cap_points,
        "confidence": confidence,
        "validation": validation,
        "feature_columns": ml_feature_columns,
    }
