"""Shared value and time helpers for the macro live pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TypeVar, cast
from zoneinfo import ZoneInfo

EVENT_CLASSIFICATION_VERSION = "macro-headline-freeze-v5-contextual-scope"
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


T = TypeVar("T")


def _deep_copy_json(data: T) -> T:
    return cast(T, json.loads(json.dumps(data, ensure_ascii=False)))


def _iso_from_timestamp(value: Any) -> str | None:
    if value is None:
        return None

    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _to_price_string(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, dict) and "mantissa" in value:
        mantissa = Decimal(str(value["mantissa"]))
        exponent = int(value.get("exponent", 0))
        return format(mantissa * (Decimal(10) ** exponent), "f")

    return str(value)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(str(value))
    except Exception:
        return None


def _parse_iso_datetime(value: Any) -> datetime | None:
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


def _bucket_start(dt: datetime, minutes: int) -> datetime:
    minute = (dt.minute // minutes) * minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


def _sha1_text(*parts: Any) -> str:
    payload = "||".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
