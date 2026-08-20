"""Shared normalization primitives for official Funds Flow sources."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _safe_float(value: Any, digits: int | None = None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except Exception:
        try:
            parsed = float(str(value).replace(",", "."))
        except Exception:
            return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return round(parsed, digits) if digits is not None else parsed


def _yyyymm_months(start_date: date, end_date: date) -> list[str]:
    months: list[str] = []
    cursor = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)
    while cursor <= end_month:
        months.append(f"{cursor.year}{cursor.month:02d}")
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_json(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        parsed = float(value)
        return None if math.isnan(parsed) or math.isinf(parsed) else parsed
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if value is pd.NaT:
        return None
    return value


def _normalize_cnpj(value: Any) -> str:
    text = re.sub(r"\D+", "", str(value or ""))
    return text.zfill(14) if text else ""


def _normalize_text(value: Any) -> str:
    text = str(value or "").upper()
    replacements = {
        "Á": "A",
        "À": "A",
        "Â": "A",
        "Ã": "A",
        "Ä": "A",
        "É": "E",
        "Ê": "E",
        "Í": "I",
        "Ó": "O",
        "Ô": "O",
        "Õ": "O",
        "Ú": "U",
        "Ü": "U",
        "Ç": "C",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text).strip()


def _matches_keyword(text: str, needle: str) -> bool:
    normalized_text = _normalize_text(text)
    normalized_needle = _normalize_text(needle)
    if not normalized_text or not normalized_needle:
        return False
    pattern = rf"(?<![A-Z0-9]){re.escape(normalized_needle)}(?![A-Z0-9])"
    return re.search(pattern, normalized_text) is not None


def _classify_master_row(row: pd.Series) -> tuple[str, str, str, float]:
    official_fields = [
        row.get("classe_cvm"),
        row.get("classe_anbima"),
    ]
    descriptor_fields = [
        row.get("tipo_fundo"),
        row.get("nome_fundo"),
    ]
    official_text = " ".join(
        _normalize_text(field) for field in official_fields if field is not None
    )
    descriptor_text = " ".join(
        _normalize_text(field) for field in descriptor_fields if field is not None
    )
    text = " ".join(part for part in [official_text, descriptor_text] if part)
    if not text.strip():
        return "Unclassified", "unclassified", "unclassified", 0.25

    checks = [
        ("Fiagro", "structured", ("FIAGRO",)),
        ("FIDC", "structured", ("FIDC", "DIREITOS CREDITORIOS")),
        ("FII", "real_estate", ("FII", "IMOBILIARIO", "IMOBILIARIA")),
        ("FIP", "private_equity", ("FIP", "PARTICIPACOES")),
        ("ETF", "listed_fund", ("ETF", "EXCHANGE TRADED", "INDICE DE MERCADO")),
        ("Previdencia", "pension", ("PREVID", "PGBL", "VGBL")),
        ("Cambial", "fx", ("CAMBIAL", "DOLAR", "MOEDA ESTRANGEIRA")),
        ("Acoes", "equity", ("ACOES", "ACAO", "IBOV", "IBRX", "BDR")),
        ("Renda Fixa", "fixed_income", ("RENDA FIXA", "REFERENCIADO", "CURTO PRAZO", "DI ")),
        ("Multimercado", "multi_asset", ("MULTIMERCADO",)),
    ]
    for macro, strategy, needles in checks:
        if any(_matches_keyword(official_text, needle) for needle in needles):
            return macro, macro, strategy, 0.96
    for macro, strategy, needles in checks:
        if any(_matches_keyword(descriptor_text, needle) for needle in needles):
            return macro, macro, strategy, 0.86
    return "Outros", "Outros", "other", 0.45
