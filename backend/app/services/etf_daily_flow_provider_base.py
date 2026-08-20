"""Base HTTP and parsing adapter for ETF providers."""

from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .etf_daily_flow_types import (
    EtfObservation,
    EtfScrapeError,
    _anchor_snippet,
    _compact_text,
    _extract_first_regex,
    _finite_float,
    _json_dumps,
    _parse_date,
    _safe_provider,
    _safe_ticker,
    _sha256,
    _utc_now_iso,
    _walk_json,
)


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
