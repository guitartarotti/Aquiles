from __future__ import annotations

import math
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from ...config import Config
from ...utils.logger import get_logger
from ..macro_options_heatmap_context_service import MacroOptionsHeatmapContextService
from ..options_store import OptionsStore
from .intraday_dependency_service import IntradayDependencyService

try:
    import torch
    from torch import nn
except Exception:  # pragma: no cover - handled at runtime
    torch = None
    nn = None


logger = get_logger("aquiles.options_fair_value.intraday_neural")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


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


def _directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(np.sign(y_true) == np.sign(y_pred)))


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(y_true - y_pred))))


def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(np.abs(y_true - y_pred)))


class _NeuralAdditiveModel(nn.Module):
    def __init__(self, factor_count: int, context_count: int, hidden_width: int) -> None:
        super().__init__()
        width = max(int(hidden_width), 4)
        self.linear = nn.Parameter(torch.zeros(factor_count))
        self.bias = nn.Parameter(torch.zeros(1))
        self.factor_nets = nn.ModuleList([
            nn.Sequential(
                nn.Linear(1, width),
                nn.SiLU(),
                nn.Linear(width, width),
                nn.SiLU(),
                nn.Linear(width, 1),
            )
            for _ in range(factor_count)
        ])
        self.context_net = (
            nn.Sequential(
                nn.Linear(context_count, width),
                nn.SiLU(),
                nn.Linear(width, max(width // 2, 2)),
                nn.SiLU(),
                nn.Linear(max(width // 2, 2), 1),
            )
            if context_count > 0
            else None
        )

    def forward(
        self,
        factor_inputs,
        context_inputs=None,
        *,
        return_contributions: bool = False,
    ):
        contributions = []
        for index, block in enumerate(self.factor_nets):
            scalar = factor_inputs[:, index:index + 1]
            contributions.append((scalar * self.linear[index]) + block(scalar))
        factor_matrix = torch.cat(contributions, dim=1) if contributions else torch.zeros_like(factor_inputs)
        total = factor_matrix.sum(dim=1, keepdim=True) + self.bias
        context_value = None
        if self.context_net is not None and context_inputs is not None:
            context_value = self.context_net(context_inputs)
            total = total + context_value
        if return_contributions:
            return total.squeeze(-1), factor_matrix, context_value
        return total.squeeze(-1)


class IntradayNeuralModelService:
    def __init__(
        self,
        *,
        store: OptionsStore | None = None,
        context_service: MacroOptionsHeatmapContextService | None = None,
        dependency_service: IntradayDependencyService | None = None,
    ) -> None:
        self.store = store or OptionsStore()
        self.context_service = context_service or MacroOptionsHeatmapContextService()
        self.dependency_service = dependency_service or IntradayDependencyService(
            store=self.store,
            context_service=self.context_service,
        )

    def _load_training_snapshots(self, underlying_security: str) -> tuple[list[dict[str, Any]], list[str]]:
        runs = self.store.list_recent_fair_value_runs(
            underlying_security,
            limit=max(int(Config.OPTIONS_INTRADAY_NEURAL_MAX_RUNS), 200),
        )
        runs_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for run in runs:
            session_date = str(run.get("session_date") or "").strip()
            if session_date:
                runs_by_session[session_date].append(run)
        live_snapshots_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for raw_snapshot in self.context_service.read_live_capture_snapshots(
            session_date=None,
            underlying_security=underlying_security,
        ):
            snapshot = dict(raw_snapshot or {})
            session_date = str(snapshot.get("session_date") or "").strip()
            if not session_date:
                continue
            factor_values = self.dependency_service._snapshot_factor_values(snapshot)
            workbook_values = self.dependency_service._snapshot_workbook_values(snapshot)
            if not factor_values and not workbook_values:
                continue
            live_snapshots_by_session[session_date].append({
                "captured_at": snapshot.get("captured_at"),
                "session_date": session_date,
                "underlying_security": snapshot.get("underlying_security") or underlying_security,
                "current_future_price": _safe_float(snapshot.get("current_future_price")),
                "current_spot_price": _safe_float(snapshot.get("current_spot_price")),
                "factor_values": factor_values,
                "workbook_values": workbook_values,
                "snapshot_source": "live_capture",
            })
        session_dates = sorted({*runs_by_session.keys(), *live_snapshots_by_session.keys()}, reverse=True)
        selected_sessions: list[str] = []
        selected_runs: list[dict[str, Any]] = []
        selected_live_snapshots: list[dict[str, Any]] = []
        target_sessions = max(int(Config.OPTIONS_INTRADAY_NEURAL_LOOKBACK_SESSIONS), 1)
        target_runs = max(int(Config.OPTIONS_INTRADAY_NEURAL_MIN_ROWS) * 2, 120)
        total_runs = 0
        for session_date in session_dates:
            session_runs = sorted(
                runs_by_session.get(session_date) or [],
                key=lambda item: str(item.get("captured_at") or ""),
            )
            session_live_snapshots = sorted(
                live_snapshots_by_session.get(session_date) or [],
                key=lambda item: str(item.get("captured_at") or ""),
            )
            if not session_runs and not session_live_snapshots:
                continue
            selected_sessions.append(session_date)
            selected_runs.extend(session_runs)
            selected_live_snapshots.extend(session_live_snapshots)
            total_runs += len(session_runs) + len(session_live_snapshots)
            if len(selected_sessions) >= target_sessions and total_runs >= target_runs:
                break

        snapshots: list[dict[str, Any]] = []
        for payload in selected_runs:
            summary = payload.get("summary") or {}
            factor_rows = summary.get("live_factor_rows") or []
            factor_values = self.dependency_service._compact_factor_values(factor_rows)
            if not factor_values:
                continue
            snapshots.append({
                "captured_at": payload.get("captured_at"),
                "session_date": payload.get("session_date"),
                "underlying_security": payload.get("underlying_security") or underlying_security,
                "current_future_price": _safe_float(summary.get("current_future_price")),
                "current_spot_price": _safe_float(summary.get("current_spot_price")),
                "factor_values": factor_values,
                "workbook_values": {},
                "snapshot_source": "fair_value_run",
            })
        snapshots.extend(dict(item or {}) for item in selected_live_snapshots)

        merged: dict[str, dict[str, Any]] = {}
        for snapshot in snapshots:
            captured_at = str(snapshot.get("captured_at") or "").strip()
            if captured_at:
                merged[captured_at] = snapshot
        ordered = [dict(item or {}) for item in merged.values()]
        ordered.sort(key=lambda item: str(item.get("captured_at") or ""))
        return ordered, selected_sessions

    @staticmethod
    def _time_features(index: pd.DatetimeIndex) -> pd.DataFrame:
        local_index = index.tz_convert(LOCAL_TZ) if index.tz is not None else index.tz_localize("UTC").tz_convert(LOCAL_TZ)
        minutes = np.array([item.hour * 60 + item.minute for item in local_index.to_pydatetime()], dtype=float)
        radians = 2.0 * math.pi * (minutes / 1440.0)
        return pd.DataFrame(
            {
                "time_sin": np.sin(radians),
                "time_cos": np.cos(radians),
            },
            index=index,
        )

    def _build_training_frame(self, snapshots: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
        factor_meta = self.dependency_service._build_factor_meta_from_snapshots(snapshots)
        observed = self.dependency_service._build_observed_frame(
            snapshots=snapshots,
            factor_meta=factor_meta,
        )
        return observed, factor_meta

    def _dataset_for_horizon(
        self,
        observed_frame: pd.DataFrame,
        factor_meta: dict[str, dict[str, Any]],
        horizon_minutes: int,
    ) -> tuple[pd.DataFrame, list[str]]:
        bar_frequency = f"{int(horizon_minutes)}min"
        factor_names = sorted(factor_meta.keys())
        rows: list[dict[str, Any]] = []
        factor_non_null_counts: dict[str, int] = defaultdict(int)

        if observed_frame.empty or "session_date" not in observed_frame.columns:
            return pd.DataFrame(), []

        for session_date, session_frame in observed_frame.groupby("session_date"):
            if not session_date:
                continue
            session_frame = session_frame.sort_index()
            price_bar = session_frame["xb1_last"].resample(bar_frequency).last().dropna()
            if len(price_bar.index) < 4:
                continue
            context_frame = self._time_features(price_bar.index)
            feature_frame = pd.DataFrame(index=price_bar.index)
            for factor in factor_names:
                raw_column = f"raw__{factor}"
                if raw_column not in session_frame.columns:
                    continue
                meta = factor_meta.get(factor) or {}
                raw_bar = session_frame[raw_column].resample(bar_frequency).last().reindex(price_bar.index)
                move = self.dependency_service._bar_move(raw_bar, str(meta.get("transform") or "return"))
                move = move * float(meta.get("direction_multiplier") or 1.0)
                feature_frame[factor] = move
                factor_non_null_counts[factor] += int(move.notna().sum())
            target_forward = np.log(price_bar.shift(-1) / price_bar)
            coverage_ratio = feature_frame.notna().mean(axis=1)
            for timestamp in price_bar.index:
                target_value = _safe_float(target_forward.get(timestamp))
                if target_value is None:
                    continue
                row = {
                    "timestamp": timestamp,
                    "session_date": session_date,
                    "xb1_last": _safe_float(price_bar.get(timestamp)),
                    "target_return": target_value,
                    "coverage_ratio": _safe_float(coverage_ratio.get(timestamp), 0.0) or 0.0,
                    "time_sin": _safe_float(context_frame.at[timestamp, "time_sin"], 0.0) or 0.0,
                    "time_cos": _safe_float(context_frame.at[timestamp, "time_cos"], 0.0) or 0.0,
                }
                for factor in factor_names:
                    row[factor] = _safe_float(feature_frame[factor].get(timestamp)) if factor in feature_frame.columns else None
                rows.append(row)

        dataset = pd.DataFrame(rows)
        if dataset.empty:
            return dataset, []

        numeric_columns = [
            "xb1_last",
            "target_return",
            "coverage_ratio",
            "time_sin",
            "time_cos",
            *factor_names,
        ]
        for column in numeric_columns:
            if column in dataset.columns:
                dataset[column] = pd.to_numeric(dataset[column], errors="coerce")
        dataset = dataset.replace([np.inf, -np.inf], np.nan)
        dataset = dataset.dropna(subset=["timestamp", "session_date", "xb1_last", "target_return"])
        dataset = dataset[dataset["xb1_last"] > 0.0].copy()
        if dataset.empty:
            return dataset, []

        dataset = self._filter_informative_sessions(dataset, factor_names, horizon_minutes)
        if dataset.empty:
            return dataset, []

        minimum_factor_points = max(12, max(int(Config.OPTIONS_INTRADAY_NEURAL_MIN_ROWS) // 4, 8))
        selected_factors = [
            factor
            for factor in factor_names
            if factor_non_null_counts.get(factor, 0) >= minimum_factor_points
            and float(pd.to_numeric(dataset[factor], errors="coerce").std(skipna=True) or 0.0) > 1e-12
        ]
        if not selected_factors:
            return pd.DataFrame(), []

        dataset = dataset.sort_values("timestamp").reset_index(drop=True)
        return dataset, selected_factors

    @staticmethod
    def _robust_scaler_fit(frame: pd.DataFrame, columns: list[str]) -> tuple[dict[str, float], dict[str, float]]:
        medians: dict[str, float] = {}
        scales: dict[str, float] = {}
        for column in columns:
            series = pd.to_numeric(frame[column], errors="coerce")
            median = float(series.median(skipna=True) or 0.0)
            if not math.isfinite(median):
                median = 0.0
            mad = float((series - median).abs().median(skipna=True) or 0.0) * 1.4826
            if not math.isfinite(mad) or mad <= 1e-9:
                mad = float(series.std(skipna=True, ddof=0) or 1.0)
            if not math.isfinite(mad) or mad <= 1e-9:
                mad = 1.0
            medians[column] = median
            scales[column] = mad
        return medians, scales

    @staticmethod
    def _robust_scaler_transform(
        frame: pd.DataFrame,
        columns: list[str],
        medians: dict[str, float],
        scales: dict[str, float],
    ) -> np.ndarray:
        transformed = []
        for column in columns:
            series = pd.to_numeric(frame[column], errors="coerce")
            series = series.replace([np.inf, -np.inf], np.nan).fillna(medians.get(column, 0.0))
            transformed.append(((series - medians.get(column, 0.0)) / max(scales.get(column, 1.0), 1e-9)).to_numpy(dtype=float))
        if not transformed:
            return np.zeros((len(frame.index), 0), dtype=float)
        matrix = np.column_stack(transformed)
        return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

    @staticmethod
    def _split_train_test(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        count = len(dataset.index)
        test_size = max(16, int(count * 0.20))
        if (count - test_size) < 40:
            test_size = max(8, count // 4)
        split_index = max(1, count - test_size)
        train = dataset.iloc[:split_index].copy()
        test = dataset.iloc[split_index:].copy()
        return train, test

    @staticmethod
    def _filter_informative_sessions(
        dataset: pd.DataFrame,
        factor_columns: list[str],
        horizon_minutes: int,
    ) -> pd.DataFrame:
        if dataset.empty:
            return dataset
        available_factors = [column for column in factor_columns if column in dataset.columns]
        if not available_factors:
            return dataset

        working = dataset.copy()
        factor_abs = working[available_factors].abs().sum(axis=1, skipna=True).fillna(0.0)
        target_abs = pd.to_numeric(working["target_return"], errors="coerce").abs().fillna(0.0)
        positive_factor = factor_abs[factor_abs > 0.0]
        positive_target = target_abs[target_abs > 0.0]
        factor_threshold = max(float(positive_factor.median() or 0.0) * 0.15, 1e-6)
        target_threshold = max(float(positive_target.median() or 0.0) * 0.15, 1e-6)
        working["__is_informative"] = (
            (factor_abs >= factor_threshold)
            | (target_abs >= target_threshold)
        )

        minimum_informative_rows = max(4, 12 // max(int(horizon_minutes), 1))
        minimum_informative_ratio = 0.08
        informative_sessions: list[str] = []
        for session_date, session_frame in working.groupby("session_date"):
            informative_count = int(pd.to_numeric(session_frame["__is_informative"], errors="coerce").fillna(0).sum())
            row_count = int(len(session_frame.index))
            informative_ratio = (informative_count / row_count) if row_count else 0.0
            if informative_count >= minimum_informative_rows and informative_ratio >= minimum_informative_ratio:
                informative_sessions.append(str(session_date))

        if not informative_sessions:
            return dataset

        filtered = working[
            working["session_date"].isin(informative_sessions)
            & working["__is_informative"]
        ].drop(columns=["__is_informative"])
        return filtered.reset_index(drop=True)

    @staticmethod
    def _build_sample_weights(frame: pd.DataFrame) -> np.ndarray:
        coverage = pd.to_numeric(frame["coverage_ratio"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        return np.clip(0.25 + (0.75 * coverage), 0.25, 1.0)

    @staticmethod
    def _select_trainable_factors(
        train: pd.DataFrame,
        test: pd.DataFrame,
        candidate_factors: list[str],
    ) -> list[str]:
        minimum_train_points = max(8, min(24, len(train.index) // 6))
        minimum_test_points = max(2, min(8, len(test.index) // 8 if len(test.index) else 0))
        selected: list[str] = []
        for factor in candidate_factors:
            train_series = pd.to_numeric(train[factor], errors="coerce") if factor in train.columns else pd.Series(dtype=float)
            test_series = pd.to_numeric(test[factor], errors="coerce") if factor in test.columns else pd.Series(dtype=float)
            train_count = int(train_series.notna().sum())
            test_count = int(test_series.notna().sum())
            std_value = float(train_series.std(skipna=True, ddof=0) or 0.0)
            if train_count < minimum_train_points:
                continue
            if len(test.index) and test_count < minimum_test_points:
                continue
            if not math.isfinite(std_value) or std_value <= 1e-12:
                continue
            selected.append(factor)
        return selected

    def _fit_linear_baseline(
        self,
        *,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict[str, Any]:
        if len(x_train) < 8 or len(x_test) < 1:
            return {}
        x_train = np.nan_to_num(x_train, nan=0.0, posinf=0.0, neginf=0.0)
        x_test = np.nan_to_num(x_test, nan=0.0, posinf=0.0, neginf=0.0)
        y_train = np.nan_to_num(y_train, nan=0.0, posinf=0.0, neginf=0.0)
        y_test = np.nan_to_num(y_test, nan=0.0, posinf=0.0, neginf=0.0)
        model = Ridge(alpha=1.0, random_state=42)
        model.fit(x_train, y_train)
        preds = model.predict(x_test)
        return {
            "rmse_return": _rmse(y_test, preds),
            "mae_return": _mae(y_test, preds),
            "directional_accuracy": _directional_accuracy(y_test, preds),
            "corr": float(np.corrcoef(y_test, preds)[0, 1]) if len(preds) > 1 and float(np.std(preds)) > 1e-9 and float(np.std(y_test)) > 1e-9 else 0.0,
        }

    def _fit_neural_additive_model(
        self,
        *,
        factor_feature_names: list[str],
        context_feature_names: list[str],
        train: pd.DataFrame,
        test: pd.DataFrame,
    ) -> dict[str, Any]:
        if torch is None or nn is None:
            return {
                "enabled": False,
                "status": "torch_unavailable",
            }
        if len(train.index) < 24 or len(test.index) < 4 or not factor_feature_names:
            return {
                "enabled": False,
                "status": "insufficient_rows",
            }

        factor_medians, factor_scales = self._robust_scaler_fit(train, factor_feature_names)
        context_medians, context_scales = self._robust_scaler_fit(train, context_feature_names)

        x_factor_train = self._robust_scaler_transform(train, factor_feature_names, factor_medians, factor_scales)
        x_factor_test = self._robust_scaler_transform(test, factor_feature_names, factor_medians, factor_scales)
        x_context_train = self._robust_scaler_transform(train, context_feature_names, context_medians, context_scales)
        x_context_test = self._robust_scaler_transform(test, context_feature_names, context_medians, context_scales)
        y_train = pd.to_numeric(train["target_return"], errors="coerce").to_numpy(dtype=float)
        y_test = pd.to_numeric(test["target_return"], errors="coerce").to_numpy(dtype=float)
        weight_train = self._build_sample_weights(train)
        y_train = np.nan_to_num(y_train, nan=0.0, posinf=0.0, neginf=0.0)
        y_test = np.nan_to_num(y_test, nan=0.0, posinf=0.0, neginf=0.0)

        device = torch.device("cpu")
        model = _NeuralAdditiveModel(
            factor_count=len(factor_feature_names),
            context_count=len(context_feature_names),
            hidden_width=int(Config.OPTIONS_INTRADAY_NEURAL_HIDDEN_WIDTH),
        ).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=float(Config.OPTIONS_INTRADAY_NEURAL_LEARNING_RATE),
            weight_decay=float(Config.OPTIONS_INTRADAY_NEURAL_WEIGHT_DECAY),
        )
        criterion = nn.HuberLoss(delta=0.75, reduction="none")

        train_factor_tensor = torch.tensor(x_factor_train, dtype=torch.float32, device=device)
        train_context_tensor = torch.tensor(x_context_train, dtype=torch.float32, device=device)
        train_target_tensor = torch.tensor(y_train, dtype=torch.float32, device=device)
        train_weight_tensor = torch.tensor(weight_train, dtype=torch.float32, device=device)
        test_factor_tensor = torch.tensor(x_factor_test, dtype=torch.float32, device=device)
        test_context_tensor = torch.tensor(x_context_test, dtype=torch.float32, device=device)
        test_target_tensor = torch.tensor(y_test, dtype=torch.float32, device=device)

        best_state = deepcopy(model.state_dict())
        best_val_loss = float("inf")
        best_epoch = -1
        patience_counter = 0
        batch_size = max(8, int(Config.OPTIONS_INTRADAY_NEURAL_BATCH_SIZE))
        epochs = max(20, int(Config.OPTIONS_INTRADAY_NEURAL_EPOCHS))
        patience = max(8, int(Config.OPTIONS_INTRADAY_NEURAL_PATIENCE))

        for epoch in range(epochs):
            model.train()
            permutation = torch.randperm(len(train_factor_tensor), device=device)
            for start in range(0, len(permutation), batch_size):
                batch_index = permutation[start:start + batch_size]
                optimizer.zero_grad(set_to_none=True)
                batch_pred = model(
                    train_factor_tensor[batch_index],
                    train_context_tensor[batch_index] if len(context_feature_names) else None,
                )
                batch_loss = criterion(batch_pred, train_target_tensor[batch_index])
                batch_loss = (batch_loss * train_weight_tensor[batch_index]).mean()
                batch_loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
                optimizer.step()

            model.eval()
            with torch.no_grad():
                val_pred = model(
                    test_factor_tensor,
                    test_context_tensor if len(context_feature_names) else None,
                )
                val_loss = float(criterion(val_pred, test_target_tensor).mean().item())
            if val_loss + 1e-8 < best_val_loss:
                best_val_loss = val_loss
                best_state = deepcopy(model.state_dict())
                best_epoch = epoch
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    break

        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            test_pred_tensor, test_factor_contrib_tensor, _ = model(
                test_factor_tensor,
                test_context_tensor if len(context_feature_names) else None,
                return_contributions=True,
            )
            train_pred_tensor = model(
                train_factor_tensor,
                train_context_tensor if len(context_feature_names) else None,
            )
        y_pred_test = test_pred_tensor.detach().cpu().numpy()
        y_pred_train = train_pred_tensor.detach().cpu().numpy()
        factor_contrib_test = test_factor_contrib_tensor.detach().cpu().numpy()

        latest_frame = pd.concat([train.tail(1), test.tail(1)], ignore_index=True).tail(1)
        latest_factor_array = self._robust_scaler_transform(
            latest_frame,
            factor_feature_names,
            factor_medians,
            factor_scales,
        )
        latest_context_array = self._robust_scaler_transform(
            latest_frame,
            context_feature_names,
            context_medians,
            context_scales,
        )
        latest_factor_tensor = torch.tensor(latest_factor_array, dtype=torch.float32, device=device, requires_grad=True)
        latest_context_tensor = torch.tensor(latest_context_array, dtype=torch.float32, device=device)
        latest_pred_tensor, latest_factor_contrib_tensor, latest_context_contrib_tensor = model(
            latest_factor_tensor,
            latest_context_tensor if len(context_feature_names) else None,
            return_contributions=True,
        )
        latest_pred_tensor.backward(torch.ones_like(latest_pred_tensor))
        latest_gradients = latest_factor_tensor.grad.detach().cpu().numpy()[0]
        latest_factor_contrib = latest_factor_contrib_tensor.detach().cpu().numpy()[0]
        latest_context_contrib = (
            float(latest_context_contrib_tensor.detach().cpu().numpy()[0][0])
            if latest_context_contrib_tensor is not None
            else 0.0
        )

        feature_importance = np.mean(np.abs(factor_contrib_test), axis=0) if len(factor_contrib_test) else np.zeros(len(factor_feature_names))
        return {
            "enabled": True,
            "status": "trained",
            "model": model,
            "best_epoch": best_epoch,
            "best_val_loss": best_val_loss,
            "factor_feature_names": factor_feature_names,
            "context_feature_names": context_feature_names,
            "factor_scaler": {"medians": factor_medians, "scales": factor_scales},
            "context_scaler": {"medians": context_medians, "scales": context_scales},
            "train_metrics": {
                "rmse_return": _rmse(y_train, y_pred_train),
                "mae_return": _mae(y_train, y_pred_train),
                "directional_accuracy": _directional_accuracy(y_train, y_pred_train),
            },
            "test_metrics": {
                "rmse_return": _rmse(y_test, y_pred_test),
                "mae_return": _mae(y_test, y_pred_test),
                "directional_accuracy": _directional_accuracy(y_test, y_pred_test),
                "corr": float(np.corrcoef(y_test, y_pred_test)[0, 1]) if len(y_pred_test) > 1 and float(np.std(y_pred_test)) > 1e-9 and float(np.std(y_test)) > 1e-9 else 0.0,
            },
            "test_predictions": y_pred_test,
            "latest_prediction_return": float(latest_pred_tensor.detach().cpu().numpy()[0]),
            "latest_factor_contributions_return": {
                factor_name: float(latest_factor_contrib[index])
                for index, factor_name in enumerate(factor_feature_names)
            },
            "latest_factor_sensitivities": {
                factor_name: float(latest_gradients[index])
                for index, factor_name in enumerate(factor_feature_names)
            },
            "latest_context_contribution_return": latest_context_contrib,
            "feature_importance_abs_return": {
                factor_name: float(feature_importance[index])
                for index, factor_name in enumerate(factor_feature_names)
            },
        }

    def _history_rows(
        self,
        dataset: pd.DataFrame,
        y_pred_test: np.ndarray,
        *,
        history_limit: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if len(dataset.index) == 0 or len(y_pred_test) == 0:
            return rows
        tail = dataset.tail(min(len(y_pred_test), history_limit)).copy()
        pred_tail = y_pred_test[-len(tail.index):]
        for (_, row), pred in zip(tail.iterrows(), pred_tail):
            xb1_last = _safe_float(row.get("xb1_last"), 0.0) or 0.0
            rows.append({
                "timestamp": row.get("timestamp").isoformat() if hasattr(row.get("timestamp"), "isoformat") else row.get("timestamp"),
                "session_date": row.get("session_date"),
                "xb1_last": _safe_float(row.get("xb1_last")),
                "actual_return": _safe_float(row.get("target_return")),
                "predicted_return": float(pred),
                "actual_move_points": xb1_last * (_safe_float(row.get("target_return"), 0.0) or 0.0),
                "predicted_move_points": xb1_last * float(pred),
                "coverage_ratio": _safe_float(row.get("coverage_ratio")),
            })
        return rows

    def _payload_for_horizon(
        self,
        *,
        observed_frame: pd.DataFrame,
        factor_meta: dict[str, dict[str, Any]],
        horizon_minutes: int,
        include_history: bool,
    ) -> dict[str, Any]:
        dataset, candidate_factors = self._dataset_for_horizon(
            observed_frame=observed_frame,
            factor_meta=factor_meta,
            horizon_minutes=horizon_minutes,
        )
        if dataset.empty or len(dataset.index) < max(int(Config.OPTIONS_INTRADAY_NEURAL_MIN_ROWS), 24):
            return {
                "horizon_minutes": horizon_minutes,
                "enabled": False,
                "status": "insufficient_history",
                "row_count": int(len(dataset.index)),
                "factor_count": len(candidate_factors),
            }

        train, test = self._split_train_test(dataset)
        context_feature_names = ["time_sin", "time_cos"]
        selected_factors = self._select_trainable_factors(train, test, candidate_factors)
        if not selected_factors:
            return {
                "horizon_minutes": horizon_minutes,
                "enabled": False,
                "status": "insufficient_trainable_factors",
                "row_count": int(len(dataset.index)),
                "factor_count": 0,
            }
        factor_medians, factor_scales = self._robust_scaler_fit(train, selected_factors)
        context_medians, context_scales = self._robust_scaler_fit(train, context_feature_names)
        x_train_factors = self._robust_scaler_transform(train, selected_factors, factor_medians, factor_scales)
        x_train_context = self._robust_scaler_transform(train, context_feature_names, context_medians, context_scales)
        x_test_factors = self._robust_scaler_transform(test, selected_factors, factor_medians, factor_scales)
        x_test_context = self._robust_scaler_transform(test, context_feature_names, context_medians, context_scales)
        y_train = pd.to_numeric(train["target_return"], errors="coerce").to_numpy(dtype=float)
        y_test = pd.to_numeric(test["target_return"], errors="coerce").to_numpy(dtype=float)

        baseline = self._fit_linear_baseline(
            x_train=np.concatenate([x_train_factors, x_train_context], axis=1),
            y_train=y_train,
            x_test=np.concatenate([x_test_factors, x_test_context], axis=1),
            y_test=y_test,
        )
        neural = self._fit_neural_additive_model(
            factor_feature_names=selected_factors,
            context_feature_names=context_feature_names,
            train=train,
            test=test,
        )
        if not neural.get("enabled"):
            return {
                "horizon_minutes": horizon_minutes,
                "enabled": False,
                "status": neural.get("status") or "training_unavailable",
                "row_count": int(len(dataset.index)),
                "factor_count": len(selected_factors),
            }

        latest_row = dataset.iloc[-1]
        latest_xb1 = _safe_float(latest_row.get("xb1_last"), 0.0) or 0.0
        latest_prediction_return = float(neural.get("latest_prediction_return") or 0.0)
        latest_prediction_points = latest_xb1 * latest_prediction_return
        factor_contrib_return = dict(neural.get("latest_factor_contributions_return") or {})
        feature_importance = dict(neural.get("feature_importance_abs_return") or {})
        sensitivities = dict(neural.get("latest_factor_sensitivities") or {})
        contribution_rows = []
        for factor_name in selected_factors:
            meta = factor_meta.get(factor_name) or {}
            contribution_return = float(factor_contrib_return.get(factor_name) or 0.0)
            contribution_points = latest_xb1 * contribution_return
            contribution_rows.append({
                "factor": factor_name,
                "label": meta.get("label") or factor_name,
                "block": meta.get("block"),
                "asset_class": meta.get("asset_class"),
                "subclass": meta.get("subclass"),
                "expected_direction_to_ibov": meta.get("expected_direction_to_ibov"),
                "contribution_return": contribution_return,
                "contribution_points": contribution_points,
                "abs_importance_return": float(feature_importance.get(factor_name) or 0.0),
                "local_sensitivity": float(sensitivities.get(factor_name) or 0.0),
            })
        contribution_rows.sort(key=lambda item: abs(float(item.get("contribution_points") or 0.0)), reverse=True)

        baseline_rmse = float((baseline or {}).get("rmse_return") or 0.0)
        neural_rmse = float(((neural.get("test_metrics") or {}).get("rmse_return")) or 0.0)
        rmse_gain = (
            (baseline_rmse - neural_rmse) / baseline_rmse
            if baseline_rmse > 1e-9
            else 0.0
        )

        payload = {
            "horizon_minutes": horizon_minutes,
            "enabled": True,
            "status": "trained",
            "row_count": int(len(dataset.index)),
            "train_row_count": int(len(train.index)),
            "test_row_count": int(len(test.index)),
            "factor_count": len(selected_factors),
            "selected_factors": selected_factors,
            "baseline_linear": baseline,
            "neural_metrics": neural.get("test_metrics") or {},
            "train_metrics": neural.get("train_metrics") or {},
            "best_epoch": neural.get("best_epoch"),
            "best_val_loss": neural.get("best_val_loss"),
            "nonlinearity_gain_rmse": rmse_gain,
            "latest_prediction": {
                "timestamp": latest_row.get("timestamp").isoformat() if hasattr(latest_row.get("timestamp"), "isoformat") else latest_row.get("timestamp"),
                "session_date": latest_row.get("session_date"),
                "xb1_last": latest_xb1,
                "predicted_return": latest_prediction_return,
                "predicted_move_points": latest_prediction_points,
                "context_contribution_return": float(neural.get("latest_context_contribution_return") or 0.0),
                "coverage_ratio": _safe_float(latest_row.get("coverage_ratio")),
            },
            "factor_contributions": contribution_rows,
        }
        if include_history:
            payload["prediction_history"] = self._history_rows(
                test.assign(timestamp=test["timestamp"] if "timestamp" in test.columns else pd.NaT),
                neural.get("test_predictions") or np.array([]),
                history_limit=120,
            )
        return payload

    def build_payload(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        horizon_minutes: int | None = None,
        include_history: bool = False,
    ) -> dict[str, Any]:
        if torch is None or nn is None:
            return {
                "underlying_security": underlying_security,
                "enabled": False,
                "status": "torch_unavailable",
            }

        snapshots, selected_sessions = self._load_training_snapshots(underlying_security)
        observed_frame, factor_meta = self._build_training_frame(snapshots)
        if observed_frame.empty:
            return {
                "underlying_security": underlying_security,
                "enabled": False,
                "status": "no_intraday_snapshots",
            }

        horizons = sorted({
            int(horizon_minutes)
        }) if horizon_minutes else sorted({
            int(value)
            for value in (Config.OPTIONS_INTRADAY_DEPENDENCY_HORIZONS or [1, 5, 15])
            if int(value) > 0
        })

        horizon_payloads: dict[str, Any] = {}
        for horizon in horizons:
            horizon_payloads[f"{int(horizon)}m"] = self._payload_for_horizon(
                observed_frame=observed_frame,
                factor_meta=factor_meta,
                horizon_minutes=int(horizon),
                include_history=include_history,
            )

        return {
            "underlying_security": underlying_security,
            "enabled": True,
            "status": "trained" if any((item or {}).get("enabled") for item in horizon_payloads.values()) else "insufficient_history",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "selected_sessions": selected_sessions,
            "snapshot_count": int(len(snapshots)),
            "observed_row_count": int(len(observed_frame.index)),
            "horizons": horizon_payloads,
        }
