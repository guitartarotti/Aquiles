from __future__ import annotations

import json
import math
import re
import warnings
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

warnings.filterwarnings(
    "once",
    message="DataFrame is highly fragmented.*",
    category=pd.errors.PerformanceWarning,
)

from ...config import Config
from ...utils.logger import get_logger
from .factor_definitions import DEFAULT_FACTOR_DEFINITIONS
from .types import FairValueFactorDefinition, FairValueRunConfig

logger = get_logger("mirofish.options_fair_value.factor_preparation")

SESSION_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _clean_numeric(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return parsed


def _append_column_batch(frame: pd.DataFrame, columns: dict[str, Any]) -> pd.DataFrame:
    if not columns:
        return frame
    replacement_frame = pd.DataFrame(columns, index=frame.index)
    replaced_columns = [column for column in replacement_frame.columns if column in frame.columns]
    base_frame = frame.drop(columns=replaced_columns) if replaced_columns else frame
    return pd.concat([base_frame, replacement_frame], axis=1).copy()


def _tail_lines(path: Path, max_lines: int) -> list[str]:
    if max_lines <= 0 or not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(0, 2)
        file_size = handle.tell()
        block_size = 65536
        data = b""
        lines: list[bytes] = []
        position = file_size
        while position > 0 and len(lines) <= max_lines:
            read_size = min(block_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            data = chunk + data
            parts = data.split(b"\n")
            data = parts[0]
            lines = parts[1:] + lines
        if data:
            lines = [data] + lines
    return [line.decode("utf-8", errors="ignore") for line in lines[-max_lines:] if line.strip()]


def _contract_close(snapshot: dict[str, Any], ticker: str) -> float | None:
    contract = (((snapshot.get("market") or {}).get("contracts") or {}).get(ticker) or {})
    ohlcv = contract.get("ohlcv") or {}
    latest_window = ohlcv.get("latest_window") or {}
    previous_window = ohlcv.get("previous_window") or {}
    for key in ("close", "open"):
        value = _safe_float(latest_window.get(key))
        if value and value > 0:
            return value
    for key in ("close", "open"):
        value = _safe_float(previous_window.get(key))
        if value and value > 0:
            return value
    book = contract.get("book") or {}
    summary = book.get("summary") or {}
    bid = _safe_float(summary.get("best_bid_price"))
    ask = _safe_float(summary.get("best_ask_price"))
    if bid and ask and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return None


def _reference_price(snapshot: dict[str, Any], security: str) -> float | None:
    row = (((snapshot.get("market") or {}).get("reference_assets") or {}).get(security) or {})
    value = _safe_float(row.get("price"))
    if value and value > 0:
        return value
    fields = row.get("fields") or {}
    return _safe_float(fields.get("PX_LAST"))


def _security_price(snapshot: dict[str, Any], security: str) -> float | None:
    row = (((snapshot.get("market") or {}).get("securities") or {}).get(security) or {})
    return _safe_float(row.get("price"))


def _mean_or_none(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _build_di_curve_metric_block(
    short_values: list[float | None],
    long_values: list[float | None],
) -> dict[str, float | None]:
    short_clean = [value for value in short_values if value is not None]
    long_clean = [value for value in long_values if value is not None]
    curve_values = short_clean + long_clean
    short_mean = _mean_or_none(short_clean)
    long_mean = _mean_or_none(long_clean)
    level_mean = _mean_or_none(curve_values)

    belly_values = long_clean[:3] if len(long_clean) >= 3 else (long_clean or curve_values)
    medium_long_values = long_clean[-2:] if len(long_clean) >= 2 else (long_clean or curve_values)
    belly_mean = _mean_or_none(belly_values)
    medium_long_mean = _mean_or_none(medium_long_values)
    curve_midpoint = _mean_or_none([short_mean, long_mean])

    if short_mean is not None and long_mean is not None:
        slope = long_mean - short_mean
    else:
        slope = None
    if belly_mean is not None and curve_midpoint is not None:
        twist = belly_mean - curve_midpoint
    else:
        twist = None
    if long_mean is not None and level_mean is not None:
        fiscal_pressure = long_mean - level_mean
    else:
        fiscal_pressure = None
    if medium_long_mean is not None and belly_mean is not None:
        duration_pressure = medium_long_mean - belly_mean
    else:
        duration_pressure = None

    return {
        "di_short_mean": short_mean,
        "di_long_mean": long_mean,
        "di_level_mean": level_mean,
        "di_belly_mean": belly_mean,
        "di_medium_long_mean": medium_long_mean,
        "di_slope": slope,
        "di_twist": twist,
        "di_fiscal_pressure_proxy": fiscal_pressure,
        "di_duration_pressure_proxy": duration_pressure,
    }


def _di_reference_security_from_contract_ticker(ticker: str) -> str | None:
    text = str(ticker or "").strip().upper()
    match = re.search(r"DI1[A-Z]?(\d{2})$", text)
    if not match:
        return None
    return f"ODF{match.group(1)} Comdty"


def _reference_asset_price(reference_rows: dict[str, dict[str, Any]], security: str | None) -> float | None:
    if not security:
        return None
    reference_row = reference_rows.get(security) or {}
    fields = reference_row.get("fields") or {}
    value = _clean_numeric(fields.get("PX_LAST"))
    if value is None:
        value = _clean_numeric(reference_row.get("price"))
    return value


def _reference_asset_daily_change(reference_rows: dict[str, dict[str, Any]], security: str | None) -> float | None:
    if not security:
        return None
    reference_row = reference_rows.get(security) or {}
    fields = reference_row.get("fields") or {}
    if fields.get("CHG_PCT_1D") not in (None, ""):
        return _clean_numeric(fields.get("CHG_PCT_1D"))
    return _clean_numeric(reference_row.get("daily_change_pct"))


def _di_curve_reference_timestamp(
    reference_rows: dict[str, dict[str, Any]],
    contract_tickers: list[str],
) -> str | None:
    timestamps: list[tuple[datetime, str]] = []
    for ticker in contract_tickers:
        security = _di_reference_security_from_contract_ticker(ticker)
        reference_row = reference_rows.get(security or "") or {}
        parsed = _parse_timestamp(reference_row.get("timestamp"))
        if parsed is None:
            continue
        timestamps.append((parsed, str(reference_row.get("timestamp") or "").strip()))
    if not timestamps:
        return None
    timestamps.sort(key=lambda item: item[0])
    return timestamps[-1][1]


def _build_di_curve_derived_values(
    snapshot: dict[str, Any],
    short_tickers: list[str],
    long_tickers: list[str],
    *,
    live_reference_rows: dict[str, dict[str, Any]] | None = None,
) -> dict[str, float | None]:
    reference_rows = live_reference_rows or {}
    short_values = []
    for ticker in short_tickers:
        security = _di_reference_security_from_contract_ticker(ticker)
        short_values.append(_reference_asset_price(reference_rows, security) or _contract_close(snapshot, ticker))
    long_values = []
    for ticker in long_tickers:
        security = _di_reference_security_from_contract_ticker(ticker)
        long_values.append(_reference_asset_price(reference_rows, security) or _contract_close(snapshot, ticker))
    return _build_di_curve_metric_block(short_values, long_values)


def _build_di_curve_derived_daily_changes(
    live_reference_rows: dict[str, dict[str, Any]] | None,
    short_tickers: list[str],
    long_tickers: list[str],
) -> dict[str, float | None]:
    reference_rows = live_reference_rows or {}
    short_values = [
        _reference_asset_daily_change(reference_rows, _di_reference_security_from_contract_ticker(ticker))
        for ticker in short_tickers
    ]
    long_values = [
        _reference_asset_daily_change(reference_rows, _di_reference_security_from_contract_ticker(ticker))
        for ticker in long_tickers
    ]
    return _build_di_curve_metric_block(short_values, long_values)


def _is_core_feature(definition: FairValueFactorDefinition) -> bool:
    layer = str(definition.model_layer or "core").strip().lower()
    return layer in {"core", "core_and_shadow", "both"}


def _model_input_direction_multiplier(expected_direction: str) -> float:
    key = str(expected_direction or "").strip().lower()
    if key in {
        "negative_when_rising",
        "positive_when_falling",
        "negative_when_steepening",
        "negative_when_widening",
        "positive_when_dovish",
    }:
        return -1.0
    return 1.0


def _recent_reference_asset_lookup(max_lines: int = 5000) -> dict[str, dict[str, Any]]:
    path = Path(Config.MACRO_DATA_DIR) / "snapshots.jsonl"
    lookup: dict[str, dict[str, Any]] = {}
    for line in reversed(_tail_lines(path, max_lines=max_lines)):
        try:
            item = json.loads(line)
        except Exception:
            continue
        generated_at = str(item.get("generated_at") or "").strip() or None
        snapshot = item.get("snapshot") or {}
        reference_assets = ((snapshot.get("market") or {}).get("reference_assets") or {})
        for security, row in reference_assets.items():
            security_key = str(security or "").strip()
            if not security_key or security_key in lookup:
                continue
            row_data = row or {}
            fields = row_data.get("fields") or {}
            price = _clean_numeric(fields.get("PX_LAST"))
            if price is None:
                price = _clean_numeric(row_data.get("price"))
            if price is None:
                continue
            lookup[security_key] = {
                "price": price,
                "timestamp": generated_at,
                "fallback_source": str(row_data.get("fallback_source") or "").strip() or "snapshot_cache",
                "row": row_data,
            }
    return lookup


def load_factor_definitions() -> list[FairValueFactorDefinition]:
    raw_json = str(Config.OPTIONS_FAIR_VALUE_STRUCTURAL_FACTORS_JSON or "").strip()
    rows = DEFAULT_FACTOR_DEFINITIONS
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list) and parsed:
                rows = parsed
        except Exception:
            logger.exception("Failed to parse OPTIONS_FAIR_VALUE_STRUCTURAL_FACTORS_JSON; using defaults")

    return [
        FairValueFactorDefinition(
            name=str(item.get("name") or "").strip(),
            label=str(item.get("label") or item.get("name") or "").strip(),
            block=str(item.get("block") or "other").strip(),
            source_kind=str(item.get("source_kind") or "reference_asset").strip(),
            source_key=str(item.get("source_key") or "").strip(),
            transform=str(item.get("transform") or "return").strip(),
            weight=max(float(item.get("weight", 1.0)), 0.0),
            economic_name=str(item.get("economic_name") or item.get("label") or item.get("name") or "").strip(),
            asset_class=str(item.get("asset_class") or "").strip(),
            subclass=str(item.get("subclass") or "").strip(),
            model_layer=str(item.get("model_layer") or "core").strip() or "core",
            expected_direction_to_ibov=str(item.get("expected_direction_to_ibov") or "").strip(),
            purpose=str(item.get("purpose") or "").strip(),
        )
        for item in rows
        if str(item.get("name") or "").strip() and str(item.get("source_key") or "").strip()
    ]


def _build_snapshot_rows(run_config: FairValueRunConfig) -> list[dict[str, Any]]:
    path = Path(Config.MACRO_DATA_DIR) / "snapshots.jsonl"
    cutoff = _utc_now() - timedelta(hours=run_config.lookback_hours)
    candidate_lines = _tail_lines(path, max(run_config.max_snapshots * 2, run_config.max_snapshots))
    rows: list[dict[str, Any]] = []
    for line in candidate_lines:
        try:
            item = json.loads(line)
        except Exception:
            continue
        timestamp = _parse_timestamp(item.get("generated_at"))
        if timestamp is None or timestamp < cutoff:
            continue
        snapshot = item.get("snapshot") or {}
        rows.append({
            "timestamp": timestamp,
            "snapshot": snapshot,
        })
    rows.sort(key=lambda item: item["timestamp"])
    if len(rows) > run_config.max_snapshots:
        rows = rows[-run_config.max_snapshots:]
    return rows


def _build_factor_run_override_frame(
    *,
    factor_definitions: list[FairValueFactorDefinition],
    run_config: FairValueRunConfig,
) -> pd.DataFrame:
    root = Path(Config.OPTIONS_MODEL_DATA_DIR) / "fair_value_runs"
    if not root.exists():
        return pd.DataFrame()

    factor_names = {definition.name for definition in factor_definitions}
    cutoff = _utc_now() - timedelta(
        hours=max(
            int(run_config.lookback_hours) + 24,
            int(math.ceil(run_config.factor_run_fill_tolerance_minutes / 60.0)) + 24,
        )
    )
    records: list[dict[str, Any]] = []

    for path in root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        timestamp = _parse_timestamp(payload.get("captured_at"))
        if timestamp is None or timestamp < cutoff:
            continue

        rows = (
            (((payload.get("summary") or {}).get("live_factor_rows")) or [])
            or (((payload.get("factor_preparation") or {}).get("latest_factor_rows")) or [])
        )
        if not rows:
            continue

        record: dict[str, Any] = {"timestamp": timestamp}
        has_signal = False
        for row in rows:
            factor = str(row.get("factor") or "").strip()
            if factor not in factor_names:
                continue
            raw_value = _clean_numeric(row.get("raw_value"))
            if raw_value is not None:
                record[f"override_raw__{factor}"] = raw_value
                has_signal = True
            daily_change_pct = _clean_numeric(row.get("daily_change_pct"))
            if daily_change_pct is not None:
                record[f"override_daily__{factor}"] = daily_change_pct / 100.0
                has_signal = True
        if has_signal:
            records.append(record)

    if not records:
        return pd.DataFrame()

    override_frame = pd.DataFrame(records)
    override_frame = override_frame.drop_duplicates(subset=["timestamp"], keep="last")
    override_frame = override_frame.sort_values("timestamp")
    return override_frame


def prepare_factor_frame(
    underlying_security: str,
    options_model_run: dict[str, Any],
    run_config: FairValueRunConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    factor_definitions = load_factor_definitions()
    snapshot_rows = _build_snapshot_rows(run_config)
    if not snapshot_rows:
        raise ValueError("No macro snapshots available for fair value preparation")

    index_ticker = (Config.MACRO_INDEX_TICKERS or ["BVMF:WINM26"])[0]
    dollar_ticker = (Config.MACRO_DOLLAR_TICKERS or ["BVMF:WDOK26"])[0]
    di_short_tickers = list(Config.MACRO_CURVE_SHORT_TICKERS or [])
    di_long_tickers = list(Config.MACRO_CURVE_LONG_TICKERS or [])

    records: list[dict[str, Any]] = []
    for item in snapshot_rows:
        snapshot = item["snapshot"]
        row: dict[str, Any] = {
            "timestamp": item["timestamp"],
            "local_future_close": _contract_close(snapshot, index_ticker),
            "usdbrl_future_close": _contract_close(snapshot, dollar_ticker),
        }
        row.update(_build_di_curve_derived_values(snapshot, di_short_tickers, di_long_tickers))

        row["reference__usgg2"] = _reference_price(snapshot, "USGG2YR Index")
        row["reference__usgg10"] = _reference_price(snapshot, "USGG10YR Index")
        row["reference__usso2"] = _reference_price(snapshot, "USSO2 Curncy")
        row["reference__usso10"] = _reference_price(snapshot, "USSO10 Curncy")
        row["reference__dxy"] = _reference_price(snapshot, "DXY Index")
        row["reference__move"] = _reference_price(snapshot, "MOVE Index")
        row["reference__jpy"] = _reference_price(snapshot, ".JPYB U Index")

        if row["reference__usgg2"] is not None and row["reference__usso2"] is not None:
            row["us_term_premium_2y"] = row["reference__usgg2"] - row["reference__usso2"]
        else:
            row["us_term_premium_2y"] = None
        if row["reference__usgg10"] is not None and row["reference__usso10"] is not None:
            row["us_term_premium_10y"] = row["reference__usgg10"] - row["reference__usso10"]
        else:
            row["us_term_premium_10y"] = None
        if row["reference__usso10"] is not None and row["reference__usso2"] is not None:
            row["us_ois_curve_slope"] = row["reference__usso10"] - row["reference__usso2"]
        else:
            row["us_ois_curve_slope"] = None
        row["us_term_premium_mean"] = _mean_or_none([
            row.get("us_term_premium_2y"),
            row.get("us_term_premium_10y"),
        ])
        if row["us_term_premium_10y"] is not None and row["us_term_premium_2y"] is not None:
            row["treasury_ois_divergence_proxy"] = row["us_term_premium_10y"] - row["us_term_premium_2y"]
        else:
            row["treasury_ois_divergence_proxy"] = row["us_term_premium_mean"]
        row["us_rates_liquidity_proxy"] = _mean_or_none([
            row.get("us_term_premium_mean"),
            row.get("treasury_ois_divergence_proxy"),
        ])
        row["funding_stress_proxy"] = _mean_or_none([
            row.get("reference__usso2"),
            row.get("reference__usso10"),
            row.get("us_term_premium_mean"),
            row.get("reference__move"),
            row.get("reference__dxy"),
            row.get("reference__jpy"),
        ])

        for definition in factor_definitions:
            key = f"raw__{definition.name}"
            if definition.source_kind == "contract":
                contract_key = dollar_ticker if definition.source_key == "__dollar__" else definition.source_key
                row[key] = _contract_close(snapshot, contract_key)
            elif definition.source_kind == "reference_asset":
                row[key] = _reference_price(snapshot, definition.source_key)
            elif definition.source_kind == "security":
                row[key] = _security_price(snapshot, definition.source_key)
            elif definition.source_kind == "derived":
                row[key] = row.get(definition.source_key)
            else:
                row[key] = None
        records.append(row)

    frame = pd.DataFrame(records)
    frame = frame.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").set_index("timestamp")
    target_return = frame["local_future_close"].pct_change(fill_method=None)
    prior_close = frame["local_future_close"].shift(1)
    target_log_return = np.log(frame["local_future_close"] / prior_close)
    local_index = frame.index.tz_convert(SESSION_TIMEZONE)
    session_date = pd.Series([stamp.date().isoformat() for stamp in local_index], index=frame.index)
    session_open_price = frame.groupby(session_date)["local_future_close"].transform("first")
    session_close_by_date = frame.groupby(session_date)["local_future_close"].last()
    previous_close_by_date = session_close_by_date.shift(1).to_dict()
    session_anchor_previous_close = session_date.map(previous_close_by_date)
    anchor_type = str(run_config.intraday_anchor_type or "previous_close").strip().lower()
    if anchor_type not in {"previous_close", "session_open"}:
        anchor_type = "previous_close"
    if anchor_type == "session_open":
        fair_value_anchor_price = session_open_price
    else:
        fair_value_anchor_price = session_anchor_previous_close.where(
            session_anchor_previous_close.notna(),
            session_open_price,
        )
    frame = _append_column_batch(
        frame,
        {
            "target_return": target_return,
            "target_log_return": target_log_return,
            "session_date": session_date,
            "session_open_price": session_open_price,
            "session_anchor_previous_close": session_anchor_previous_close,
            "fair_value_anchor_price": fair_value_anchor_price,
            "fair_value_anchor_type": anchor_type,
        },
    )

    factor_override_frame = _build_factor_run_override_frame(
        factor_definitions=factor_definitions,
        run_config=run_config,
    )
    if not factor_override_frame.empty and len(frame.index):
        merged = pd.merge_asof(
            frame.reset_index().sort_values("timestamp"),
            factor_override_frame,
            on="timestamp",
            direction="backward",
            tolerance=pd.Timedelta(minutes=run_config.factor_run_fill_tolerance_minutes),
        )
        override_columns: dict[str, Any] = {}
        for definition in factor_definitions:
            raw_col = f"raw__{definition.name}"
            override_raw_col = f"override_raw__{definition.name}"
            override_daily_col = f"override_daily__{definition.name}"
            if override_raw_col in merged.columns:
                override_columns[raw_col] = merged[raw_col].where(merged[raw_col].notna(), merged[override_raw_col])
            if override_daily_col in merged.columns:
                override_columns[f"daily__{definition.name}"] = pd.to_numeric(
                    merged[override_daily_col],
                    errors="coerce",
                )
        merged = _append_column_batch(merged, override_columns)
        frame = merged.set_index("timestamp")

    feature_meta: OrderedDict[str, dict[str, Any]] = OrderedDict()
    feature_column_batch: dict[str, Any] = {}

    for definition in factor_definitions:
        raw_col = f"raw__{definition.name}"
        feature_col = f"feature__{definition.name}"
        z_col = f"{feature_col}__z"
        daily_col = f"daily__{definition.name}"
        raw_series = pd.to_numeric(frame[raw_col], errors="coerce")
        if definition.transform == "return":
            feature_series = raw_series.pct_change(fill_method=None)
            if daily_col in frame.columns:
                feature_series = feature_series.where(
                    feature_series.notna(),
                    pd.to_numeric(frame[daily_col], errors="coerce"),
                )
        elif definition.transform == "diff":
            feature_series = raw_series.diff()
        else:
            feature_series = raw_series
        rolling_mean = feature_series.rolling(run_config.zscore_window, min_periods=8).mean()
        rolling_std = feature_series.rolling(run_config.zscore_window, min_periods=8).std(ddof=0)
        z_series = (feature_series - rolling_mean) / rolling_std.replace(0.0, pd.NA)
        model_col = f"{feature_col}__model"
        model_series = (
            z_series
            * _model_input_direction_multiplier(definition.expected_direction_to_ibov)
            * float(definition.weight or 1.0)
        )
        feature_column_batch[raw_col] = raw_series
        feature_column_batch[feature_col] = feature_series
        feature_column_batch[z_col] = z_series
        feature_column_batch[model_col] = model_series
        feature_meta[definition.name] = {
            "label": definition.label,
            "economic_name": definition.economic_name,
            "block": definition.block,
            "asset_class": definition.asset_class,
            "subclass": definition.subclass,
            "source_kind": definition.source_kind,
            "source_key": definition.source_key,
            "raw_column": raw_col,
            "feature_column": feature_col,
            "z_column": z_col,
            "model_column": model_col,
            "transform": definition.transform,
            "weight": definition.weight,
            "model_layer": definition.model_layer,
            "expected_direction_to_ibov": definition.expected_direction_to_ibov,
            "model_input_direction_multiplier": _model_input_direction_multiplier(definition.expected_direction_to_ibov),
            "purpose": definition.purpose,
        }
    frame = _append_column_batch(frame, feature_column_batch)

    selected_feature_columns: list[str] = []
    selected_feature_z_columns: list[str] = []
    selected_feature_meta: OrderedDict[str, dict[str, Any]] = OrderedDict()
    min_feature_points = max(
        int(run_config.feature_min_coverage_floor),
        min(
            max(int(run_config.min_points * 0.65), 24),
            max(int(len(frame.index) * run_config.feature_min_coverage_ratio), int(run_config.feature_min_coverage_floor)),
        ),
    )
    eligible_by_block: dict[str, list[tuple[str, dict[str, Any], int]]] = {}
    composite_label_map = {
        "global_equities": "Global Equities Composite",
        "brazil_equities": "Brazil Equities Composite",
        "commodities": "Commodities Composite",
        "credit": "Global Credit Composite",
        "brazil_credit": "Brazil Credit Composite",
        "fx": "FX Composite",
        "us_rates": "US Rates Composite",
        "volatility": "Volatility Composite",
    }
    structural_context_excluded_blocks: set[str] = set()

    for name, meta in feature_meta.items():
        z_col = meta["z_column"]
        coverage = int(frame[z_col].notna().sum()) if z_col in frame.columns else 0
        if coverage < min_feature_points or not _is_core_feature(FairValueFactorDefinition(
            name=name,
            label=str(meta.get("label") or ""),
            block=str(meta.get("block") or ""),
            source_kind=str(meta.get("source_kind") or ""),
            source_key=str(meta.get("source_key") or ""),
            transform=str(meta.get("transform") or "return"),
            weight=float(meta.get("weight") or 1.0),
            economic_name=str(meta.get("economic_name") or ""),
            asset_class=str(meta.get("asset_class") or ""),
            subclass=str(meta.get("subclass") or ""),
            model_layer=str(meta.get("model_layer") or "core"),
            expected_direction_to_ibov=str(meta.get("expected_direction_to_ibov") or ""),
            purpose=str(meta.get("purpose") or ""),
        )):
            continue
        block = str(meta.get("block") or "other")
        if block == "local_brazil":
            selected_feature_columns.append(meta["feature_column"])
            selected_feature_z_columns.append(meta["model_column"])
            selected_feature_meta[name] = {**meta, "coverage_points": coverage}
            continue
        if block in structural_context_excluded_blocks:
            continue
        eligible_by_block.setdefault(block, []).append((name, meta, coverage))

    composite_column_batch: dict[str, Any] = {}
    for block, members in sorted(eligible_by_block.items()):
        if not members:
            continue
        composite_name = f"core_{block}_composite"
        composite_feature_col = f"feature__{composite_name}"
        composite_z_col = f"{composite_feature_col}__z"
        composite_model_col = f"{composite_feature_col}__model"
        member_model_cols = [meta["model_column"] for _, meta, _ in members]
        member_frame = frame[member_model_cols].apply(pd.to_numeric, errors="coerce")
        weighted_sum = member_frame.sum(axis=1, min_count=1)
        weight_sum = member_frame.notna().sum(axis=1)
        composite_feature_series = pd.to_numeric(
            weighted_sum / weight_sum.replace(0.0, np.nan),
            errors="coerce",
        )
        rolling_mean = composite_feature_series.rolling(run_config.zscore_window, min_periods=8).mean()
        rolling_std = composite_feature_series.rolling(run_config.zscore_window, min_periods=8).std(ddof=0)
        composite_z_series = (composite_feature_series - rolling_mean) / rolling_std.replace(0.0, pd.NA)
        composite_model_series = composite_z_series
        composite_column_batch[composite_feature_col] = composite_feature_series
        composite_column_batch[composite_z_col] = composite_z_series
        composite_column_batch[composite_model_col] = composite_model_series
        composite_coverage = int(composite_z_series.notna().sum())
        if composite_coverage < min_feature_points:
            continue
        first_meta = members[0][1]
        selected_feature_columns.append(composite_feature_col)
        selected_feature_z_columns.append(composite_model_col)
        selected_feature_meta[composite_name] = {
            "label": composite_label_map.get(block, f"{block.replace('_', ' ').title()} Composite"),
            "economic_name": composite_label_map.get(block, f"{block.replace('_', ' ').title()} Composite"),
            "block": block,
            "asset_class": first_meta.get("asset_class"),
            "subclass": f"{block}_composite",
            "source_kind": "composite",
            "source_key": block,
            "raw_column": composite_feature_col,
            "feature_column": composite_feature_col,
            "z_column": composite_z_col,
            "model_column": composite_model_col,
            "transform": "composite",
            "weight": 1.0,
            "model_layer": "core",
            "expected_direction_to_ibov": "positive_when_rising",
            "model_input_direction_multiplier": 1.0,
            "purpose": f"Agrega {block} para evitar dupla contagem estrutural entre fatores altamente correlacionados.",
            "coverage_points": composite_coverage,
            "component_factors": [name for name, _, _ in members],
        }
    frame = _append_column_batch(frame, composite_column_batch)

    if not selected_feature_z_columns:
        raise ValueError("No fair value factors survived the coverage filter")

    frame = _append_column_batch(
        frame,
        {
            "realized_vol_rolling": frame["target_return"]
            .rolling(run_config.zscore_window, min_periods=8)
            .std(ddof=0),
            "structural_anchor_price": frame["local_future_close"].shift(1),
            "basis_points_current": _safe_float(
                ((options_model_run.get("market_context") or {}).get("future_basis_points")),
                0.0,
            ),
        },
    )

    latest_factor_rows: list[dict[str, Any]] = []
    if len(frame.index):
        latest_timestamp = frame.index[-1].isoformat()
        latest_record = frame.iloc[-1]
        for name, meta in feature_meta.items():
            coverage = int(frame[meta["z_column"]].notna().sum()) if meta["z_column"] in frame.columns else 0
            latest_factor_rows.append({
                "factor": name,
                "label": meta["label"],
                "economic_name": meta.get("economic_name"),
                "block": meta["block"],
                "asset_class": meta.get("asset_class"),
                "subclass": meta.get("subclass"),
                "model_layer": meta.get("model_layer"),
                "expected_direction_to_ibov": meta.get("expected_direction_to_ibov"),
                "purpose": meta.get("purpose"),
                "source_kind": meta.get("source_kind"),
                "source_key": meta.get("source_key"),
                "timestamp": latest_timestamp,
                "raw_value": _clean_numeric(latest_record.get(meta["raw_column"])),
                "feature_value": _clean_numeric(latest_record.get(meta["feature_column"])),
                "feature_zscore": _clean_numeric(latest_record.get(meta["z_column"])),
                "model_input_zscore": _clean_numeric(latest_record.get(meta["model_column"])),
                "session_date": latest_record.get("session_date"),
                "session_anchor_price": _clean_numeric(latest_record.get("fair_value_anchor_price")),
                "transform": meta.get("transform"),
                "weight": meta.get("weight"),
                "coverage_points": coverage,
                "selected_for_core_model": name in selected_feature_meta,
            })
        latest_factor_rows.sort(key=lambda item: (str(item.get("block") or ""), str(item.get("label") or "")))

    usable = frame.dropna(
        subset=[
            "target_return",
            "target_log_return",
            "structural_anchor_price",
            "fair_value_anchor_price",
        ]
    )
    diagnostics = {
        "snapshot_rows_considered": len(snapshot_rows),
        "frame_rows_total": int(len(frame)),
        "frame_rows_usable": int(len(usable)),
        "timestamp_start": frame.index.min().isoformat() if len(frame.index) else None,
        "timestamp_end": frame.index.max().isoformat() if len(frame.index) else None,
        "engine_mode": run_config.engine_mode,
        "intraday_anchor_type": anchor_type,
        "feature_columns": list(feature_meta.keys()),
        "core_feature_columns": list(selected_feature_meta.keys()),
        "feature_blocks": sorted({item["block"] for item in selected_feature_meta.values()}),
        "dropped_factors": sorted(set(feature_meta.keys()) - set(selected_feature_meta.keys())),
        "local_future_ticker": index_ticker,
        "dollar_ticker": dollar_ticker,
        "factor_run_override_rows": int(len(factor_override_frame.index)) if not factor_override_frame.empty else 0,
        "factor_run_fill_tolerance_minutes": float(run_config.factor_run_fill_tolerance_minutes),
        "min_feature_points_required": int(min_feature_points),
    }
    return usable, {
        "diagnostics": diagnostics,
        "all_feature_meta": feature_meta,
        "feature_columns": selected_feature_columns,
        "feature_z_columns": selected_feature_z_columns,
        "feature_meta": selected_feature_meta,
        "latest_factor_rows": latest_factor_rows,
    }


def build_live_factor_rows(
    *,
    latest_fair_value_run: dict[str, Any] | None,
    macro_state: dict[str, Any] | None,
    live_reference_rows: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    factor_definitions = load_factor_definitions()
    baseline_rows = {
        str(row.get("factor") or ""): dict(row)
        for row in ((((latest_fair_value_run or {}).get("summary") or {}).get("live_factor_rows") or []))
        if str(row.get("factor") or "").strip()
    }

    state = macro_state or {}
    snapshot = state.get("snapshot") or {}
    market = snapshot.get("market") or {}
    snapshot_timestamp = str(snapshot.get("generated_at") or state.get("updated_at") or "").strip() or None
    live_reference_rows = live_reference_rows or {}
    recent_reference_lookup = _recent_reference_asset_lookup()

    dollar_ticker = (Config.MACRO_DOLLAR_TICKERS or ["BVMF:WDOK26"])[0]
    di_short_tickers = list(Config.MACRO_CURVE_SHORT_TICKERS or [])
    di_long_tickers = list(Config.MACRO_CURVE_LONG_TICKERS or [])

    derived_values = _build_di_curve_derived_values(
        snapshot,
        di_short_tickers,
        di_long_tickers,
        live_reference_rows=live_reference_rows,
    )
    derived_daily_changes = _build_di_curve_derived_daily_changes(
        live_reference_rows,
        di_short_tickers,
        di_long_tickers,
    )
    derived_timestamp = _di_curve_reference_timestamp(
        live_reference_rows,
        [*di_short_tickers, *di_long_tickers],
    ) or snapshot_timestamp

    def reference_value(security: str) -> float | None:
        reference_row = live_reference_rows.get(security) or ((market.get("reference_assets") or {}).get(security) or {})
        fields = reference_row.get("fields") or {}
        value = _clean_numeric(fields.get("PX_LAST"))
        if value is None:
            value = _clean_numeric(reference_row.get("price"))
        if value is None:
            cached_reference = recent_reference_lookup.get(security) or {}
            value = _clean_numeric(cached_reference.get("price"))
        return value

    derived_values["reference__usgg2"] = reference_value("USGG2YR Index")
    derived_values["reference__usgg10"] = reference_value("USGG10YR Index")
    derived_values["reference__usso2"] = reference_value("USSO2 Curncy")
    derived_values["reference__usso10"] = reference_value("USSO10 Curncy")
    derived_values["reference__dxy"] = reference_value("DXY Index")
    derived_values["reference__move"] = reference_value("MOVE Index")
    derived_values["reference__jpy"] = reference_value(".JPYB U Index")
    if derived_values["reference__usgg2"] is not None and derived_values["reference__usso2"] is not None:
        derived_values["us_term_premium_2y"] = derived_values["reference__usgg2"] - derived_values["reference__usso2"]
    else:
        derived_values["us_term_premium_2y"] = None
    if derived_values["reference__usgg10"] is not None and derived_values["reference__usso10"] is not None:
        derived_values["us_term_premium_10y"] = derived_values["reference__usgg10"] - derived_values["reference__usso10"]
    else:
        derived_values["us_term_premium_10y"] = None
    if derived_values["reference__usso10"] is not None and derived_values["reference__usso2"] is not None:
        derived_values["us_ois_curve_slope"] = derived_values["reference__usso10"] - derived_values["reference__usso2"]
    else:
        derived_values["us_ois_curve_slope"] = None
    derived_values["us_term_premium_mean"] = _mean_or_none([
        derived_values.get("us_term_premium_2y"),
        derived_values.get("us_term_premium_10y"),
    ])
    if derived_values["us_term_premium_10y"] is not None and derived_values["us_term_premium_2y"] is not None:
        derived_values["treasury_ois_divergence_proxy"] = (
            derived_values["us_term_premium_10y"] - derived_values["us_term_premium_2y"]
        )
    else:
        derived_values["treasury_ois_divergence_proxy"] = derived_values["us_term_premium_mean"]
    derived_values["us_rates_liquidity_proxy"] = _mean_or_none([
        derived_values.get("us_term_premium_mean"),
        derived_values.get("treasury_ois_divergence_proxy"),
    ])
    derived_values["funding_stress_proxy"] = _mean_or_none([
        derived_values.get("reference__usso2"),
        derived_values.get("reference__usso10"),
        derived_values.get("us_term_premium_mean"),
        derived_values.get("reference__move"),
        derived_values.get("reference__dxy"),
        derived_values.get("reference__jpy"),
    ])

    rows: list[dict[str, Any]] = []
    for definition in factor_definitions:
        base = baseline_rows.get(definition.name, {
            "factor": definition.name,
            "label": definition.label,
            "block": definition.block,
            "source_kind": definition.source_kind,
            "source_key": definition.source_key,
            "transform": definition.transform,
            "feature_value": None,
            "feature_zscore": None,
            "coverage_points": None,
        })
        row = dict(base)
        row["factor"] = definition.name
        row["label"] = definition.label
        row["economic_name"] = definition.economic_name
        row["block"] = definition.block
        row["asset_class"] = definition.asset_class
        row["subclass"] = definition.subclass
        row["model_layer"] = definition.model_layer
        row["expected_direction_to_ibov"] = definition.expected_direction_to_ibov
        row["purpose"] = definition.purpose
        row["source_kind"] = definition.source_kind
        row["source_key"] = definition.source_key
        row["transform"] = definition.transform
        row["weight"] = definition.weight
        row["daily_change_pct"] = _clean_numeric(base.get("daily_change_pct"))

        raw_value = None
        value_timestamp = snapshot_timestamp
        live_source = None
        daily_change_pct = None

        if definition.source_kind == "contract":
            contract_key = dollar_ticker if definition.source_key == "__dollar__" else definition.source_key
            raw_value = _contract_close(snapshot, contract_key)
            live_source = f"macro_contract:{contract_key}"
        elif definition.source_kind == "reference_asset":
            reference_row = live_reference_rows.get(definition.source_key) or ((market.get("reference_assets") or {}).get(definition.source_key) or {})
            fields = reference_row.get("fields") or {}
            raw_value = _clean_numeric(fields.get("PX_LAST"))
            daily_change_pct = _clean_numeric(
                fields.get("CHG_PCT_1D")
                if fields.get("CHG_PCT_1D") not in (None, "")
                else reference_row.get("daily_change_pct")
            )
            if raw_value is None:
                raw_value = _clean_numeric(reference_row.get("price"))
            if raw_value is None:
                cached_reference = recent_reference_lookup.get(definition.source_key) or {}
                raw_value = _clean_numeric(cached_reference.get("price"))
                if raw_value is not None:
                    live_source = f"reference_asset:{cached_reference.get('fallback_source') or 'snapshot_cache'}:{definition.source_key}"
                    value_timestamp = str(cached_reference.get("timestamp") or value_timestamp or "").strip() or value_timestamp
                else:
                    fallback_source = str(reference_row.get("fallback_source") or "").strip()
                    live_source = f"reference_asset:{fallback_source or 'state'}:{definition.source_key}"
                    value_timestamp = str(reference_row.get("timestamp") or value_timestamp or "").strip() or value_timestamp
            else:
                fallback_source = str(reference_row.get("fallback_source") or "").strip()
                live_source = f"reference_asset:{fallback_source or 'state'}:{definition.source_key}"
                value_timestamp = str(reference_row.get("timestamp") or value_timestamp or "").strip() or value_timestamp
        elif definition.source_kind == "security":
            security_row = (market.get("securities") or {}).get(definition.source_key) or {}
            raw_value = _clean_numeric(security_row.get("price"))
            live_source = f"security_state:{definition.source_key}"
        elif definition.source_kind == "derived":
            raw_value = _clean_numeric(derived_values.get(definition.source_key))
            daily_change_pct = _clean_numeric(derived_daily_changes.get(definition.source_key))
            value_timestamp = str(derived_timestamp or value_timestamp or "").strip() or value_timestamp
            live_source = f"macro_derived:{definition.source_key}"

        if raw_value is None:
            raw_value = _clean_numeric(base.get("raw_value"))
            if raw_value is not None:
                value_timestamp = str(base.get("timestamp") or value_timestamp or "").strip() or value_timestamp
                live_source = str(base.get("live_source") or live_source or "").strip() or live_source
                if daily_change_pct is None:
                    daily_change_pct = _clean_numeric(base.get("daily_change_pct"))

        row["raw_value"] = raw_value
        row["daily_change_pct"] = daily_change_pct
        row["timestamp"] = value_timestamp
        row["live_source"] = live_source
        row["is_live"] = raw_value is not None
        rows.append(row)

    rows.sort(key=lambda item: (str(item.get("block") or ""), str(item.get("label") or "")))
    return {
        "captured_at": _utc_now().isoformat(),
        "snapshot_timestamp": snapshot_timestamp,
        "rows": rows,
    }
