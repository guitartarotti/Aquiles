"""Value objects and normalization helpers for daily ETF flows."""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .etf_daily_flow_catalog import (
    COUNTRY_KEYWORDS,
    DEVELOPED_HINTS,
    EMERGING_HINTS,
    FACTOR_HINTS,
    INCOME_HINTS,
    PROVIDER_LABELS,
    SECTOR_HINTS,
)


class EtfScrapeError(RuntimeError):
    pass


@dataclass(frozen=True)
class EtfObservation:
    provider: str
    ticker: str
    as_of_date: str
    captured_at: str
    source_url: str
    nav: float | None
    shares_outstanding: float | None
    total_net_assets: float | None
    currency: str
    confidence: float
    field_hash: str
    extraction_method: str
    raw_payload: dict[str, Any]
    warnings: list[str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _safe_provider(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    aliases = {
        "statestreet": "state_street",
        "state_street_global_advisors": "state_street",
        "ssga": "state_street",
        "blackrock": "ishares",
        "globalx": "global_x",
        "global_x_msci": "global_x",
    }
    return aliases.get(text, text)


def _safe_ticker(value: Any) -> str:
    return re.sub(r"[^A-Z0-9.\-]+", "", str(value or "").strip().upper())


def _slugify(value: Any) -> str:
    text = html.unescape(str(value or "").strip().lower())
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return re.sub(r"-+", "-", text)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = html.unescape(text)
    text = re.sub(r"[\s$€£¥]", "", text)
    multiplier = 1.0
    if re.search(r"(?i)trillion|tn|tri\b|t$", text):
        multiplier = 1_000_000_000_000.0
    elif re.search(r"(?i)billion|bn|bil\b|b$", text):
        multiplier = 1_000_000_000.0
    elif re.search(r"(?i)million|mn|mm|mil\b|m$", text):
        multiplier = 1_000_000.0
    elif re.search(r"(?i)thousand|k\b|k$", text):
        multiplier = 1_000.0
    text = re.sub(r"(?i)(trillion|billion|million|thousand|tn|bn|mn|mm|tri|bil|mil|[tbmk]$)", "", text)
    text = text.replace("%", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts[-1]) == 3 and all(part.isdigit() for part in parts if part):
            text = "".join(parts)
        else:
            text = text.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0)) * multiplier
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _parse_date(value: Any, fallback_tz: ZoneInfo) -> str | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = html.unescape(str(value or "").strip())
    if not text:
        return None
    text = text.replace("$D", "")
    text = re.sub(r"(?i)\bas\s+of\b", "", text).strip(" :,-")
    text = re.sub(r"T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", "", text)
    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%b %d %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d-%b-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%m-%d-%Y",
        "%m-%d-%y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    if match:
        return match.group(0)
    match = re.search(r"\d{1,2}/\d{1,2}/20\d{2}", text)
    if match:
        for fmt in ("%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(match.group(0), fmt).date().isoformat()
            except ValueError:
                continue
    month_match = re.search(
        r"(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+20\d{2}",
        text,
    )
    if month_match:
        return _parse_date(month_match.group(0), fallback_tz)
    return None


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _meta_float(metadata: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _finite_float(metadata.get(key))
        if value is not None:
            return value
    return None


def _meta_text(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(_safe_provider(provider), provider.replace("_", " ").title())


def _fund_text_blob(name: str, metadata: dict[str, Any]) -> str:
    bits = [
        name,
        _meta_text(metadata, "catalog_category", "catalog_style", "catalog_asset_class", "catalog_asset_subclass"),
        _meta_text(metadata, "catalog_strategy", "catalog_fund_type", "catalog_daily_objective"),
    ]
    labels = metadata.get("catalog_labels")
    if isinstance(labels, list):
        bits.extend(str(item) for item in labels[:6])
    row = metadata.get("catalog_row")
    if isinstance(row, list):
        bits.extend(str(item) for item in row[:8])
    elif isinstance(row, dict):
        bits.extend(str(value) for value in list(row.values())[:8])
    return " ".join(bit for bit in bits if bit).lower()


def _classify_country_focus(name: str, metadata: dict[str, Any]) -> str:
    text = f" {_fund_text_blob(name, metadata)} "
    for token, label in COUNTRY_KEYWORDS:
        if token in text:
            return label
    if "emerging markets" in text:
        return "Emerging Markets"
    if "asia ex japan" in text:
        return "Asia ex Japan"
    if "latin america" in text:
        return "Latin America"
    if "world ex us" in text or "world ex u.s." in text:
        return "World ex US"
    if "global ex us" in text or "global ex u.s." in text:
        return "Global ex US"
    if "international" in text:
        return "International"
    if "global" in text or "world" in text or "acwi" in text:
        return "Global"
    if "europe" in text:
        return "Europe"
    if "u.s." in text or " us " in text or "s&p 500" in text or "russell" in text or "dow jones u.s." in text:
        return "Estados Unidos"
    return "Diversificado"


def _classify_development(name: str, metadata: dict[str, Any]) -> str:
    text = _fund_text_blob(name, metadata)
    country = _classify_country_focus(name, metadata)
    if any(token in text for token in EMERGING_HINTS) or country in {"China", "India", "Brasil", "Mexico", "Vietna", "Africa", "Argentina", "Turquia"}:
        return "Emergentes"
    if "global" in country.lower() or "international" in country.lower() or country in {"Diversificado", "Asia ex Japan", "World ex US", "Global ex US"}:
        return "Global"
    if any(token in text for token in DEVELOPED_HINTS) or country in {"Estados Unidos", "Japao", "Canada", "Alemanha", "Franca", "Italia", "Espanha", "Coreia", "Taiwan", "Europe"}:
        return "Desenvolvidos"
    return "Outros"


def _classify_segment(name: str, metadata: dict[str, Any]) -> str:
    text = _fund_text_blob(name, metadata)
    asset_class = _meta_text(metadata, "catalog_asset_class", "catalog_style", "catalog_fund_type").lower()
    category = _meta_text(metadata, "catalog_category", "catalog_asset_subclass").lower()
    if any(token in text for token in ("bitcoin", "ethereum", "crypto")):
        return "Digital assets"
    if "currency" in text or " fx " in f" {text} ":
        return "Moedas"
    if "real estate" in text or "reit" in text:
        return "Imobiliario"
    if any(token in asset_class for token in ("fixed income", "bond")) or any(token in category for token in ("bond", "income", "treasury", "municipal", "loan")):
        return "Renda fixa"
    if "commodity" in asset_class or any(token in text for token in ("gold", "silver", "oil", "gas", "uranium", "commodity")):
        return "Commodities"
    if "alternative" in asset_class or "volatility" in text:
        return "Alternativos"
    if "equity" in asset_class or "equity" in category or "sector" in category or "market" in text:
        return "Equity"
    if "etf" in text or "trust" in text or "fund" in text:
        return "Equity"
    return "Outros"


def _classify_type(name: str, metadata: dict[str, Any], segment: str, country_focus: str) -> str:
    text = _fund_text_blob(name, metadata)
    objective = _meta_text(metadata, "catalog_daily_objective").replace(" ", "")
    if objective.startswith("-") or "short" in text or "inverse" in text:
        return "Inverse"
    if objective.startswith("+") and objective != "+1x":
        return "Alavancado long"
    if any(token in text for token in INCOME_HINTS):
        return "Income / options"
    if country_focus not in {"Diversificado", "Global", "International", "World ex US", "Global ex US", "Emerging Markets", "Asia ex Japan", "Europe", "Estados Unidos"}:
        return "Single country"
    if any(token in text for token in FACTOR_HINTS):
        return "Factor / style"
    if any(token in text for token in SECTOR_HINTS):
        return "Setorial / tematico"
    if segment == "Renda fixa":
        return "Renda fixa"
    if segment == "Commodities":
        return "Commodity"
    if segment == "Digital assets":
        return "Digital asset"
    if segment == "Imobiliario":
        return "Imobiliario"
    return "Core market"


def _classify_aum_bucket(aum_usd: float | None) -> str:
    if aum_usd is None:
        return "Sem AUM"
    if aum_usd >= 50_000_000_000:
        return "US$ 50 bi+"
    if aum_usd >= 10_000_000_000:
        return "US$ 10-50 bi"
    if aum_usd >= 2_000_000_000:
        return "US$ 2-10 bi"
    if aum_usd >= 500_000_000:
        return "US$ 500 mi-2 bi"
    return "< US$ 500 mi"


def _extract_first_regex(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            for group in match.groups():
                if group is not None and str(group).strip():
                    return html.unescape(str(group).strip())
    return None


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _text_by_data_id(soup: BeautifulSoup, *data_ids: str) -> str | None:
    for data_id in data_ids:
        node = soup.find(attrs={"data-id": data_id})
        if node is not None:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return None


def _row_text_for_label(soup: BeautifulSoup, label: str) -> str | None:
    label_pattern = re.compile(rf"^\s*{re.escape(label)}\s*$", flags=re.IGNORECASE)
    for label_node in soup.find_all(string=label_pattern):
        parent = label_node.parent
        if parent is None:
            continue
        for ancestor in [parent, *parent.find_parents(["li", "div", "tr"], limit=4)]:
            text = ancestor.get_text(" ", strip=True) if ancestor is not None else ""
            if text and re.search(re.escape(label), text, flags=re.IGNORECASE):
                return text
    return None


def _value_after_label(row_text: str | None, label: str) -> str | None:
    if not row_text:
        return None
    text = _compact_text(row_text)
    text = re.sub(rf"(?i)^\s*{re.escape(label)}\s*", "", text).strip()
    text = re.split(r"(?i)\bas of\b", text, maxsplit=1)[0].strip()
    return text or None


def _anchor_snippet(text: str, anchor: str, radius: int = 180) -> str:
    index = text.lower().find(anchor.lower())
    if index < 0:
        return ""
    return _compact_text(text[max(0, index - radius): index + len(anchor) + radius])


def _walk_json(value: Any) -> list[tuple[str, Any]]:
    output: list[tuple[str, Any]] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                output.append((child_path, child))
                visit(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node[:500]):
                visit(child, f"{path}[{index}]")

    visit(value, "")
    return output
