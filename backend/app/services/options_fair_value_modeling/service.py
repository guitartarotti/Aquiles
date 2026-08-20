from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any, overload

import numpy as np
import pandas as pd

from ...config import Config
from ...utils.logger import get_logger
from ..excel_live_workbook_service import ExcelLiveWorkbookService
from ..options_bloomberg_service import OptionsBloombergService
from ..options_global_modeling import OptionsGlobalTriangulationService
from ..options_modeling import OptionsModelingService
from ..options_store import OptionsStore
from .dynamic_fair_value_model import run_dynamic_structural_model
from .factor_preparation import (
    build_live_factor_rows,
    load_factor_definitions,
    prepare_factor_frame,
)
from .fair_value_band_model import build_fair_value_band
from .fair_value_output_builder import build_fair_value_output
from .fair_value_quality_model import (
    BR_IMPLIED_INFLATION_REFERENCE_ASSETS,
    DI_CURVE_REFERENCE_ASSETS,
    build_fair_value_quality_package,
)
from .global_distortion_overlay import build_global_distortion_overlay
from .options_overlay_model import build_options_overlay
from .regime_model import classify_market_regime
from .residual_ml_model import build_residual_ml_adjustment
from .types import FairValueRunConfig
from .us_rates_factor_model import build_us_rates_factor_context

logger = get_logger("aquiles.options_fair_value.service")


@overload
def _finite_float(value: Any, default: None) -> float | None: ...


@overload
def _finite_float(value: Any, default: float = 0.0) -> float: ...


def _finite_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


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


def _build_proxy_factor_contributions(
    *,
    frame: pd.DataFrame,
    all_feature_meta: dict[str, dict[str, Any]] | None,
    structural_model: dict[str, Any],
    run_config: FairValueRunConfig,
) -> dict[str, dict[str, Any]]:
    if frame.empty:
        return {}

    latest_anchor = _finite_float(
        frame["fair_value_anchor_price"].iloc[-1],
        _finite_float(frame["local_future_close"].iloc[-1], 0.0),
    )
    if latest_anchor <= 0:
        return {}

    primary_factor_names = set((structural_model.get("factor_contributions_now") or {}).keys())
    subtract_first_step = str(run_config.intraday_anchor_type or "previous_close").strip().lower() == "session_open"
    minimum_history = max(int(run_config.min_points * 0.50), 24)
    beta_lookback = max(int(run_config.min_points * 3), 96)

    proxy_contributions: dict[str, dict[str, Any]] = {}
    for name, meta in (all_feature_meta or {}).items():
        if name in primary_factor_names:
            continue

        model_layer = str(meta.get("model_layer") or "core").strip().lower()
        if model_layer not in {"core", "core_and_shadow", "both"}:
            continue

        model_column = str(meta.get("model_column") or meta.get("z_column") or "").strip()
        feature_column = str(meta.get("feature_column") or "").strip()
        z_column = str(meta.get("z_column") or "").strip()
        if not model_column or model_column not in frame.columns:
            continue

        subset = frame.dropna(
            subset=["target_log_return", "fair_value_anchor_price", "session_date", model_column]
        ).copy()
        if len(subset.index) < minimum_history:
            continue

        x_raw = subset[model_column].to_numpy(dtype=float)
        y_raw = subset["target_log_return"].to_numpy(dtype=float)
        session_keys = subset["session_date"].astype(str).to_numpy()
        if not len(x_raw):
            continue

        x_reference = x_raw[:-1] if len(x_raw) > 1 else x_raw
        x_mean = float(np.nanmean(x_reference))
        x_std = float(np.nanstd(x_reference))
        if not math.isfinite(x_std) or x_std <= 1e-9:
            x_std = 1.0
        x_norm = np.nan_to_num((x_raw - x_mean) / x_std, nan=0.0, posinf=0.0, neginf=0.0)

        lookback = min(len(x_norm), beta_lookback)
        x_window = x_norm[-lookback:]
        y_window = y_raw[-lookback:]
        if len(x_window) < minimum_history:
            continue

        x_centered = x_window - float(np.nanmean(x_window))
        y_centered = y_window - float(np.nanmean(y_window))
        x_var = float(np.nanmean(np.square(x_centered)))
        y_var = float(np.nanmean(np.square(y_centered)))
        if not math.isfinite(x_var) or x_var <= 1e-9:
            continue

        covariance = float(np.nanmean(x_centered * y_centered))
        raw_beta = covariance / x_var
        correlation = covariance / max(math.sqrt(max(x_var * y_var, 1e-12)), 1e-6)
        coverage_ratio = min(1.0, len(x_window) / max(float(run_config.min_points), 1.0))
        shrinkage = 0.25 + (0.75 * coverage_ratio * min(abs(correlation), 1.0))
        beta = raw_beta * shrinkage
        if not math.isfinite(beta):
            continue

        factor_return_history = beta * x_norm
        cumulative_returns = _cumulative_by_session(
            factor_return_history,
            session_keys,
            subtract_first_step=subtract_first_step,
        )
        cumulative_return_now = float(cumulative_returns[-1])
        expected_return = float(beta * x_norm[-1])
        contribution_points = latest_anchor * (math.exp(cumulative_return_now) - 1.0)

        proxy_contributions[name] = {
            "label": meta.get("label"),
            "block": meta.get("block"),
            "beta": beta,
            "feature_value": _finite_float(subset[feature_column].iloc[-1], 0.0) if feature_column in subset.columns else None,
            "feature_zscore": _finite_float(subset[z_column].iloc[-1], 0.0) if z_column in subset.columns else None,
            "model_input_zscore": float(x_norm[-1]),
            "weight": float(meta.get("weight") or 1.0),
            "model_layer": meta.get("model_layer"),
            "contribution_return": expected_return,
            "cumulative_contribution_return": cumulative_return_now,
            "contribution_points": contribution_points,
            "anchor_xb1": latest_anchor,
            "contribution_source": "proxy_regression",
            "coverage_points": int(len(subset.index)),
            "correlation": correlation,
        }

    return proxy_contributions


def _split_security_candidates(raw_value: Any) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    for separator in ("|", ";"):
        text = text.replace(separator, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _normalize_cached_factor_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows or []:
        item = dict(row or {})
        original_source = str(item.get("live_source") or "").strip()
        item["is_live"] = False
        item["live_source"] = "persisted_cache"
        if original_source:
            item["cache_source"] = original_source
        normalized.append(item)
    return normalized


class OptionsFairValueService:
    def __init__(
        self,
        store: OptionsStore | None = None,
        options_modeling: OptionsModelingService | None = None,
        global_service: OptionsGlobalTriangulationService | None = None,
    ):
        self.store = store or OptionsStore()
        self.options_modeling = options_modeling or OptionsModelingService(store=self.store)
        self.global_service = global_service or OptionsGlobalTriangulationService(store=self.store)
        self.bloomberg = OptionsBloombergService()
        self.excel_live_workbook = ExcelLiveWorkbookService()

    @staticmethod
    def _live_sources_enabled() -> bool:
        return bool(
            Config.OPTIONS_FAIR_VALUE_LIVE_ENABLE
            or Config.OPTIONS_FAIR_VALUE_EXCEL_BASKET_ENABLE
            or getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False)
        )

    @staticmethod
    def _normalize_security_key(value: Any) -> str:
        return " ".join(str(value or "").strip().upper().split())

    def _collect_live_reference_rows(
        self,
        underlying_security: str,
        *,
        workbook_only: bool = False,
    ) -> dict[str, dict[str, Any]]:
        if not self._live_sources_enabled():
            return {}
        reference_securities = sorted({
            definition.source_key
            for definition in load_factor_definitions()
            if definition.source_kind == "reference_asset" and str(definition.source_key).strip()
        })
        for item in [*DI_CURVE_REFERENCE_ASSETS, *BR_IMPLIED_INFLATION_REFERENCE_ASSETS]:
            security = str(item.get("security") or "").strip()
            if security and security not in reference_securities:
                reference_securities.append(security)
        for security in _split_security_candidates((Config.OPTIONS_MODEL_SPOT_SECURITY_MAP or {}).get(underlying_security)):
            if security and security not in reference_securities:
                reference_securities.append(security)
        for security in _split_security_candidates((Config.OPTIONS_MODEL_FORWARD_SECURITY_MAP or {}).get(underlying_security)):
            if security and security not in reference_securities:
                reference_securities.append(security)

        live_reference_map: dict[str, dict[str, Any]] = {}
        if not reference_securities:
            return live_reference_map

        if Config.OPTIONS_FAIR_VALUE_LIVE_ENABLE and not workbook_only:
            payload = self.bloomberg.fetch_reference_securities(reference_securities, ["PX_LAST"])
            captured_at = datetime.now(timezone.utc).isoformat()
            for row in payload.get("rows") or []:
                security = str((row or {}).get("security") or "").strip()
                if not security:
                    continue
                live_reference_map[security] = {
                    **row,
                    "timestamp": captured_at,
                }

        if (
            Config.OPTIONS_FAIR_VALUE_EXCEL_BASKET_ENABLE
            or getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False)
        ):
            basket_payload = self.excel_live_workbook.read_fair_value_basket()
            if basket_payload.get("ok"):
                normalized_rows = {
                    self._normalize_security_key(item.get("security")): dict(item)
                    for item in (basket_payload.get("rows") or [])
                    if str(item.get("security") or "").strip()
                }
                for security in reference_securities:
                    workbook_row = normalized_rows.get(self._normalize_security_key(security))
                    if workbook_row:
                        live_reference_map[security] = workbook_row
        return live_reference_map

    def _resolve_live_forward_row(
        self,
        underlying_security: str,
        live_reference_map: dict[str, dict[str, Any]],
    ) -> tuple[str | None, dict[str, Any], float]:
        for security in _split_security_candidates((Config.OPTIONS_MODEL_FORWARD_SECURITY_MAP or {}).get(underlying_security)):
            row = live_reference_map.get(security) or {}
            fields = row.get("fields") or {}
            price = _finite_float(fields.get("PX_LAST"), 0.0)
            if price > 0:
                return security, row, price
        return None, {}, 0.0

    def _resolve_live_spot_row(
        self,
        underlying_security: str,
        live_reference_map: dict[str, dict[str, Any]],
    ) -> tuple[str | None, dict[str, Any], float]:
        for security in _split_security_candidates((Config.OPTIONS_MODEL_SPOT_SECURITY_MAP or {}).get(underlying_security)):
            row = live_reference_map.get(security) or {}
            fields = row.get("fields") or {}
            price = _finite_float(fields.get("PX_LAST"), 0.0)
            if price > 0:
                return security, row, price
        return None, {}, 0.0

    def build_run_config(self) -> FairValueRunConfig:
        return FairValueRunConfig(
            lookback_hours=max(int(Config.OPTIONS_FAIR_VALUE_LOOKBACK_HOURS), 24),
            max_snapshots=max(int(Config.OPTIONS_FAIR_VALUE_MAX_SNAPSHOTS), 200),
            min_points=max(int(Config.OPTIONS_FAIR_VALUE_MIN_POINTS), 40),
            zscore_window=max(int(Config.OPTIONS_FAIR_VALUE_ZSCORE_WINDOW), 12),
            feature_min_coverage_ratio=min(
                max(float(Config.OPTIONS_FAIR_VALUE_FEATURE_MIN_COVERAGE_RATIO), 0.05),
                0.95,
            ),
            feature_min_coverage_floor=max(int(Config.OPTIONS_FAIR_VALUE_FEATURE_MIN_COVERAGE_FLOOR), 8),
            factor_run_fill_tolerance_minutes=max(
                float(Config.OPTIONS_FAIR_VALUE_FACTOR_RUN_FILL_TOLERANCE_MINUTES),
                15.0,
            ),
            engine_mode=(
                str(Config.OPTIONS_FAIR_VALUE_ENGINE_MODE or "intraday_anchor").strip().lower()
                or "intraday_anchor"
            ),
            intraday_anchor_type=(
                str(Config.OPTIONS_FAIR_VALUE_INTRADAY_ANCHOR_TYPE or "previous_close").strip().lower()
                or "previous_close"
            ),
            rls_forgetting=min(max(float(Config.OPTIONS_FAIR_VALUE_RLS_FORGETTING), 0.85), 0.9995),
            rls_init_covariance=max(float(Config.OPTIONS_FAIR_VALUE_RLS_INIT_COVARIANCE), 10.0),
            residual_sigma_halflife=max(float(Config.OPTIONS_FAIR_VALUE_RESIDUAL_SIGMA_HALFLIFE), 4.0),
            state_space_measurement_noise=max(float(Config.OPTIONS_FAIR_VALUE_STATE_SPACE_MEASUREMENT_NOISE), 1.0),
            state_space_process_noise=max(float(Config.OPTIONS_FAIR_VALUE_STATE_SPACE_PROCESS_NOISE), 1e-8),
            breadth_scale_floor=min(max(float(Config.OPTIONS_FAIR_VALUE_BREADTH_SCALE_FLOOR), 0.05), 0.90),
            breadth_warmup_minutes=max(float(Config.OPTIONS_FAIR_VALUE_BREADTH_WARMUP_MINUTES), 5.0),
            band_sigma_multiplier=max(float(Config.OPTIONS_FAIR_VALUE_BAND_SIGMA_MULTIPLIER), 0.5),
            band_floor_points=max(float(Config.OPTIONS_FAIR_VALUE_BAND_FLOOR_POINTS), 50.0),
            band_vol_weight=max(float(Config.OPTIONS_FAIR_VALUE_BAND_VOL_WEIGHT), 0.0),
            options_overlay_weight=max(float(Config.OPTIONS_FAIR_VALUE_OPTIONS_OVERLAY_WEIGHT), 0.0),
            global_overlay_weight=max(float(Config.OPTIONS_FAIR_VALUE_GLOBAL_OVERLAY_WEIGHT), 0.0),
            residual_overlay_weight=max(float(Config.OPTIONS_FAIR_VALUE_RESIDUAL_OVERLAY_WEIGHT), 0.0),
            options_max_sigma_mult=max(float(Config.OPTIONS_FAIR_VALUE_OPTIONS_MAX_SIGMA_MULT), 0.2),
            global_max_sigma_mult=max(float(Config.OPTIONS_FAIR_VALUE_GLOBAL_MAX_SIGMA_MULT), 0.2),
            residual_max_sigma_mult=max(float(Config.OPTIONS_FAIR_VALUE_RESIDUAL_MAX_SIGMA_MULT), 0.2),
        )

    def _ensure_options_model_run(self, underlying_security: str, refresh: bool) -> dict[str, Any]:
        payload = self.store.read_latest_model_run(underlying_security) or {}
        if payload and not refresh:
            return payload
        return self.options_modeling.run_latest(underlying_security=underlying_security, persist=True)

    def _ensure_global_run(self, underlying_security: str, refresh: bool) -> dict[str, Any]:
        payload = self.store.read_latest_global_run(underlying_security) or {}
        if payload and not refresh:
            return payload
        return self.global_service.run_latest(
            underlying_security=underlying_security,
            refresh_local_model=False,
            persist=True,
        )

    @staticmethod
    def _realign_leg_implied_prices(
        summary: dict[str, Any],
        current_future_price: float,
    ) -> None:
        core_legs = dict(summary.get("core_legs") or {})
        core_reference = _finite_float(summary.get("core_fair_value_xb1"), None)
        isolated_core_reference = (
            _finite_float(summary.get("anchor_xb1"), None)
            or _finite_float(summary.get("fair_value_intraday_anchor_future"), None)
            or core_reference
        )
        core_contribution_total = 0.0
        for leg_payload in core_legs.values():
            if not isinstance(leg_payload, dict):
                continue
            contribution_points = _finite_float(leg_payload.get("contribution_points"), None)
            if contribution_points is not None:
                core_contribution_total += contribution_points
        if core_reference is None:
            core_reference = current_future_price if current_future_price > 0 else None
        if core_reference is not None:
            core_reference -= core_contribution_total
            for leg_key, leg_payload in core_legs.items():
                if not isinstance(leg_payload, dict):
                    continue
                leg_row = dict(leg_payload)
                contribution_points = _finite_float(leg_row.get("contribution_points"), None)
                if contribution_points is None:
                    continue
                leg_row["model_relative_implied_fair_value_xb1"] = core_reference + contribution_points
                if isolated_core_reference is not None:
                    leg_row["isolated_implied_fair_value_xb1"] = isolated_core_reference + contribution_points
                    leg_row["implied_fair_value_xb1"] = isolated_core_reference + contribution_points
                else:
                    leg_row["implied_fair_value_xb1"] = core_reference + contribution_points
                core_legs[leg_key] = leg_row
        if core_legs:
            summary["core_legs"] = core_legs

        shadow_legs = dict(summary.get("shadow_legs") or {})
        shadow_reference = _finite_float(summary.get("quality_adjusted_fair_value_xb1"), None)
        isolated_shadow_reference = (
            _finite_float(summary.get("core_fair_value_xb1"), None)
            or _finite_float(summary.get("anchor_xb1"), None)
            or shadow_reference
        )
        shadow_impact_total = 0.0
        for leg_payload in shadow_legs.values():
            if not isinstance(leg_payload, dict):
                continue
            quality_impact = _finite_float(leg_payload.get("quality_impact"), None)
            if quality_impact is not None:
                shadow_impact_total += (quality_impact * 0.65)
        if shadow_reference is None:
            shadow_reference = current_future_price if current_future_price > 0 else None
        if shadow_reference is not None:
            shadow_reference -= shadow_impact_total
            for leg_key, leg_payload in shadow_legs.items():
                if not isinstance(leg_payload, dict):
                    continue
                leg_row = dict(leg_payload)
                quality_impact = _finite_float(leg_row.get("quality_impact"), None)
                if quality_impact is None:
                    continue
                leg_row["model_relative_implied_fair_value_xb1"] = shadow_reference + (quality_impact * 0.65)
                if isolated_shadow_reference is not None:
                    leg_row["isolated_implied_fair_value_xb1"] = isolated_shadow_reference + (quality_impact * 0.65)
                    leg_row["implied_fair_value_xb1"] = isolated_shadow_reference + (quality_impact * 0.65)
                else:
                    leg_row["implied_fair_value_xb1"] = shadow_reference + (quality_impact * 0.65)
                shadow_legs[leg_key] = leg_row
        if shadow_legs:
            summary["shadow_legs"] = shadow_legs

    def run_latest(
        self,
        underlying_security: str = "IBOVE Index",
        refresh_options_model: bool = False,
        refresh_global_overlay: bool = False,
        persist: bool = True,
        workbook_only: bool = False,
    ) -> dict[str, Any]:
        if not Config.OPTIONS_FAIR_VALUE_ENABLE:
            raise ValueError("Options fair value engine is disabled")

        run_config = self.build_run_config()
        options_model_run = self._ensure_options_model_run(underlying_security, refresh_options_model)
        global_run = self._ensure_global_run(underlying_security, refresh_global_overlay)

        factor_frame, preparation = prepare_factor_frame(
            underlying_security=underlying_security,
            options_model_run=options_model_run,
            run_config=run_config,
        )
        live_reference_map = self._collect_live_reference_rows(
            underlying_security,
            workbook_only=workbook_only,
        )
        feature_meta = preparation["feature_meta"]
        all_feature_meta = preparation.get("all_feature_meta") or feature_meta
        structural_model = run_dynamic_structural_model(
            frame=factor_frame,
            feature_meta=feature_meta,
            feature_universe_meta=all_feature_meta,
            run_config=run_config,
        )
        proxy_factor_contributions = _build_proxy_factor_contributions(
            frame=factor_frame,
            all_feature_meta=all_feature_meta,
            structural_model=structural_model,
            run_config=run_config,
        )

        market_context = options_model_run.get("market_context") or {}
        options_summary = options_model_run.get("summary") or {}
        spot_source = ((market_context.get("sources") or {}).get("spot") or {})
        forward_source = ((market_context.get("sources") or {}).get("forward") or {})
        live_spot_price = _finite_float(
            market_context.get("spot_price"),
            _finite_float(options_summary.get("spot_price"), 0.0),
        )
        live_forward_price = _finite_float(
            market_context.get("forward_price"),
            _finite_float(options_summary.get("forward_price"), 0.0),
        )
        live_spot_security, live_spot_row, live_spot_reference_price = self._resolve_live_spot_row(
            underlying_security,
            live_reference_map,
        )
        live_forward_security, live_forward_row, live_forward_reference_price = self._resolve_live_forward_row(
            underlying_security,
            live_reference_map,
        )
        if live_spot_reference_price > 0:
            live_spot_price = live_spot_reference_price
        if live_forward_reference_price > 0:
            live_forward_price = live_forward_reference_price
        frame_current_future_price = _finite_float(factor_frame["local_future_close"].iloc[-1], 0.0)
        current_future_price = live_forward_price if live_forward_price > 0 else frame_current_future_price
        if live_spot_price > 0:
            spot_security = live_spot_security or str(market_context.get("spot_security") or "")
            spot_fallback_source = str(live_spot_row.get("fallback_source") or "").strip()
            if live_spot_reference_price > 0 and spot_security:
                current_spot_source = f"live_reference:{spot_fallback_source or 'state'}:{spot_security}"
            else:
                spot_source_label = str(spot_source.get("source") or "options_model_spot")
                current_spot_source = f"{spot_source_label}:{spot_security}" if spot_security else spot_source_label
        else:
            current_spot_source = str(spot_source.get("source") or "market_context_spot")
        current_spot_timestamp = (
            str(live_spot_row.get("timestamp") or "").strip()
            or str(options_model_run.get("captured_at") or "").strip()
            or None
        )
        if live_forward_price > 0:
            forward_security = live_forward_security or str(market_context.get("forward_security") or "")
            fallback_source = str(live_forward_row.get("fallback_source") or "").strip()
            if live_forward_reference_price > 0 and forward_security:
                current_price_source = f"live_reference:{fallback_source or 'state'}:{forward_security}"
            else:
                source_label = str(forward_source.get("source") or "options_model_forward")
                current_price_source = f"{source_label}:{forward_security}" if forward_security else source_label
        else:
            current_price_source = "factor_frame_latest"
        current_price_timestamp = (
            str(live_forward_row.get("timestamp") or "").strip()
            or str(options_model_run.get("captured_at") or "").strip()
            or None
        )
        structural_snapshot_timestamp = factor_frame.index[-1].isoformat() if len(factor_frame.index) else None
        basis_points = _finite_float(
            market_context.get("future_basis_points"),
            _finite_float(factor_frame["basis_points_current"].iloc[-1], 0.0),
        )
        realized_vol_points = max(
            _finite_float(factor_frame["realized_vol_rolling"].iloc[-1], 0.0)
            * _finite_float(factor_frame["structural_anchor_price"].iloc[-1], current_future_price),
            0.0,
        )
        live_factor_snapshot = build_live_factor_rows(
            latest_fair_value_run={
                "summary": {
                    "live_factor_rows": preparation.get("latest_factor_rows") or [],
                }
            },
            macro_state=self.store.read_state() or {},
            live_reference_rows=live_reference_map,
        )
        us_rates_context = build_us_rates_factor_context(
            (live_factor_snapshot.get("rows") or [])
            or (preparation.get("latest_factor_rows") or [])
        )

        options_overlay = build_options_overlay(
            current_future_price=current_future_price,
            structural_fair_value=float(structural_model["fair_value_structural"]),
            current_sigma_points=float(structural_model["residual_sigma_points"]),
            options_model_run=options_model_run,
            run_config=run_config,
        )
        global_overlay = build_global_distortion_overlay(
            current_future_price=current_future_price,
            current_sigma_points=float(structural_model["residual_sigma_points"]),
            global_run=global_run,
            run_config=run_config,
        )
        regime = classify_market_regime(
            frame=factor_frame,
            feature_meta=feature_meta,
            options_overlay=options_overlay,
            global_overlay=global_overlay,
            us_rates_context=us_rates_context,
        )
        residual_ml = build_residual_ml_adjustment(
            frame=factor_frame,
            structural_model=structural_model,
            feature_meta=feature_meta,
            run_config=run_config,
        )
        band = build_fair_value_band(
            fair_value_final=(
                float(structural_model["fair_value_structural"])
                + float(options_overlay.get("fair_value_options_adjustment") or 0.0)
                + float(global_overlay.get("fair_value_global_adjustment") or 0.0)
                + float(residual_ml.get("fair_value_residual_adjustment") or 0.0)
            ),
            structural_sigma_points=float(structural_model["residual_sigma_points"]),
            realized_vol_points=realized_vol_points,
            options_overlay=options_overlay,
            global_overlay=global_overlay,
            regime=regime,
            us_rates_context=us_rates_context,
            options_model_run=options_model_run,
            run_config=run_config,
        )
        summary = build_fair_value_output(
            underlying_security=underlying_security,
            current_future_price=current_future_price,
            basis_points=basis_points,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            structural_snapshot_timestamp=structural_snapshot_timestamp,
            structural_model=structural_model,
            residual_ml=residual_ml,
            options_overlay=options_overlay,
            global_overlay=global_overlay,
            regime=regime,
            band=band,
            us_rates_context=us_rates_context,
        )
        summary["fair_value_structural"] = summary["fair_value_structural_future"]
        summary["fair_value_tactical"] = summary["fair_value_tactical_future"]
        summary["fair_value_final"] = summary["fair_value_final_future"]
        summary["current_spot_price"] = live_spot_price if live_spot_price > 0 else None
        summary["current_spot_source"] = current_spot_source
        summary["current_spot_timestamp"] = current_spot_timestamp
        if live_spot_price > 0 and current_future_price > 0:
            summary["live_basis_points"] = current_future_price - live_spot_price
            summary["live_basis_pct"] = (current_future_price - live_spot_price) / live_spot_price
        summary["live_factor_rows"] = live_factor_snapshot.get("rows") or (preparation.get("latest_factor_rows") or [])
        quality_package: dict[str, Any] = {}
        if Config.OPTIONS_FAIR_VALUE_QUALITY_ENABLE:
            quality_package = build_fair_value_quality_package(
                current_future_price=current_future_price,
                core_fair_value_xb1=float(summary.get("fair_value_final_future") or 0.0),
                band_half_width_points=float(band.get("band_half_width_points") or 0.0),
                live_factor_rows=summary.get("live_factor_rows") or [],
                live_reference_rows=live_reference_map,
                structural_model=structural_model,
                proxy_contributions_by_factor=proxy_factor_contributions,
                options_overlay=options_overlay,
                global_overlay=global_overlay,
                regime=regime,
                us_rates_context=us_rates_context,
                base_confidence=float(summary.get("confidence") or 0.35),
                base_risk_quality_score=float(summary.get("risk_quality_score") or 0.5),
                convergence_probability=float(summary.get("convergence_probability") or 0.5),
            )
            self._realign_leg_implied_prices(quality_package, current_future_price)
            summary.update(quality_package)
        self._realign_leg_implied_prices(summary, current_future_price)
        summary["timestamp"] = captured_at = datetime.now(timezone.utc).isoformat()
        summary["ibov_last"] = summary.get("current_spot_price")
        summary["xb1_last"] = summary.get("current_future_price")
        summary["basis_ibov_xb1"] = summary.get("live_basis_points", basis_points)
        summary["core_fair_value_xb1"] = summary.get("core_fair_value_xb1") or summary.get("fair_value_final_future")
        summary["quality_adjusted_fair_value_xb1"] = (
            summary.get("quality_adjusted_fair_value_xb1")
            or summary.get("fair_value_final_future")
        )
        summary["dislocation_points"] = summary.get("mispricing_value")
        summary["dislocation_pct"] = summary.get("mispricing_pct")
        summary["zscore_dislocation"] = summary.get("mispricing_zscore")
        summary["feature_flags"] = {
            "fair_value_quality_enabled": bool(Config.OPTIONS_FAIR_VALUE_QUALITY_ENABLE),
        }

        session_date = str(options_model_run.get("session_date") or captured_at[:10])
        run_id = hashlib.sha1(
            f"fair_value|{underlying_security}|{captured_at}|{options_model_run.get('run_id')}|{global_run.get('run_id')}".encode("utf-8")
        ).hexdigest()
        payload = {
            "run_id": run_id,
            "captured_at": captured_at,
            "session_date": session_date,
            "underlying_security": underlying_security,
            "source": {
                "options_model_run_id": options_model_run.get("run_id"),
                "global_run_id": global_run.get("run_id"),
            },
            "config": {
                "lookback_hours": run_config.lookback_hours,
                "max_snapshots": run_config.max_snapshots,
                "min_points": run_config.min_points,
                "zscore_window": run_config.zscore_window,
                "engine_mode": run_config.engine_mode,
                "intraday_anchor_type": run_config.intraday_anchor_type,
                "rls_forgetting": run_config.rls_forgetting,
                "rls_init_covariance": run_config.rls_init_covariance,
                "state_space_measurement_noise": run_config.state_space_measurement_noise,
                "state_space_process_noise": run_config.state_space_process_noise,
                "band_sigma_multiplier": run_config.band_sigma_multiplier,
            },
            "factor_preparation": {
                "diagnostics": preparation["diagnostics"],
                "feature_meta": feature_meta,
                "all_feature_meta": all_feature_meta,
                "latest_factor_rows": preparation.get("latest_factor_rows") or [],
                "latest_features": {
                    name: {
                        "feature_value": float(factor_frame.iloc[-1][meta["feature_column"]]),
                        "feature_zscore": float(factor_frame.iloc[-1][meta["z_column"]]),
                        "block": meta["block"],
                        "label": meta["label"],
                    }
                    for name, meta in feature_meta.items()
                },
            },
            "structural_model": structural_model,
            "proxy_factor_contributions": proxy_factor_contributions,
            "residual_ml": residual_ml,
            "options_overlay": options_overlay,
            "global_overlay": global_overlay,
            "regime": regime,
            "band": band,
            "us_rates_context": us_rates_context,
            "quality": quality_package,
            "feature_flags": summary.get("feature_flags") or {},
            "summary": summary,
            "timestamp": captured_at,
            "ibov_last": summary.get("ibov_last"),
            "xb1_last": summary.get("xb1_last"),
            "anchor_xb1": summary.get("anchor_xb1"),
            "session_anchor_xb1": summary.get("session_anchor_xb1"),
            "anchor_type": summary.get("anchor_type"),
            "model_mode": summary.get("model_mode"),
            "basis_ibov_xb1": summary.get("basis_ibov_xb1"),
            "core_fair_value_xb1": summary.get("core_fair_value_xb1"),
            "quality_adjusted_fair_value_xb1": summary.get("quality_adjusted_fair_value_xb1"),
            "dislocation_points": summary.get("dislocation_points"),
            "dislocation_pct": summary.get("dislocation_pct"),
            "zscore_dislocation": summary.get("zscore_dislocation"),
            "factor_expected_returns": summary.get("factor_expected_returns"),
            "factor_cumulative_contributions_from_anchor": summary.get("factor_cumulative_contributions_from_anchor"),
            "mispricing": summary.get("mispricing"),
            "is_price_above_fv": summary.get("is_price_above_fv"),
            "convergence_probability": summary.get("convergence_probability"),
            "model_confidence": summary.get("confidence"),
            "confidence": summary.get("confidence"),
            "risk_quality_score": summary.get("risk_quality_score"),
            "implicit_sentiment": summary.get("implicit_sentiment"),
            "sentiment_confidence": summary.get("sentiment_confidence"),
            "quality_ribbon": summary.get("quality_ribbon"),
            "curve_conditions": summary.get("curve_conditions"),
            "core_legs": summary.get("core_legs"),
            "shadow_legs": summary.get("shadow_legs"),
            "explanation": summary.get("explanation"),
        }
        if persist:
            payload["persisted"] = self.store.write_fair_value_run(payload)
            if bool(Config.OPTIONS_REGIME_PRICE_MAKING_ENABLE):
                try:
                    from .regime_price_making_service import RegimePriceMakingService

                    regime_payload = RegimePriceMakingService(store=self.store).build_latest(
                        underlying_security=underlying_security,
                        persist=True,
                    )
                    payload["regime_price_making"] = (regime_payload.get("summary") or {})
                except Exception:
                    logger.exception("Failed to persist RegimePriceMakingEngine snapshot")
        return payload

    def read_latest_run(self, underlying_security: str) -> dict[str, Any] | None:
        return self.store.read_latest_fair_value_run(underlying_security)

    def read_run(self, run_id: str) -> dict[str, Any] | None:
        return self.store.read_fair_value_run(run_id)

    def live_factor_snapshot(
        self,
        underlying_security: str = "IBOVE Index",
        *,
        workbook_only: bool = False,
    ) -> dict[str, Any]:
        latest_run = self.read_latest_run(underlying_security) or {}
        macro_state = self.store.read_state() or {}
        if not self._live_sources_enabled():
            summary = latest_run.get("summary") or {}
            return {
                "underlying_security": underlying_security,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "snapshot_timestamp": summary.get("current_price_timestamp"),
                "rows": _normalize_cached_factor_rows(
                    summary.get("live_factor_rows")
                    or ((latest_run.get("factor_preparation") or {}).get("latest_factor_rows") or [])
                ),
                "current_future_price": summary.get("current_future_price"),
                "current_price_source": summary.get("current_price_source") or "persisted_fair_value_run",
                "current_price_timestamp": summary.get("current_price_timestamp"),
                "current_spot_price": summary.get("current_spot_price"),
                "current_spot_source": summary.get("current_spot_source"),
                "current_spot_timestamp": summary.get("current_spot_timestamp"),
                "live_basis_points": summary.get("live_basis_points"),
                "live_basis_pct": summary.get("live_basis_pct"),
                "live_disabled": True,
            }
        live_reference_map = self._collect_live_reference_rows(
            underlying_security,
            workbook_only=workbook_only,
        )

        live_payload = build_live_factor_rows(
            latest_fair_value_run=latest_run,
            macro_state=macro_state,
            live_reference_rows=live_reference_map,
        )
        live_payload["underlying_security"] = underlying_security
        forward_security, live_forward_row, live_forward_price = self._resolve_live_forward_row(
            underlying_security,
            live_reference_map,
        )
        if live_forward_price > 0:
            fallback_source = str(live_forward_row.get("fallback_source") or "").strip()
            live_payload["current_future_price"] = live_forward_price
            live_payload["current_price_source"] = f"live_reference:{fallback_source or 'state'}:{forward_security}"
            live_payload["current_price_timestamp"] = live_forward_row.get("timestamp") or live_payload.get("captured_at")
        else:
            live_payload["current_future_price"] = (((latest_run.get("summary") or {}).get("current_future_price")))
            live_payload["current_price_source"] = (((latest_run.get("summary") or {}).get("current_price_source")))
            live_payload["current_price_timestamp"] = (((latest_run.get("summary") or {}).get("current_price_timestamp")))
        spot_security, live_spot_row, live_spot_price = self._resolve_live_spot_row(
            underlying_security,
            live_reference_map,
        )
        if live_spot_price > 0:
            spot_fallback_source = str(live_spot_row.get("fallback_source") or "").strip()
            live_payload["current_spot_price"] = live_spot_price
            live_payload["current_spot_source"] = f"live_reference:{spot_fallback_source or 'state'}:{spot_security}"
            live_payload["current_spot_timestamp"] = live_spot_row.get("timestamp") or live_payload.get("captured_at")
        else:
            summary = latest_run.get("summary") or {}
            live_payload["current_spot_price"] = summary.get("current_spot_price")
            live_payload["current_spot_source"] = summary.get("current_spot_source")
            live_payload["current_spot_timestamp"] = summary.get("current_spot_timestamp")
        current_future_price = _finite_float(live_payload.get("current_future_price"), 0.0)
        current_spot_price = _finite_float(live_payload.get("current_spot_price"), 0.0)
        if current_future_price > 0 and current_spot_price > 0:
            live_payload["live_basis_points"] = current_future_price - current_spot_price
            live_payload["live_basis_pct"] = (current_future_price - current_spot_price) / current_spot_price
        return live_payload
