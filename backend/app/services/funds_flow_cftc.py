from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from typing import Any

import numpy as np
import requests

from ..domains.funds_flow.contracts.source_catalog import (
    CFTC_COT_EXTRA_DATASETS,
    CFTC_EXTRA_HISTORY_WEEKS,
    CFTC_EXTRA_PARTICIPANTS,
    CFTC_FOCUS_MARKET_TOKENS,
    CFTC_PRE_STORY_URL,
    CFTC_PRIMARY_PARTICIPANT_BY_FAMILY,
    CFTC_TFF_FIELDS,
    CFTC_TFF_PARTICIPANTS,
    CFTC_TFF_RESOURCE_URLS,
)
from ..utils.logger import get_logger
from .funds_flow_utils import (
    _normalize_text,
    _parse_date,
    _safe_float,
)

logger = get_logger("aquiles.funds_flow.cftc")


class FundsFlowCftcMixin:
    def _load_cftc_tff_positioning(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "cftc_cot",
            "source": "CFTC COT/PRE",
            "url": CFTC_PRE_STORY_URL,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        errors: list[str] = []
        records: list[dict[str, Any]] = []
        cached_paths: list[str] = []
        latest_report_date: date | None = None
        try:
            latest_report_date = self._cftc_latest_report_date(CFTC_TFF_RESOURCE_URLS["combined"])
        except Exception as exc:
            errors.append(f"latest_date: {exc}")
            logger.warning("Failed to discover CFTC latest report date: %s", exc)

        if latest_report_date:
            start_date = latest_report_date - timedelta(weeks=156)
            for variant, url in CFTC_TFF_RESOURCE_URLS.items():
                try:
                    raw_rows, cache_path = self._load_cftc_tff_variant(
                        url,
                        variant=variant,
                        latest_report_date=latest_report_date,
                        start_date=start_date,
                        force=force,
                    )
                    cached_paths.append(cache_path)
                    records.extend(self._normalize_cftc_tff_rows(raw_rows, variant=variant))
                except Exception as exc:
                    errors.append(f"{variant}: {exc}")
                    logger.warning("Failed to load CFTC %s: %s", variant, exc)

        payload = self._build_cftc_tff_payload(records, errors=errors, latest_report_date=latest_report_date)
        extra_payload, extra_status = self._load_cftc_extra_positioning(force=force)
        for list_key in [
            "datasets",
            "family_summaries",
            "extended_participant_summary",
            "extended_asset_bucket_summary",
            "extended_contracts",
            "position_matrix",
        ]:
            payload[list_key] = [*(payload.get(list_key) or []), *(extra_payload.get(list_key) or [])]
        payload["pre_api"] = extra_payload.get("pre_api") or payload.get("pre_api")
        payload["extra_coverage_notes"] = extra_payload.get("coverage_notes") or []
        row_count = len(records)
        total_row_count = row_count + int(extra_status.get("rows") or 0)
        cached_paths.extend(extra_status.get("cached_paths") or [])
        if extra_status.get("error"):
            errors.append(str(extra_status["error"]))
        status.update(
            {
                "ok": total_row_count > 0,
                "rows": total_row_count,
                "tff_rows": row_count,
                "extra_rows": int(extra_status.get("rows") or 0),
                "error": "; ".join(errors) if errors else None,
                "cached_path": cached_paths[0] if cached_paths else None,
                "cached_paths": cached_paths,
                "report_date": payload.get("report_date"),
                "publication_date": payload.get("publication_date"),
                "latest_data_date": payload.get("report_date"),
            }
        )
        status["latency_ms"] = int((time.monotonic() - started) * 1000)
        return payload, status

    def _cftc_latest_report_date(self, url: str) -> date:
        response = requests.get(
            url,
            params={"$select": "max(report_date_as_yyyy_mm_dd)"},
            timeout=max(self.timeout_seconds, 45),
        )
        response.raise_for_status()
        rows = response.json()
        value = (rows[0] or {}).get("max_report_date_as_yyyy_mm_dd") if rows else None
        parsed = _parse_date(value)
        if not parsed:
            raise RuntimeError("CFTC latest report date not found")
        return parsed

    def _load_cftc_tff_variant(
        self,
        url: str,
        *,
        variant: str,
        latest_report_date: date,
        start_date: date,
        force: bool,
    ) -> tuple[list[dict[str, Any]], str]:
        cache_path = os.path.join(
            self.raw_dir,
            "cftc",
            "tff",
            f"{variant}_{latest_report_date.strftime('%Y%m%d')}.json",
        )
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0 and not force:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return json.load(handle), cache_path
        params = {
            "$select": ",".join(CFTC_TFF_FIELDS),
            "$where": (
                f"report_date_as_yyyy_mm_dd >= '{start_date.isoformat()}T00:00:00' "
                "AND commodity_group_name='FINANCIAL INSTRUMENTS'"
            ),
            "$limit": "50000",
            "$order": "report_date_as_yyyy_mm_dd ASC, market_and_exchange_names ASC",
        }
        response = requests.get(url, params=params, timeout=max(self.timeout_seconds, 90))
        response.raise_for_status()
        rows = response.json()
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        temp_path = f"{cache_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False)
        os.replace(temp_path, cache_path)
        return rows, cache_path

    def _load_cftc_extra_positioning(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        errors: list[str] = []
        records: list[dict[str, Any]] = []
        datasets: list[dict[str, Any]] = []
        cached_paths: list[str] = []
        for dataset_key, config in CFTC_COT_EXTRA_DATASETS.items():
            try:
                latest_report_date = self._cftc_latest_report_date(str(config["url"]))
                start_date = latest_report_date - timedelta(weeks=CFTC_EXTRA_HISTORY_WEEKS)
                raw_rows, cache_path = self._load_cftc_extra_dataset(
                    dataset_key=dataset_key,
                    config=config,
                    latest_report_date=latest_report_date,
                    start_date=start_date,
                    force=force,
                )
                cached_paths.append(cache_path)
                normalized = self._normalize_cftc_extra_rows(raw_rows, dataset_key=dataset_key, config=config)
                records.extend(normalized)
                field_count = len(raw_rows[0].keys()) if raw_rows else 0
                datasets.append(
                    {
                        "key": dataset_key,
                        "family": config.get("family"),
                        "family_label": config.get("family_label"),
                        "variant": config.get("variant"),
                        "variant_label": config.get("variant_label"),
                        "url": config.get("url"),
                        "role": config.get("role"),
                        "status": "ok" if raw_rows else "empty",
                        "rows": len(raw_rows),
                        "fields": field_count,
                        "latest_report_date": latest_report_date.isoformat(),
                        "cached_path": cache_path,
                    }
                )
            except Exception as exc:
                errors.append(f"{dataset_key}: {exc}")
                datasets.append(
                    {
                        "key": dataset_key,
                        "family": config.get("family"),
                        "family_label": config.get("family_label"),
                        "variant": config.get("variant"),
                        "variant_label": config.get("variant_label"),
                        "url": config.get("url"),
                        "role": config.get("role"),
                        "status": "error",
                        "rows": 0,
                        "fields": 0,
                        "error": str(exc),
                    }
                )
                logger.warning("Failed to load CFTC extra dataset %s: %s", dataset_key, exc)
        payload = self._build_cftc_extra_payload(records, datasets=datasets, errors=errors)
        status = {
            "ok": bool(records),
            "rows": len(records),
            "error": "; ".join(errors) if errors else None,
            "cached_paths": cached_paths,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
        return payload, status

    def _load_cftc_extra_dataset(
        self,
        *,
        dataset_key: str,
        config: dict[str, Any],
        latest_report_date: date,
        start_date: date,
        force: bool,
    ) -> tuple[list[dict[str, Any]], str]:
        cache_path = os.path.join(
            self.raw_dir,
            "cftc",
            str(config.get("family") or "cot"),
            f"{dataset_key}_{latest_report_date.strftime('%Y%m%d')}.json",
        )
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0 and not force:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return json.load(handle), cache_path

        rows: list[dict[str, Any]] = []
        limit = 50000
        offset = 0
        while True:
            params = {
                "$where": f"report_date_as_yyyy_mm_dd >= '{start_date.isoformat()}T00:00:00'",
                "$limit": str(limit),
                "$offset": str(offset),
                "$order": "report_date_as_yyyy_mm_dd ASC, market_and_exchange_names ASC",
            }
            response = requests.get(str(config["url"]), params=params, timeout=max(self.timeout_seconds, 90))
            response.raise_for_status()
            chunk = response.json()
            if not isinstance(chunk, list):
                raise RuntimeError(f"Unexpected CFTC response for {dataset_key}")
            rows.extend(chunk)
            if len(chunk) < limit:
                break
            offset += limit
            if offset >= 250000:
                logger.warning("Stopping CFTC pagination for %s at %s rows", dataset_key, offset)
                break

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        temp_path = f"{cache_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False)
        os.replace(temp_path, cache_path)
        return rows, cache_path

    @staticmethod
    def _cftc_row_get(row: dict[str, Any], key: str | None) -> Any:
        if not key:
            return None
        if key in row:
            return row.get(key)
        lowered = key.lower()
        for existing_key, value in row.items():
            if str(existing_key).lower() == lowered:
                return value
        return None

    def _normalize_cftc_extra_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        dataset_key: str,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        family = str(config.get("family") or "")
        participants = CFTC_EXTRA_PARTICIPANTS.get(family, ())
        normalized: list[dict[str, Any]] = []
        for row in rows:
            report_date = _parse_date(row.get("report_date_as_yyyy_mm_dd"))
            if not report_date:
                continue
            market_name = str(row.get("contract_market_name") or row.get("market_and_exchange_names") or "").strip()
            item: dict[str, Any] = {
                "date": report_date.isoformat(),
                "report_date": report_date.isoformat(),
                "report_week": row.get("yyyy_report_week_ww"),
                "position_weekday": "Tuesday",
                "publication_weekday": "Friday",
                "dataset_key": dataset_key,
                "family": family,
                "family_label": config.get("family_label"),
                "variant": config.get("variant"),
                "variant_label": config.get("variant_label"),
                "futonly_or_combined": row.get("futonly_or_combined") or config.get("variant_label"),
                "market_name": market_name,
                "market_and_exchange_names": row.get("market_and_exchange_names"),
                "contract_code": row.get("cftc_contract_market_code"),
                "market_code": str(row.get("cftc_market_code") or "").strip(),
                "commodity_code": str(row.get("cftc_commodity_code") or "").strip(),
                "commodity_name": row.get("commodity_name") or row.get("commodity"),
                "commodity_group": row.get("commodity_group_name"),
                "commodity_subgroup": row.get("commodity_subgroup_name"),
                "asset_bucket": self._cftc_asset_bucket(row),
                "contract_units": row.get("contract_units"),
                "open_interest": _safe_float(row.get("open_interest_all"), 2),
                "open_interest_change": _safe_float(
                    row.get("change_in_open_interest_all") or row.get("change_open_interest_all"),
                    2,
                ),
                "total_reportable_long": _safe_float(row.get("tot_rept_positions_long_all"), 2),
                "total_reportable_short": _safe_float(row.get("tot_rept_positions_short"), 2),
                "concentration_gross_4_long": _safe_float(row.get("conc_gross_le_4_tdr_long"), 2),
                "concentration_gross_4_short": _safe_float(row.get("conc_gross_le_4_tdr_short"), 2),
                "concentration_gross_8_long": _safe_float(row.get("conc_gross_le_8_tdr_long"), 2),
                "concentration_gross_8_short": _safe_float(row.get("conc_gross_le_8_tdr_short"), 2),
                "concentration_net_4_long": _safe_float(row.get("conc_net_le_4_tdr_long_all"), 2),
                "concentration_net_4_short": _safe_float(row.get("conc_net_le_4_tdr_short_all"), 2),
                "concentration_net_8_long": _safe_float(row.get("conc_net_le_8_tdr_long_all"), 2),
                "concentration_net_8_short": _safe_float(row.get("conc_net_le_8_tdr_short_all"), 2),
                "source": f"CFTC {config.get('family_label')}",
            }
            total_long = item.get("total_reportable_long")
            total_short = item.get("total_reportable_short")
            item["total_reportable_net"] = (
                round(float(total_long or 0) - float(total_short or 0), 2)
                if total_long is not None or total_short is not None
                else None
            )
            for (
                key,
                _label,
                long_col,
                short_col,
                spread_col,
                change_long_col,
                change_short_col,
                pct_long_col,
                pct_short_col,
                traders_long_col,
                traders_short_col,
            ) in participants:
                long_value = _safe_float(self._cftc_row_get(row, long_col), 2)
                short_value = _safe_float(self._cftc_row_get(row, short_col), 2)
                spread_value = _safe_float(self._cftc_row_get(row, spread_col), 2) if spread_col else None
                change_long = _safe_float(self._cftc_row_get(row, change_long_col), 2)
                change_short = _safe_float(self._cftc_row_get(row, change_short_col), 2)
                pct_long = _safe_float(self._cftc_row_get(row, pct_long_col), 4)
                pct_short = _safe_float(self._cftc_row_get(row, pct_short_col), 4)
                item[f"{key}_long"] = long_value
                item[f"{key}_short"] = short_value
                item[f"{key}_spread"] = spread_value
                item[f"{key}_net"] = (
                    round(float(long_value or 0) - float(short_value or 0), 2)
                    if long_value is not None or short_value is not None
                    else None
                )
                item[f"{key}_change_long"] = change_long
                item[f"{key}_change_short"] = change_short
                item[f"{key}_change_net"] = (
                    round(float(change_long or 0) - float(change_short or 0), 2)
                    if change_long is not None or change_short is not None
                    else None
                )
                item[f"{key}_pct_oi_long"] = pct_long
                item[f"{key}_pct_oi_short"] = pct_short
                item[f"{key}_pct_oi_net"] = (
                    round(float(pct_long or 0) - float(pct_short or 0), 4)
                    if pct_long is not None or pct_short is not None
                    else None
                )
                item[f"{key}_traders_long"] = _safe_float(self._cftc_row_get(row, traders_long_col), 0) if traders_long_col else None
                item[f"{key}_traders_short"] = _safe_float(self._cftc_row_get(row, traders_short_col), 0) if traders_short_col else None
            normalized.append(item)
        return normalized

    def _normalize_cftc_tff_rows(self, rows: list[dict[str, Any]], *, variant: str) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            report_date = _parse_date(row.get("report_date_as_yyyy_mm_dd"))
            if not report_date:
                continue
            market_name = str(row.get("contract_market_name") or row.get("market_and_exchange_names") or "").strip()
            item: dict[str, Any] = {
                "date": report_date.isoformat(),
                "report_date": report_date.isoformat(),
                "report_week": row.get("yyyy_report_week_ww"),
                "position_weekday": "Tuesday",
                "publication_weekday": "Friday",
                "variant": variant,
                "variant_label": "Combined futures+options" if variant == "combined" else "Futures only",
                "futonly_or_combined": row.get("futonly_or_combined"),
                "market_name": market_name,
                "market_and_exchange_names": row.get("market_and_exchange_names"),
                "contract_code": row.get("cftc_contract_market_code"),
                "market_code": str(row.get("cftc_market_code") or "").strip(),
                "commodity_code": str(row.get("cftc_commodity_code") or "").strip(),
                "commodity_name": row.get("commodity_name"),
                "commodity_group": row.get("commodity_group_name"),
                "commodity_subgroup": row.get("commodity_subgroup_name"),
                "asset_bucket": self._cftc_asset_bucket(row),
                "contract_units": row.get("contract_units"),
                "open_interest": _safe_float(row.get("open_interest_all"), 2),
                "open_interest_change": _safe_float(row.get("change_in_open_interest_all"), 2),
                "total_reportable_long": _safe_float(row.get("tot_rept_positions_long_all"), 2),
                "total_reportable_short": _safe_float(row.get("tot_rept_positions_short"), 2),
                "concentration_gross_4_long": _safe_float(row.get("conc_gross_le_4_tdr_long"), 2),
                "concentration_gross_4_short": _safe_float(row.get("conc_gross_le_4_tdr_short"), 2),
                "concentration_gross_8_long": _safe_float(row.get("conc_gross_le_8_tdr_long"), 2),
                "concentration_gross_8_short": _safe_float(row.get("conc_gross_le_8_tdr_short"), 2),
                "concentration_net_4_long": _safe_float(row.get("conc_net_le_4_tdr_long_all"), 2),
                "concentration_net_4_short": _safe_float(row.get("conc_net_le_4_tdr_short_all"), 2),
                "concentration_net_8_long": _safe_float(row.get("conc_net_le_8_tdr_long_all"), 2),
                "concentration_net_8_short": _safe_float(row.get("conc_net_le_8_tdr_short_all"), 2),
                "source": "CFTC Traders in Financial Futures",
            }
            total_long = item.get("total_reportable_long")
            total_short = item.get("total_reportable_short")
            item["total_reportable_net"] = (
                round(float(total_long or 0) - float(total_short or 0), 2)
                if total_long is not None or total_short is not None
                else None
            )
            for (
                key,
                _label,
                long_col,
                short_col,
                spread_col,
                change_long_col,
                change_short_col,
                pct_long_col,
                pct_short_col,
                traders_long_col,
                traders_short_col,
            ) in CFTC_TFF_PARTICIPANTS:
                long_value = _safe_float(row.get(long_col), 2)
                short_value = _safe_float(row.get(short_col), 2)
                spread_value = _safe_float(row.get(spread_col), 2) if spread_col else None
                change_long = _safe_float(row.get(change_long_col), 2)
                change_short = _safe_float(row.get(change_short_col), 2)
                pct_long = _safe_float(row.get(pct_long_col), 4)
                pct_short = _safe_float(row.get(pct_short_col), 4)
                item[f"{key}_long"] = long_value
                item[f"{key}_short"] = short_value
                item[f"{key}_spread"] = spread_value
                item[f"{key}_net"] = (
                    round(float(long_value or 0) - float(short_value or 0), 2)
                    if long_value is not None or short_value is not None
                    else None
                )
                item[f"{key}_change_long"] = change_long
                item[f"{key}_change_short"] = change_short
                item[f"{key}_change_net"] = (
                    round(float(change_long or 0) - float(change_short or 0), 2)
                    if change_long is not None or change_short is not None
                    else None
                )
                item[f"{key}_pct_oi_long"] = pct_long
                item[f"{key}_pct_oi_short"] = pct_short
                item[f"{key}_pct_oi_net"] = (
                    round(float(pct_long or 0) - float(pct_short or 0), 4)
                    if pct_long is not None or pct_short is not None
                    else None
                )
                item[f"{key}_traders_long"] = _safe_float(row.get(traders_long_col), 0) if traders_long_col else None
                item[f"{key}_traders_short"] = _safe_float(row.get(traders_short_col), 0) if traders_short_col else None
            normalized.append(item)
        return normalized

    @staticmethod
    def _cftc_asset_bucket(row: dict[str, Any]) -> str:
        text = _normalize_text(
            " ".join(
                str(row.get(key) or "")
                for key in ["commodity_group_name", "commodity_subgroup_name", "commodity_name", "commodity", "contract_market_name", "market_and_exchange_names"]
            )
        )
        if any(token in text for token in ["AGRICULTURE", "GRAIN", "OILSEED", "WHEAT", "CORN", "SOYBEAN", "COTTON", "COFFEE", "SUGAR", "COCOA"]):
            return "Agriculture"
        if any(token in text for token in ["ENERGY", "CRUDE", "OIL", "GASOLINE", "HEATING OIL", "NATURAL GAS", "PETROLEUM"]):
            return "Energy"
        if any(token in text for token in ["METAL", "GOLD", "SILVER", "COPPER", "PLATINUM", "PALLADIUM"]):
            return "Metals"
        if any(token in text for token in ["LIVESTOCK", "CATTLE", "HOGS"]):
            return "Livestock"
        if "BITCOIN" in text or "ETHER" in text:
            return "Crypto"
        if "VIX" in text or "VOLATILITY" in text:
            return "Volatility"
        if any(token in text for token in ["CURRENCY", "EURO FX", "YEN", "POUND", "DOLLAR", "PESO", "REAL", "FRANC"]):
            return "FX"
        if any(token in text for token in ["TREASURY", "SOFR", "FED FUNDS", "EURODOLLAR", "BOND", "NOTE"]):
            return "Rates"
        if any(token in text for token in ["STOCK INDICES", "S&P", "NASDAQ", "DOW", "RUSSELL", "DIVIDEND INDICES"]):
            return "Equity Index"
        return "Financial Futures"

    def _build_cftc_tff_payload(
        self,
        records: list[dict[str, Any]],
        *,
        errors: list[str],
        latest_report_date: date | None,
    ) -> dict[str, Any]:
        if not records:
            return {
                "status": "error" if errors else "empty",
                "source": "CFTC Traders in Financial Futures",
                "source_url": "https://publicreporting.cftc.gov/",
                "pre_api": {"story_url": CFTC_PRE_STORY_URL, "mode": "PRE/API", "token_required": False},
                "frequency": "weekly",
                "position_weekday": "Tuesday",
                "publication_weekday": "Friday",
                "errors": errors,
                "rows": [],
                "latest_contracts": [],
                "weekly_series": [],
                "participant_summary": [],
                "asset_bucket_summary": [],
                "datasets": [],
                "family_summaries": [],
                "extended_participant_summary": [],
                "extended_asset_bucket_summary": [],
                "extended_contracts": [],
                "position_matrix": [],
            }

        latest_date = max(_parse_date(row.get("date")) for row in records if _parse_date(row.get("date")))
        latest_date = latest_date or latest_report_date
        publication_date = latest_date + timedelta(days=3) if latest_date else None
        combined_rows = [row for row in records if row.get("variant") == "combined"] or records
        latest_rows = [row for row in combined_rows if row.get("date") == latest_date.isoformat()] if latest_date else []
        latest_rows = sorted(latest_rows, key=lambda row: float(row.get("open_interest") or 0), reverse=True)
        focus_rows = [
            row
            for row in latest_rows
            if any(token in _normalize_text(row.get("market_name")) for token in CFTC_FOCUS_MARKET_TOKENS)
        ]
        latest_contracts = [self._compact_cftc_contract_row(row, records=combined_rows) for row in latest_rows[:80]]
        focus_contracts = [self._compact_cftc_contract_row(row, records=combined_rows) for row in (focus_rows[:50] or latest_rows[:30])]
        focus_codes = {str(row.get("contract_code")) for row in focus_contracts if row.get("contract_code")}
        weekly_series = [
            self._compact_cftc_series_row(row)
            for row in combined_rows
            if str(row.get("contract_code")) in focus_codes
        ]
        weekly_series = sorted(weekly_series, key=lambda row: (row.get("date") or "", row.get("market_name") or ""))[-4500:]
        tff_datasets = self._cftc_tff_dataset_summaries(records)
        tff_family = self._cftc_family_summary_from_rows(
            combined_rows,
            family="tff",
            family_label="TFF - Financial Futures",
            dataset_count=len(tff_datasets),
        )
        tff_extended_contracts = [
            self._compact_cftc_extended_contract_row(row, primary_key="lev_money")
            for row in latest_rows[:80]
        ]

        return {
            "status": "ok",
            "source": "CFTC Traders in Financial Futures",
            "source_url": "https://publicreporting.cftc.gov/",
            "pre_api": {"story_url": CFTC_PRE_STORY_URL, "mode": "PRE/API", "token_required": False},
            "frequency": "weekly",
            "position_weekday": "Tuesday",
            "publication_weekday": "Friday",
            "report_date": latest_date.isoformat() if latest_date else None,
            "publication_date": publication_date.isoformat() if publication_date else None,
            "report_date_label": "Tuesday close/open interest snapshot",
            "publication_date_label": "Usually released Friday",
            "variants": [
                {"key": "combined", "label": "Combined futures+options"},
                {"key": "futures_only", "label": "Futures only"},
            ],
            "row_count": len(records),
            "latest_contracts": latest_contracts,
            "focus_contracts": focus_contracts,
            "weekly_series": weekly_series,
            "participant_summary": self._cftc_participant_summary(latest_rows),
            "asset_bucket_summary": self._cftc_asset_bucket_summary(latest_rows),
            "datasets": tff_datasets,
            "family_summaries": [tff_family] if tff_family else [],
            "extended_participant_summary": self._cftc_generic_participant_summary(
                latest_rows,
                family="tff",
                family_label="TFF - Financial Futures",
                participants=CFTC_TFF_PARTICIPANTS,
            ),
            "extended_asset_bucket_summary": self._cftc_generic_bucket_summary(
                latest_rows,
                family="tff",
                family_label="TFF - Financial Futures",
                primary_key="lev_money",
            ),
            "extended_contracts": tff_extended_contracts,
            "position_matrix": self._cftc_position_matrix(
                latest_rows,
                family="tff",
                family_label="TFF - Financial Futures",
                participants=CFTC_TFF_PARTICIPANTS,
            ),
            "coverage_notes": [
                "CFTC TFF/COT is weekly: positions are reported as of Tuesday.",
                "Public release is normally Friday; daily participant-level variation is not available in this public file.",
                "Values are contracts, not fund flow; use as global positioning proxy.",
            ],
            "errors": errors,
        }

    def _build_cftc_extra_payload(
        self,
        records: list[dict[str, Any]],
        *,
        datasets: list[dict[str, Any]],
        errors: list[str],
    ) -> dict[str, Any]:
        if not records:
            return {
                "pre_api": {"story_url": CFTC_PRE_STORY_URL, "mode": "PRE/API", "token_required": False},
                "datasets": datasets,
                "family_summaries": [],
                "extended_participant_summary": [],
                "extended_asset_bucket_summary": [],
                "extended_contracts": [],
                "position_matrix": [],
                "coverage_notes": [
                    "Disaggregated, Legacy and CIT are weekly COT datasets from CFTC PRE.",
                    "These datasets are positioning proxies in contracts, not fund-flow records.",
                ],
                "errors": errors,
            }

        latest_by_dataset: dict[str, str] = {}
        for row in records:
            dataset_key = str(row.get("dataset_key") or "")
            row_date = str(row.get("date") or "")
            if dataset_key and row_date > latest_by_dataset.get(dataset_key, ""):
                latest_by_dataset[dataset_key] = row_date
        latest_rows = [
            row
            for row in records
            if str(row.get("date") or "") == latest_by_dataset.get(str(row.get("dataset_key") or ""))
        ]

        family_summaries: list[dict[str, Any]] = []
        participant_rows: list[dict[str, Any]] = []
        bucket_rows: list[dict[str, Any]] = []
        contract_rows: list[dict[str, Any]] = []
        matrix_rows: list[dict[str, Any]] = []
        for family, participants in CFTC_EXTRA_PARTICIPANTS.items():
            family_records = [row for row in records if row.get("family") == family]
            family_latest = [row for row in latest_rows if row.get("family") == family and row.get("variant") in {"combined", "supplemental"}]
            if not family_latest:
                family_latest = [row for row in latest_rows if row.get("family") == family]
            family_label = next((str(row.get("family_label") or family) for row in family_latest), family)
            family_dataset_count = len({str(row.get("dataset_key") or "") for row in family_latest if row.get("dataset_key")})
            family_summary = self._cftc_family_summary_from_rows(
                family_latest,
                family=family,
                family_label=family_label,
                dataset_count=family_dataset_count,
            )
            if family_summary:
                family_summary["rows"] = len(family_records)
                family_summaries.append(family_summary)
            primary_key = CFTC_PRIMARY_PARTICIPANT_BY_FAMILY.get(family)
            participant_rows.extend(
                self._cftc_generic_participant_summary(
                    family_latest,
                    family=family,
                    family_label=family_label,
                    participants=participants,
                )
            )
            bucket_rows.extend(
                self._cftc_generic_bucket_summary(
                    family_latest,
                    family=family,
                    family_label=family_label,
                    primary_key=primary_key,
                )
            )
            matrix_rows.extend(
                self._cftc_position_matrix(
                    family_latest,
                    family=family,
                    family_label=family_label,
                    participants=participants,
                )
            )
            family_contracts = sorted(
                family_latest,
                key=lambda row: abs(float(row.get(f"{primary_key}_net") or row.get("open_interest") or 0)),
                reverse=True,
            )[:80]
            contract_rows.extend(
                self._compact_cftc_extended_contract_row(row, primary_key=primary_key)
                for row in family_contracts
            )

        return {
            "pre_api": {"story_url": CFTC_PRE_STORY_URL, "mode": "PRE/API", "token_required": False},
            "datasets": datasets,
            "family_summaries": sorted(family_summaries, key=lambda row: float(row.get("open_interest") or 0), reverse=True),
            "extended_participant_summary": sorted(participant_rows, key=lambda row: abs(float(row.get("net") or 0)), reverse=True),
            "extended_asset_bucket_summary": sorted(bucket_rows, key=lambda row: abs(float(row.get("primary_net") or 0)), reverse=True),
            "extended_contracts": sorted(contract_rows, key=lambda row: abs(float(row.get("primary_net") or 0)), reverse=True),
            "position_matrix": sorted(matrix_rows, key=lambda row: (row.get("family_label") or "", row.get("asset_bucket") or "", row.get("participant") or "")),
            "coverage_notes": [
                "Disaggregated adds Producer/Merchant, Swap Dealer and Managed Money views.",
                "Legacy adds the classic Commercial and Non-commercial split.",
                "Supplemental CIT adds Commodity Index Trader positioning.",
            ],
            "errors": errors,
        }

    @staticmethod
    def _cftc_tff_dataset_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for variant, url in CFTC_TFF_RESOURCE_URLS.items():
            variant_rows = [row for row in records if row.get("variant") == variant]
            latest_date = max((str(row.get("date") or "") for row in variant_rows), default=None)
            summaries.append(
                {
                    "key": f"tff_{variant}",
                    "family": "tff",
                    "family_label": "TFF - Financial Futures",
                    "variant": variant,
                    "variant_label": "Futures + Options Combined" if variant == "combined" else "Futures only",
                    "url": url,
                    "role": "Financial futures positioning by dealer, asset manager and leveraged funds",
                    "status": "ok" if variant_rows else "empty",
                    "rows": len(variant_rows),
                    "fields": len(CFTC_TFF_FIELDS),
                    "latest_report_date": latest_date,
                }
            )
        return summaries

    @staticmethod
    def _cftc_family_summary_from_rows(
        rows: list[dict[str, Any]],
        *,
        family: str,
        family_label: str,
        dataset_count: int,
    ) -> dict[str, Any] | None:
        if not rows:
            return None
        latest_date = max((str(row.get("date") or "") for row in rows), default=None)
        latest_rows = [row for row in rows if str(row.get("date") or "") == latest_date]
        open_interest = sum(float(row.get("open_interest") or 0) for row in latest_rows)
        open_interest_change = sum(float(row.get("open_interest_change") or 0) for row in latest_rows)
        buckets: dict[str, float] = {}
        for row in latest_rows:
            bucket = str(row.get("asset_bucket") or "Other")
            buckets[bucket] = buckets.get(bucket, 0.0) + float(row.get("open_interest") or 0)
        top_bucket = max(buckets.items(), key=lambda item: item[1])[0] if buckets else None
        return {
            "family": family,
            "family_label": family_label,
            "datasets": dataset_count,
            "contracts": len(latest_rows),
            "rows": len(rows),
            "latest_report_date": latest_date,
            "open_interest": round(open_interest, 2),
            "open_interest_change": round(open_interest_change, 2),
            "top_bucket": top_bucket,
        }

    @staticmethod
    def _cftc_generic_participant_summary(
        rows: list[dict[str, Any]],
        *,
        family: str,
        family_label: str,
        participants: tuple[tuple[Any, ...], ...],
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        total_oi = sum(float(row.get("open_interest") or 0) for row in rows)
        summary: list[dict[str, Any]] = []
        for participant in participants:
            key = str(participant[0])
            label = str(participant[1])
            long_value = sum(float(row.get(f"{key}_long") or 0) for row in rows)
            short_value = sum(float(row.get(f"{key}_short") or 0) for row in rows)
            net_value = long_value - short_value
            change_net = sum(float(row.get(f"{key}_change_net") or 0) for row in rows)
            summary.append(
                {
                    "family": family,
                    "family_label": family_label,
                    "participant_key": key,
                    "participant": label,
                    "long": round(long_value, 2),
                    "short": round(short_value, 2),
                    "net": round(net_value, 2),
                    "weekly_net_change": round(change_net, 2),
                    "net_pct_open_interest": round(net_value / total_oi * 100, 4) if total_oi else None,
                }
            )
        return summary

    @staticmethod
    def _cftc_generic_bucket_summary(
        rows: list[dict[str, Any]],
        *,
        family: str,
        family_label: str,
        primary_key: str | None,
    ) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        if not rows:
            return []
        for row in rows:
            bucket = str(row.get("asset_bucket") or "Other")
            item = buckets.setdefault(
                bucket,
                {
                    "family": family,
                    "family_label": family_label,
                    "asset_bucket": bucket,
                    "contracts": 0,
                    "open_interest": 0.0,
                    "open_interest_change": 0.0,
                    "primary_participant_key": primary_key,
                    "primary_net": 0.0,
                    "primary_weekly_net_change": 0.0,
                },
            )
            item["contracts"] += 1
            item["open_interest"] += float(row.get("open_interest") or 0)
            item["open_interest_change"] += float(row.get("open_interest_change") or 0)
            if primary_key:
                item["primary_net"] += float(row.get(f"{primary_key}_net") or 0)
                item["primary_weekly_net_change"] += float(row.get(f"{primary_key}_change_net") or 0)
        output: list[dict[str, Any]] = []
        for item in buckets.values():
            output.append(
                {
                    **item,
                    "open_interest": round(float(item["open_interest"]), 2),
                    "open_interest_change": round(float(item["open_interest_change"]), 2),
                    "primary_net": round(float(item["primary_net"]), 2),
                    "primary_weekly_net_change": round(float(item["primary_weekly_net_change"]), 2),
                }
            )
        return output

    @staticmethod
    def _cftc_position_matrix(
        rows: list[dict[str, Any]],
        *,
        family: str,
        family_label: str,
        participants: tuple[tuple[Any, ...], ...],
    ) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            bucket = str(row.get("asset_bucket") or "Other")
            open_interest = float(row.get("open_interest") or 0)
            for participant in participants:
                key = str(participant[0])
                label = str(participant[1])
                item = buckets.setdefault(
                    (bucket, key),
                    {
                        "family": family,
                        "family_label": family_label,
                        "asset_bucket": bucket,
                        "participant_key": key,
                        "participant": label,
                        "open_interest": 0.0,
                        "net": 0.0,
                        "weekly_net_change": 0.0,
                    },
                )
                item["open_interest"] += open_interest
                item["net"] += float(row.get(f"{key}_net") or 0)
                item["weekly_net_change"] += float(row.get(f"{key}_change_net") or 0)
        output: list[dict[str, Any]] = []
        for item in buckets.values():
            open_interest = float(item["open_interest"] or 0)
            net = float(item["net"] or 0)
            output.append(
                {
                    **item,
                    "open_interest": round(open_interest, 2),
                    "net": round(net, 2),
                    "weekly_net_change": round(float(item["weekly_net_change"] or 0), 2),
                    "net_pct_open_interest": round(net / open_interest * 100, 4) if open_interest else None,
                }
            )
        return output

    @staticmethod
    def _compact_cftc_extended_contract_row(row: dict[str, Any], *, primary_key: str | None) -> dict[str, Any]:
        return {
            "date": row.get("date"),
            "dataset_key": row.get("dataset_key") or f"tff_{row.get('variant')}",
            "family": row.get("family") or "tff",
            "family_label": row.get("family_label") or "TFF - Financial Futures",
            "variant": row.get("variant"),
            "variant_label": row.get("variant_label"),
            "market_name": row.get("market_name"),
            "market_and_exchange_names": row.get("market_and_exchange_names"),
            "contract_code": row.get("contract_code"),
            "asset_bucket": row.get("asset_bucket"),
            "commodity_group": row.get("commodity_group"),
            "commodity_subgroup": row.get("commodity_subgroup"),
            "open_interest": row.get("open_interest"),
            "open_interest_change": row.get("open_interest_change"),
            "primary_participant_key": primary_key,
            "primary_net": row.get(f"{primary_key}_net") if primary_key else None,
            "primary_weekly_net_change": row.get(f"{primary_key}_change_net") if primary_key else None,
            "primary_pct_oi_net": row.get(f"{primary_key}_pct_oi_net") if primary_key else None,
            "total_reportable_net": row.get("total_reportable_net"),
            "concentration_gross_4_long": row.get("concentration_gross_4_long"),
            "concentration_gross_4_short": row.get("concentration_gross_4_short"),
        }

    def _compact_cftc_contract_row(self, row: dict[str, Any], *, records: list[dict[str, Any]]) -> dict[str, Any]:
        code = row.get("contract_code")
        history = [item for item in records if item.get("contract_code") == code]
        lev_stats = self._cftc_net_stats(history, "lev_money_net")
        asset_mgr_stats = self._cftc_net_stats(history, "asset_mgr_net")
        return {
            "date": row.get("date"),
            "market_name": row.get("market_name"),
            "market_and_exchange_names": row.get("market_and_exchange_names"),
            "contract_code": code,
            "asset_bucket": row.get("asset_bucket"),
            "commodity_subgroup": row.get("commodity_subgroup"),
            "open_interest": row.get("open_interest"),
            "open_interest_change": row.get("open_interest_change"),
            "dealer_net": row.get("dealer_net"),
            "dealer_change_net": row.get("dealer_change_net"),
            "asset_mgr_net": row.get("asset_mgr_net"),
            "asset_mgr_change_net": row.get("asset_mgr_change_net"),
            "asset_mgr_net_zscore_156w": asset_mgr_stats.get("zscore"),
            "asset_mgr_net_percentile_156w": asset_mgr_stats.get("percentile"),
            "lev_money_net": row.get("lev_money_net"),
            "lev_money_change_net": row.get("lev_money_change_net"),
            "lev_money_net_zscore_156w": lev_stats.get("zscore"),
            "lev_money_net_percentile_156w": lev_stats.get("percentile"),
            "other_rept_net": row.get("other_rept_net"),
            "nonrept_net": row.get("nonrept_net"),
            "lev_money_pct_oi_net": row.get("lev_money_pct_oi_net"),
            "asset_mgr_pct_oi_net": row.get("asset_mgr_pct_oi_net"),
            "dealer_pct_oi_net": row.get("dealer_pct_oi_net"),
            "concentration_gross_4_long": row.get("concentration_gross_4_long"),
            "concentration_gross_4_short": row.get("concentration_gross_4_short"),
        }

    @staticmethod
    def _compact_cftc_series_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "date": row.get("date"),
            "market_name": row.get("market_name"),
            "contract_code": row.get("contract_code"),
            "asset_bucket": row.get("asset_bucket"),
            "open_interest": row.get("open_interest"),
            "dealer_net": row.get("dealer_net"),
            "asset_mgr_net": row.get("asset_mgr_net"),
            "lev_money_net": row.get("lev_money_net"),
            "other_rept_net": row.get("other_rept_net"),
            "nonrept_net": row.get("nonrept_net"),
        }

    @staticmethod
    def _cftc_net_stats(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
        values = [float(row.get(field)) for row in rows if _safe_float(row.get(field)) is not None]
        if not values:
            return {"zscore": None, "percentile": None}
        latest = values[-1]
        mean = float(np.mean(values))
        std = float(np.std(values))
        zscore = (latest - mean) / std if std > 0 else 0.0
        percentile = sum(1 for value in values if value <= latest) / len(values)
        return {"zscore": round(zscore, 4), "percentile": round(percentile, 4)}

    def _cftc_participant_summary(self, latest_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total_oi = sum(float(row.get("open_interest") or 0) for row in latest_rows)
        summary: list[dict[str, Any]] = []
        for key, label, *_rest in CFTC_TFF_PARTICIPANTS:
            long_value = sum(float(row.get(f"{key}_long") or 0) for row in latest_rows)
            short_value = sum(float(row.get(f"{key}_short") or 0) for row in latest_rows)
            net_value = long_value - short_value
            change_net = sum(float(row.get(f"{key}_change_net") or 0) for row in latest_rows)
            summary.append(
                {
                    "participant_key": key,
                    "participant": label,
                    "long": round(long_value, 2),
                    "short": round(short_value, 2),
                    "net": round(net_value, 2),
                    "weekly_net_change": round(change_net, 2),
                    "net_pct_open_interest": round(net_value / total_oi * 100, 4) if total_oi else None,
                }
            )
        return sorted(summary, key=lambda row: abs(float(row.get("net") or 0)), reverse=True)

    def _cftc_asset_bucket_summary(self, latest_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in latest_rows:
            bucket = str(row.get("asset_bucket") or "Other")
            item = buckets.setdefault(
                bucket,
                {
                    "asset_bucket": bucket,
                    "contracts": 0,
                    "open_interest": 0.0,
                    "open_interest_change": 0.0,
                    "dealer_net": 0.0,
                    "asset_mgr_net": 0.0,
                    "lev_money_net": 0.0,
                    "lev_money_change_net": 0.0,
                },
            )
            item["contracts"] += 1
            for key in [
                "open_interest",
                "open_interest_change",
                "dealer_net",
                "asset_mgr_net",
                "lev_money_net",
                "lev_money_change_net",
            ]:
                item[key] += float(row.get(key) or 0)
        return sorted(
            [{**row, **{key: round(value, 2) for key, value in row.items() if isinstance(value, float)}} for row in buckets.values()],
            key=lambda row: abs(float(row.get("lev_money_net") or 0)),
            reverse=True,
        )
