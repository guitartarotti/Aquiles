from __future__ import annotations

import copy
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ...config import Config
from ...utils.logger import get_logger
from ..macro_options_heatmap_context_service import MacroOptionsHeatmapContextService
from ..options_store import OptionsStore
from .intraday_dependency_service import IntradayDependencyService
from .intraday_neural_model_service import IntradayNeuralModelService

try:
    import torch
    from torch import nn
except Exception:  # pragma: no cover - handled at runtime
    torch = None
    nn = None


logger = get_logger("mirofish.options_fair_value.intraday_correlation_history")
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


def _rolling_corr(sample: pd.DataFrame, method: str) -> float | None:
    if len(sample.index) < 2:
        return None
    corr = sample["x"].corr(sample["y"], method=method)
    return _safe_float(corr)


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


class _SingleFactorNeuralRegressor(nn.Module):
    def __init__(self, hidden_width: int) -> None:
        super().__init__()
        width = max(int(hidden_width), 4)
        self.linear = nn.Linear(1, 1, bias=False)
        self.factor_net = nn.Sequential(
            nn.Linear(1, width),
            nn.SiLU(),
            nn.Linear(width, width),
            nn.SiLU(),
            nn.Linear(width, 1),
        )
        self.context_net = nn.Sequential(
            nn.Linear(2, width),
            nn.SiLU(),
            nn.Linear(width, max(width // 2, 2)),
            nn.SiLU(),
            nn.Linear(max(width // 2, 2), 1),
        )
        self.bias = nn.Parameter(torch.zeros(1))

    def forward(self, factor_inputs, context_inputs, *, return_parts: bool = False):
        linear_term = self.linear(factor_inputs)
        nonlinear_term = self.factor_net(factor_inputs)
        context_term = self.context_net(context_inputs)
        total = linear_term + nonlinear_term + context_term + self.bias
        if return_parts:
            return total.squeeze(-1), (linear_term + nonlinear_term), context_term
        return total.squeeze(-1)


class IntradayCorrelationHistoryService:
    _payload_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
    _payload_cache_ttl_seconds = 90.0
    _schema_version = "v2_full_asset_universe"

    def __init__(
        self,
        *,
        store: OptionsStore | None = None,
        context_service: MacroOptionsHeatmapContextService | None = None,
        dependency_service: IntradayDependencyService | None = None,
        neural_service: IntradayNeuralModelService | None = None,
    ) -> None:
        self.store = store or OptionsStore()
        self.context_service = context_service or MacroOptionsHeatmapContextService()
        self.dependency_service = dependency_service or IntradayDependencyService(
            store=self.store,
            context_service=self.context_service,
        )
        self.neural_service = neural_service or IntradayNeuralModelService(
            store=self.store,
            context_service=self.context_service,
            dependency_service=self.dependency_service,
        )

    @classmethod
    def _cache_key(
        cls,
        *,
        underlying_security: str,
        lookback_days: int,
        horizon_minutes: int,
        factors: list[str],
        modes: list[str],
    ) -> tuple[Any, ...]:
        return (
            str(underlying_security or "").strip().upper(),
            int(lookback_days),
            int(horizon_minutes),
            tuple(sorted({str(value or "").strip() for value in factors if str(value or "").strip()})),
            tuple(modes),
        )

    @classmethod
    def _read_cached_payload(cls, cache_key: tuple[Any, ...]) -> dict[str, Any] | None:
        cached = cls._payload_cache.get(cache_key)
        if not cached:
            return None
        cached_at, payload = cached
        if (time.monotonic() - cached_at) > cls._payload_cache_ttl_seconds:
            cls._payload_cache.pop(cache_key, None)
            return None
        return copy.deepcopy(payload)

    @classmethod
    def _write_cached_payload(cls, cache_key: tuple[Any, ...], payload: dict[str, Any]) -> None:
        cls._payload_cache[cache_key] = (time.monotonic(), copy.deepcopy(payload))

    def _latest_context_watermark(self, underlying_security: str) -> dict[str, Any]:
        state = self.context_service.read_state()
        history = state.get("live_capture_history") or {}
        latest_session_date = str(history.get("current_session_date") or "").strip()
        latest_captured_at = ""
        latest_captured_dt: datetime | None = None
        sample_count = 0
        for raw_snapshot in (history.get("snapshots") or []):
            snapshot = dict(raw_snapshot or {})
            if str(snapshot.get("underlying_security") or underlying_security) != underlying_security:
                continue
            if not self.dependency_service._snapshot_has_observed_values(snapshot):
                continue
            captured_at = str(snapshot.get("captured_at") or "").strip()
            captured_dt = _parse_iso(captured_at)
            session_date = str(snapshot.get("session_date") or "").strip()
            if not session_date:
                continue
            sample_count += 1
            if not latest_session_date or session_date > latest_session_date:
                latest_session_date = session_date
            if captured_dt is not None and (latest_captured_dt is None or captured_dt > latest_captured_dt):
                latest_captured_dt = captured_dt
                latest_captured_at = captured_at
        return {
            "session_date": latest_session_date,
            "captured_at": latest_captured_at,
            "captured_at_dt": latest_captured_dt,
            "sample_count": sample_count,
        }

    @classmethod
    def _payload_latest_series_dt(cls, payload: dict[str, Any] | None) -> datetime | None:
        payload = payload or {}
        explicit = _parse_iso(payload.get("series_latest_timestamp"))
        if explicit is not None:
            return explicit
        latest_dt: datetime | None = None
        for series in (payload.get("series") or []):
            for point in (series.get("points") or []):
                point_dt = _parse_iso((point or {}).get("timestamp"))
                if point_dt is not None and (latest_dt is None or point_dt > latest_dt):
                    latest_dt = point_dt
        return latest_dt

    @classmethod
    def _payload_is_stale_for_context(cls, payload: dict[str, Any] | None, watermark: dict[str, Any]) -> bool:
        if not payload:
            return False
        if str(payload.get("schema_version") or "").strip() != cls._schema_version:
            return True
        context_session_date = str((watermark or {}).get("session_date") or "").strip()
        context_captured_dt = (watermark or {}).get("captured_at_dt")
        context_sample_count = int((watermark or {}).get("sample_count") or 0)
        if not context_session_date or context_sample_count <= 0:
            return False
        payload_session_date = str(payload.get("session_date") or "").strip()
        if payload_session_date < context_session_date:
            return True
        payload_captured_dt = (
            _parse_iso(payload.get("captured_at"))
            or _parse_iso(payload.get("generated_at"))
        )
        payload_latest_series_dt = cls._payload_latest_series_dt(payload)
        payload_effective_dt = payload_latest_series_dt or payload_captured_dt
        horizon_minutes = max(int(payload.get("horizon_minutes") or 1), 1)
        stale_after_seconds = max(
            float(max(int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS), 60)) * 4.0,
            float(horizon_minutes) * 60.0 * 2.25,
        )
        return (
            payload_session_date == context_session_date
            and context_captured_dt is not None
            and payload_effective_dt is not None
            and (context_captured_dt - payload_effective_dt).total_seconds() >= stale_after_seconds
        )

    @staticmethod
    def _normalize_modes(modes: list[str] | None) -> list[str]:
        allowed = {"pure", "neural"}
        normalized = []
        for value in modes or ["pure", "neural"]:
            key = str(value or "").strip().lower()
            if key in allowed and key not in normalized:
                normalized.append(key)
        return normalized or ["pure", "neural"]

    @staticmethod
    def _normalize_factors(factors: list[str] | None) -> list[str]:
        return [
            str(value or "").strip()
            for value in (factors or [])
            if str(value or "").strip()
        ]

    @classmethod
    def _factors_signature(cls, factors: list[str]) -> str:
        if not factors:
            return f"{cls._schema_version}__default__"
        ordered = sorted({str(value or "").strip() for value in factors if str(value or "").strip()})
        suffix = "__".join(ordered) if ordered else "__default__"
        return f"{cls._schema_version}__{suffix}"

    @staticmethod
    def _modes_signature(modes: list[str]) -> str:
        ordered = sorted({str(value or "").strip().lower() for value in modes if str(value or "").strip()})
        return "__".join(ordered) if ordered else "pure__neural"

    @classmethod
    def _project_payload_modes(cls, payload: dict[str, Any], modes: list[str]) -> dict[str, Any]:
        projected = copy.deepcopy(payload or {})
        allowed_modes = {str(value or "").strip().lower() for value in modes if str(value or "").strip()}
        raw_series = projected.get("series") or []
        projected["series"] = [
            dict(item or {})
            for item in raw_series
            if str((item or {}).get("mode") or "pure").strip().lower() in allowed_modes
        ]
        projected["request_modes"] = list(modes)
        projected["modes"] = list(modes)
        projected["modes_signature"] = cls._modes_signature(modes)
        projected["schema_version"] = cls._schema_version
        projected["status"] = "ready" if projected.get("series") else "insufficient_history"
        return projected

    @staticmethod
    def _build_run_id(underlying_security: str, lookback_days: int, horizon_minutes: int) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        base = str(underlying_security or "underlying").strip().upper().replace(" ", "_")
        return f"intraday-correlation-{base}-d{int(lookback_days)}-h{int(horizon_minutes)}-{stamp}"

    def _load_snapshots(
        self,
        *,
        underlying_security: str,
        lookback_days: int,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        snapshots, session_dates = self.neural_service._load_training_snapshots(underlying_security)
        unique_dates = [
            value
            for value in sorted({
                str(snapshot.get("session_date") or "").strip()
                for snapshot in snapshots
                if str(snapshot.get("session_date") or "").strip()
            }, reverse=True)
        ]
        scoped_dates = unique_dates[:max(1, min(int(lookback_days), 3))]
        scoped_set = set(scoped_dates)
        filtered = [
            dict(snapshot or {})
            for snapshot in snapshots
            if str(snapshot.get("session_date") or "").strip() in scoped_set
        ]
        filtered.sort(key=lambda item: str(item.get("captured_at") or ""))
        return filtered, sorted(scoped_dates)

    def _build_dataset(
        self,
        *,
        underlying_security: str,
        lookback_days: int,
        horizon_minutes: int,
    ) -> tuple[pd.DataFrame, dict[str, dict[str, Any]], list[str], list[str]]:
        snapshots, selected_sessions = self._load_snapshots(
            underlying_security=underlying_security,
            lookback_days=lookback_days,
        )
        if not snapshots:
            return pd.DataFrame(), {}, [], []
        observed_frame, factor_meta = self.neural_service._build_training_frame(snapshots)
        if observed_frame.empty:
            return pd.DataFrame(), factor_meta, selected_sessions, []
        bar_frequency = f"{int(horizon_minutes)}min"
        factor_names = sorted(factor_meta.keys())
        session_datasets: list[pd.DataFrame] = []
        factor_non_null_counts: dict[str, int] = {factor: 0 for factor in factor_names}
        if "session_date" not in observed_frame.columns:
            return pd.DataFrame(), factor_meta, selected_sessions, []

        for session_date, session_frame in observed_frame.groupby("session_date"):
            if not session_date:
                continue
            session_frame = session_frame.sort_index()
            price_bar = session_frame["xb1_last"].resample(bar_frequency).last().dropna()
            if len(price_bar.index) < 2:
                continue
            context_frame = self.neural_service._time_features(price_bar.index)
            feature_columns: dict[str, pd.Series] = {}
            for factor in factor_names:
                raw_column = f"raw__{factor}"
                if raw_column not in session_frame.columns:
                    continue
                meta = factor_meta.get(factor) or {}
                raw_bar = session_frame[raw_column].resample(bar_frequency).last().reindex(price_bar.index)
                move = self.dependency_service._bar_move(raw_bar, str(meta.get("transform") or "return"))
                move = move * float(meta.get("direction_multiplier") or 1.0)
                feature_columns[factor] = move
                factor_non_null_counts[factor] += int(move.notna().sum())
            target_forward = np.log(price_bar.shift(-1) / price_bar)
            feature_frame = (
                pd.DataFrame(feature_columns, index=price_bar.index)
                if feature_columns
                else pd.DataFrame(index=price_bar.index)
            )
            coverage_ratio = (
                feature_frame.notna().mean(axis=1)
                if feature_columns
                else pd.Series(0.0, index=price_bar.index, dtype="float64")
            )
            session_dataset = pd.DataFrame(
                {
                    "timestamp": price_bar.index,
                    "session_date": session_date,
                    "xb1_last": pd.to_numeric(price_bar, errors="coerce"),
                    "target_return": pd.to_numeric(target_forward, errors="coerce"),
                    "coverage_ratio": pd.to_numeric(coverage_ratio, errors="coerce").fillna(0.0),
                    "time_sin": pd.to_numeric(context_frame["time_sin"], errors="coerce").reindex(price_bar.index).fillna(0.0),
                    "time_cos": pd.to_numeric(context_frame["time_cos"], errors="coerce").reindex(price_bar.index).fillna(0.0),
                },
                index=price_bar.index,
            )
            if feature_columns:
                session_dataset = pd.concat([session_dataset, feature_frame], axis=1)
            session_datasets.append(session_dataset.reset_index(drop=True))

        dataset = pd.concat(session_datasets, ignore_index=True) if session_datasets else pd.DataFrame()
        if dataset.empty:
            return pd.DataFrame(), factor_meta, selected_sessions, []
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
            return pd.DataFrame(), factor_meta, selected_sessions, []

        dataset = self.neural_service._filter_informative_sessions(dataset, factor_names, horizon_minutes)
        if dataset.empty:
            return pd.DataFrame(), factor_meta, selected_sessions, []

        minimum_factor_points = max(4, min(8, len(dataset.index)))
        candidate_factors = [
            factor
            for factor in factor_names
            if factor_non_null_counts.get(factor, 0) >= minimum_factor_points
            and float(pd.to_numeric(dataset[factor], errors="coerce").std(skipna=True) or 0.0) > 1e-12
        ]
        dataset = dataset.sort_values("timestamp").reset_index(drop=True)
        return dataset, factor_meta, selected_sessions, candidate_factors

    @staticmethod
    def _window_points(horizon_minutes: int, row_count: int) -> tuple[int, int]:
        rolling_minutes = max(int(Config.OPTIONS_INTRADAY_DEPENDENCY_ROLLING_WINDOW_MINUTES), int(horizon_minutes))
        window_points = max(4, int(math.ceil(rolling_minutes / max(int(horizon_minutes), 1))))
        window_points = min(window_points, max(row_count, 1))
        min_points = max(4, min(window_points, 6))
        return window_points, min_points

    def _build_pure_factor_series(
        self,
        *,
        dataset: pd.DataFrame,
        factor: str,
        factor_meta: dict[str, Any],
        horizon_minutes: int,
        include_points: bool,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if factor not in dataset.columns:
            return None, []
        scoped = dataset[["timestamp", "session_date", "xb1_last", "target_return", factor]].copy()
        scoped = scoped.rename(columns={factor: "factor_move"})
        scoped = scoped.dropna(subset=["timestamp", "target_return", "factor_move"])
        if len(scoped.index) < 4:
            return None, []

        window_points, min_points = self._window_points(horizon_minutes, len(scoped.index))
        scoped = scoped.reset_index(drop=True)
        factor_move = pd.to_numeric(scoped["factor_move"], errors="coerce")
        target_return = pd.to_numeric(scoped["target_return"], errors="coerce")
        pearson_series = factor_move.rolling(window_points, min_periods=min_points).corr(target_return)
        sample_count_series = pd.Series(
            np.minimum(np.arange(1, len(scoped.index) + 1), window_points),
            index=scoped.index,
            dtype="int64",
        )
        valid_latest = pearson_series.dropna()
        if valid_latest.empty:
            return None, []

        tail_sample = pd.DataFrame({"x": factor_move, "y": target_return}).tail(window_points).dropna(subset=["x", "y"])
        latest_spearman_corr = _rolling_corr(tail_sample, "spearman") if len(tail_sample.index) >= min_points else None
        latest_index = int(valid_latest.index[-1])
        latest_corr = _safe_float(valid_latest.iloc[-1])
        latest_point = {
            "timestamp": scoped.iloc[latest_index]["timestamp"].isoformat() if hasattr(scoped.iloc[latest_index]["timestamp"], "isoformat") else scoped.iloc[latest_index]["timestamp"],
            "session_date": str(scoped.iloc[latest_index]["session_date"] or ""),
            "xb1_last": _safe_float(scoped.iloc[latest_index]["xb1_last"]),
            "target_return": _safe_float(scoped.iloc[latest_index]["target_return"]),
            "factor_move": _safe_float(scoped.iloc[latest_index]["factor_move"]),
            "value": latest_corr,
            "pearson_corr": latest_corr,
            "spearman_corr": latest_spearman_corr,
            "sample_count": int(sample_count_series.iloc[latest_index]),
        }

        points: list[dict[str, Any]] = []
        if include_points:
            point_frame = pd.DataFrame(
                {
                    "timestamp": scoped["timestamp"],
                    "session_date": scoped["session_date"],
                    "xb1_last": pd.to_numeric(scoped["xb1_last"], errors="coerce"),
                    "target_return": target_return,
                    "factor_move": factor_move,
                    "pearson_corr": pearson_series,
                    "sample_count": sample_count_series,
                }
            )
            for _, row in point_frame.iterrows():
                pearson_corr = _safe_float(row.get("pearson_corr"))
                timestamp = row.get("timestamp")
                points.append({
                    "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
                    "session_date": str(row.get("session_date") or ""),
                    "xb1_last": _safe_float(row.get("xb1_last")),
                    "target_return": _safe_float(row.get("target_return")),
                    "factor_move": _safe_float(row.get("factor_move")),
                    "value": pearson_corr,
                    "pearson_corr": pearson_corr,
                    "spearman_corr": None,
                    "sample_count": int(row.get("sample_count") or 0),
                })

        summary = {
            "factor": factor,
            "label": factor_meta.get("label") or factor,
            "block": factor_meta.get("block"),
            "asset_class": factor_meta.get("asset_class"),
            "subclass": factor_meta.get("subclass"),
            "mode": "pure",
            "window_points": window_points,
            "window_minutes": window_points * max(int(horizon_minutes), 1),
            "row_count": int(len(scoped.index)),
            "latest_value": _safe_float(latest_point.get("value")),
            "latest_pearson_corr": _safe_float(latest_point.get("pearson_corr")),
            "latest_spearman_corr": _safe_float(latest_spearman_corr),
            "latest_sample_count": int(latest_point.get("sample_count") or 0),
        }
        return summary, points

    def _fit_single_factor_neural(
        self,
        *,
        dataset: pd.DataFrame,
        factor: str,
    ) -> dict[str, Any]:
        if torch is None or nn is None:
            return {"enabled": False, "status": "torch_unavailable"}
        if factor not in dataset.columns:
            return {"enabled": False, "status": "factor_unavailable"}

        scoped = dataset[["timestamp", "session_date", "xb1_last", "target_return", "coverage_ratio", "time_sin", "time_cos", factor]].copy()
        scoped = scoped.rename(columns={factor: "factor_move"})
        scoped = scoped.dropna(subset=["timestamp", "target_return", "factor_move", "time_sin", "time_cos"])
        if len(scoped.index) < 8:
            return {
                "enabled": False,
                "status": "insufficient_rows",
                "row_count": int(len(scoped.index)),
            }

        factor_medians, factor_scales = self.neural_service._robust_scaler_fit(scoped, ["factor_move"])
        context_medians, context_scales = self.neural_service._robust_scaler_fit(scoped, ["time_sin", "time_cos"])
        x_factor = self.neural_service._robust_scaler_transform(scoped, ["factor_move"], factor_medians, factor_scales)
        x_context = self.neural_service._robust_scaler_transform(scoped, ["time_sin", "time_cos"], context_medians, context_scales)
        y = pd.to_numeric(scoped["target_return"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        y_series = pd.Series(y)
        y_scale = float((y_series - y_series.median()).abs().median() or 0.0) * 1.4826
        if not math.isfinite(y_scale) or y_scale <= 1e-6:
            y_scale = float(y_series.std(ddof=0) or 1.0)
        if not math.isfinite(y_scale) or y_scale <= 1e-6:
            y_scale = 1.0
        y_scaled = y / y_scale
        weights = self.neural_service._build_sample_weights(scoped)

        device = torch.device("cpu")
        model = _SingleFactorNeuralRegressor(int(Config.OPTIONS_INTRADAY_NEURAL_HIDDEN_WIDTH)).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=float(Config.OPTIONS_INTRADAY_NEURAL_LEARNING_RATE),
            weight_decay=float(Config.OPTIONS_INTRADAY_NEURAL_WEIGHT_DECAY),
        )
        criterion = nn.HuberLoss(delta=0.75, reduction="none")

        factor_tensor = torch.tensor(x_factor, dtype=torch.float32, device=device)
        context_tensor = torch.tensor(x_context, dtype=torch.float32, device=device)
        target_tensor = torch.tensor(y_scaled, dtype=torch.float32, device=device)
        weight_tensor = torch.tensor(weights, dtype=torch.float32, device=device)

        best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        best_loss = float("inf")
        patience_counter = 0
        epochs = min(max(36, int(Config.OPTIONS_INTRADAY_NEURAL_EPOCHS)), 160)
        patience = min(max(8, int(Config.OPTIONS_INTRADAY_NEURAL_PATIENCE)), 24)
        batch_size = min(max(8, int(Config.OPTIONS_INTRADAY_NEURAL_BATCH_SIZE)), max(len(scoped.index), 8))

        for _ in range(epochs):
            model.train()
            permutation = torch.randperm(len(factor_tensor), device=device)
            for start in range(0, len(permutation), batch_size):
                batch_index = permutation[start:start + batch_size]
                optimizer.zero_grad(set_to_none=True)
                prediction = model(factor_tensor[batch_index], context_tensor[batch_index])
                loss = criterion(prediction, target_tensor[batch_index])
                loss = (loss * weight_tensor[batch_index]).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
                optimizer.step()
            model.eval()
            with torch.no_grad():
                full_pred = model(factor_tensor, context_tensor)
                full_loss = float((criterion(full_pred, target_tensor) * weight_tensor).mean().item())
            if full_loss + 1e-8 < best_loss:
                best_loss = full_loss
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    break

        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            pred_tensor, factor_contrib_tensor, _ = model(
                factor_tensor,
                context_tensor,
                return_parts=True,
            )
        prediction_scaled = pred_tensor.detach().cpu().numpy()
        contribution_scaled = factor_contrib_tensor.detach().cpu().numpy()[:, 0]
        prediction = prediction_scaled * y_scale
        contribution = contribution_scaled * y_scale

        grad_factor_tensor = torch.tensor(x_factor, dtype=torch.float32, device=device, requires_grad=True)
        grad_context_tensor = torch.tensor(x_context, dtype=torch.float32, device=device)
        grad_pred = model(grad_factor_tensor, grad_context_tensor)
        grad_pred.sum().backward()
        sensitivities = grad_factor_tensor.grad.detach().cpu().numpy()[:, 0]

        directional_accuracy = float(np.mean(np.sign(y) == np.sign(prediction))) if len(y) else 0.0
        rmse = float(np.sqrt(np.mean(np.square(y - prediction)))) if len(y) else 0.0
        corr = float(np.corrcoef(y, prediction)[0, 1]) if len(y) > 1 and float(np.std(y)) > 1e-9 and float(np.std(prediction)) > 1e-9 else 0.0

        return {
            "enabled": True,
            "status": "trained",
            "row_count": int(len(scoped.index)),
            "frame": scoped.reset_index(drop=True),
            "predicted_return": prediction,
            "factor_contribution_return": contribution,
            "local_sensitivity": sensitivities,
            "rmse_return": rmse,
            "directional_accuracy": directional_accuracy,
            "prediction_corr": corr,
        }

    def _build_neural_factor_series(
        self,
        *,
        dataset: pd.DataFrame,
        factor: str,
        factor_meta: dict[str, Any],
        horizon_minutes: int,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        fit_result = self._fit_single_factor_neural(dataset=dataset, factor=factor)
        if not fit_result.get("enabled"):
            return {
                "factor": factor,
                "label": factor_meta.get("label") or factor,
                "mode": "neural",
                "status": fit_result.get("status") or "training_unavailable",
                "row_count": int(fit_result.get("row_count") or 0),
            }, []

        scoped = fit_result["frame"]
        prediction = np.asarray(fit_result["predicted_return"], dtype=float)
        contribution = np.asarray(fit_result["factor_contribution_return"], dtype=float)
        sensitivities = np.asarray(fit_result["local_sensitivity"], dtype=float)
        window_points, min_points = self._window_points(horizon_minutes, len(scoped.index))

        points: list[dict[str, Any]] = []
        latest_point = None
        for index in range(len(scoped.index)):
            start = max(0, index - window_points + 1)
            sample = pd.DataFrame({
                "x": prediction[start:index + 1],
                "y": pd.to_numeric(scoped.iloc[start:index + 1]["target_return"], errors="coerce").fillna(0.0).to_numpy(dtype=float),
            })
            sample_count = int(len(sample.index))
            neural_corr = _rolling_corr(sample, "pearson") if sample_count >= min_points else None
            point = {
                "timestamp": scoped.iloc[index]["timestamp"].isoformat() if hasattr(scoped.iloc[index]["timestamp"], "isoformat") else scoped.iloc[index]["timestamp"],
                "session_date": str(scoped.iloc[index]["session_date"] or ""),
                "xb1_last": _safe_float(scoped.iloc[index]["xb1_last"]),
                "target_return": _safe_float(scoped.iloc[index]["target_return"]),
                "factor_move": _safe_float(scoped.iloc[index]["factor_move"]),
                "predicted_return": _safe_float(prediction[index]),
                "contribution_return": _safe_float(contribution[index]),
                "local_sensitivity": _safe_float(sensitivities[index]),
                "value": neural_corr,
                "sample_count": sample_count,
            }
            if neural_corr is not None:
                latest_point = point
            points.append(point)

        summary = {
            "factor": factor,
            "label": factor_meta.get("label") or factor,
            "block": factor_meta.get("block"),
            "asset_class": factor_meta.get("asset_class"),
            "subclass": factor_meta.get("subclass"),
            "mode": "neural",
            "status": "trained",
            "window_points": window_points,
            "window_minutes": window_points * max(int(horizon_minutes), 1),
            "row_count": int(fit_result.get("row_count") or 0),
            "latest_value": _safe_float((latest_point or {}).get("value")),
            "latest_sample_count": int((latest_point or {}).get("sample_count") or 0),
            "rmse_return": _safe_float(fit_result.get("rmse_return")),
            "directional_accuracy": _safe_float(fit_result.get("directional_accuracy")),
            "prediction_corr": _safe_float(fit_result.get("prediction_corr")),
        }
        return summary, points

    @classmethod
    def _merge_mode_payloads(
        cls,
        *,
        pure_payload: dict[str, Any] | None,
        neural_payload: dict[str, Any] | None,
        requested_modes: list[str],
    ) -> dict[str, Any] | None:
        pure_payload = dict(pure_payload or {})
        neural_payload = dict(neural_payload or {})
        if not pure_payload and not neural_payload:
            return None
        if "pure" not in requested_modes:
            return cls._project_payload_modes(neural_payload, requested_modes) if neural_payload else None
        if not pure_payload:
            return cls._project_payload_modes(neural_payload, requested_modes) if neural_payload else None

        merged = copy.deepcopy(pure_payload)
        if neural_payload and str(neural_payload.get("session_date") or "").strip() != str(pure_payload.get("session_date") or "").strip():
            neural_payload = {}
        neural_projected = (
            cls._project_payload_modes(neural_payload, ["neural"])
            if neural_payload
            else {"series": [], "training": {"neural": {}}}
        )
        selected_factors = {
            str(value or "").strip()
            for value in (merged.get("selected_factors") or [])
            if str(value or "").strip()
        }
        pure_series = [
            dict(item or {})
            for item in (merged.get("series") or [])
            if str((item or {}).get("mode") or "").strip().lower() == "pure"
        ]
        neural_series = [
            dict(item or {})
            for item in (neural_projected.get("series") or [])
            if not selected_factors or str((item or {}).get("factor") or "").strip() in selected_factors
        ]
        merged["series"] = pure_series + (neural_series if "neural" in requested_modes else [])
        neural_training = ((neural_projected.get("training") or {}).get("neural") or {}) if "neural" in requested_modes else {}
        merged["training"] = {"neural": neural_training}

        latest_neural_by_factor: dict[str, tuple[float | None, str]] = {}
        for factor, summary in neural_training.items():
            latest_neural_by_factor[str(factor or "").strip()] = (
                _safe_float((summary or {}).get("latest_value")),
                str((summary or {}).get("status") or ""),
            )

        updated_available = []
        for item in (merged.get("available_factors") or []):
            factor = str((item or {}).get("factor") or "").strip()
            latest_neural, neural_status = latest_neural_by_factor.get(factor, (None, ""))
            updated = dict(item or {})
            updated["latest_neural_correlation"] = latest_neural
            updated["neural_status"] = neural_status
            updated_available.append(updated)
        merged["available_factors"] = updated_available
        merged["request_modes"] = list(requested_modes)
        merged["modes"] = list(requested_modes)
        merged["modes_signature"] = cls._modes_signature(requested_modes)
        series_latest_dt = cls._payload_latest_series_dt({"series": merged.get("series") or []})
        merged["series_latest_timestamp"] = series_latest_dt.isoformat() if series_latest_dt is not None else None
        merged["status"] = "ready" if merged.get("series") else merged.get("status") or "insufficient_history"
        merged["generated_at"] = datetime.now(timezone.utc).isoformat()
        merged["captured_at"] = merged.get("captured_at") or merged["generated_at"]
        return merged

    def build_payload(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        lookback_days: int = 1,
        horizon_minutes: int = 5,
        factors: list[str] | None = None,
        modes: list[str] | None = None,
        bypass_cache: bool = False,
        prefer_persisted: bool = True,
        persist: bool = False,
    ) -> dict[str, Any]:
        resolved_modes = self._normalize_modes(modes)
        resolved_lookback_days = max(1, min(int(lookback_days), 3))
        resolved_horizon = max(1, int(horizon_minutes))
        resolved_factors = self._normalize_factors(factors)
        factors_signature = self._factors_signature(resolved_factors)
        modes_signature = self._modes_signature(resolved_modes)
        cache_key = self._cache_key(
            underlying_security=underlying_security,
            lookback_days=resolved_lookback_days,
            horizon_minutes=resolved_horizon,
            factors=resolved_factors,
            modes=resolved_modes,
        )
        context_watermark = self._latest_context_watermark(underlying_security)
        if not bypass_cache:
            cached_payload = self._read_cached_payload(cache_key)
            if cached_payload is not None and not self._payload_is_stale_for_context(cached_payload, context_watermark):
                return cached_payload
            if prefer_persisted:
                fresh_pure_payload = None
                if "pure" in resolved_modes:
                    fresh_pure_payload = self.store.read_latest_intraday_correlation_run(
                        underlying_security=underlying_security,
                        lookback_days=resolved_lookback_days,
                        horizon_minutes=resolved_horizon,
                        factors_signature=factors_signature,
                        modes_signature=self._modes_signature(["pure"]),
                    )
                    pure_matches_session = (
                        fresh_pure_payload
                        and str((fresh_pure_payload or {}).get("session_date") or "").strip()
                        == str((context_watermark or {}).get("session_date") or "").strip()
                    )
                    if fresh_pure_payload and not (
                        pure_matches_session
                        or not self._payload_is_stale_for_context(fresh_pure_payload, context_watermark)
                    ):
                        fresh_pure_payload = None
                persisted_payload = self.store.read_latest_intraday_correlation_run(
                    underlying_security=underlying_security,
                    lookback_days=resolved_lookback_days,
                    horizon_minutes=resolved_horizon,
                    factors_signature=factors_signature,
                    modes_signature=modes_signature,
                )
                persisted_matches_session = (
                    persisted_payload
                    and str((persisted_payload or {}).get("session_date") or "").strip()
                    == str((context_watermark or {}).get("session_date") or "").strip()
                )
                if persisted_payload and (
                    persisted_matches_session
                    or not self._payload_is_stale_for_context(persisted_payload, context_watermark)
                ):
                    if fresh_pure_payload and "pure" in resolved_modes:
                        fresh_pure_dt = self._payload_latest_series_dt(fresh_pure_payload)
                        persisted_dt = self._payload_latest_series_dt(persisted_payload)
                        if fresh_pure_dt is not None and (persisted_dt is None or fresh_pure_dt > persisted_dt):
                            merged_payload = self._merge_mode_payloads(
                                pure_payload=fresh_pure_payload,
                                neural_payload=persisted_payload,
                                requested_modes=resolved_modes,
                            )
                            if merged_payload:
                                self._write_cached_payload(cache_key, merged_payload)
                                return copy.deepcopy(merged_payload)
                    self._write_cached_payload(cache_key, persisted_payload)
                    return copy.deepcopy(persisted_payload)
                if fresh_pure_payload and resolved_modes == ["pure"]:
                    self._write_cached_payload(cache_key, fresh_pure_payload)
                    return copy.deepcopy(fresh_pure_payload)
                if fresh_pure_payload and "neural" in resolved_modes:
                    merged_payload = self._merge_mode_payloads(
                        pure_payload=fresh_pure_payload,
                        neural_payload=persisted_payload,
                        requested_modes=resolved_modes,
                    )
                    if merged_payload:
                        self._write_cached_payload(cache_key, merged_payload)
                        return copy.deepcopy(merged_payload)
                if set(resolved_modes) != {"pure", "neural"}:
                    superset_payload = self.store.read_latest_intraday_correlation_run(
                        underlying_security=underlying_security,
                        lookback_days=resolved_lookback_days,
                        horizon_minutes=resolved_horizon,
                        factors_signature=factors_signature,
                        modes_signature=self._modes_signature(["pure", "neural"]),
                    )
                    superset_matches_session = (
                        superset_payload
                        and str((superset_payload or {}).get("session_date") or "").strip()
                        == str((context_watermark or {}).get("session_date") or "").strip()
                    )
                    if superset_payload and (
                        superset_matches_session
                        or not self._payload_is_stale_for_context(superset_payload, context_watermark)
                    ):
                        projected_payload = self._project_payload_modes(superset_payload, resolved_modes)
                        self._write_cached_payload(cache_key, projected_payload)
                        return copy.deepcopy(projected_payload)

        dataset, factor_meta, selected_sessions, candidate_factors = self._build_dataset(
            underlying_security=underlying_security,
            lookback_days=resolved_lookback_days,
            horizon_minutes=resolved_horizon,
        )
        if dataset.empty:
            payload = {
                "underlying_security": underlying_security,
                "enabled": False,
                "status": "insufficient_history",
                "schema_version": self._schema_version,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "session_date": None,
                "lookback_days": resolved_lookback_days,
                "horizon_minutes": resolved_horizon,
                "request_factors": resolved_factors,
                "request_modes": resolved_modes,
                "factors_signature": factors_signature,
                "modes_signature": modes_signature,
                "selected_sessions": selected_sessions,
                "available_factors": [],
                "available_factor_count": 0,
                "default_factors": [],
                "selected_factors": [],
                "series": [],
                "series_latest_timestamp": None,
            }
            if persist:
                payload["run_id"] = self._build_run_id(underlying_security, resolved_lookback_days, resolved_horizon)
                payload["persisted"] = self.store.write_intraday_correlation_run(payload)
            self._write_cached_payload(cache_key, payload)
            return copy.deepcopy(payload)

        pure_summaries: dict[str, dict[str, Any]] = {}
        available_factors = []
        for factor in candidate_factors:
            summary, _ = self._build_pure_factor_series(
                dataset=dataset,
                factor=factor,
                factor_meta=factor_meta.get(factor) or {},
                horizon_minutes=resolved_horizon,
                include_points=False,
            )
            pure_summaries[factor] = summary or {}
            meta = factor_meta.get(factor) or {}
            available_factors.append({
                "factor": factor,
                "label": meta.get("label") or factor,
                "block": meta.get("block"),
                "asset_class": meta.get("asset_class"),
                "subclass": meta.get("subclass"),
                "latest_pure_correlation": _safe_float((summary or {}).get("latest_value")),
                "sample_count": int((summary or {}).get("latest_sample_count") or 0),
            })

        available_factors.sort(
            key=lambda item: (
                abs(_safe_float(item.get("latest_pure_correlation"), 0.0) or 0.0),
                int(item.get("sample_count") or 0),
                str(item.get("label") or ""),
            ),
            reverse=True,
        )

        requested_factors = [
            value
            for value in resolved_factors
            if value in set(candidate_factors)
        ]
        default_factors = [
            str(item.get("factor") or "")
            for item in available_factors[:min(4, len(available_factors))]
            if str(item.get("factor") or "").strip()
        ]
        selected_factors = requested_factors or default_factors

        series = []
        neural_training = {}
        for factor in selected_factors:
            meta = factor_meta.get(factor) or {}
            if "pure" in resolved_modes:
                summary, points = self._build_pure_factor_series(
                    dataset=dataset,
                    factor=factor,
                    factor_meta=meta,
                    horizon_minutes=resolved_horizon,
                    include_points=True,
                )
                if summary and points:
                    series.append({
                        "key": f"{factor}:pure",
                        "factor": factor,
                        "label": meta.get("label") or factor,
                        "mode": "pure",
                        "line_style": "solid",
                        "latest_value": _safe_float(summary.get("latest_value")),
                        "window_points": int(summary.get("window_points") or 0),
                        "window_minutes": int(summary.get("window_minutes") or 0),
                        "points": points,
                    })
            if "neural" in resolved_modes:
                summary, points = self._build_neural_factor_series(
                    dataset=dataset,
                    factor=factor,
                    factor_meta=meta,
                    horizon_minutes=resolved_horizon,
                )
                if summary:
                    neural_training[factor] = summary
                if summary and points:
                    series.append({
                        "key": f"{factor}:neural",
                        "factor": factor,
                        "label": meta.get("label") or factor,
                        "mode": "neural",
                        "line_style": "dashed",
                        "latest_value": _safe_float(summary.get("latest_value")),
                        "window_points": int(summary.get("window_points") or 0),
                        "window_minutes": int(summary.get("window_minutes") or 0),
                        "points": points,
                    })

        selected_factor_set = set(selected_factors)
        for item in available_factors:
            factor = str(item.get("factor") or "")
            item["selected"] = factor in selected_factor_set
            neural_summary = neural_training.get(factor) or {}
            item["latest_neural_correlation"] = _safe_float(neural_summary.get("latest_value"))
            item["neural_status"] = str(neural_summary.get("status") or "")

        generated_at = datetime.now(timezone.utc).isoformat()
        series_latest_dt = self._payload_latest_series_dt({"series": series})
        payload = {
            "underlying_security": underlying_security,
            "enabled": True,
            "status": "ready" if series else "insufficient_history",
            "schema_version": self._schema_version,
            "generated_at": generated_at,
            "captured_at": generated_at,
            "session_date": selected_sessions[-1] if selected_sessions else None,
            "lookback_days": resolved_lookback_days,
            "horizon_minutes": resolved_horizon,
            "request_factors": resolved_factors,
            "request_modes": resolved_modes,
            "factors_signature": factors_signature,
            "modes_signature": modes_signature,
            "modes": resolved_modes,
            "selected_sessions": selected_sessions,
            "row_count": int(len(dataset.index)),
            "available_factors": available_factors,
            "available_factor_count": int(len(available_factors)),
            "default_factors": default_factors,
            "selected_factors": selected_factors,
            "series": series,
            "series_latest_timestamp": series_latest_dt.isoformat() if series_latest_dt is not None else None,
            "training": {
                "neural": neural_training,
            },
        }
        if persist:
            payload["run_id"] = self._build_run_id(underlying_security, resolved_lookback_days, resolved_horizon)
            payload["persisted"] = self.store.write_intraday_correlation_run(payload)
        self._write_cached_payload(cache_key, payload)
        return copy.deepcopy(payload)


class IntradayCorrelationTrainingManager:
    _instance: "IntradayCorrelationTrainingManager | None" = None
    _instance_lock = threading.Lock()
    _default_underlyings = ("IBOVE Index",)
    _default_lookbacks = (1, 2, 3)

    def __init__(
        self,
        *,
        service: IntradayCorrelationHistoryService | None = None,
        poll_seconds: int = 600,
        cutoff_hour_local: int = 18,
    ) -> None:
        self.service = service or IntradayCorrelationHistoryService()
        self.store = self.service.store
        self.poll_seconds = max(int(poll_seconds), 120)
        self.cutoff_hour_local = max(0, min(int(cutoff_hour_local), 23))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status_lock = threading.RLock()
        self._last_completed_at: str | None = None
        self._last_error: str | None = None
        self._last_session_date: str | None = None

    @classmethod
    def get_instance(cls) -> "IntradayCorrelationTrainingManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @staticmethod
    def _default_modes() -> list[str]:
        return ["pure", "neural"]

    @staticmethod
    def _default_factors_signature() -> str:
        return IntradayCorrelationHistoryService._factors_signature([])

    @staticmethod
    def _default_modes_signature() -> str:
        return IntradayCorrelationHistoryService._modes_signature(["pure", "neural"])

    def _default_horizons(self) -> list[int]:
        horizons = [
            int(value)
            for value in (Config.OPTIONS_INTRADAY_DEPENDENCY_HORIZONS or [1, 5, 15])
            if int(value) > 0
        ]
        ordered = sorted({*horizons, 1, 5, 15})
        return ordered

    def _thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _current_local_session_date(self) -> str:
        return datetime.now(LOCAL_TZ).date().isoformat()

    def _past_cutoff(self) -> bool:
        return datetime.now(LOCAL_TZ).hour >= self.cutoff_hour_local

    def _has_persisted_default_pack(
        self,
        *,
        underlying_security: str,
        lookback_days: int,
        horizon_minutes: int,
        session_date: str,
    ) -> bool:
        payload = self.store.read_latest_intraday_correlation_run(
            underlying_security=underlying_security,
            lookback_days=lookback_days,
            horizon_minutes=horizon_minutes,
            factors_signature=self._default_factors_signature(),
            modes_signature=self._default_modes_signature(),
        )
        if not payload:
            return False
        return str(payload.get("session_date") or "") == str(session_date or "")

    def refresh_default_payloads(self, *, force: bool = False) -> dict[str, Any]:
        session_date = self._current_local_session_date()
        jobs_run = 0
        skipped = 0
        last_payload: dict[str, Any] | None = None
        for underlying_security in self._default_underlyings:
            for lookback_days in self._default_lookbacks:
                for horizon_minutes in self._default_horizons():
                    if not force and self._has_persisted_default_pack(
                        underlying_security=underlying_security,
                        lookback_days=lookback_days,
                        horizon_minutes=horizon_minutes,
                        session_date=session_date,
                    ):
                        skipped += 1
                        continue
                    last_payload = self.service.build_payload(
                        underlying_security=underlying_security,
                        lookback_days=lookback_days,
                        horizon_minutes=horizon_minutes,
                        factors=[],
                        modes=self._default_modes(),
                        bypass_cache=force,
                        prefer_persisted=False,
                        persist=True,
                    )
                    jobs_run += 1
        with self._status_lock:
            self._last_completed_at = datetime.now(timezone.utc).isoformat()
            self._last_error = None
            self._last_session_date = session_date
        return {
            "session_date": session_date,
            "jobs_run": jobs_run,
            "jobs_skipped": skipped,
            "last_payload_status": (last_payload or {}).get("status"),
            "last_completed_at": self._last_completed_at,
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._past_cutoff():
                    self.refresh_default_payloads(force=False)
            except Exception as exc:  # pragma: no cover - defensive background loop
                logger.exception("Failed intraday correlation training cycle")
                with self._status_lock:
                    self._last_error = str(exc)
            self._stop_event.wait(self.poll_seconds)

    def resume_if_needed(self) -> dict[str, Any]:
        with self._status_lock:
            if not self._thread_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                    name="intraday-correlation-training-loop",
                )
                self._thread.start()
            return {
                "running": self._thread_alive(),
                "poll_seconds": self.poll_seconds,
                "cutoff_hour_local": self.cutoff_hour_local,
                "last_completed_at": self._last_completed_at,
                "last_error": self._last_error,
                "last_session_date": self._last_session_date,
            }


def refresh_live_pure_intraday_correlation_payloads(
    *,
    store: OptionsStore | None = None,
    context_service: MacroOptionsHeatmapContextService | None = None,
    underlying_security: str = "IBOVE Index",
    lookback_days: int = 1,
    horizons: list[int] | None = None,
) -> list[dict[str, Any]]:
    service = IntradayCorrelationHistoryService(
        store=store,
        context_service=context_service,
    )
    refreshed: list[dict[str, Any]] = []
    for horizon_minutes in sorted({
        int(value)
        for value in (horizons or Config.OPTIONS_INTRADAY_DEPENDENCY_HORIZONS or [1, 5, 15])
        if int(value) > 0
    }):
        payload = service.build_payload(
            underlying_security=underlying_security,
            lookback_days=max(1, int(lookback_days)),
            horizon_minutes=int(horizon_minutes),
            factors=[],
            modes=["pure"],
            bypass_cache=True,
            prefer_persisted=False,
            persist=True,
        )
        refreshed.append(
            {
                "horizon_minutes": int(horizon_minutes),
                "status": str(payload.get("status") or ""),
                "session_date": str(payload.get("session_date") or ""),
                "series_latest_timestamp": payload.get("series_latest_timestamp"),
                "available_factor_count": int(payload.get("available_factor_count") or 0),
                "row_count": int(payload.get("row_count") or 0),
                "run_id": payload.get("run_id"),
            }
        )
    return refreshed
