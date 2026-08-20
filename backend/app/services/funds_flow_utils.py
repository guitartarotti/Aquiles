from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from ..domains.funds_flow.domain.rules import period_to_window, pressure_regime, safe_divide
from ..utils.funds_flow_source_values import (
    LOCAL_TZ as LOCAL_TZ,
)
from ..utils.funds_flow_source_values import (
    _classify_master_row as _classify_master_row,
)
from ..utils.funds_flow_source_values import _clean_json as _clean_json
from ..utils.funds_flow_source_values import _local_now as _local_now
from ..utils.funds_flow_source_values import _normalize_cnpj as _normalize_cnpj
from ..utils.funds_flow_source_values import _normalize_text as _normalize_text
from ..utils.funds_flow_source_values import _now_iso as _now_iso
from ..utils.funds_flow_source_values import _parse_date as _parse_date
from ..utils.funds_flow_source_values import _parse_iso as _parse_iso
from ..utils.funds_flow_source_values import _safe_float as _safe_float
from ..utils.funds_flow_source_values import _utc_now as _utc_now
from ..utils.funds_flow_source_values import _yyyymm_months as _yyyymm_months


def _parse_brazilian_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%d/%m/%Y").date()
    except Exception:
        return _parse_date(value)


def _max_iso_date_value(*values: Any) -> str | None:
    parsed = [_parse_date(value) for value in values if value]
    parsed = [value for value in parsed if value]
    if not parsed:
        return None
    return max(parsed).isoformat()


def _max_iso_datetime_value(*values: Any) -> str | None:
    parsed = [_parse_iso(value) for value in values if value]
    parsed = [value for value in parsed if value]
    if not parsed:
        return None
    return max(parsed).isoformat()


def _path_mtime_iso(path: Any) -> str | None:
    if not path:
        return None
    try:
        file_path = os.fspath(path)
    except Exception:
        return None
    try:
        if not os.path.exists(file_path):
            return None
        return datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    return safe_divide(numerator, denominator)


def _period_to_window(period: str | None) -> int:
    return period_to_window(period)


def _money_brl(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "n/d"
    sign = "-" if parsed < 0 else ""
    absolute = abs(parsed)
    if absolute >= 1_000_000_000:
        return f"{sign}R$ {absolute / 1_000_000_000:.1f} bi"
    if absolute >= 1_000_000:
        return f"{sign}R$ {absolute / 1_000_000:.1f} mi"
    return f"{sign}R$ {absolute:,.0f}".replace(",", ".")


def _money_usd_mn(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "n/d"
    sign = "-" if parsed < 0 else ""
    absolute = abs(parsed)
    if absolute >= 1_000_000:
        return f"{sign}US$ {absolute / 1_000_000:.1f} tri"
    if absolute >= 1_000:
        return f"{sign}US$ {absolute / 1_000:.1f} bi"
    return f"{sign}US$ {absolute:.0f} mi"


def _pct(value: Any, digits: int = 2) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "n/d"
    return f"{parsed * 100:.{digits}f}%"


def _zscore(series: pd.Series, window: int, *, min_periods: int | None = None) -> pd.Series:
    periods = min_periods or max(5, min(window, 21))
    rolling = series.rolling(window, min_periods=periods)
    mean = rolling.mean()
    std = rolling.std(ddof=0)
    return ((series - mean) / std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _regime_from_pressure(value: Any) -> str:
    return pressure_regime(value)
