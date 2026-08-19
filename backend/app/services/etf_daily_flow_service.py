from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, NavigableString

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("aquiles.etf_daily_flow")

ETF_DAILY_FLOW_SCHEMA_VERSION = 1

DEFAULT_PROVIDER_ORDER = (
    "schwab",
    "state_street",
    "vaneck",
    "ishares",
    "dimensional",
    "vanguard",
    "invesco",
    "proshares",
    "global_x",
)

DEFAULT_ETF_UNIVERSE = (
    {
        "provider": "schwab",
        "ticker": "SCHX",
        "name": "Schwab U.S. Large-Cap ETF",
        "url": "https://www.schwabassetmanagement.com/products/schx",
        "currency": "USD",
    },
    {
        "provider": "state_street",
        "ticker": "SPY",
        "name": "State Street SPDR S&P 500 ETF Trust",
        "url": "https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy",
        "currency": "USD",
    },
    {
        "provider": "vaneck",
        "ticker": "SMH",
        "name": "VanEck Semiconductor ETF",
        "url": "https://www.vaneck.com/us/en/investments/semiconductor-etf-smh/",
        "currency": "USD",
    },
    {
        "provider": "ishares",
        "ticker": "IVV",
        "name": "iShares Core S&P 500 ETF",
        "url": "https://www.blackrock.com/us/individual/products/239726/ishares-core-s-p-500-etf",
        "currency": "USD",
    },
    {
        "provider": "dimensional",
        "ticker": "DFAU",
        "name": "Dimensional US Core Equity Market ETF",
        "url": "https://www.dimensional.com/us-en/funds/dfau/us-core-equity-market-etf",
        "currency": "USD",
    },
    {
        "provider": "vanguard",
        "ticker": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "url": "https://investor.vanguard.com/investment-products/etfs/profile/voo",
        "currency": "USD",
    },
    {
        "provider": "invesco",
        "ticker": "QQQ",
        "name": "Invesco QQQ Trust",
        "url": "https://www.invesco.com/qqq-etf/en/home.html",
        "currency": "USD",
    },
    {
        "provider": "proshares",
        "ticker": "TQQQ",
        "name": "ProShares UltraPro QQQ",
        "url": "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq",
        "currency": "USD",
    },
    {
        "provider": "global_x",
        "ticker": "QYLD",
        "name": "Global X Nasdaq 100 Covered Call ETF",
        "url": "https://www.globalxetfs.com/funds/qyld",
        "currency": "USD",
    },
)

PROVIDER_LABELS = {
    "schwab": "Schwab",
    "state_street": "State Street",
    "vaneck": "VanEck",
    "ishares": "iShares",
    "dimensional": "Dimensional",
    "vanguard": "Vanguard",
    "invesco": "Invesco",
    "proshares": "ProShares",
    "global_x": "Global X",
}

COUNTRY_KEYWORDS = (
    ("united states", "Estados Unidos"),
    ("u.s.", "Estados Unidos"),
    (" us ", "Estados Unidos"),
    ("china", "China"),
    ("japan", "Japao"),
    ("india", "India"),
    ("brazil", "Brasil"),
    ("mexico", "Mexico"),
    ("canada", "Canada"),
    ("germany", "Alemanha"),
    ("france", "Franca"),
    ("italy", "Italia"),
    ("spain", "Espanha"),
    ("taiwan", "Taiwan"),
    ("korea", "Coreia"),
    ("south korea", "Coreia"),
    ("vietnam", "Vietna"),
    ("argentina", "Argentina"),
    ("saudi", "Arabia Saudita"),
    ("turkey", "Turquia"),
    ("israel", "Israel"),
    ("africa", "Africa"),
)

EMERGING_HINTS = ("emerging", "latin america", "africa", "vietnam", "india", "brazil", "mexico", "china")
DEVELOPED_HINTS = ("developed", "united states", "u.s.", "europe", "japan", "canada", "germany", "france")
FACTOR_HINTS = ("value", "growth", "quality", "momentum", "size", "min vol", "minimum volatility", "factor")
SECTOR_HINTS = (
    "semiconductor",
    "biotech",
    "cyber",
    "technology",
    "health",
    "financial",
    "energy",
    "industrial",
    "infrastructure",
    "robot",
    "ai",
    "artificial intelligence",
    "uranium",
    "cloud",
    "real estate",
)
INCOME_HINTS = ("covered call", "income", "premium", "yield", "buywrite", "option", "buffer", "collar")


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


class GenericHtmlEtfProvider:
    provider = "generic"

    def __init__(self, timeout_seconds: float, user_agent: str):
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.session = requests.Session()
        self._json_cache: dict[str, tuple[float, Any, str, str]] = {}

    def fetch_observation(self, fund: dict[str, Any], tz: ZoneInfo) -> EtfObservation:
        source_url = str(fund.get("url") or "").strip()
        if not source_url:
            raise EtfScrapeError("missing source url")
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
            "Cache-Control": "no-cache",
        }
        response = self.session.get(source_url, headers=headers, timeout=self.timeout_seconds, allow_redirects=True)
        if response.status_code >= 400:
            raise EtfScrapeError(f"http {response.status_code}")
        return self.parse_observation(fund, response.text, str(response.url), tz)

    def fetch_html(self, source_url: str) -> tuple[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
            "Cache-Control": "no-cache",
        }
        response = self.session.get(source_url, headers=headers, timeout=self.timeout_seconds, allow_redirects=True)
        if response.status_code >= 400:
            raise EtfScrapeError(f"http {response.status_code}")
        return response.text, str(response.url)

    def fetch_json(
        self,
        source_url: str,
        headers: dict[str, str] | None = None,
        cache_key: str | None = None,
        ttl_seconds: float = 900,
        params: list[tuple[str, str]] | dict[str, str] | None = None,
    ) -> tuple[Any, str, str]:
        key = cache_key or f"{source_url}|{_json_dumps(params or {})}"
        cached = self._json_cache.get(key)
        now = time.time()
        if cached and now - cached[0] <= ttl_seconds:
            return cached[1], cached[2], cached[3]
        response = self.session.get(
            source_url,
            headers=headers or {},
            params=params,
            timeout=self.timeout_seconds,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            raise EtfScrapeError(f"http {response.status_code}")
        text = response.text or ""
        try:
            payload = response.json()
        except Exception:
            try:
                payload = json.loads(text)
            except Exception as exc:
                raise EtfScrapeError("invalid json response") from exc
        self._json_cache[key] = (now, payload, str(response.url), text)
        return payload, str(response.url), text

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        raise EtfScrapeError(f"{self.provider} catalog discovery is not implemented")

    def parse_observation(self, fund: dict[str, Any], text: str, source_url: str, tz: ZoneInfo) -> EtfObservation:
        decoded = html.unescape(text or "")
        soup = BeautifulSoup(decoded, "html.parser")
        plain_text = _compact_text(soup.get_text(" ", strip=True))

        fields = self.extract_fields(decoded, soup, plain_text, tz)
        raw_payload = {
            "field_values": fields,
            "field_sources": self.field_sources(decoded),
            "html_size": len(text or ""),
        }
        return self.build_observation_from_fields(
            fund=fund,
            fields=fields,
            source_url=source_url,
            tz=tz,
            raw_payload=raw_payload,
            extraction_method=self.provider,
        )

    def build_observation_from_fields(
        self,
        fund: dict[str, Any],
        fields: dict[str, Any],
        source_url: str,
        tz: ZoneInfo,
        raw_payload: dict[str, Any] | None = None,
        extraction_method: str | None = None,
        allow_nav_only: bool = False,
        confidence: float = 0.95,
        warnings: list[str] | None = None,
    ) -> EtfObservation:
        ticker = _safe_ticker(fund.get("ticker"))
        provider = _safe_provider(fund.get("provider") or self.provider)
        currency = str(fund.get("currency") or fields.get("currency") or "USD").strip().upper()
        warning_list = list(warnings or [])

        nav = _finite_float(fields.get("nav"))
        shares = _finite_float(fields.get("shares_outstanding"))
        total_assets = _finite_float(fields.get("total_net_assets"))
        as_of_date = _parse_date(fields.get("as_of_date"), tz)

        if shares is None and nav not in (None, 0) and total_assets is not None:
            shares = total_assets / float(nav)
            warning_list.append("shares_outstanding_inferred_from_assets_and_nav")
        if not as_of_date:
            as_of_date = datetime.now(tz).date().isoformat()
            warning_list.append("as_of_date_missing_used_local_date")
        if nav is None:
            raise EtfScrapeError("missing nav")
        if shares is None and total_assets is None:
            if not allow_nav_only:
                raise EtfScrapeError("missing shares_outstanding_or_total_net_assets")
            warning_list.append("shares_and_assets_missing_flow_unavailable")

        payload = dict(raw_payload or {})
        payload.setdefault("field_values", fields)
        field_hash = _sha256(_json_dumps(payload.get("field_sources") or payload.get("field_values") or payload))
        confidence = float(confidence)
        if "shares_outstanding_inferred_from_assets_and_nav" in warning_list:
            confidence = 0.75
        if "shares_and_assets_missing_flow_unavailable" in warning_list:
            confidence = min(confidence, 0.45)
        if "as_of_date_missing_used_local_date" in warning_list:
            confidence = min(confidence, 0.65)

        return EtfObservation(
            provider=provider,
            ticker=ticker,
            as_of_date=as_of_date,
            captured_at=_utc_now_iso(),
            source_url=source_url,
            nav=nav,
            shares_outstanding=shares,
            total_net_assets=total_assets,
            currency=currency,
            confidence=confidence,
            field_hash=field_hash,
            extraction_method=extraction_method or self.provider,
            raw_payload=payload,
            warnings=warning_list,
        )

    def extract_fields(self, decoded: str, soup: BeautifulSoup, plain_text: str, tz: ZoneInfo) -> dict[str, Any]:
        fields = self._extract_structured_json(decoded, tz)
        fields.update({key: value for key, value in self._extract_dom_fields(soup).items() if value is not None})
        fields.update({key: value for key, value in self._extract_regex_fields(decoded, plain_text).items() if value is not None})
        return fields

    def field_sources(self, decoded: str) -> dict[str, str]:
        return {
            "nav": _anchor_snippet(decoded, "NAV"),
            "shares_outstanding": _anchor_snippet(decoded, "Shares Outstanding")
            or _anchor_snippet(decoded, "SHARES_OUTSTANDING"),
            "total_net_assets": _anchor_snippet(decoded, "Net Assets")
            or _anchor_snippet(decoded, "NET_ASSETS")
            or _anchor_snippet(decoded, "Assets Under Management"),
            "as_of_date": _anchor_snippet(decoded, "as of") or _anchor_snippet(decoded, "AS_OF_DATE"),
        }

    def _extract_dom_fields(self, soup: BeautifulSoup) -> dict[str, Any]:
        def by_id(*ids: str) -> str | None:
            for html_id in ids:
                node = soup.find(id=html_id)
                if node is not None:
                    text = node.get_text(" ", strip=True)
                    if text:
                        return text
            return None

        fields = {
            "nav": by_id("price-nav", "nav", "snapshot-nav"),
            "total_net_assets": by_id("snapshot-netAssets", "netAssets", "totalNetAssets"),
            "as_of_date": by_id("price-asOfDate", "navDate", "asOfDate"),
            "shares_outstanding": by_id("sharesOutstanding", "shares-outstanding"),
        }
        return fields

    def _extract_regex_fields(self, decoded: str, plain_text: str) -> dict[str, Any]:
        nav = _extract_first_regex(
            decoded,
            [
                r'"NET_ASSET_VALUE"\s*:\s*"([^"]+)"',
                r'"nav"\s*:\s*\{.*?"originalValue"\s*:\s*"([^"]+)"',
                r'id=["\']price-nav["\'][^>]*>\s*([^<]+)',
                r'>\s*NAV\s*</[^>]+>\s*<[^>]+>\s*<[^>]+>\s*([^<]+)',
                r'\bNAV\b[^$0-9]{0,80}([$]?\s*-?\d[\d,]*(?:\.\d+)?)',
            ],
        )
        shares = _extract_first_regex(
            decoded,
            [
                r'"SHARES_OUTSTANDING"\s*:\s*"?([\d,.\s]+)"?',
                r'"sharesOutstanding"\s*:\s*"?([\d,.\s]+)"?',
                r'Shares Outstanding.{0,500}?"children"\s*:\s*"?([\d,.\s]+)"?',
                r'Shares Outstanding.{0,250}?([$]?\s*\d[\d,.\s]+)',
            ],
        )
        assets = _extract_first_regex(
            decoded,
            [
                r'"aum"\s*:\s*\{.*?"originalValue"\s*:\s*"([^"]+)"',
                r'"NET_ASSETS"\s*:\s*"?([\d,.\s]+)"?',
                r'"TOTAL_NET_ASSETS"\s*:\s*"?([\d,.\s]+)"?',
                r'id=["\']snapshot-netAssets["\'][^>]*>\s*([^<]+)',
                r'Net Assets.{0,250}?([$]?\s*\d[\d,.\s]+(?:\s*[MBTK]| million| billion| trillion)?)',
                r'Assets Under Management.{0,250}?([$]?\s*\d[\d,.\s]+(?:\s*[MBTK]| million| billion| trillion)?)',
            ],
        )
        as_of_date = _extract_first_regex(
            decoded,
            [
                r'"AS_OF_DATE"\s*:\s*"\$?D?([^"]+)"',
                r'"asOfDateSimple"\s*:\s*"([^"]+)"',
                r'id=["\']price-asOfDate["\'][^>]*>\s*([^<]+)',
                r'NAV Date.{0,120}?(\d{1,2}-[A-Za-z]{3}-20\d{2})',
                r'as of\s+([A-Za-z]{3,9}\s+\d{1,2},?\s+20\d{2})',
                r'as of\s+(\d{1,2}/\d{1,2}/20\d{2})',
                r'(\$D20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)',
            ],
        )

        if not nav:
            nav = _extract_first_regex(
                plain_text,
                [r'\bNAV\b\s*([$]?\s*-?\d[\d,]*(?:\.\d+)?)'],
            )
        return {
            "nav": nav,
            "shares_outstanding": shares,
            "total_net_assets": assets,
            "as_of_date": as_of_date,
        }

    def _extract_structured_json(self, decoded: str, tz: ZoneInfo) -> dict[str, Any]:
        candidates: list[Any] = []
        for match in re.finditer(
            r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
            decoded,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            raw = match.group(1).strip()
            if not raw:
                continue
            try:
                candidates.append(json.loads(raw))
            except Exception:
                continue
        fields: dict[str, Any] = {}
        for candidate in candidates:
            for path, value in _walk_json(candidate):
                key = path.lower().replace("_", "").replace("-", "")
                if fields.get("nav") is None and any(token in key for token in ("netassetvalue", "navamount", ".nav")):
                    if _finite_float(value) is not None:
                        fields["nav"] = value
                if fields.get("shares_outstanding") is None and "sharesoutstanding" in key:
                    if _finite_float(value) is not None:
                        fields["shares_outstanding"] = value
                if fields.get("total_net_assets") is None and any(
                    token in key for token in ("totalnetassets", "netassets", "assetsundermanagement")
                ):
                    if _finite_float(value) is not None:
                        fields["total_net_assets"] = value
                if fields.get("as_of_date") is None and any(token in key for token in ("asofdate", "navdate")):
                    if _parse_date(value, tz):
                        fields["as_of_date"] = value
        return fields


class SchwabEtfProvider(GenericHtmlEtfProvider):
    provider = "schwab"
    catalog_url = "https://www.schwabassetmanagement.com/product-finder?combine=&field_product_solution_target_id%5B0%5D=291&field_product_solution_target_id%5B1%5D=291"

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        try:
            text, final_url = self.fetch_html(url)
        except EtfScrapeError as exc:
            if "http 403" in str(exc):
                raise EtfScrapeError("Schwab official catalog blocked by Akamai (http 403)") from exc
            raise
        soup = BeautifulSoup(html.unescape(text or ""), "html.parser")
        funds: list[dict[str, Any]] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            label = _compact_text(anchor.get_text(" ", strip=True))
            match = re.match(r"^([A-Z0-9.\-]{2,8})\s+(.+\bETF\b.*)$", label)
            if not match:
                continue
            ticker = _safe_ticker(match.group(1))
            name = match.group(2).strip()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            row_text = _compact_text(anchor.find_parent().get_text(" ", strip=True) if anchor.find_parent() else "")
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": name,
                    "url": urljoin(final_url, anchor.get("href") or f"/products/{ticker.lower()}"),
                    "currency": "USD",
                    "active": True,
                    "priority": 30,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_row_text": row_text,
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("Schwab catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }


class StateStreetEtfProvider(GenericHtmlEtfProvider):
    provider = "state_street"
    catalog_url = "https://www.ssga.com/bin/v1/ssmp/fund/fundfinder?country=us&language=en&role=intermediary&product=&ui=fund-finder"

    def catalog_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
            "Referer": "https://www.ssga.com/us/en/intermediary/fund-finder",
        }

    @staticmethod
    def _display_value(row: dict[str, Any], key: str) -> Any:
        value = row.get(key)
        if isinstance(value, list) and value:
            return value[0]
        return value

    @staticmethod
    def _date_value(row: dict[str, Any], key: str) -> Any:
        value = row.get(key)
        if isinstance(value, list) and len(value) > 1:
            return value[1]
        if isinstance(value, list) and value:
            return value[0]
        return value

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        payload, final_url, raw_text = self.fetch_json(
            url,
            headers=self.catalog_headers(),
            cache_key="state_street_catalog",
        )
        rows = (
            payload.get("data", {})
            .get("funds", {})
            .get("etfs", {})
            .get("datas", [])
            if isinstance(payload, dict)
            else []
        )
        funds: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            ticker = _safe_ticker(row.get("fundTicker") or row.get("fundFilter"))
            name = str(row.get("fundName") or "").strip()
            href = str(row.get("fundUri") or "").strip()
            if not ticker or not name or not href:
                continue
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": name,
                    "url": urljoin("https://www.ssga.com", href),
                    "currency": "USD",
                    "active": True,
                    "priority": 25,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_category": row.get("fundFilter"),
                        "catalog_primary_exchange": row.get("primaryExchange"),
                        "catalog_nav": _finite_float(self._display_value(row, "nav")),
                        "catalog_total_net_assets_usd": _finite_float(self._display_value(row, "aum")),
                        "catalog_as_of_date": _parse_date(self._date_value(row, "asOfDate"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                        "catalog_inception_date": _parse_date(self._date_value(row, "inceptionDate"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                        "catalog_net_expense_ratio": _finite_float(self._display_value(row, "ter")),
                        "catalog_ytd_return": _finite_float(self._display_value(row, "ytd")),
                        "catalog_perf_as_of": _parse_date(self._date_value(row, "PerfAsOf"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("State Street catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(raw_text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }

    def fetch_observation(self, fund: dict[str, Any], tz: ZoneInfo) -> EtfObservation:
        payload, final_url, raw_text = self.fetch_json(
            self.catalog_url,
            headers=self.catalog_headers(),
            cache_key="state_street_catalog",
        )
        rows = (
            payload.get("data", {})
            .get("funds", {})
            .get("etfs", {})
            .get("datas", [])
            if isinstance(payload, dict)
            else []
        )
        ticker = _safe_ticker(fund.get("ticker"))
        row = next(
            (
                item
                for item in rows
                if isinstance(item, dict)
                and _safe_ticker(item.get("fundTicker") or item.get("fundFilter")) == ticker
            ),
            None,
        )
        if not row:
            raise EtfScrapeError("State Street catalog row not found")
        fields = {
            "nav": self._display_value(row, "nav"),
            "total_net_assets": self._display_value(row, "aum"),
            "as_of_date": self._date_value(row, "asOfDate"),
        }
        raw_payload = {
            "field_values": fields,
            "source_row": row,
            "html_size": len(raw_text or ""),
            "standardized": {
                "primary_exchange": row.get("primaryExchange"),
                "expense_ratio": _finite_float(self._display_value(row, "ter")),
                "ytd_return": _finite_float(self._display_value(row, "ytd")),
                "close_price": _finite_float(self._display_value(row, "closePrice")),
                "bid_ask_spread": _finite_float(self._display_value(row, "bidAsk")),
                "premium_discount": self._display_value(row, "premiumDiscount"),
            },
        }
        return self.build_observation_from_fields(
            fund=fund,
            fields=fields,
            source_url=str(fund.get("url") or final_url),
            tz=tz,
            raw_payload=raw_payload,
            extraction_method="state_street_catalog_api",
            confidence=0.9,
        )

    def extract_fields(self, decoded: str, soup: BeautifulSoup, plain_text: str, tz: ZoneInfo) -> dict[str, Any]:
        return {
            "nav": _extract_first_regex(
                decoded,
                [r'"nav"\s*:\s*\{.*?"originalValue"\s*:\s*"([^"]+)"'],
            ),
            "total_net_assets": _extract_first_regex(
                decoded,
                [r'"aum"\s*:\s*\{.*?"originalValue"\s*:\s*"([^"]+)"'],
            ),
            "as_of_date": _extract_first_regex(
                decoded,
                [r'"nav-date"\s*:\s*\{.*?"value"\s*:\s*"([^"]+)"', r'"nav"\s*:\s*\{.*?"asOfDateSimple"\s*:\s*"([^"]+)"'],
            ),
        }


class VanEckEtfProvider(GenericHtmlEtfProvider):
    provider = "vaneck"
    catalog_url = "https://www.vaneck.com/Main/FundListingUs/GetDataset/?pageId=5517"

    def catalog_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
        }

    def fetch_catalog_rows(self) -> tuple[list[dict[str, Any]], str, str]:
        payload, final_url, raw_text = self.fetch_json(
            self.catalog_url,
            headers=self.catalog_headers(),
            cache_key="vaneck_catalog",
        )
        rows = payload.get("ExchangeTradedFunds") if isinstance(payload, dict) else []
        return [row for row in rows or [] if isinstance(row, dict)], final_url, raw_text

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        if url == self.catalog_url:
            rows, final_url, raw_text = self.fetch_catalog_rows()
        else:
            payload, final_url, raw_text = self.fetch_json(url, headers=self.catalog_headers())
            rows = payload.get("ExchangeTradedFunds") if isinstance(payload, dict) else []
        funds: list[dict[str, Any]] = []
        for row in rows or []:
            ticker = _safe_ticker(row.get("Ticker"))
            name = str(row.get("Name") or "").strip()
            if not ticker or not name:
                continue
            slug_name = re.sub(r"(?i)^vaneck\s+", "", name).strip() or name
            slug = f"{_slugify(slug_name)}-{ticker.lower()}"
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": name,
                    "url": f"https://www.vaneck.com/us/en/investments/{slug}/",
                    "currency": "USD",
                    "active": True,
                    "priority": 30,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_row": row,
                        "catalog_nav": _finite_float(row.get("NAV")),
                        "catalog_as_of_date": _parse_date(row.get("AsOfDate"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                        "catalog_inception_date": _parse_date(row.get("InceptionDate"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("VanEck catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(raw_text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }

    def fetch_observation(self, fund: dict[str, Any], tz: ZoneInfo) -> EtfObservation:
        try:
            return super().fetch_observation(fund, tz)
        except EtfScrapeError as exc:
            rows, final_url, raw_text = self.fetch_catalog_rows()
            ticker = _safe_ticker(fund.get("ticker"))
            row = next((item for item in rows if _safe_ticker(item.get("Ticker")) == ticker), None)
            if not row or _finite_float(row.get("NAV")) is None:
                raise exc
            fields = {
                "nav": row.get("NAV"),
                "as_of_date": row.get("AsOfDate"),
                "currency": "USD",
            }
            raw_payload = {
                "field_values": fields,
                "source_row": row,
                "detail_page_error": str(exc),
                "html_size": len(raw_text or ""),
                "standardized": {
                    "distribution_frequency": row.get("Distribution Frequency"),
                    "sec_yield_30_day": _finite_float(row.get("30 Day SEC Yield")),
                    "distribution_yield": _finite_float(row.get("Distribution Yield")),
                    "twelve_month_yield": _finite_float(row.get("12 Month Yield")),
                    "daily_change": row.get("Daily Change"),
                },
            }
            return self.build_observation_from_fields(
                fund=fund,
                fields=fields,
                source_url=str(fund.get("url") or final_url),
                tz=tz,
                raw_payload=raw_payload,
                extraction_method="vaneck_catalog_api_fallback",
                allow_nav_only=True,
                confidence=0.55,
                warnings=["detail_page_failed_used_catalog_nav"],
            )

    def extract_fields(self, decoded: str, soup: BeautifulSoup, plain_text: str, tz: ZoneInfo) -> dict[str, Any]:
        def metric(label: str) -> tuple[str | None, str | None]:
            for node in soup.select(".item-title"):
                direct_text = " ".join(
                    str(child).strip()
                    for child in node.children
                    if isinstance(child, NavigableString) and str(child).strip()
                )
                title = _compact_text(direct_text or node.get_text(" ", strip=True))
                if title.lower() == label.lower():
                    row = node.find_parent("li")
                    if row is None:
                        continue
                    value_node = row.select_one(".item-value")
                    date_node = row.select_one(".as-of-date")
                    value = value_node.get_text(" ", strip=True) if value_node else None
                    as_of = date_node.get_text(" ", strip=True) if date_node else None
                    return value, as_of
            return None, None

        nav, nav_as_of = metric("NAV")
        assets, assets_as_of = metric("Total Net Assets")
        return {
            "nav": nav,
            "total_net_assets": assets,
            "as_of_date": nav_as_of or assets_as_of,
        }


class ISharesEtfProvider(GenericHtmlEtfProvider):
    provider = "ishares"
    catalog_url = "https://www.ishares.com/us/products/etf-investments"

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        text, final_url = self.fetch_html(url)
        soup = BeautifulSoup(html.unescape(text or ""), "html.parser")
        tables = soup.find_all("table")
        if not tables:
            raise EtfScrapeError("missing iShares catalog table")
        funds: list[dict[str, Any]] = []
        # The first static fallback table is the ETF universe. A second table on
        # the same page contains index mutual funds and must not be mixed in.
        for tr in tables[0].find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            links = tr.find_all("a", href=True)
            if len(cells) < 10 or len(links) < 2:
                continue
            href = links[0].get("href") or links[1].get("href") or ""
            if "/us/products/" not in href:
                continue
            ticker = _safe_ticker(cells[0])
            name = cells[1].strip()
            if not ticker or not name:
                continue
            metadata = {
                "catalog_source_url": final_url,
                "catalog_row": cells,
                "catalog_total_net_assets_usd": _finite_float(cells[9]),
                "catalog_inception_date": _parse_date(cells[6], ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                "catalog_gross_expense_ratio": _finite_float(cells[7]),
                "catalog_net_expense_ratio": _finite_float(cells[8]),
                "catalog_twelve_month_yield": _finite_float(cells[2]),
                "catalog_yield_as_of": _parse_date(cells[3], ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                "catalog_ytd_return": _finite_float(cells[4]),
                "catalog_perf_as_of": _parse_date(cells[5], ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
            }
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": name,
                    "url": urljoin(final_url, href),
                    "currency": "USD",
                    "active": True,
                    "priority": 20,
                    "metadata": metadata,
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("iShares catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }

    def extract_fields(self, decoded: str, soup: BeautifulSoup, plain_text: str, tz: ZoneInfo) -> dict[str, Any]:
        return {
            "nav": _text_by_data_id(soup, "fundHeader-navAmount-data"),
            "shares_outstanding": _text_by_data_id(soup, "keyFundFacts-sharesOutstanding-data"),
            "total_net_assets": _text_by_data_id(soup, "keyFundFacts-totalNetAssetsFundLevel-data"),
            "as_of_date": _text_by_data_id(
                soup,
                "keyFundFacts-sharesOutstanding-asOf",
                "keyFundFacts-totalNetAssetsFundLevel-asOf",
                "fundHeader-navAmount-asOf",
            ),
        }


class DimensionalEtfProvider(GenericHtmlEtfProvider):
    provider = "dimensional"
    catalog_url = "https://etf.dimensional.com/public/v2/fundcenter?allowMorningstarFixedIncome=true"

    @staticmethod
    def _identifier(meta: dict[str, Any], slug: str) -> str | None:
        for item in meta.get("identifiers") or []:
            if isinstance(item, dict) and item.get("slug") == slug:
                return str(item.get("value") or "").strip() or None
        return None

    @staticmethod
    def _value_payload(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("value") if value.get("value") is not None else value.get("display")
        return value

    def catalog_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US",
            "Content-Type": "application/json",
            "Referer": "https://www.dimensional.com/us-en/funds/?ft=etf",
            "x-selected-country": "US",
        }

    def _portfolio_ticker(self, row: dict[str, Any]) -> str:
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        return _safe_ticker(
            self._identifier(meta, "ticker")
            or (meta.get("primaryIdentifier") or {}).get("value")
        )

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        payload, final_url, raw_text = self.fetch_json(
            url,
            headers=self.catalog_headers(),
            cache_key="dimensional_catalog",
        )
        rows = payload.get("data", {}).get("portfolios", []) if isinstance(payload, dict) else []
        funds: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
            name = str(meta.get("marketingName") or "").strip()
            is_etf = bool(meta.get("isEtf")) or name.lower().endswith(" etf")
            if not is_etf:
                continue
            ticker = self._portfolio_ticker(row)
            if not ticker or not name:
                continue
            first_price = (row.get("prices") or [{}])[0] if isinstance(row.get("prices"), list) else {}
            fees = {
                fee.get("slug"): self._value_payload(fee.get("value"))
                for fee in row.get("fees") or []
                if isinstance(fee, dict)
            }
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": f"Dimensional {name}" if not name.lower().startswith("dimensional") else name,
                    "url": f"https://www.dimensional.com/us-en/funds/{ticker.lower()}/{_slugify(name)}",
                    "currency": str(meta.get("dfaCurrencyCode") or "USD").upper(),
                    "active": True,
                    "priority": 35,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_portfolio_number": row.get("portfolioNumber"),
                        "catalog_category": meta.get("category"),
                        "catalog_nav": _finite_float(self._value_payload((first_price.get("nav") if isinstance(first_price, dict) else None))),
                        "catalog_as_of_date": _parse_date(
                            self._value_payload(first_price.get("date") if isinstance(first_price, dict) else None),
                            ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE),
                        )
                        or _parse_date(row.get("pricesAsOfDate", {}).get("value"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                        "catalog_inception_date": _parse_date(
                            (meta.get("inceptionDate") or {}).get("value"),
                            ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE),
                        ),
                        "catalog_gross_expense_ratio": _finite_float(fees.get("tot-op-exp-ratio")),
                        "catalog_net_expense_ratio": _finite_float(fees.get("net-exp-ratio")),
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("Dimensional catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(raw_text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }

    def fetch_observation(self, fund: dict[str, Any], tz: ZoneInfo) -> EtfObservation:
        payload, final_url, raw_text = self.fetch_json(
            self.catalog_url,
            headers=self.catalog_headers(),
            cache_key="dimensional_catalog",
        )
        rows = payload.get("data", {}).get("portfolios", []) if isinstance(payload, dict) else []
        ticker = _safe_ticker(fund.get("ticker"))
        row = next(
            (item for item in rows if isinstance(item, dict) and self._portfolio_ticker(item) == ticker),
            None,
        )
        if not row:
            raise EtfScrapeError("Dimensional catalog row not found")
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        first_price = (row.get("prices") or [{}])[0] if isinstance(row.get("prices"), list) else {}
        fees = {
            fee.get("slug"): self._value_payload(fee.get("value"))
            for fee in row.get("fees") or []
            if isinstance(fee, dict)
        }
        fields = {
            "nav": self._value_payload(first_price.get("nav") if isinstance(first_price, dict) else None),
            "as_of_date": self._value_payload(first_price.get("date") if isinstance(first_price, dict) else None)
            or row.get("pricesAsOfDate", {}).get("value"),
            "currency": meta.get("dfaCurrencyCode") or "USD",
        }
        raw_payload = {
            "field_values": fields,
            "source_row": row,
            "html_size": len(raw_text or ""),
            "standardized": {
                "portfolio_number": row.get("portfolioNumber"),
                "market_price": _finite_float(
                    self._value_payload(first_price.get("marketPrice") if isinstance(first_price, dict) else None)
                ),
                "gross_expense_ratio": _finite_float(fees.get("tot-op-exp-ratio")),
                "net_expense_ratio": _finite_float(fees.get("net-exp-ratio")),
                "category": meta.get("category"),
                "returns_daily": row.get("returnsDaily"),
                "returns_daily_market_price": row.get("returnsDailyMarketPrice"),
                "returns_monthly": row.get("returnsMonthly"),
            },
        }
        return self.build_observation_from_fields(
            fund=fund,
            fields=fields,
            source_url=str(fund.get("url") or final_url),
            tz=tz,
            raw_payload=raw_payload,
            extraction_method="dimensional_fundcenter_api",
            allow_nav_only=True,
            confidence=0.55,
        )


class VanguardEtfProvider(GenericHtmlEtfProvider):
    provider = "vanguard"
    catalog_url = "https://investor.vanguard.com/investment-products/list/funddetail/all"

    def catalog_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
            "Referer": "https://investor.vanguard.com/investment-products/list/etfs",
        }

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        payload, final_url, raw_text = self.fetch_json(
            url,
            headers=self.catalog_headers(),
            cache_key="vanguard_catalog",
        )
        rows = payload.get("fund", {}).get("entity", []) if isinstance(payload, dict) else []
        funds: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
            if profile.get("isETF") is not True:
                continue
            ticker = _safe_ticker(profile.get("ticker"))
            name = str(profile.get("longName") or profile.get("shortName") or "").strip()
            if not ticker or not name:
                continue
            daily_price = row.get("dailyPrice") if isinstance(row.get("dailyPrice"), dict) else {}
            regular_price = daily_price.get("regular") if isinstance(daily_price.get("regular"), dict) else {}
            ytd = row.get("ytd") if isinstance(row.get("ytd"), dict) else {}
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": name,
                    "url": f"https://investor.vanguard.com/investment-products/etfs/profile/{ticker.lower()}",
                    "currency": "USD",
                    "active": True,
                    "priority": 30,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_fund_id": profile.get("fundId"),
                        "catalog_category": profile.get("category"),
                        "catalog_style": profile.get("style"),
                        "catalog_nav": _finite_float(regular_price.get("price")),
                        "catalog_as_of_date": _parse_date(regular_price.get("asOfDate"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                        "catalog_inception_date": _parse_date(profile.get("inceptionDate"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                        "catalog_net_expense_ratio": _finite_float(profile.get("expenseRatio")),
                        "catalog_ytd_return": _finite_float(ytd.get("regular")),
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("Vanguard catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(raw_text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }

    def fetch_observation(self, fund: dict[str, Any], tz: ZoneInfo) -> EtfObservation:
        ticker = _safe_ticker(fund.get("ticker"))
        if not ticker:
            raise EtfScrapeError("missing ticker")
        price_url = f"https://investor.vanguard.com/vmf/api/{ticker}/price"
        payload, final_url, raw_text = self.fetch_json(
            price_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
                "Referer": str(fund.get("url") or f"https://investor.vanguard.com/investment-products/etfs/profile/{ticker.lower()}"),
            },
            cache_key=f"vanguard_price:{ticker}",
            ttl_seconds=300,
        )
        current = payload.get("currentPrice", {}) if isinstance(payload, dict) else {}
        daily_price = current.get("dailyPrice", {}) if isinstance(current.get("dailyPrice"), dict) else {}
        regular = daily_price.get("regular") if isinstance(daily_price.get("regular"), dict) else {}
        market = daily_price.get("market") if isinstance(daily_price.get("market"), dict) else {}
        fields = {
            "nav": regular.get("price"),
            "as_of_date": regular.get("asOfDate"),
            "currency": "USD",
        }
        raw_payload = {
            "field_values": fields,
            "source_payload": payload,
            "html_size": len(raw_text or ""),
            "standardized": {
                "market_price": _finite_float(market.get("price")),
                "market_price_as_of_date": _parse_date(market.get("asOfDate"), tz),
                "premium_or_discount": _finite_float(current.get("premiumOrDiscount")),
                "yield_pct": _finite_float((current.get("yield") or {}).get("yieldPct") if isinstance(current.get("yield"), dict) else None),
                "price_change_amount": _finite_float(regular.get("priceChangeAmount")),
                "price_change_pct": _finite_float(regular.get("priceChangePct")),
            },
        }
        return self.build_observation_from_fields(
            fund=fund,
            fields=fields,
            source_url=final_url,
            tz=tz,
            raw_payload=raw_payload,
            extraction_method="vanguard_price_api",
            allow_nav_only=True,
            confidence=0.55,
        )


class InvescoEtfProvider(GenericHtmlEtfProvider):
    provider = "invesco"
    catalog_url = "https://www.invesco.com/content/dam/invesco/us/en/etf-search-component/etf_performance.csv"
    product_search_url = "https://dng-api.invesco.com/product/search"

    def api_headers(self, referer: str | None = None) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
            "Origin": "https://www.invesco.com",
            "Referer": referer or "https://www.invesco.com/us/en/financial-products/etfs.html",
        }

    def product_search_params(self) -> list[tuple[str, str]]:
        return [
            ("facet", "true"),
            ("facet.field", "assetClass"),
            ("fq", 'countryCode:"US"'),
            ("fq", 'language:"en_us"'),
            ("fq", 'accountType:"ETF"'),
            ("fq", 'contentType:"Product"'),
            ("fq", 'shareClassStatus:"open"'),
            ("q", "_suggest_:*"),
            (
                "fl",
                "url,uniqueIdentifier,shareClassStatus,shareClassState,primaryShareClassIndicator,"
                "assetSubClass,assetClass,cusip,title,accountName,isin,youngFund,fundId,inceptionDate,"
                "solutionCategory,shareClassIdentifier,strategy,shareClassInceptionDate,shareClassSuffix,"
                "maxLoad,ticker,totalExpenseRatio,factsheet,footnotes",
            ),
            ("rows", "2000"),
            ("start", "0"),
            ("sort", "shareClassFullName asc"),
            ("facet.field", "assetClass"),
            ("facet.pivot", "assetClass,assetSubClass"),
            ("fq", "assetClass:[* TO *]"),
            ("fq", "assetSubClass:[* TO *]"),
            ("f.assetSubClass.facet.sort", "index"),
            ("f.assetClass.facet.sort", "index"),
        ]

    def fetch_product_docs(self) -> tuple[list[dict[str, Any]], str, str]:
        payload, final_url, raw_text = self.fetch_json(
            self.product_search_url,
            headers=self.api_headers(),
            params=self.product_search_params(),
            cache_key="invesco_product_search",
        )
        docs = payload.get("response", {}).get("docs", []) if isinstance(payload, dict) else []
        return [doc for doc in docs if isinstance(doc, dict)], final_url, raw_text

    def fetch_catalog_csv(self, url: str) -> tuple[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/csv,application/octet-stream,*/*",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.7",
            "Referer": "https://www.invesco.com/us/en/solutions/invesco-etfs.html",
        }
        response = self.session.get(url, headers=headers, timeout=self.timeout_seconds, allow_redirects=True)
        if response.status_code < 400 and response.text.strip():
            return response.text, str(response.url)

        curl_path = shutil.which("curl.exe") or shutil.which("curl")
        if not curl_path:
            raise EtfScrapeError(f"http {response.status_code}; curl fallback unavailable")
        try:
            completed = subprocess.run(
                [
                    curl_path,
                    "--silent",
                    "--show-error",
                    "--location",
                    "--max-time",
                    str(max(10, int(self.timeout_seconds))),
                    "--user-agent",
                    self.user_agent,
                    "--referer",
                    "https://www.invesco.com/us/en/solutions/invesco-etfs.html",
                    url,
                ],
                capture_output=True,
                check=False,
                timeout=max(15, int(self.timeout_seconds) + 5),
            )
        except Exception as exc:
            raise EtfScrapeError(f"http {response.status_code}; curl fallback failed: {exc}") from exc
        text = completed.stdout.decode("utf-8-sig", errors="replace")
        if completed.returncode != 0 or not text.strip():
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise EtfScrapeError(f"http {response.status_code}; curl fallback failed: {error or completed.returncode}")
        return text, url

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        if source_url is None:
            try:
                docs, final_url, raw_text = self.fetch_product_docs()
                funds: list[dict[str, Any]] = []
                for doc in docs:
                    ticker = _safe_ticker(doc.get("ticker"))
                    name = str(doc.get("accountName") or doc.get("title") or "").strip()
                    cusip = str(doc.get("cusip") or "").strip()
                    href = str(doc.get("url") or "").strip()
                    if not ticker or not name or not cusip:
                        continue
                    funds.append(
                        {
                            "provider": self.provider,
                            "ticker": ticker,
                            "name": name,
                            "url": urljoin("https://www.invesco.com", href)
                            if href
                            else f"https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker={ticker}",
                            "currency": "USD",
                            "active": True,
                            "priority": 35,
                            "metadata": {
                                "catalog_source_url": final_url,
                                "catalog_cusip": cusip,
                                "catalog_isin": doc.get("isin"),
                                "catalog_asset_class": doc.get("assetClass"),
                                "catalog_asset_subclass": doc.get("assetSubClass"),
                                "catalog_strategy": doc.get("strategy"),
                                "catalog_inception_date": _parse_date(doc.get("inceptionDate"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                                "catalog_net_expense_ratio": _finite_float(doc.get("totalExpenseRatio")),
                                "catalog_factsheet": urljoin("https://www.invesco.com", str(doc.get("factsheet") or "")),
                                "catalog_row": doc,
                            },
                        }
                    )
                    if max_funds and len(funds) >= max_funds:
                        break
                if not funds:
                    raise EtfScrapeError("Invesco product search returned zero ETFs")
                return {
                    "ok": True,
                    "provider": self.provider,
                    "source_url": final_url,
                    "count": len(funds),
                    "funds": funds,
                    "html_size": len(raw_text or ""),
                    "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
                }
            except Exception as exc:
                logger.warning("Invesco product search failed, falling back to CSV: %s", exc)

        url = source_url or self.catalog_url
        text, final_url = self.fetch_catalog_csv(url)
        lines = text.splitlines()
        header_index = next((index for index, line in enumerate(lines) if line.startswith("Products,Ticker,")), None)
        if header_index is None:
            raise EtfScrapeError("Invesco catalog CSV header not found")
        rows = list(csv.DictReader(io.StringIO("\n".join(lines[header_index:]))))
        funds: list[dict[str, Any]] = []
        for row in rows:
            ticker = _safe_ticker(row.get("Ticker"))
            name = str(row.get("Products") or "").strip()
            if not ticker or not name:
                continue
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": name,
                    "url": f"https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker={ticker}",
                    "currency": "USD",
                    "active": True,
                    "priority": 35,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_row": row,
                        "catalog_inception_date": _parse_date(row.get("Inception"), ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)),
                        "catalog_gross_expense_ratio": _finite_float(row.get("Gross Exp. Ratio")),
                        "catalog_ytd_return": _finite_float(row.get("YTD")),
                        "catalog_category": row.get("Category"),
                        "catalog_subcategory": row.get("SubCategory"),
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("Invesco catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }

    def fetch_observation(self, fund: dict[str, Any], tz: ZoneInfo) -> EtfObservation:
        ticker = _safe_ticker(fund.get("ticker"))
        if not ticker:
            raise EtfScrapeError("missing ticker")
        metadata = fund.get("metadata") if isinstance(fund.get("metadata"), dict) else {}
        cusip = str(metadata.get("catalog_cusip") or "").strip()
        doc: dict[str, Any] | None = None
        if not cusip:
            docs, _, _ = self.fetch_product_docs()
            doc = next((item for item in docs if _safe_ticker(item.get("ticker")) == ticker), None)
            cusip = str((doc or {}).get("cusip") or "").strip()
        if not cusip:
            raise EtfScrapeError("missing Invesco CUSIP")
        price_url = f"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/{cusip}/prices"
        payload, final_url, raw_text = self.fetch_json(
            price_url,
            headers=self.api_headers(str(fund.get("url") or "")),
            params={
                "idType": "cusip",
                "variationType": "priceListing",
                "productType": "ETF",
                "productSubType": "ETF",
            },
            cache_key=f"invesco_price:{cusip}",
            ttl_seconds=300,
        )
        if not isinstance(payload, dict):
            raise EtfScrapeError("invalid Invesco price payload")
        fields = {
            "nav": payload.get("nav"),
            "shares_outstanding": payload.get("sharesOutstanding"),
            "total_net_assets": payload.get("marketValue"),
            "as_of_date": payload.get("effectiveDate"),
            "currency": payload.get("currency") or "USD",
        }
        raw_payload = {
            "field_values": fields,
            "source_payload": payload,
            "source_row": doc or metadata.get("catalog_row"),
            "html_size": len(raw_text or ""),
            "standardized": {
                "cusip": cusip,
                "opening_price": _finite_float(payload.get("openingPrice")),
                "closing_price": _finite_float(payload.get("closingPrice")),
                "market_price": _finite_float(payload.get("closingPrice")),
                "bid_ask_midpoint": _finite_float(payload.get("bidAskMidpoint")),
                "bid_ask_midpoint_premium_discount": _finite_float(payload.get("bidAskMidpointPremiumDiscount")),
                "bid_ask_midpoint_premium_discount_pct": _finite_float(payload.get("bidAskMidpointPremiumDiscountPercentage")),
                "one_day_nav_change_pct": _finite_float(payload.get("oneDayNetAssetValueChangePercent")),
                "average_trading_volume_30d": _finite_float(payload.get("30dayAverageTradingVolume")),
                "previous_day_trading_volume": _finite_float(payload.get("previousDayTradingVolume")),
            },
        }
        return self.build_observation_from_fields(
            fund=fund,
            fields=fields,
            source_url=final_url,
            tz=tz,
            raw_payload=raw_payload,
            extraction_method="invesco_dng_price_api",
            confidence=0.95,
        )


class ProSharesEtfProvider(GenericHtmlEtfProvider):
    provider = "proshares"
    catalog_url = "https://www.proshares.com/our-etfs/find-leveraged-and-inverse-etfs"

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        text, final_url = self.fetch_html(url)
        soup = BeautifulSoup(html.unescape(text or ""), "html.parser")
        funds: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tr in soup.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 6 or cells[0].strip().lower() == "ticker":
                continue
            ticker = _safe_ticker(cells[0])
            name = cells[1].strip()
            link = tr.find("a", href=True)
            if not ticker or not name or ticker in seen:
                continue
            seen.add(ticker)
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": f"ProShares {name}" if not name.lower().startswith("proshares") else name,
                    "url": urljoin(final_url, link.get("href") if link else f"/our-etfs/{ticker.lower()}"),
                    "currency": "USD",
                    "active": True,
                    "priority": 40,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_row": cells,
                        "catalog_fund_type": cells[2] if len(cells) > 2 else None,
                        "catalog_daily_objective": cells[3] if len(cells) > 3 else None,
                        "catalog_asset_class": cells[4] if len(cells) > 4 else None,
                        "catalog_total_net_assets_usd": _finite_float(cells[5] if len(cells) > 5 else None),
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("ProShares catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }


class GlobalXEtfProvider(GenericHtmlEtfProvider):
    provider = "global_x"
    catalog_url = "https://www.globalxetfs.com/explore"

    def discover_funds(self, source_url: str | None = None, max_funds: int | None = None) -> dict[str, Any]:
        url = source_url or self.catalog_url
        text, final_url = self.fetch_html(url)
        soup = BeautifulSoup(html.unescape(text or ""), "html.parser")
        grouped: dict[str, list[str]] = {}
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            match = re.search(r"/funds/([A-Za-z0-9.\-]+)", href)
            if not match:
                continue
            ticker = _safe_ticker(match.group(1))
            if len(ticker) > 6 or ticker in {"DOCUMENTS", "FUND-DOCUMENTS"}:
                continue
            text_value = _compact_text(anchor.get_text(" ", strip=True))
            if not ticker:
                continue
            grouped.setdefault(ticker, [])
            if text_value and text_value not in grouped[ticker]:
                grouped[ticker].append(text_value)
        funds: list[dict[str, Any]] = []
        for ticker in sorted(grouped):
            labels = grouped[ticker]
            name = next((label for label in labels if _safe_ticker(label) != ticker and len(label) > 3), ticker)
            funds.append(
                {
                    "provider": self.provider,
                    "ticker": ticker,
                    "name": f"Global X {name}" if not name.lower().startswith("global x") else name,
                    "url": f"https://www.globalxetfs.com/funds/{ticker}",
                    "currency": "USD",
                    "active": True,
                    "priority": 50,
                    "metadata": {
                        "catalog_source_url": final_url,
                        "catalog_labels": labels,
                    },
                }
            )
            if max_funds and len(funds) >= max_funds:
                break
        if not funds:
            raise EtfScrapeError("Global X catalog returned zero ETFs")
        return {
            "ok": True,
            "provider": self.provider,
            "source_url": final_url,
            "count": len(funds),
            "funds": funds,
            "html_size": len(text or ""),
            "catalog_hash": _sha256("\n".join(f"{fund['ticker']}|{fund['url']}" for fund in funds)),
        }

    def extract_fields(self, decoded: str, soup: BeautifulSoup, plain_text: str, tz: ZoneInfo) -> dict[str, Any]:
        nav = _extract_first_regex(decoded, [r'\\?"NET_ASSET_VALUE\\?"\s*:\s*\\?"([^"\\]+)'])
        shares = _extract_first_regex(decoded, [r'\\?"SHARES_OUTSTANDING\\?"\s*:\s*\\?"?([\d,.\s]+)\\?"?'])
        as_of_date = _extract_first_regex(
            decoded,
            [
                r'\\?"SHARES_OUTSTANDING_DATE\\?"\s*:\s*\\?"\$?D?([^"\\]+)',
                r'\\?"THIRTY_DAY_MEDIAN_BID_ASK_DATE\\?"\s*:\s*\\?"\$?D?([^"\\]+)',
                r'\\?"AS_OF_DATE\\?"\s*:\s*\\?"\$?D?([^"\\]+)',
            ],
        )
        total_assets = None
        nav_float = _finite_float(nav)
        shares_float = _finite_float(shares)
        if nav_float is not None and shares_float is not None:
            total_assets = nav_float * shares_float
        return {
            "nav": nav,
            "shares_outstanding": shares,
            "total_net_assets": total_assets,
            "as_of_date": as_of_date,
        }


PROVIDER_CLASSES = {
    "schwab": SchwabEtfProvider,
    "state_street": StateStreetEtfProvider,
    "vaneck": VanEckEtfProvider,
    "ishares": ISharesEtfProvider,
    "dimensional": DimensionalEtfProvider,
    "vanguard": VanguardEtfProvider,
    "invesco": InvescoEtfProvider,
    "proshares": ProSharesEtfProvider,
    "global_x": GlobalXEtfProvider,
}


class EtfDailyFlowService:
    def __init__(self, data_dir: str | os.PathLike[str] | None = None):
        self.data_dir = Path(data_dir or Config.ETF_DAILY_FLOW_DATA_DIR).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "etf_daily_flows.sqlite"
        self.tz = ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)
        self.timeout_seconds = float(Config.ETF_DAILY_FLOW_REQUEST_TIMEOUT_SECONDS)
        self.max_attempts = int(Config.ETF_DAILY_FLOW_REQUEST_MAX_ATTEMPTS)
        self.retry_backoff_seconds = float(Config.ETF_DAILY_FLOW_RETRY_BACKOFF_SECONDS)
        self.contract_failure_threshold = int(Config.ETF_DAILY_FLOW_CONTRACT_FAILURE_THRESHOLD)
        self.max_stale_hours = float(Config.ETF_DAILY_FLOW_MAX_STALE_HOURS)
        self.user_agent = Config.ETF_DAILY_FLOW_USER_AGENT
        self._providers: dict[str, GenericHtmlEtfProvider] = {}
        self._lock = threading.RLock()
        self._ensure_schema()
        if Config.ETF_DAILY_FLOW_SEED_DEFAULT_UNIVERSE:
            self.seed_default_universe()
        self.seed_universe_from_env()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS service_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS etf_universe (
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT,
                    url TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    active INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 100,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, ticker)
                );

                CREATE TABLE IF NOT EXISTS etf_source_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    provider TEXT,
                    tickers_json TEXT,
                    funds_attempted INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    observations_count INTEGER NOT NULL DEFAULT 0,
                    flows_count INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT
                );

                CREATE TABLE IF NOT EXISTS etf_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    nav REAL,
                    shares_outstanding REAL,
                    total_net_assets REAL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    confidence REAL NOT NULL DEFAULT 0,
                    field_hash TEXT,
                    extraction_method TEXT,
                    raw_payload_json TEXT,
                    warnings_json TEXT,
                    run_id TEXT,
                    UNIQUE(provider, ticker, as_of_date)
                );

                CREATE TABLE IF NOT EXISTS etf_daily_flows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    nav REAL NOT NULL,
                    shares_outstanding REAL NOT NULL,
                    previous_as_of_date TEXT NOT NULL,
                    previous_nav REAL NOT NULL,
                    previous_shares_outstanding REAL NOT NULL,
                    share_delta REAL NOT NULL,
                    flow_usd REAL NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    method TEXT NOT NULL,
                    warnings_json TEXT,
                    run_id TEXT,
                    UNIQUE(provider, ticker, as_of_date)
                );

                CREATE TABLE IF NOT EXISTS etf_source_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    provider TEXT,
                    ticker TEXT,
                    source_url TEXT,
                    stage TEXT,
                    error_type TEXT,
                    error TEXT,
                    traceback TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS etf_scrape_contracts (
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_field_hash TEXT,
                    previous_field_hash TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, ticker)
                );

                CREATE INDEX IF NOT EXISTS idx_etf_observations_lookup
                    ON etf_observations(provider, ticker, as_of_date DESC);
                CREATE INDEX IF NOT EXISTS idx_etf_flows_lookup
                    ON etf_daily_flows(provider, ticker, as_of_date DESC);
                CREATE INDEX IF NOT EXISTS idx_etf_errors_created
                    ON etf_source_errors(created_at DESC);
                """
            )
            self._set_state(conn, "schema_version", str(ETF_DAILY_FLOW_SCHEMA_VERSION))

    def _set_state(self, conn: sqlite3.Connection, key: str, value: Any) -> None:
        conn.execute(
            """
            INSERT INTO service_state(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, str(value), _utc_now_iso()),
        )

    def _get_state(self, conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute("SELECT value FROM service_state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def seed_default_universe(self) -> dict[str, Any]:
        inserted = 0
        updated = 0
        skipped_existing = 0
        with self._connect() as conn:
            existing_keys = {
                (_safe_provider(row["provider"]), _safe_ticker(row["ticker"]))
                for row in conn.execute("SELECT provider, ticker FROM etf_universe").fetchall()
            }
        for item in DEFAULT_ETF_UNIVERSE:
            key = (_safe_provider(item.get("provider")), _safe_ticker(item.get("ticker")))
            if key in existing_keys:
                skipped_existing += 1
                continue
            result = self.upsert_fund(item)
            existing_keys.add(key)
            inserted += 1 if result.get("created") else 0
            updated += 1 if not result.get("created") else 0
        return {
            "ok": True,
            "inserted": inserted,
            "updated": updated,
            "skipped_existing": skipped_existing,
            "total": len(DEFAULT_ETF_UNIVERSE),
        }

    def seed_universe_from_env(self) -> dict[str, Any]:
        raw = str(getattr(Config, "ETF_DAILY_FLOW_UNIVERSE_JSON", "") or "").strip()
        if not raw:
            return {"ok": True, "inserted": 0, "updated": 0}
        try:
            payload = json.loads(raw)
        except Exception as exc:
            logger.warning("ETF_DAILY_FLOW_UNIVERSE_JSON is invalid: %s", exc)
            return {"ok": False, "error": str(exc)}
        items = payload if isinstance(payload, list) else payload.get("funds", [])
        inserted = 0
        updated = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            result = self.upsert_fund(item)
            inserted += 1 if result.get("created") else 0
            updated += 1 if not result.get("created") else 0
        return {"ok": True, "inserted": inserted, "updated": updated}

    def discover_provider(
        self,
        provider: str,
        source_url: str | None = None,
        seed_universe: bool = True,
        reset_provider: bool = False,
        max_funds: int | None = None,
    ) -> dict[str, Any]:
        provider = _safe_provider(provider)
        if not provider:
            raise ValueError("provider is required")
        run_id = f"etf-catalog-{provider}-{_utc_now().strftime('%Y%m%dT%H%M%S')}-{_sha256(str(time.time()))[:8]}"
        started_at = _utc_now_iso()
        try:
            result = self._provider_instance(provider).discover_funds(source_url=source_url, max_funds=max_funds)
            funds = result.get("funds") if isinstance(result.get("funds"), list) else []
            inserted = 0
            updated = 0
            deactivated = 0
            if seed_universe:
                discovered_tickers = {_safe_ticker(fund.get("ticker")) for fund in funds if isinstance(fund, dict)}
                previous_active_tickers: set[str] = set()
                if reset_provider:
                    with self._connect() as conn:
                        previous_active_tickers = {
                            _safe_ticker(row["ticker"])
                            for row in conn.execute(
                                "SELECT ticker FROM etf_universe WHERE provider = ? AND active = 1",
                                (provider,),
                            ).fetchall()
                        }
                        conn.execute(
                            "UPDATE etf_universe SET active = 0, updated_at = ? WHERE provider = ?",
                            (_utc_now_iso(), provider),
                        )
                    deactivated = len(previous_active_tickers - discovered_tickers)
                for fund in funds:
                    outcome = self.upsert_fund(fund)
                    inserted += 1 if outcome.get("created") else 0
                    updated += 1 if not outcome.get("created") else 0
            completed_at = _utc_now_iso()
            if max_funds is None:
                with self._connect() as conn:
                    self._set_state(conn, f"catalog:{provider}:last_run_id", run_id)
                    self._set_state(conn, f"catalog:{provider}:last_completed_at", completed_at)
                    self._set_state(conn, f"catalog:{provider}:last_count", len(funds))
                    self._set_state(conn, f"catalog:{provider}:last_hash", result.get("catalog_hash") or "")
                    self._set_state(conn, f"catalog:{provider}:last_status", "ok")
                    self._set_state(conn, f"catalog:{provider}:last_error", "")
            return {
                "ok": True,
                "run_id": run_id,
                "provider": provider,
                "started_at": started_at,
                "completed_at": completed_at,
                "source_url": result.get("source_url") or source_url,
                "catalog_count": len(funds),
                "inserted": inserted,
                "updated": updated,
                "deactivated": deactivated,
                "seed_universe": seed_universe,
                "reset_provider": reset_provider,
                "funds": funds,
            }
        except Exception as exc:
            self._record_error(
                run_id,
                {"provider": provider, "ticker": "", "url": source_url or ""},
                "discover",
                exc,
            )
            with self._connect() as conn:
                self._set_state(conn, f"catalog:{provider}:last_run_id", run_id)
                self._set_state(conn, f"catalog:{provider}:last_completed_at", _utc_now_iso())
                self._set_state(conn, f"catalog:{provider}:last_status", "failed")
                self._set_state(conn, f"catalog:{provider}:last_error", str(exc))
            raise

    def refresh_universe(
        self,
        provider: str | None = None,
        providers: list[str] | None = None,
        reset_provider: bool = True,
    ) -> dict[str, Any]:
        if provider:
            provider_order = [_safe_provider(provider)]
        elif providers:
            provider_order = [_safe_provider(item) for item in providers if _safe_provider(item)]
        else:
            configured = [
                _safe_provider(item)
                for item in str(getattr(Config, "ETF_DAILY_FLOW_CATALOG_PROVIDERS", "") or "").split(",")
                if _safe_provider(item)
            ]
            provider_order = configured or list(DEFAULT_PROVIDER_ORDER)

        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for item in dict.fromkeys(provider_order):
            if not item:
                continue
            try:
                result = self.discover_provider(item, reset_provider=reset_provider)
                results.append(
                    {
                        "provider": item,
                        "ok": True,
                        "catalog_count": result.get("catalog_count"),
                        "inserted": result.get("inserted"),
                        "updated": result.get("updated"),
                        "deactivated": result.get("deactivated"),
                        "run_id": result.get("run_id"),
                    }
                )
            except Exception as exc:
                failures.append({"provider": item, "ok": False, "error": str(exc)})
                logger.warning("ETF catalog refresh failed: provider=%s error=%s", item, exc)
        return {
            "ok": not failures,
            "status": "ok" if not failures else "partial" if results else "failed",
            "providers_attempted": len(results) + len(failures),
            "success_count": len(results),
            "failure_count": len(failures),
            "results": results,
            "failures": failures,
        }

    def upsert_fund(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = _safe_provider(payload.get("provider"))
        ticker = _safe_ticker(payload.get("ticker"))
        url = str(payload.get("url") or "").strip()
        if not provider or not ticker or not url:
            raise ValueError("provider, ticker and url are required")
        now = _utc_now_iso()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        active = 1 if payload.get("active", True) else 0
        priority = int(payload.get("priority") or 100)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT provider, ticker FROM etf_universe WHERE provider = ? AND ticker = ?",
                (provider, ticker),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO etf_universe(
                    provider, ticker, name, url, currency, active, priority, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, ticker) DO UPDATE SET
                    name=excluded.name,
                    url=excluded.url,
                    currency=excluded.currency,
                    active=excluded.active,
                    priority=excluded.priority,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    provider,
                    ticker,
                    str(payload.get("name") or ticker).strip(),
                    url,
                    str(payload.get("currency") or "USD").strip().upper(),
                    active,
                    priority,
                    _json_dumps(metadata),
                    now,
                    now,
                ),
            )
        return {"ok": True, "provider": provider, "ticker": ticker, "created": existing is None}

    def list_universe(self, active: bool | None = None, provider: str | None = None, limit: int | None = None) -> dict[str, Any]:
        sql = "SELECT * FROM etf_universe"
        params: list[Any] = []
        clauses: list[str] = []
        if active is not None:
            clauses.append("active = ?")
            params.append(1 if active else 0)
        if provider:
            clauses.append("provider = ?")
            params.append(_safe_provider(provider))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY priority ASC, provider ASC, ticker ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(max(1, min(int(limit), 5000)))
        with self._connect() as conn:
            rows = [self._row_to_fund(row) for row in conn.execute(sql, params).fetchall()]
        return {"ok": True, "count": len(rows), "funds": rows}

    def _row_to_fund(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["active"] = bool(item.get("active"))
        item["metadata"] = _json_loads(item.pop("metadata_json", None), {})
        return item

    def _provider_instance(self, provider: str) -> GenericHtmlEtfProvider:
        provider = _safe_provider(provider)
        if provider not in self._providers:
            cls = PROVIDER_CLASSES.get(provider, GenericHtmlEtfProvider)
            self._providers[provider] = cls(timeout_seconds=self.timeout_seconds, user_agent=self.user_agent)
        return self._providers[provider]

    def collect(
        self,
        provider: str | None = None,
        tickers: list[str] | None = None,
        force: bool = False,
        limit: int | None = None,
        refresh_universe: bool | None = None,
    ) -> dict[str, Any]:
        provider = _safe_provider(provider) if provider else None
        ticker_set = {_safe_ticker(ticker) for ticker in tickers or [] if _safe_ticker(ticker)}
        refresh_result: dict[str, Any] | None = None
        should_refresh_universe = (
            Config.ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT
            if refresh_universe is None
            else bool(refresh_universe)
        )
        if should_refresh_universe:
            refresh_result = self.refresh_universe(provider=provider, reset_provider=True)
        funds = self._select_funds(provider=provider, tickers=sorted(ticker_set) if ticker_set else None, limit=limit)
        run_id = f"etf-flow-{_utc_now().strftime('%Y%m%dT%H%M%S')}-{_sha256(str(time.time()))[:8]}"
        started_at = _utc_now_iso()
        errors: list[dict[str, Any]] = []
        success_count = 0
        observations_count = 0
        flows_count = 0

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO etf_source_runs(
                    run_id, started_at, status, provider, tickers_json, funds_attempted, errors_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    started_at,
                    "running",
                    provider,
                    _json_dumps(sorted(ticker_set)) if ticker_set else None,
                    len(funds),
                    "[]",
                ),
            )

        logger.info("ETF daily flow collection started: run_id=%s funds=%s", run_id, len(funds))
        for fund in funds:
            try:
                observation = self._collect_one_with_retries(fund, run_id)
                flow = self._save_observation_and_flow(observation, run_id, force=force)
                self._record_contract_success(observation)
                success_count += 1
                observations_count += 1
                flows_count += 1 if flow.get("created") else 0
            except Exception as exc:
                error_payload = self._record_error(run_id, fund, "collect", exc)
                errors.append(error_payload)
                self._record_contract_failure(fund, exc)

        failure_count = len(funds) - success_count
        status = "ok" if failure_count == 0 else "partial" if success_count else "failed"
        completed_at = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE etf_source_runs
                SET completed_at = ?, status = ?, success_count = ?, failure_count = ?,
                    observations_count = ?, flows_count = ?, errors_json = ?
                WHERE run_id = ?
                """,
                (
                    completed_at,
                    status,
                    success_count,
                    failure_count,
                    observations_count,
                    flows_count,
                    _json_dumps(errors[:50]),
                    run_id,
                ),
            )
            self._set_state(conn, "last_run_id", run_id)
            self._set_state(conn, "last_run_completed_at", completed_at)

        logger.info(
            "ETF daily flow collection finished: run_id=%s status=%s success=%s failure=%s",
            run_id,
            status,
            success_count,
            failure_count,
        )
        return {
            "ok": success_count > 0 and status != "failed",
            "run_id": run_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "funds_attempted": len(funds),
            "success_count": success_count,
            "failure_count": failure_count,
            "observations_count": observations_count,
            "flows_count": flows_count,
            "catalog_refresh": refresh_result,
            "errors": errors[:20],
        }

    def _select_funds(
        self,
        provider: str | None = None,
        tickers: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM etf_universe WHERE active = 1"
        params: list[Any] = []
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if tickers:
            placeholders = ",".join("?" for _ in tickers)
            sql += f" AND ticker IN ({placeholders})"
            params.extend(tickers)
        sql += " ORDER BY priority ASC, provider ASC, ticker ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(max(1, min(int(limit), 5000)))
        with self._connect() as conn:
            return [self._row_to_fund(row) for row in conn.execute(sql, params).fetchall()]

    def _collect_one_with_retries(self, fund: dict[str, Any], run_id: str) -> EtfObservation:
        provider = self._provider_instance(fund["provider"])
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                observation = provider.fetch_observation(fund, self.tz)
                if not observation.ticker:
                    raise EtfScrapeError("empty ticker after normalization")
                return observation
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "ETF scrape attempt failed: run_id=%s provider=%s ticker=%s attempt=%s/%s error=%s",
                    run_id,
                    fund.get("provider"),
                    fund.get("ticker"),
                    attempt,
                    self.max_attempts,
                    exc,
                )
                if attempt < self.max_attempts:
                    time.sleep(self.retry_backoff_seconds * attempt)
        assert last_exc is not None
        raise last_exc

    def _save_observation_and_flow(self, observation: EtfObservation, run_id: str, force: bool = False) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO etf_observations(
                    provider, ticker, as_of_date, captured_at, source_url, nav, shares_outstanding,
                    total_net_assets, currency, confidence, field_hash, extraction_method,
                    raw_payload_json, warnings_json, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, ticker, as_of_date) DO UPDATE SET
                    captured_at=excluded.captured_at,
                    source_url=excluded.source_url,
                    nav=excluded.nav,
                    shares_outstanding=excluded.shares_outstanding,
                    total_net_assets=excluded.total_net_assets,
                    currency=excluded.currency,
                    confidence=excluded.confidence,
                    field_hash=excluded.field_hash,
                    extraction_method=excluded.extraction_method,
                    raw_payload_json=excluded.raw_payload_json,
                    warnings_json=excluded.warnings_json,
                    run_id=excluded.run_id
                """,
                (
                    observation.provider,
                    observation.ticker,
                    observation.as_of_date,
                    observation.captured_at,
                    observation.source_url,
                    observation.nav,
                    observation.shares_outstanding,
                    observation.total_net_assets,
                    observation.currency,
                    observation.confidence,
                    observation.field_hash,
                    observation.extraction_method,
                    _json_dumps(observation.raw_payload),
                    _json_dumps(observation.warnings),
                    run_id,
                ),
            )
            prev = conn.execute(
                """
                SELECT *
                FROM etf_observations
                WHERE provider = ? AND ticker = ? AND as_of_date < ?
                    AND nav IS NOT NULL AND shares_outstanding IS NOT NULL
                ORDER BY as_of_date DESC
                LIMIT 1
                """,
                (observation.provider, observation.ticker, observation.as_of_date),
            ).fetchone()
            if not prev:
                return {"ok": True, "created": False, "reason": "no_previous_observation"}
            if observation.nav is None or observation.shares_outstanding is None:
                return {"ok": False, "created": False, "reason": "missing_current_observation_fields"}

            warnings = list(observation.warnings)
            share_delta = float(observation.shares_outstanding) - float(prev["shares_outstanding"])
            flow_usd = share_delta * float(observation.nav)
            method = "shares_delta_x_nav"
            if "shares_outstanding_inferred_from_assets_and_nav" in warnings:
                method = "assets_nav_implied_share_delta_x_nav"

            split_like = self._looks_like_split(
                prev_shares=float(prev["shares_outstanding"]),
                current_shares=float(observation.shares_outstanding),
                prev_nav=float(prev["nav"]),
                current_nav=float(observation.nav),
            )
            if split_like:
                warnings.append("probable_split_or_share_class_event_flow_requires_review")
                method = "review_required_probable_split"
                flow_usd = 0.0

            confidence = min(float(prev["confidence"] or 0.0), observation.confidence)
            if split_like:
                confidence = min(confidence, 0.25)
            conn.execute(
                """
                INSERT INTO etf_daily_flows(
                    provider, ticker, as_of_date, captured_at, nav, shares_outstanding,
                    previous_as_of_date, previous_nav, previous_shares_outstanding,
                    share_delta, flow_usd, confidence, method, warnings_json, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, ticker, as_of_date) DO UPDATE SET
                    captured_at=excluded.captured_at,
                    nav=excluded.nav,
                    shares_outstanding=excluded.shares_outstanding,
                    previous_as_of_date=excluded.previous_as_of_date,
                    previous_nav=excluded.previous_nav,
                    previous_shares_outstanding=excluded.previous_shares_outstanding,
                    share_delta=excluded.share_delta,
                    flow_usd=excluded.flow_usd,
                    confidence=excluded.confidence,
                    method=excluded.method,
                    warnings_json=excluded.warnings_json,
                    run_id=excluded.run_id
                """,
                (
                    observation.provider,
                    observation.ticker,
                    observation.as_of_date,
                    observation.captured_at,
                    observation.nav,
                    observation.shares_outstanding,
                    prev["as_of_date"],
                    prev["nav"],
                    prev["shares_outstanding"],
                    share_delta,
                    flow_usd,
                    confidence,
                    method,
                    _json_dumps(warnings),
                    run_id,
                ),
            )
            return {"ok": True, "created": True, "method": method, "flow_usd": flow_usd}

    def _looks_like_split(self, prev_shares: float, current_shares: float, prev_nav: float, current_nav: float) -> bool:
        if prev_shares <= 0 or current_shares <= 0 or prev_nav <= 0 or current_nav <= 0:
            return False
        share_ratio = current_shares / prev_shares
        nav_ratio = current_nav / prev_nav
        if 0.55 <= share_ratio <= 1.8:
            return False
        return abs((share_ratio * nav_ratio) - 1.0) <= 0.18

    def _record_contract_success(self, observation: EtfObservation) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT last_field_hash FROM etf_scrape_contracts WHERE provider = ? AND ticker = ?",
                (observation.provider, observation.ticker),
            ).fetchone()
            previous_hash = existing["last_field_hash"] if existing else None
            status = "ok"
            if previous_hash and previous_hash != observation.field_hash:
                status = "contract_changed"
            conn.execute(
                """
                INSERT INTO etf_scrape_contracts(
                    provider, ticker, status, last_field_hash, previous_field_hash,
                    consecutive_failures, last_success_at, last_failure_at, last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, NULL, NULL, ?)
                ON CONFLICT(provider, ticker) DO UPDATE SET
                    status=excluded.status,
                    previous_field_hash=excluded.previous_field_hash,
                    last_field_hash=excluded.last_field_hash,
                    consecutive_failures=0,
                    last_success_at=excluded.last_success_at,
                    last_error=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    observation.provider,
                    observation.ticker,
                    status,
                    observation.field_hash,
                    previous_hash,
                    now,
                    now,
                ),
            )

    def _record_contract_failure(self, fund: dict[str, Any], exc: Exception) -> None:
        provider = _safe_provider(fund.get("provider"))
        ticker = _safe_ticker(fund.get("ticker"))
        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT consecutive_failures FROM etf_scrape_contracts WHERE provider = ? AND ticker = ?",
                (provider, ticker),
            ).fetchone()
            consecutive = int(existing["consecutive_failures"] if existing else 0) + 1
            status = "broken_contract" if consecutive >= self.contract_failure_threshold else "degraded"
            conn.execute(
                """
                INSERT INTO etf_scrape_contracts(
                    provider, ticker, status, last_field_hash, previous_field_hash,
                    consecutive_failures, last_success_at, last_failure_at, last_error, updated_at
                )
                VALUES (?, ?, ?, NULL, NULL, ?, NULL, ?, ?, ?)
                ON CONFLICT(provider, ticker) DO UPDATE SET
                    status=excluded.status,
                    consecutive_failures=excluded.consecutive_failures,
                    last_failure_at=excluded.last_failure_at,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (provider, ticker, status, consecutive, now, str(exc), now),
            )

    def _record_error(self, run_id: str, fund: dict[str, Any], stage: str, exc: Exception) -> dict[str, Any]:
        payload = {
            "provider": _safe_provider(fund.get("provider")),
            "ticker": _safe_ticker(fund.get("ticker")),
            "source_url": str(fund.get("url") or ""),
            "stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "created_at": _utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO etf_source_errors(
                    run_id, provider, ticker, source_url, stage, error_type, error, traceback, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    payload["provider"],
                    payload["ticker"],
                    payload["source_url"],
                    stage,
                    payload["error_type"],
                    payload["error"],
                    traceback.format_exc(),
                    payload["created_at"],
                ),
            )
        return payload

    def health(self, manager_status: dict[str, Any] | None = None) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            last_run = conn.execute(
                "SELECT * FROM etf_source_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            latest_obs = conn.execute(
                "SELECT MAX(captured_at) AS captured_at, COUNT(*) AS count FROM etf_observations"
            ).fetchone()
            contracts = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT c.*
                    FROM etf_scrape_contracts c
                    JOIN etf_universe u
                        ON u.provider = c.provider
                        AND u.ticker = c.ticker
                        AND u.active = 1
                    ORDER BY c.provider, c.ticker
                    """
                ).fetchall()
            ]
            active_count = conn.execute("SELECT COUNT(*) AS count FROM etf_universe WHERE active = 1").fetchone()["count"]
            flow_count = conn.execute("SELECT COUNT(*) AS count FROM etf_daily_flows").fetchone()["count"]
            universe_by_provider = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT provider, COUNT(*) AS funds
                    FROM etf_universe
                    WHERE active = 1
                    GROUP BY provider
                    ORDER BY provider
                    """
                ).fetchall()
            ]
            observations_by_provider = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT provider, COUNT(DISTINCT ticker) AS funds, COUNT(*) AS observations, MAX(captured_at) AS latest_captured_at
                    FROM etf_observations
                    GROUP BY provider
                    ORDER BY provider
                    """
                ).fetchall()
            ]
            catalog_state = {
                str(row["key"]): str(row["value"])
                for row in conn.execute("SELECT key, value FROM service_state WHERE key LIKE 'catalog:%'").fetchall()
            }

        latest_captured_at = latest_obs["captured_at"] if latest_obs else None
        stale = True
        if latest_captured_at:
            try:
                age_hours = (now - datetime.fromisoformat(latest_captured_at)).total_seconds() / 3600
                stale = age_hours > self.max_stale_hours
            except Exception:
                age_hours = None
                stale = True
        else:
            age_hours = None

        broken = [item for item in contracts if item.get("status") == "broken_contract"]
        degraded = [item for item in contracts if item.get("status") in {"degraded", "contract_changed"}]
        service_status = "ok"
        if broken or degraded or stale:
            service_status = "degraded"
        if active_count and len(broken) >= active_count:
            service_status = "down"

        return {
            "ok": service_status == "ok",
            "status": service_status,
            "schema_version": ETF_DAILY_FLOW_SCHEMA_VERSION,
            "db_path": str(self.db_path),
            "timezone": str(self.tz),
            "capture_times": Config.ETF_DAILY_FLOW_CAPTURE_TIMES,
            "active_funds": active_count,
            "universe_by_provider": universe_by_provider,
            "observations_by_provider": observations_by_provider,
            "catalog_state": catalog_state,
            "observations": int(latest_obs["count"] or 0) if latest_obs else 0,
            "flows": int(flow_count or 0),
            "latest_captured_at": latest_captured_at,
            "latest_age_hours": age_hours,
            "stale": stale,
            "last_run": dict(last_run) if last_run else None,
            "contract_summary": {
                "total": len(contracts),
                "broken": len(broken),
                "degraded": len(degraded),
                "failure_threshold": self.contract_failure_threshold,
            },
            "contracts": contracts,
            "manager": manager_status or {},
        }

    def list_runs(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(int(limit or 20), 200))
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_source_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()]
        for row in rows:
            row["tickers"] = _json_loads(row.pop("tickers_json", None), [])
            row["errors"] = _json_loads(row.pop("errors_json", None), [])
        return {"ok": True, "count": len(rows), "runs": rows}

    def list_errors(self, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit or 50), 500))
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_source_errors ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()]
        return {"ok": True, "count": len(rows), "errors": rows}

    def list_observations(self, provider: str | None = None, ticker: str | None = None, limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit or 200), 1000))
        sql = "SELECT * FROM etf_observations WHERE 1=1"
        params: list[Any] = []
        if provider:
            sql += " AND provider = ?"
            params.append(_safe_provider(provider))
        if ticker:
            sql += " AND ticker = ?"
            params.append(_safe_ticker(ticker))
        sql += " ORDER BY as_of_date DESC, captured_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        for row in rows:
            row["raw_payload"] = _json_loads(row.pop("raw_payload_json", None), {})
            row["warnings"] = _json_loads(row.pop("warnings_json", None), [])
        return {"ok": True, "count": len(rows), "observations": rows}

    def list_flows(self, provider: str | None = None, ticker: str | None = None, limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit or 200), 1000))
        sql = "SELECT * FROM etf_daily_flows WHERE 1=1"
        params: list[Any] = []
        if provider:
            sql += " AND provider = ?"
            params.append(_safe_provider(provider))
        if ticker:
            sql += " AND ticker = ?"
            params.append(_safe_ticker(ticker))
        sql += " ORDER BY as_of_date DESC, captured_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        for row in rows:
            row["warnings"] = _json_loads(row.pop("warnings_json", None), [])
        return {"ok": True, "count": len(rows), "flows": rows}

    def dashboard(self, top_n: int = 20) -> dict[str, Any]:
        top_n = max(5, min(int(top_n or 20), 50))
        with self._connect() as conn:
            universe_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_universe WHERE active = 1 ORDER BY provider, ticker"
            ).fetchall()]
            observation_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_observations ORDER BY provider, ticker, as_of_date DESC, captured_at DESC"
            ).fetchall()]
            flow_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_daily_flows ORDER BY provider, ticker, as_of_date DESC, captured_at DESC"
            ).fetchall()]
            last_run = conn.execute(
                "SELECT * FROM etf_source_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()

        latest_observation_by_fund: dict[tuple[str, str], dict[str, Any]] = {}
        for row in observation_rows:
            key = (_safe_provider(row.get("provider")), _safe_ticker(row.get("ticker")))
            if key not in latest_observation_by_fund:
                item = dict(row)
                item["raw_payload"] = _json_loads(item.pop("raw_payload_json", None), {})
                item["warnings"] = _json_loads(item.pop("warnings_json", None), [])
                latest_observation_by_fund[key] = item

        latest_flow_by_fund: dict[tuple[str, str], dict[str, Any]] = {}
        for row in flow_rows:
            key = (_safe_provider(row.get("provider")), _safe_ticker(row.get("ticker")))
            if key not in latest_flow_by_fund:
                item = dict(row)
                item["warnings"] = _json_loads(item.pop("warnings_json", None), [])
                latest_flow_by_fund[key] = item

        funds: list[dict[str, Any]] = []
        for row in universe_rows:
            key = (_safe_provider(row.get("provider")), _safe_ticker(row.get("ticker")))
            metadata = _json_loads(row.get("metadata_json"), {})
            observation = latest_observation_by_fund.get(key)
            flow = latest_flow_by_fund.get(key)
            name = str(row.get("name") or key[1] or "").strip()
            aum_usd = _coalesce(
                _finite_float(observation.get("total_net_assets")) if observation else None,
                _meta_float(metadata, "catalog_total_net_assets_usd"),
            )
            expense_ratio = _meta_float(metadata, "catalog_net_expense_ratio", "catalog_gross_expense_ratio")
            segment = _classify_segment(name, metadata)
            country_focus = _classify_country_focus(name, metadata)
            development = _classify_development(name, metadata)
            type_label = _classify_type(name, metadata, segment, country_focus)
            funds.append({
                "provider": key[0],
                "issuer": _provider_label(key[0]),
                "ticker": key[1],
                "name": name,
                "url": row.get("url"),
                "aum_usd": aum_usd,
                "expense_ratio": expense_ratio,
                "observation_date": observation.get("as_of_date") if observation else None,
                "captured_at": observation.get("captured_at") if observation else None,
                "flow_as_of_date": flow.get("as_of_date") if flow else None,
                "flow_usd": _finite_float(flow.get("flow_usd")) if flow else None,
                "share_delta": _finite_float(flow.get("share_delta")) if flow else None,
                "confidence": _coalesce(_finite_float(flow.get("confidence")) if flow else None, _finite_float(observation.get("confidence")) if observation else None),
                "segment": segment,
                "country_focus": country_focus,
                "development": development,
                "type_label": type_label,
                "aum_bucket": _classify_aum_bucket(aum_usd),
                "nav_only": bool(observation and observation.get("nav") is not None and observation.get("shares_outstanding") is None),
                "flow_ready": bool(observation and observation.get("nav") is not None and observation.get("shares_outstanding") is not None),
                "has_flow": bool(flow),
            })

        def aggregate(rows: list[dict[str, Any]], field: str, include_diversified: bool = True) -> list[dict[str, Any]]:
            grouped: dict[str, dict[str, Any]] = {}
            for item in rows:
                key = str(item.get(field) or "Sem classificacao")
                if not include_diversified and key in {"Diversificado", "Outros", "Global", "International"}:
                    continue
                bucket = grouped.setdefault(key, {
                    "key": key,
                    "label": key,
                    "funds": 0,
                    "flow_funds": 0,
                    "nav_only_funds": 0,
                    "net_flow_usd": 0.0,
                    "inflow_usd": 0.0,
                    "outflow_usd": 0.0,
                    "total_aum_usd": 0.0,
                    "expense_ratio_sum": 0.0,
                    "expense_ratio_count": 0,
                })
                bucket["funds"] += 1
                if item.get("has_flow"):
                    bucket["flow_funds"] += 1
                    flow_usd = float(item.get("flow_usd") or 0.0)
                    bucket["net_flow_usd"] += flow_usd
                    if flow_usd >= 0:
                        bucket["inflow_usd"] += flow_usd
                    else:
                        bucket["outflow_usd"] += flow_usd
                if item.get("nav_only"):
                    bucket["nav_only_funds"] += 1
                if item.get("aum_usd") is not None:
                    bucket["total_aum_usd"] += float(item["aum_usd"])
                if item.get("expense_ratio") is not None:
                    bucket["expense_ratio_sum"] += float(item["expense_ratio"])
                    bucket["expense_ratio_count"] += 1
            rows_out = []
            for bucket in grouped.values():
                bucket["avg_expense_ratio"] = (
                    bucket["expense_ratio_sum"] / bucket["expense_ratio_count"]
                    if bucket["expense_ratio_count"]
                    else None
                )
                bucket.pop("expense_ratio_sum", None)
                bucket.pop("expense_ratio_count", None)
                rows_out.append(bucket)
            rows_out.sort(key=lambda item: (abs(float(item.get("net_flow_usd") or 0.0)), float(item.get("total_aum_usd") or 0.0)), reverse=True)
            return rows_out

        funds_with_flow = [item for item in funds if item.get("has_flow")]
        funds_with_observation = [item for item in funds if item.get("captured_at")]
        flow_ready_funds = [item for item in funds if item.get("flow_ready")]
        nav_only_funds = [item for item in funds if item.get("nav_only")]
        inflow_total = sum(float(item.get("flow_usd") or 0.0) for item in funds_with_flow if float(item.get("flow_usd") or 0.0) > 0)
        outflow_total = sum(float(item.get("flow_usd") or 0.0) for item in funds_with_flow if float(item.get("flow_usd") or 0.0) < 0)
        total_aum = sum(float(item.get("aum_usd") or 0.0) for item in funds if item.get("aum_usd") is not None)
        latest_capture_at = max((str(item.get("captured_at")) for item in funds_with_observation if item.get("captured_at")), default=None)
        latest_flow_date = max((str(item.get("flow_as_of_date")) for item in funds_with_flow if item.get("flow_as_of_date")), default=None)

        by_issuer = aggregate(funds, "issuer")
        by_country = aggregate(funds_with_flow, "country_focus", include_diversified=False)
        by_development = aggregate(funds, "development")
        by_segment = aggregate(funds, "segment")
        by_type = aggregate(funds, "type_label")
        by_aum_bucket = aggregate(funds, "aum_bucket")

        top_inflows = sorted(
            [item for item in funds_with_flow if float(item.get("flow_usd") or 0.0) > 0],
            key=lambda item: float(item.get("flow_usd") or 0.0),
            reverse=True,
        )[:top_n]
        top_outflows = sorted(
            [item for item in funds_with_flow if float(item.get("flow_usd") or 0.0) < 0],
            key=lambda item: float(item.get("flow_usd") or 0.0),
        )[:top_n]

        heatmap_x = [row["label"] for row in sorted(by_segment, key=lambda item: float(item.get("total_aum_usd") or 0.0), reverse=True)[:8]]
        heatmap_y = [row["label"] for row in sorted(by_issuer, key=lambda item: float(item.get("total_aum_usd") or 0.0), reverse=True)]
        heatmap_matrix: list[list[float]] = []
        heatmap_cells: list[dict[str, Any]] = []
        for issuer in heatmap_y:
            row_values: list[float] = []
            for segment in heatmap_x:
                value = sum(
                    float(item.get("flow_usd") or 0.0)
                    for item in funds_with_flow
                    if item.get("issuer") == issuer and item.get("segment") == segment
                )
                row_values.append(value)
                heatmap_cells.append({
                    "issuer": issuer,
                    "segment": segment,
                    "value": value,
                })
            heatmap_matrix.append(row_values)

        flow_dates = sorted({str(row.get("as_of_date")) for row in flow_rows if row.get("as_of_date")})[-10:]
        trend_series = []
        for issuer in heatmap_y:
            points = []
            for flow_date in flow_dates:
                value = sum(
                    float(row.get("flow_usd") or 0.0)
                    for row in flow_rows
                    if _provider_label(str(row.get("provider") or "")) == issuer and str(row.get("as_of_date") or "") == flow_date
                )
                points.append({"date": flow_date, "value": value})
            trend_series.append({"issuer": issuer, "points": points})

        cards = [
            {"key": "active", "label": "Universo ativo", "value": len(funds), "detail": f"{len(funds_with_observation)} capturados"},
            {"key": "flow_ready", "label": "Flow-ready", "value": len(flow_ready_funds), "detail": f"{len(nav_only_funds)} nav-only"},
            {"key": "computed", "label": "Flows calculados", "value": len(funds_with_flow), "detail": latest_flow_date or "sem data"},
            {"key": "net", "label": "Net flow", "value": inflow_total + outflow_total, "detail": "latest por ETF"},
            {"key": "inflow", "label": "Entradas", "value": inflow_total, "detail": "soma positiva"},
            {"key": "outflow", "label": "Saidas", "value": outflow_total, "detail": "soma negativa"},
            {"key": "aum", "label": "AUM coberto", "value": total_aum, "detail": "US$ agregado"},
        ]

        return {
            "ok": True,
            "latest_capture_at": latest_capture_at,
            "latest_flow_date": latest_flow_date,
            "last_run": dict(last_run) if last_run else None,
            "cards": cards,
            "summary": {
                "active_funds": len(funds),
                "captured_funds": len(funds_with_observation),
                "flow_ready_funds": len(flow_ready_funds),
                "nav_only_funds": len(nav_only_funds),
                "flow_funds": len(funds_with_flow),
                "net_flow_usd": inflow_total + outflow_total,
                "inflow_usd": inflow_total,
                "outflow_usd": outflow_total,
                "total_aum_usd": total_aum,
            },
            "tables": {
                "by_issuer": by_issuer,
                "by_country": by_country[:top_n],
                "by_development": by_development,
                "by_segment": by_segment,
                "by_type": by_type,
                "by_aum_bucket": by_aum_bucket,
            },
            "top_inflows": top_inflows,
            "top_outflows": top_outflows,
            "heatmap": {
                "x": heatmap_x,
                "y": heatmap_y,
                "z": heatmap_matrix,
                "cells": heatmap_cells,
            },
            "trend": {
                "dates": flow_dates,
                "series": trend_series,
            },
        }

    def due_slot(self, now: datetime | None = None) -> str | None:
        now_local = (now or datetime.now(self.tz)).astimezone(self.tz)
        capture_times = self._capture_times()
        if not capture_times:
            return None
        candidates: list[datetime] = []
        for day_offset in (0, -1):
            base_date = now_local.date() + timedelta(days=day_offset)
            for capture_time in capture_times:
                candidates.append(datetime.combine(base_date, capture_time, tzinfo=self.tz))
        due = [candidate for candidate in candidates if candidate <= now_local]
        if not due:
            return None
        latest_due = max(due)
        slot = latest_due.strftime("%Y-%m-%dT%H:%M%z")
        with self._connect() as conn:
            last_slot = self._get_state(conn, "last_scheduler_slot")
        return None if last_slot == slot else slot

    def mark_slot_started(self, slot: str) -> None:
        with self._connect() as conn:
            self._set_state(conn, "last_scheduler_slot", slot)

    def next_run_at(self, now: datetime | None = None) -> str | None:
        now_local = (now or datetime.now(self.tz)).astimezone(self.tz)
        capture_times = self._capture_times()
        if not capture_times:
            return None
        candidates: list[datetime] = []
        for day_offset in (0, 1):
            base_date = now_local.date() + timedelta(days=day_offset)
            for capture_time in capture_times:
                candidate = datetime.combine(base_date, capture_time, tzinfo=self.tz)
                if candidate > now_local:
                    candidates.append(candidate)
        if not candidates:
            return None
        return min(candidates).isoformat()

    def _capture_times(self) -> list[dt_time]:
        output: list[dt_time] = []
        for item in str(Config.ETF_DAILY_FLOW_CAPTURE_TIMES or "").split(","):
            text = item.strip()
            if not text:
                continue
            try:
                hour, minute = text.split(":", 1)
                output.append(dt_time(hour=int(hour), minute=int(minute[:2])))
            except Exception:
                continue
        return sorted(output)


class EtfDailyFlowManager:
    def __init__(self, service: EtfDailyFlowService):
        self.service = service
        self.poll_interval_seconds = float(Config.ETF_DAILY_FLOW_SCHEDULER_POLL_SECONDS)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = threading.Event()
        self._last_error: str | None = None
        self._last_tick_at: str | None = None

    def start(self) -> dict[str, Any]:
        if self._thread and self._thread.is_alive():
            return {"ok": True, "running": True, "message": "already_running"}
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="etf-daily-flow-manager", daemon=True)
        self._thread.start()
        return {"ok": True, "running": True}

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        return {"ok": True, "running": self.running}

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "busy": self._running.is_set(),
            "poll_interval_seconds": self.poll_interval_seconds,
            "next_run_at": self.service.next_run_at(),
            "last_tick_at": self._last_tick_at,
            "last_error": self._last_error,
        }

    def _loop(self) -> None:
        logger.info("ETF daily flow scheduler started")
        while not self._stop.is_set():
            self._last_tick_at = _utc_now_iso()
            try:
                slot = self.service.due_slot()
                if slot and not self._running.is_set():
                    self._running.set()
                    self.service.mark_slot_started(slot)
                    try:
                        logger.info("ETF daily flow scheduled collection due: slot=%s", slot)
                        self.service.collect()
                    finally:
                        self._running.clear()
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("ETF daily flow scheduler failed")
            self._stop.wait(self.poll_interval_seconds)
        logger.info("ETF daily flow scheduler stopped")
