from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from statistics import pstdev
from typing import Any

from ...config import Config
from ...utils.logger import get_logger
from .types import GlobalAssetConfig, GlobalTriangulationConfig

logger = get_logger("mirofish.options_global.input_preparation")


DEFAULT_ASSET_CONFIGS: list[dict[str, Any]] = [
    {
        "slug": "local_index",
        "label": "Local Index Future",
        "primary_security": "XB1 Index",
        "alternate_securities": [],
        "region": "BR",
        "support_level": "A",
        "weight": 1.35,
        "model_underlying": "IBOVE Index",
        "trade_symbol": "BVMF:WINM26",
        "use_future_space": True,
    },
    {
        "slug": "spx",
        "label": "S&P 500 Index",
        "primary_security": "SPX Index",
        "alternate_securities": ["ES1 Index", "ESA Index"],
        "region": "US",
        "support_level": "A",
        "weight": 1.0,
        "model_underlying": "SPX Index",
    },
    {
        "slug": "russell",
        "label": "Russell 2000 Future",
        "primary_security": "RTYA Index",
        "alternate_securities": [],
        "region": "US",
        "support_level": "C",
        "weight": 0.9,
    },
    {
        "slug": "us_proxy",
        "label": "S&P Future Proxy",
        "primary_security": "ES1 Index",
        "alternate_securities": ["ESA Index"],
        "region": "US",
        "support_level": "A",
        "weight": 0.65,
        "model_underlying": "SPX Index",
    },
    {
        "slug": "em_future",
        "label": "Emerging Markets Future (MES1)",
        "primary_security": "MES1 Index",
        "alternate_securities": [],
        "region": "EM",
        "support_level": "C",
        "weight": 0.55,
    },
    {
        "slug": "em",
        "label": "Emerging Markets Proxy",
        "primary_security": "EEM US Equity",
        "alternate_securities": ["EMBIV Index"],
        "region": "EM",
        "support_level": "C",
        "weight": 0.8,
    },
    {
        "slug": "europe",
        "label": "DAX",
        "primary_security": "DAX Index",
        "alternate_securities": ["DMA Index"],
        "region": "EU",
        "support_level": "C",
        "weight": 0.8,
    },
    {
        "slug": "ewz",
        "label": "EWZ",
        "primary_security": "EWZ US Equity",
        "alternate_securities": ["BRAZIL CDS USD SR 3Y D14 Curncy"],
        "region": "BR",
        "support_level": "C",
        "weight": 0.8,
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def load_global_triangulation_config() -> GlobalTriangulationConfig:
    return GlobalTriangulationConfig(
        bar_interval_minutes=max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_BAR_INTERVAL_MINUTES), 1),
        lookback_hours=max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_LOOKBACK_HOURS), 2),
        min_points=max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_MIN_POINTS), 8),
        ewma_alpha=min(max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_EWMA_ALPHA), 0.01), 0.99),
        corr_short_window=max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_CORR_SHORT_WINDOW), 4),
        corr_smooth_window=max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_CORR_SMOOTH_WINDOW), 8),
        distortion_sigma_multiplier=max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_DISTORTION_SIGMA_MULTIPLIER), 0.5),
        distortion_weight=max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_DISTORTION_WEIGHT), 0.0),
        structural_weight=max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_STRUCTURAL_WEIGHT), 0.0),
        corr_weight=max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_CORR_WEIGHT), 0.0),
        local_model_max_age_seconds=max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_LOCAL_MODEL_MAX_AGE_SECONDS), 0),
        level_cluster_points=max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_LEVEL_CLUSTER_POINTS), 50.0),
        level_match_points=max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_LEVEL_MATCH_POINTS), 50.0),
        min_corr_for_mapping=min(max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_MIN_CORR_FOR_MAPPING), 0.0), 0.99),
        vol_band_sigma=max(float(Config.OPTIONS_GLOBAL_TRIANGULATION_VOL_BAND_SIGMA), 0.25),
        top_mapped_levels=max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_TOP_MAPPED_LEVELS), 4),
    )


def load_asset_configs() -> list[GlobalAssetConfig]:
    raw_json = str(Config.OPTIONS_GLOBAL_TRIANGULATION_ASSETS_JSON or "").strip()
    rows: list[dict[str, Any]]
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            rows = parsed if isinstance(parsed, list) else DEFAULT_ASSET_CONFIGS
        except Exception:
            logger.exception("Failed to parse OPTIONS_GLOBAL_TRIANGULATION_ASSETS_JSON; using defaults")
            rows = DEFAULT_ASSET_CONFIGS
    else:
        rows = DEFAULT_ASSET_CONFIGS

    configs: list[GlobalAssetConfig] = []
    for row in rows:
        primary_security = str(row.get("primary_security") or "").strip()
        slug = str(row.get("slug") or "").strip()
        label = str(row.get("label") or slug or primary_security).strip()
        if not slug or not primary_security:
            continue
        alternates = tuple(str(item).strip() for item in (row.get("alternate_securities") or []) if str(item).strip())
        configs.append(
            GlobalAssetConfig(
                slug=slug,
                label=label,
                primary_security=primary_security,
                region=str(row.get("region") or "GLOBAL").strip().upper(),
                support_level=str(row.get("support_level") or "C").strip().upper(),
                weight=max(_safe_float(row.get("weight"), 1.0), 0.0),
                alternate_securities=alternates,
                model_underlying=str(row.get("model_underlying") or "").strip() or None,
                trade_symbol=str(row.get("trade_symbol") or "").strip() or None,
                use_future_space=bool(row.get("use_future_space", False)),
            )
        )
    return configs


def _compute_series_metrics(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes: list[tuple[datetime, float]] = []
    for row in bars:
        ts = _parse_timestamp(row.get("event_time"))
        close = _safe_float(row.get("close"), 0.0)
        if ts is None or close <= 0:
            continue
        closes.append((ts, close))
    closes.sort(key=lambda item: item[0])

    returns: list[tuple[datetime, float]] = []
    for index in range(1, len(closes)):
        previous = closes[index - 1][1]
        current = closes[index][1]
        if previous <= 0 or current <= 0:
            continue
        returns.append((closes[index][0], (current / previous) - 1.0))

    intraday_return = 0.0
    latest_return = 0.0
    realized_vol = 0.0
    if len(closes) >= 2:
        intraday_return = (closes[-1][1] / closes[0][1]) - 1.0
    if returns:
        latest_return = returns[-1][1]
        values = [item[1] for item in returns]
        realized_vol = pstdev(values) if len(values) >= 2 else abs(latest_return)

    return {
        "bars": closes,
        "return_series": returns,
        "current_price": closes[-1][1] if closes else None,
        "previous_price": closes[-2][1] if len(closes) >= 2 else None,
        "intraday_return": intraday_return,
        "latest_return": latest_return,
        "realized_vol_intraday": realized_vol,
        "point_count": len(closes),
    }


def _choose_live_security(config: GlobalAssetConfig, quote_rows: dict[str, dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    for security in (config.primary_security, *config.alternate_securities):
        row = quote_rows.get(security) or {}
        fields = row.get("fields") or {}
        price = _safe_float(row.get("price"), 0.0) or _safe_float(fields.get("PX_LAST"), 0.0)
        if row.get("ok") and price > 0:
            return security, row
    return None, {}


def prepare_global_inputs(
    *,
    local_model_run: dict[str, Any],
    model_runs_by_underlying: dict[str, dict[str, Any]],
    bloomberg_service: Any,
    run_config: GlobalTriangulationConfig,
) -> dict[str, Any]:
    asset_configs = load_asset_configs()
    now = _utc_now()
    start_dt = now - timedelta(hours=run_config.lookback_hours)

    candidate_securities = []
    for config in asset_configs:
        candidate_securities.append(config.primary_security)
        candidate_securities.extend(config.alternate_securities)
    reference_response = bloomberg_service.fetch_reference_securities(list(dict.fromkeys(candidate_securities)))
    quote_rows = {
        str(row.get("security") or ""): row
        for row in (reference_response.get("rows") or [])
        if row.get("security")
    }

    assets: list[dict[str, Any]] = []
    for config in asset_configs:
        selected_security, quote = _choose_live_security(config, quote_rows)
        selected_row = quote or {}
        bars_response = {"rows": [], "status": {"session_ok": False}}
        if selected_security:
            try:
                bars_response = bloomberg_service.fetch_intraday_bars(
                    selected_security,
                    start_dt=start_dt,
                    end_dt=now,
                    interval_minutes=run_config.bar_interval_minutes,
                )
            except Exception:
                logger.exception("Failed to fetch intraday bars for %s", selected_security)
        series_metrics = _compute_series_metrics(bars_response.get("rows") or [])
        fields = selected_row.get("fields") or {}
        current_price = series_metrics.get("current_price") or _safe_float(selected_row.get("price"), 0.0) or _safe_float(fields.get("PX_LAST"), 0.0) or None
        model_run = model_runs_by_underlying.get(config.model_underlying or "") if config.model_underlying else None
        if not model_run and config.model_underlying and config.model_underlying == (local_model_run.get("underlying_security") or ""):
            model_run = local_model_run

        if model_run and model_run.get("summary"):
            actual_support_level = "A"
        elif any(field in fields for field in ("IVOL_MID", "IVOL_LAST", "IVOL_BID", "IVOL_ASK")):
            actual_support_level = "B"
        else:
            actual_support_level = "C"

        point_count = int(series_metrics.get("point_count") or 0)
        state_quality_score = min(
            1.0,
            (0.45 if current_price else 0.0)
            + min(point_count / max(run_config.min_points, 1), 1.0) * 0.35
            + (0.20 if actual_support_level == "A" else 0.12 if actual_support_level == "B" else 0.06),
        )

        assets.append(
            {
                "slug": config.slug,
                "label": config.label,
                "region": config.region,
                "configured_support_level": config.support_level,
                "support_level": actual_support_level,
                "weight": config.weight,
                "primary_security": config.primary_security,
                "selected_security": selected_security or config.primary_security,
                "trade_symbol": config.trade_symbol,
                "use_future_space": config.use_future_space,
                "model_underlying": config.model_underlying,
                "dealer_zone_source_underlying": config.model_underlying,
                "dealer_zone_source_security": (config.model_underlying if actual_support_level == "A" and config.model_underlying else (selected_security or config.primary_security)),
                "dealer_zone_source_mode": (
                    "options_model"
                    if actual_support_level == "A" and config.model_underlying
                    else "partial_iv"
                    if actual_support_level == "B"
                    else "price_proxy"
                ),
                "quote": selected_row,
                "current_price": current_price,
                "point_count": point_count,
                "intraday_return": series_metrics.get("intraday_return") or 0.0,
                "latest_return": series_metrics.get("latest_return") or 0.0,
                "realized_vol_intraday": series_metrics.get("realized_vol_intraday") or 0.0,
                "previous_price": series_metrics.get("previous_price"),
                "return_series": series_metrics.get("return_series") or [],
                "bars": series_metrics.get("bars") or [],
                "state_quality_score": state_quality_score,
                "options_model_run": model_run or {},
                "current_fields": fields,
                "bar_status": bars_response.get("status") or {},
            }
        )

    return {
        "generated_at": now.isoformat(),
        "bar_interval_minutes": run_config.bar_interval_minutes,
        "lookback_hours": run_config.lookback_hours,
        "assets": assets,
        "reference_status": reference_response.get("status") or {},
    }
