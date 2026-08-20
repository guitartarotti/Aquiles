from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from ...config import Config
from ...utils.logger import get_logger
from ..macro_options_heatmap_context_service import MacroOptionsHeatmapContextService
from ..options_store import OptionsStore
from .factor_preparation import _model_input_direction_multiplier, load_factor_definitions

logger = get_logger("aquiles.options_fair_value.intraday_dependency")


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
    mask_x = np.abs(x) >= threshold
    if not mask_x.any():
        return 0.0
    conditional = np.abs(y[mask_x]) >= threshold
    return float(_clamp(np.mean(conditional), 0.0, 1.0))


class IntradayDependencyService:
    def __init__(
        self,
        *,
        store: OptionsStore | None = None,
        context_service: MacroOptionsHeatmapContextService | None = None,
    ) -> None:
        self.store = store or OptionsStore()
        self.context_service = context_service or MacroOptionsHeatmapContextService()

    @staticmethod
    def _factor_meta() -> dict[str, dict[str, Any]]:
        return {
            definition.name: {
                "factor": definition.name,
                "label": definition.label,
                "block": definition.block,
                "asset_class": definition.asset_class,
                "subclass": definition.subclass,
                "source_kind": definition.source_kind,
                "source_key": definition.source_key,
                "transform": definition.transform,
                "model_layer": definition.model_layer,
                "expected_direction_to_ibov": definition.expected_direction_to_ibov,
                "direction_multiplier": _model_input_direction_multiplier(definition.expected_direction_to_ibov),
            }
            for definition in load_factor_definitions()
        }

    @staticmethod
    def _workbook_factor_key(security: str) -> str:
        return f"asset::{str(security or '').strip()}"

    @staticmethod
    def _compact_workbook_values(values: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        compact: dict[str, dict[str, Any]] = {}
        for key, raw_dynamic in (values or {}).items():
            security = str(key or "").strip()
            if not security:
                continue
            dynamic = dict(raw_dynamic or {})
            compact[security] = {
                "raw_value": _safe_float(dynamic.get("raw_value")),
                "daily_change_pct": _safe_float(dynamic.get("daily_change_pct")),
                "timestamp": dynamic.get("timestamp"),
                "row_number": dynamic.get("row_number"),
                "worksheet_name": dynamic.get("worksheet_name"),
                "fallback_source": dynamic.get("fallback_source"),
            }
        return compact

    @staticmethod
    def _compact_factor_values(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
        compact: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            factor = str((row or {}).get("factor") or "").strip()
            if not factor:
                continue
            compact[factor] = {
                "raw_value": _safe_float((row or {}).get("raw_value")),
                "daily_change_pct": _safe_float((row or {}).get("daily_change_pct")),
                "timestamp": (row or {}).get("timestamp"),
                "is_live": bool((row or {}).get("is_live")),
                "live_source": (row or {}).get("live_source"),
            }
        return compact

    def _snapshot_factor_values(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        factor_values = snapshot.get("factor_values") or {}
        if factor_values:
            return {
                str(key): dict(value or {})
                for key, value in factor_values.items()
                if str(key).strip()
            }
        factor_rows = snapshot.get("factor_rows") or []
        return self._compact_factor_values(factor_rows)

    def _snapshot_workbook_values(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        workbook_values = snapshot.get("workbook_values") or {}
        if workbook_values:
            return self._compact_workbook_values(workbook_values)
        return {}

    def _snapshot_has_observed_values(self, snapshot: dict[str, Any]) -> bool:
        return bool(
            self._snapshot_factor_values(snapshot)
            or self._snapshot_workbook_values(snapshot)
        )

    @classmethod
    def _reference_asset_meta_by_security(cls) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for meta in cls._factor_meta().values():
            source_kind = str(meta.get("source_kind") or "").strip().lower()
            source_key = str(meta.get("source_key") or "").strip()
            if source_kind != "reference_asset" or not source_key:
                continue
            mapping.setdefault(source_key.lower(), dict(meta))
        return mapping

    @staticmethod
    def _workbook_asset_transform(security: str, matched_meta: dict[str, Any] | None = None) -> str:
        if matched_meta and str(matched_meta.get("transform") or "").strip():
            return str(matched_meta.get("transform") or "").strip().lower()
        text = str(security or "").strip().lower()
        diff_tokens = (
            "odf",
            ".brii",
            "brii",
            "usgg",
            "usggbe",
            "usggt",
            "usso",
            "usosfr",
            "sofrrate",
            "tgcrrate",
            "fwis",
            "eubsvt",
            "gtmxn",
            "ctzar",
            "jybss",
        )
        if any(token in text for token in diff_tokens) or text.endswith(" govt"):
            return "diff"
        return "return"

    @staticmethod
    def _workbook_asset_direction(security: str, matched_meta: dict[str, Any] | None = None) -> str:
        if matched_meta and str(matched_meta.get("expected_direction_to_ibov") or "").strip():
            return str(matched_meta.get("expected_direction_to_ibov") or "").strip()
        text = str(security or "").strip().lower()
        positive_falling_tokens = (
            "odf",
            ".brii",
            "brii",
            "usgg",
            "usggbe",
            "usggt",
            "usso",
            "usosfr",
            "sofrrate",
            "tgcrrate",
            "fwis",
            "eubsvt",
            "gtmxn",
            "ctzar",
            "jybss",
        )
        negative_rising_tokens = (
            "cds",
            "cdx",
            "itrx",
            "embiv",
            "vix",
            "move",
            "vxbr",
            "vvix",
            "ovx",
            "dxy",
            "wdo",
            ".jpyb",
            "jpyb",
        )
        positive_rising_tokens = (
            ".bbr",
            ".cbbr",
            " equity",
            "xlb us equity",
            "xlc us equity",
            "xle us equity",
            "xlf us equity",
            "xli us equity",
            "xlk us equity",
            "xlp us equity",
            "xlre us equity",
            "xlu us equity",
            "xlv us equity",
            "xly us equity",
            "index",
            "comdty",
        )
        if any(token in text for token in positive_falling_tokens) or text.endswith(" govt"):
            return "positive_when_falling"
        if any(token in text for token in negative_rising_tokens):
            return "negative_when_rising"
        if ".bbr" in text or ".cbbr" in text:
            return "positive_when_rising"
        if text.endswith(" curncy"):
            return "contextual"
        if any(token in text for token in positive_rising_tokens):
            return "positive_when_rising"
        return "contextual"

    @staticmethod
    def _workbook_asset_class_block(security: str, matched_meta: dict[str, Any] | None = None) -> tuple[str, str, str]:
        if matched_meta:
            return (
                str(matched_meta.get("asset_class") or "captured"),
                str(matched_meta.get("block") or "planilha"),
                str(matched_meta.get("subclass") or "workbook_asset"),
            )
        text = str(security or "").strip().lower()
        if any(token in text for token in ("cds", "cdx", "itrx", "embiv", ".bbr", ".cbbr")):
            return ("credit", "planilha_credit", "workbook_credit")
        if any(token in text for token in ("vix", "move", "vxbr", "vvix", "ovx")):
            return ("volatility", "planilha_volatility", "workbook_volatility")
        if any(token in text for token in ("odf", ".brii", "brii", "usgg", "usso", "usosfr", "sofrrate", "tgcrrate", "fwis", "eubsvt", "gtmxn", "ctzar", "jybss")) or text.endswith(" govt"):
            return ("rates", "planilha_rates", "workbook_rates")
        if text.endswith(" equity") or re.match(r"^(x[a-z]{2,3}|ewz|eem|fxi|mes1|rtya|dma|esa|icon|idiv|ifncbv|imat|small11|vale3|petr4)\b", text):
            return ("equity", "planilha_equity", "workbook_equity")
        if text.endswith(" comdty"):
            return ("commodities", "planilha_commodities", "workbook_commodity")
        if text.endswith(" curncy"):
            return ("fx", "planilha_fx", "workbook_fx")
        return ("captured", "planilha", "workbook_asset")

    def _build_factor_meta_from_snapshots(self, snapshots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        factor_meta = {
            key: dict(value or {})
            for key, value in self._factor_meta().items()
        }
        reference_meta = self._reference_asset_meta_by_security()
        workbook_securities = {
            security
            for snapshot in (snapshots or [])
            for security in self._snapshot_workbook_values(snapshot)
        }
        for security in sorted(workbook_securities):
            asset_key = self._workbook_factor_key(security)
            if asset_key in factor_meta:
                continue
            matched_meta = reference_meta.get(security.lower())
            asset_class, block, subclass = self._workbook_asset_class_block(security, matched_meta)
            expected_direction = self._workbook_asset_direction(security, matched_meta)
            factor_meta[asset_key] = {
                "factor": asset_key,
                "label": security,
                "block": block,
                "asset_class": asset_class,
                "subclass": subclass,
                "source_kind": "workbook_asset",
                "source_key": security,
                "transform": self._workbook_asset_transform(security, matched_meta),
                "model_layer": "workbook",
                "expected_direction_to_ibov": expected_direction,
                "direction_multiplier": _model_input_direction_multiplier(expected_direction),
            }
        return factor_meta

    def _load_context_snapshots(
        self,
        *,
        underlying_security: str,
        session_date: str,
    ) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for raw_snapshot in self.context_service.read_live_capture_snapshots(
            session_date=session_date,
            underlying_security=underlying_security,
        ):
            snapshot = dict(raw_snapshot or {})
            if not self._snapshot_has_observed_values(snapshot):
                continue
            snapshots.append(snapshot)
        return snapshots

    def _load_backfill_snapshots(
        self,
        *,
        underlying_security: str,
        session_date: str,
        limit: int = 480,
    ) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for payload in self.store.list_recent_fair_value_runs(underlying_security, limit=limit):
            if str(payload.get("session_date") or "") != session_date:
                continue
            summary = payload.get("summary") or {}
            factor_values = self._compact_factor_values(summary.get("live_factor_rows") or [])
            if not factor_values:
                continue
            snapshots.append({
                "captured_at": payload.get("captured_at"),
                "session_date": session_date,
                "underlying_security": underlying_security,
                "current_future_price": _safe_float(summary.get("current_future_price")),
                "current_spot_price": _safe_float(summary.get("current_spot_price")),
                "factor_values": factor_values,
                "snapshot_source": "fair_value_backfill",
            })
        return snapshots

    def _load_intraday_snapshots(
        self,
        *,
        underlying_security: str,
        session_date: str,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for snapshot in self._load_backfill_snapshots(
            underlying_security=underlying_security,
            session_date=session_date,
        ):
            ts = str(snapshot.get("captured_at") or "").strip()
            if ts:
                merged[ts] = snapshot
        for snapshot in self._load_context_snapshots(
            underlying_security=underlying_security,
            session_date=session_date,
        ):
            ts = str(snapshot.get("captured_at") or "").strip()
            if not ts:
                continue
            item = dict(snapshot)
            item["snapshot_source"] = "live_capture"
            merged[ts] = item
        rows = [dict(item or {}) for item in merged.values()]
        rows.sort(key=lambda item: str(item.get("captured_at") or ""))
        return rows

    def _build_observed_frame(
        self,
        *,
        snapshots: list[dict[str, Any]],
        factor_meta: dict[str, dict[str, Any]],
    ) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for snapshot in snapshots:
            ts = _parse_iso(snapshot.get("captured_at"))
            xb1_last = _safe_float(snapshot.get("current_future_price"))
            if ts is None or xb1_last in (None, 0.0):
                continue
            record: dict[str, Any] = {
                "timestamp": pd.Timestamp(ts).floor("min"),
                "session_date": str(snapshot.get("session_date") or ""),
                "xb1_last": xb1_last,
                "snapshot_source": snapshot.get("snapshot_source") or "unknown",
                "current_spot_price": _safe_float(snapshot.get("current_spot_price")),
            }
            factor_values = self._snapshot_factor_values(snapshot)
            for factor, dynamic in factor_values.items():
                if factor not in factor_meta:
                    continue
                raw_value = _safe_float(dynamic.get("raw_value"))
                if raw_value is None:
                    raw_value = _safe_float(dynamic.get("daily_change_pct"))
                record[f"raw__{factor}"] = raw_value
            workbook_values = self._snapshot_workbook_values(snapshot)
            for security, dynamic in workbook_values.items():
                asset_factor = self._workbook_factor_key(security)
                if asset_factor not in factor_meta:
                    continue
                raw_value = _safe_float(dynamic.get("raw_value"))
                if raw_value is None:
                    raw_value = _safe_float(dynamic.get("daily_change_pct"))
                record[f"raw__{asset_factor}"] = raw_value
            for factor, dynamic in factor_values.items():
                meta = factor_meta.get(factor) or {}
                source_kind = str(meta.get("source_kind") or "").strip().lower()
                source_key = str(meta.get("source_key") or "").strip()
                if source_kind != "reference_asset" or not source_key:
                    continue
                asset_factor = self._workbook_factor_key(source_key)
                target_column = f"raw__{asset_factor}"
                if asset_factor not in factor_meta or target_column in record:
                    continue
                raw_value = _safe_float(dynamic.get("raw_value"))
                if raw_value is None:
                    raw_value = _safe_float(dynamic.get("daily_change_pct"))
                record[target_column] = raw_value
            records.append(record)
        if not records:
            return pd.DataFrame()
        frame = pd.DataFrame(records)
        frame = frame.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
        return frame.set_index("timestamp").sort_index()

    @staticmethod
    def _bar_move(series: pd.Series, transform: str) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        previous = numeric.shift(1)
        key = str(transform or "return").strip().lower()
        if key == "return":
            log_move = np.log(numeric / previous)
            pct_move = numeric.pct_change(fill_method=None)
            return pd.Series(
                np.where(
                    (numeric > 0) & (previous > 0),
                    log_move,
                    pct_move,
                ),
                index=numeric.index,
                dtype="float64",
            )
        return numeric - previous

    @staticmethod
    def _rolling_robust_zscore(series: pd.Series, window_points: int, min_points: int) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        rolling_median = numeric.rolling(window_points, min_periods=min_points).median()
        rolling_mad = (numeric - rolling_median).abs().rolling(window_points, min_periods=min_points).median()
        rolling_std = numeric.rolling(window_points, min_periods=min_points).std(ddof=0)
        scale = (rolling_mad * 1.4826).replace(0.0, np.nan)
        scale = scale.fillna(rolling_std.replace(0.0, np.nan))
        return ((numeric - rolling_median) / scale).clip(-6.0, 6.0)

    @staticmethod
    def _latest_window_tail(series_x: pd.Series, series_y: pd.Series, window_points: int) -> dict[str, float]:
        sample = pd.concat([series_x.rename("x"), series_y.rename("y")], axis=1).dropna().tail(window_points)
        if len(sample.index) < 6:
            return {
                "spearman_corr": 0.0,
                "distance_corr": 0.0,
                "tail_dependence": 0.0,
            }
        x = sample["x"].to_numpy(dtype=float)
        y = sample["y"].to_numpy(dtype=float)
        return {
            "spearman_corr": float(sample["x"].corr(sample["y"], method="spearman") or 0.0),
            "distance_corr": _distance_correlation(x, y),
            "tail_dependence": _tail_dependence(x, y),
        }

    def _build_factor_horizon_result(
        self,
        *,
        observed_frame: pd.DataFrame,
        factor: str,
        meta: dict[str, Any],
        horizon_minutes: int,
        include_history: bool,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        raw_column = f"raw__{factor}"
        if raw_column not in observed_frame.columns:
            return None, []

        bar_frequency = f"{int(horizon_minutes)}min"
        price_bar = observed_frame["xb1_last"].resample(bar_frequency).last()
        factor_bar = observed_frame[raw_column].resample(bar_frequency).last()
        if factor_bar.notna().sum() < 4 or price_bar.notna().sum() < 4:
            return None, []

        y_forward = np.log(price_bar.shift(-1) / price_bar)
        x_move_raw = self._bar_move(factor_bar, str(meta.get("transform") or "return"))
        direction_multiplier = float(meta.get("direction_multiplier") or 1.0)
        x_move_aligned = x_move_raw * direction_multiplier

        window_points = max(
            int(Config.OPTIONS_INTRADAY_DEPENDENCY_MIN_POINTS),
            int(round(max(int(Config.OPTIONS_INTRADAY_DEPENDENCY_ROLLING_WINDOW_MINUTES), horizon_minutes) / max(horizon_minutes, 1))),
        )
        min_points = max(4, min(window_points, int(Config.OPTIONS_INTRADAY_DEPENDENCY_MIN_POINTS)))

        x_z = self._rolling_robust_zscore(x_move_aligned, window_points, min_points)
        y_z = self._rolling_robust_zscore(y_forward, window_points, min_points)
        valid_pairs = x_z.notna() & y_z.notna()
        rolling_count = valid_pairs.astype(float).rolling(window_points, min_periods=1).sum()
        rolling_beta = x_z.rolling(window_points, min_periods=min_points).cov(y_z)
        rolling_var = x_z.rolling(window_points, min_periods=min_points).var(ddof=0)
        rolling_beta = (rolling_beta / rolling_var.replace(0.0, np.nan)).clip(-4.0, 4.0)
        rolling_corr = x_z.rolling(window_points, min_periods=min_points).corr(y_z)
        rolling_agreement = (
            (np.sign(x_z) == np.sign(y_z))
            .astype(float)
            .rolling(window_points, min_periods=min_points)
            .mean()
        )
        rolling_coverage = (rolling_count / max(float(window_points), 1.0)).clip(0.0, 1.0)
        impact_score = (rolling_beta * x_z).clip(-6.0, 6.0)
        confidence = (
            rolling_corr.abs().fillna(0.0)
            * rolling_coverage.fillna(0.0)
            * (0.55 + (0.45 * rolling_agreement.fillna(0.0)))
        ).clip(0.0, 1.0)

        summary_base = pd.DataFrame({
            "price_bar": price_bar,
            "factor_raw": factor_bar,
            "factor_move_raw": x_move_raw,
            "xb1_forward_return": y_forward,
            "x_z": x_z,
            "y_z": y_z,
            "rolling_beta": rolling_beta,
            "rolling_corr": rolling_corr,
            "impact_score": impact_score,
            "confidence": confidence,
            "rolling_count": rolling_count,
            "rolling_coverage": rolling_coverage,
        })
        summary_frame = summary_base.dropna(subset=["rolling_beta", "rolling_corr", "confidence"])
        if summary_frame.empty:
            paired = summary_base.dropna(subset=["x_z", "y_z"]).tail(window_points)
            if len(paired.index) < 2:
                return None, []
            x_values = paired["x_z"].to_numpy(dtype=float)
            y_values = paired["y_z"].to_numpy(dtype=float)
            fallback_beta = float(np.cov(
                x_values,
                y_values,
            )[0, 1] / max(np.var(paired["x_z"].to_numpy(dtype=float)), 1e-9))
            fallback_beta = _clamp(fallback_beta, -4.0, 4.0)
            if float(np.std(x_values)) <= 1e-9 or float(np.std(y_values)) <= 1e-9:
                fallback_corr = 0.0
            else:
                fallback_corr = float(paired["x_z"].corr(paired["y_z"], method="pearson") or 0.0)
            fallback_agreement = float(
                np.mean(np.sign(x_values) == np.sign(y_values))
            )
            latest_timestamp = paired.index[-1]
            latest_pair = paired.iloc[-1]
            fallback_impact = _clamp(float(fallback_beta * float(latest_pair["x_z"])), -6.0, 6.0)
            fallback_confidence = _clamp(
                abs(fallback_corr) * min(len(paired.index) / max(float(min_points), 1.0), 1.0) * (0.40 + (0.35 * fallback_agreement)),
                0.0,
                0.55,
            )
            summary_frame = pd.DataFrame([{
                "price_bar": latest_pair["price_bar"],
                "factor_raw": latest_pair["factor_raw"],
                "factor_move_raw": latest_pair["factor_move_raw"],
                "xb1_forward_return": latest_pair["xb1_forward_return"],
                "rolling_beta": fallback_beta,
                "rolling_corr": fallback_corr,
                "impact_score": fallback_impact,
                "confidence": fallback_confidence,
                "rolling_count": float(len(paired.index)),
                "rolling_coverage": min(len(paired.index) / max(float(window_points), 1.0), 1.0),
            }], index=[latest_timestamp])

        latest_timestamp = summary_frame.index[-1]
        latest = summary_frame.iloc[-1]
        tail_metrics = self._latest_window_tail(x_z, y_z, window_points)
        direction = "bullish" if float(latest["impact_score"]) > 0 else "bearish" if float(latest["impact_score"]) < 0 else "neutral"
        summary = {
            "factor": factor,
            "label": meta.get("label") or factor,
            "block": meta.get("block"),
            "asset_class": meta.get("asset_class"),
            "subclass": meta.get("subclass"),
            "source_kind": meta.get("source_kind"),
            "transform": meta.get("transform"),
            "expected_direction_to_ibov": meta.get("expected_direction_to_ibov"),
            "horizon_minutes": int(horizon_minutes),
            "latest_timestamp": latest_timestamp.isoformat(),
            "latest_xb1_price": _safe_float(latest["price_bar"]),
            "latest_factor_raw_value": _safe_float(latest["factor_raw"]),
            "latest_factor_move_raw": _safe_float(latest["factor_move_raw"]),
            "latest_xb1_forward_return": _safe_float(latest["xb1_forward_return"]),
            "rolling_beta": _safe_float(latest["rolling_beta"]),
            "rolling_corr": _safe_float(latest["rolling_corr"]),
            "rolling_spearman_corr": tail_metrics["spearman_corr"],
            "distance_corr": tail_metrics["distance_corr"],
            "tail_dependence": tail_metrics["tail_dependence"],
            "impact_score": _safe_float(latest["impact_score"]),
            "confidence": _safe_float(latest["confidence"]),
            "coverage_ratio": _safe_float(latest["rolling_coverage"]),
            "sample_count": int(latest["rolling_count"] or 0),
            "direction": direction,
            "snapshot_pressure_label": (
                "pressionando alta" if direction == "bullish"
                else "pressionando baixa" if direction == "bearish"
                else "sem pressao clara"
            ),
        }

        history_rows: list[dict[str, Any]] = []
        if include_history:
            max_history_points = max(int(Config.OPTIONS_INTRADAY_DEPENDENCY_MAX_HISTORY_POINTS), 60)
            for timestamp, row in summary_frame.tail(max_history_points).iterrows():
                history_rows.append({
                    "timestamp": timestamp.isoformat(),
                    "xb1_price": _safe_float(row.get("price_bar")),
                    "factor_raw_value": _safe_float(row.get("factor_raw")),
                    "factor_move_raw": _safe_float(row.get("factor_move_raw")),
                    "xb1_forward_return": _safe_float(row.get("xb1_forward_return")),
                    "rolling_beta": _safe_float(row.get("rolling_beta")),
                    "rolling_corr": _safe_float(row.get("rolling_corr")),
                    "impact_score": _safe_float(row.get("impact_score")),
                    "confidence": _safe_float(row.get("confidence")),
                    "coverage_ratio": _safe_float(row.get("rolling_coverage")),
                })
        return summary, history_rows

    def build_payload(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        session_date: str | None = None,
        factor: str | None = None,
        include_history: bool = False,
    ) -> dict[str, Any]:
        state = self.context_service.read_state()
        context_history = state.get("live_capture_history") or {}
        resolved_session_date = (
            str(session_date or "").strip()
            or str(context_history.get("current_session_date") or "").strip()
            or datetime.now(timezone.utc).date().isoformat()
        )
        horizons = sorted({
            int(value)
            for value in (Config.OPTIONS_INTRADAY_DEPENDENCY_HORIZONS or [1, 5, 15])
            if int(value) > 0
        })
        selected_factor = str(factor or "").strip() or None
        history_for_factor = bool(include_history or selected_factor)

        snapshots = self._load_intraday_snapshots(
            underlying_security=underlying_security,
            session_date=resolved_session_date,
        )
        factor_meta = self._build_factor_meta_from_snapshots(snapshots)
        observed_frame = self._build_observed_frame(
            snapshots=snapshots,
            factor_meta=factor_meta,
        )
        if observed_frame.empty:
            return {
                "underlying_security": underlying_security,
                "session_date": resolved_session_date,
                "horizons": {},
                "available_factors": [],
                "snapshot_count": 0,
                "message": "Sem snapshots intradiarios suficientes para calcular dependencia.",
            }

        live_capture_count = sum(1 for snapshot in snapshots if snapshot.get("snapshot_source") == "live_capture")
        backfill_count = len(snapshots) - live_capture_count
        horizon_payloads: dict[str, Any] = {}
        available_factors: set[str] = set()

        for horizon_minutes in horizons:
            ranking: list[dict[str, Any]] = []
            factor_history: dict[str, list[dict[str, Any]]] = {}
            for factor_name, meta in factor_meta.items():
                summary, history_rows = self._build_factor_horizon_result(
                    observed_frame=observed_frame,
                    factor=factor_name,
                    meta=meta,
                    horizon_minutes=horizon_minutes,
                    include_history=history_for_factor and (selected_factor in {None, factor_name}),
                )
                if not summary:
                    continue
                ranking.append(summary)
                available_factors.add(factor_name)
                if history_rows:
                    factor_history[factor_name] = history_rows
            ranking.sort(
                key=lambda item: abs(float(item.get("impact_score") or 0.0)) * float(item.get("confidence") or 0.0),
                reverse=True,
            )
            horizon_payloads[f"{horizon_minutes}m"] = {
                "horizon_minutes": horizon_minutes,
                "ranking": ranking,
                "top_positive": [item for item in ranking if float(item.get("impact_score") or 0.0) > 0][:12],
                "top_negative": [item for item in ranking if float(item.get("impact_score") or 0.0) < 0][:12],
                "factor_history": factor_history,
            }

        return {
            "underlying_security": underlying_security,
            "session_date": resolved_session_date,
            "capture_interval_seconds": int(Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
            "fair_value_interval_seconds": int(Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
            "rolling_window_minutes": int(Config.OPTIONS_INTRADAY_DEPENDENCY_ROLLING_WINDOW_MINUTES),
            "snapshot_count": int(len(snapshots)),
            "snapshot_source_mix": {
                "live_capture": int(live_capture_count),
                "fair_value_backfill": int(backfill_count),
            },
            "observed_timestamp_start": observed_frame.index.min().isoformat() if len(observed_frame.index) else None,
            "observed_timestamp_end": observed_frame.index.max().isoformat() if len(observed_frame.index) else None,
            "available_factors": sorted(available_factors),
            "horizons": horizon_payloads,
        }
