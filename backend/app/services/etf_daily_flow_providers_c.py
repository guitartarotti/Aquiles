"""Invesco, ProShares and Global X ETF adapters."""

from __future__ import annotations

import csv
import html
import io
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..config import Config
from ..utils.logger import get_logger
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
)

logger = get_logger("aquiles.etf_daily_flow.providers")

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
