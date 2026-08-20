"""Dimensional and Vanguard ETF adapters."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from ..config import Config
from .etf_daily_flow_provider_base import GenericHtmlEtfProvider
from .etf_daily_flow_types import (
    EtfObservation,
    EtfScrapeError,
    _finite_float,
    _parse_date,
    _safe_ticker,
    _sha256,
    _slugify,
)


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
