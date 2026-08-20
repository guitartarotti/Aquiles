"""Pure financial and windowing rules used by Funds Flow."""

from __future__ import annotations

import math
import re
from typing import Any


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        try:
            parsed = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None
    return parsed if math.isfinite(parsed) else None


def safe_divide(numerator: Any, denominator: Any) -> float | None:
    num = _finite_float(numerator)
    den = _finite_float(denominator)
    if num is None or den is None or abs(den) < 1e-12:
        return None
    return num / den


def period_to_window(period: str | None) -> int:
    text = str(period or "21d").strip().lower()
    mapping = {
        "1d": 1,
        "5d": 5,
        "21d": 21,
        "1m": 21,
        "63d": 63,
        "3m": 63,
        "126d": 126,
        "6m": 126,
        "252d": 252,
        "12m": 252,
        "ytd": 252,
    }
    if text in mapping:
        return mapping[text]
    match = re.match(r"^(\d+)\s*d$", text)
    if match:
        return max(1, min(int(match.group(1)), 252))
    return 21


def pressure_regime(value: Any) -> str:
    parsed = _finite_float(value) or 0.0
    if parsed >= 2:
        return "entrada_forte"
    if parsed >= 1:
        return "entrada"
    if parsed <= -2:
        return "stress"
    if parsed <= -1:
        return "resgate"
    return "neutral"
