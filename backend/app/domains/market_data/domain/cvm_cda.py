"""Pure rules and value objects used while processing CVM CDA data."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone


def month_from_text(value: object) -> str | None:
    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", str(value or ""))
    return "".join(match.groups()) if match else None


def month_label(yyyymm: str | None) -> str:
    text = str(yyyymm or "")
    if not re.fullmatch(r"20\d{4}", text):
        return text or "-"
    return f"{text[:4]}-{text[4:6]}"


def previous_months(month: str, count: int) -> list[str]:
    if not re.fullmatch(r"20\d{4}", str(month or "")):
        return []
    year = int(month[:4])
    month_num = int(month[4:6])
    result: list[str] = []
    for _ in range(max(0, count)):
        result.append(f"{year:04d}{month_num:02d}")
        month_num -= 1
        if month_num <= 0:
            month_num = 12
            year -= 1
    return result


def safe_float(value: object) -> float:
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def safe_div(numerator: object, denominator: object, default: float = 0.0) -> float:
    parsed_denominator = safe_float(denominator)
    if parsed_denominator == 0:
        return default
    return safe_float(numerator) / parsed_denominator


def clamp(value: object, lower: float, upper: float) -> float:
    parsed = safe_float(value)
    return max(lower, min(parsed, upper))


def parse_date_text(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def parse_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_text(value: object) -> str:
    text = str(value if value is not None else "").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", text)


def normalize_key(value: object) -> str:
    text = normalize_text(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def first_nonempty(values: Iterable[object], default: str = "") -> str:
    for value in values:
        text = normalize_text(value)
        if text:
            return text
    return default


def source_block(file_name: str) -> str:
    text = str(file_name or "").upper()
    if "CONFID" in text and "FIE" in text:
        return "FIE_CONFID"
    if "CONFID" in text:
        return "CONFID"
    match = re.search(r"_BLC_(\d)_", text)
    if match:
        return f"BLC_{match.group(1)}"
    if "CDA_FIE_" in text:
        return "FIE"
    return "CDA"


def asset_class_for(block: str, tp_aplic: object, tp_ativo: object, asset_desc: object) -> str:
    block_text = str(block or "").upper()
    text = normalize_key(f"{tp_aplic} {tp_ativo} {asset_desc} {block}")
    use_block_hint = block_text not in {"CONFID", "FIE", "FIE_CONFID"}
    if (
        (use_block_hint and block_text == "BLC_1")
        or "TITULO PUBLICO" in text
        or "SELIC" in text
        or "COMPROMISSAD" in text
    ):
        return "Titulos Publicos"
    if (
        (use_block_hint and block_text == "BLC_2")
        or "COTAS DE FUNDOS" in text
        or ("FUNDO" in text and "COTA" in text)
    ):
        return "Cotas de Fundos"
    if (
        (use_block_hint and block_text == "BLC_3")
        or "SWAP" in text
        or "MERCADO FUTURO" in text
        or "FUTURO" in text
        or "OPCO" in text
        or "TERMO" in text
    ):
        return "Derivativos"
    if "ACAO" in text or "ACOES" in text or "BDR" in text or "ETF" in text:
        return "Acoes"
    if (
        (use_block_hint and block_text == "BLC_5")
        or "DEPOSITO" in text
        or "CDB" in text
        or "LETRA FINANCEIRA" in text
        or "DISPONIBILIDADE" in text
    ):
        return "Depositos e IF"
    if (
        (use_block_hint and block_text == "BLC_6")
        or "AGRONEGOCIO" in text
        or "CRA" in text
        or "CRI" in text
        or "DIREITOS CREDITORIOS" in text
    ):
        return "Agronegocio/Credito"
    if (use_block_hint and block_text == "BLC_7") or "EXTERIOR" in text or "OFFSHORE" in text:
        return "Investimento Exterior"
    if (
        "DEBENTURE" in text
        or "NOTA COMERCIAL" in text
        or "CREDITO PRIVADO" in text
        or "TITULOS DE CREDITO PRIVADO" in text
    ):
        return "Credito Privado"
    return "Outros"


def maturity_bucket(maturity_date: object, as_of_date: object) -> str:
    maturity = str(maturity_date or "").strip()[:10]
    as_of = str(as_of_date or "").strip()[:10]
    if not maturity or not as_of:
        return "sem vencimento"
    try:
        years = (
            datetime.fromisoformat(maturity).date() - datetime.fromisoformat(as_of).date()
        ).days / 365.25
    except ValueError:
        return "sem vencimento"
    if years < 0:
        return "vencido/indefinido"
    if years <= 1:
        return "0-1y"
    if years <= 3:
        return "1-3y"
    if years <= 5:
        return "3-5y"
    if years <= 7:
        return "5-7y"
    if years <= 10:
        return "7-10y"
    if years <= 30:
        return "10-30y"
    return "30y+"


@dataclass(frozen=True, slots=True)
class CdaRemoteMonth:
    month: str
    url: str
    name: str = ""
    last_modified: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "month": self.month,
            "label": month_label(self.month),
            "url": self.url,
            "name": self.name,
            "last_modified": self.last_modified,
        }
