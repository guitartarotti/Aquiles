"""Schwab, State Street, VanEck and iShares ETF adapters."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, NavigableString

from ..config import Config
from .etf_daily_flow_provider_base import GenericHtmlEtfProvider
from .etf_daily_flow_types import (
    EtfObservation,
    EtfScrapeError,
    _compact_text,
    _extract_first_regex,
    _finite_float,
    _parse_date,
    _safe_ticker,
    _sha256,
    _slugify,
    _text_by_data_id,
)


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
