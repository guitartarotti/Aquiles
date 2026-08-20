"""ICI download, cache and parsing adapter for Funds Flow."""

from __future__ import annotations

import html
import os
import re
import time
from typing import Any
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from ....utils.funds_flow_source_values import (
    _local_now,
    _normalize_text,
    _safe_float,
)
from ....utils.logger import get_logger
from ..contracts.source_catalog import (
    ICI_MONTHLY_ETF_PAGE_URL,
    ICI_MUTUAL_FUND_WEEKLY_COLUMNS,
    ICI_SIMPLE_WEEKLY_COLUMNS,
    ICI_WEEKLY_FLOW_URLS,
    ICI_WORLDWIDE_COLUMNS,
    ICI_WORLDWIDE_PAGE_URL,
)
from .source_http import CachedHttpSource

logger = get_logger("aquiles.funds_flow.sources.ici")


class IciFundsFlowAdapter(CachedHttpSource):
    provider = "ici"

    def load_global_flows(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "ici_global_flows",
            "source": "ICI Global Fund Flows",
            "url": "https://www.ici.org/research/stats/flows",
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        errors: list[str] = []
        try:
            weekly_payload = self._load_ici_weekly_flow_files(force=force)
        except Exception as exc:
            weekly_payload = {"status": "error", "error": str(exc), "weekly_series": []}
            errors.append(f"weekly: {exc}")
            logger.warning("Failed to load ICI weekly files: %s", exc)

        try:
            monthly_etf = self._load_ici_monthly_etf(force=force)
        except Exception as exc:
            monthly_etf = {"status": "error", "error": str(exc), "assets_by_type": []}
            errors.append(f"monthly_etf: {exc}")
            logger.warning("Failed to load ICI monthly ETF data: %s", exc)

        try:
            worldwide = self._load_ici_worldwide_quarterly(force=force)
        except Exception as exc:
            worldwide = {"status": "error", "error": str(exc), "regions": [], "countries": []}
            errors.append(f"worldwide: {exc}")
            logger.warning("Failed to load ICI worldwide quarterly data: %s", exc)

        row_count = (
            len(weekly_payload.get("weekly_series") or [])
            + len(monthly_etf.get("assets_by_type") or [])
            + len(worldwide.get("regions") or [])
            + len(worldwide.get("countries") or [])
        )
        payload = {
            "status": "ok" if row_count else "error" if errors else "empty",
            "source": "Investment Company Institute",
            "source_url": "https://www.ici.org/research/stats/flows",
            "currency": "USD",
            "unit": "USD millions",
            "weekly": weekly_payload,
            "monthly_etf": monthly_etf,
            "worldwide_quarterly": worldwide,
            "coverage_notes": [
                "ICI weekly public files split ETFs into domestic equity, world equity, bond, hybrid and commodity.",
                "Country and regional cuts are quarterly in the Worldwide Public Tables, not weekly.",
                "Weekly rows are estimates; monthly and quarterly rows are official reported aggregates.",
            ],
            "errors": errors,
        }
        cached_paths = [
            *(weekly_payload.get("cached_paths") or []),
            monthly_etf.get("cached_path"),
            worldwide.get("cached_path"),
        ]
        cached_paths = [str(item) for item in cached_paths if item]
        status.update(
            {
                "ok": row_count > 0,
                "status": "active" if row_count > 0 else "error" if errors else "empty",
                "label": "ICI Global Fund Flows",
                "provider": "Investment Company Institute",
                "kind": "official_public",
                "cadence": "weekly_quarterly",
                "role": "Fluxos semanais de mutual funds/ETFs e suplemento trimestral por pais/regiao",
                "rows": row_count,
                "error": "; ".join(errors) if errors else None,
                "cached_path": cached_paths[0] if cached_paths else None,
                "cached_paths": cached_paths,
                "latest_data_date": weekly_payload.get("latest_date"),
                "reference_label": monthly_etf.get("reference_month") or worldwide.get("quarter"),
            }
        )
        status["latency_ms"] = int((time.monotonic() - started) * 1000)
        return payload, status

    def _load_ici_weekly_flow_files(self, *, force: bool) -> dict[str, Any]:
        year = _local_now().year
        records: list[dict[str, Any]] = []
        cached_paths: list[str] = []
        for vehicle, url_pattern in ICI_WEEKLY_FLOW_URLS.items():
            url = url_pattern.format(year=year)
            cache_path = os.path.join(self.raw_dir, "ici", "weekly", str(year), f"{vehicle}.xls")
            self._download(url, cache_path, force=force)
            cached_paths.append(cache_path)
            records.extend(self._parse_ici_weekly_file(cache_path, vehicle=vehicle, source_url=url))

        weekly_series = [row for row in records if row.get("frequency") == "W"]
        monthly_series = [row for row in records if row.get("frequency") == "M"]
        latest_by_vehicle: dict[str, Any] = {}
        for vehicle in sorted(
            {str(row.get("vehicle")) for row in weekly_series if row.get("vehicle")}
        ):
            vehicle_rows = [row for row in weekly_series if row.get("vehicle") == vehicle]
            latest_date = max(str(row.get("date")) for row in vehicle_rows)
            latest_categories = [row for row in vehicle_rows if row.get("date") == latest_date]
            total_row = next(
                (
                    row
                    for row in latest_categories
                    if str(row.get("category_key") or "").startswith("total")
                    or row.get("category_key") == "total"
                ),
                latest_categories[0] if latest_categories else {},
            )
            latest_by_vehicle[vehicle] = {
                "vehicle": vehicle,
                "date": latest_date,
                "total_flow_usd_mn": total_row.get("flow_usd_mn"),
                "categories": latest_categories,
            }

        overall_latest_date: str | None = max(
            [str(row.get("date")) for row in weekly_series], default=None
        )
        return {
            "status": "ok" if weekly_series else "empty",
            "year": year,
            "cached_paths": cached_paths,
            "weekly_series": weekly_series[-900:],
            "monthly_series": monthly_series[-360:],
            "latest_date": overall_latest_date,
            "latest_by_vehicle": latest_by_vehicle,
        }

    def _parse_ici_weekly_file(
        self, cache_path: str, *, vehicle: str, source_url: str
    ) -> list[dict[str, Any]]:
        df = pd.read_excel(cache_path, header=None)
        weekly_header_idx = None
        for idx, value in enumerate(df.iloc[:, 0].astype(str).tolist()):
            if "estimated weekly" in value.lower():
                weekly_header_idx = idx
                break
        columns = (
            ICI_MUTUAL_FUND_WEEKLY_COLUMNS
            if vehicle == "mutual_fund"
            else ICI_SIMPLE_WEEKLY_COLUMNS
        )
        records: list[dict[str, Any]] = []
        for idx, row in df.iterrows():
            parsed_date = pd.to_datetime(row.get(0), errors="coerce")
            if pd.isna(parsed_date):
                continue
            frequency = "W" if weekly_header_idx is not None and idx > weekly_header_idx else "M"
            data_kind = "estimated_weekly" if frequency == "W" else "actual_monthly"
            for col_idx, key, label, group in columns:
                value = _safe_float(row.get(col_idx), 2)
                if value is None:
                    continue
                records.append(
                    {
                        "date": parsed_date.date().isoformat(),
                        "frequency": frequency,
                        "data_kind": data_kind,
                        "vehicle": vehicle,
                        "vehicle_label": self._ici_vehicle_label(vehicle),
                        "category_key": key,
                        "category": label,
                        "category_group": group,
                        "flow_usd_mn": value,
                        "source": "ICI",
                        "source_url": source_url,
                        "source_file": os.path.basename(cache_path),
                    }
                )
        return records

    def _load_ici_monthly_etf(self, *, force: bool) -> dict[str, Any]:
        page_html = self._download_text_cached(
            ICI_MONTHLY_ETF_PAGE_URL,
            os.path.join(self.raw_dir, "ici", "monthly_etf", "monthly_etf_page.html"),
            force=force,
        )
        release_url = self._first_ici_href(
            page_html, ICI_MONTHLY_ETF_PAGE_URL, r"/research/stats/etf/etfs_[0-9]{2}_[0-9]{2}"
        )
        release_html = self._download_text_cached(
            release_url,
            os.path.join(
                self.raw_dir, "ici", "monthly_etf", f"{release_url.rstrip('/').split('/')[-1]}.html"
            ),
            force=force,
        )
        tables = self._html_tables(release_html)
        assets_table = tables[0] if len(tables) > 0 else []
        issuance_table = tables[1] if len(tables) > 1 else []
        funds_table = tables[2] if len(tables) > 2 else []

        reference_label = assets_table[0][1] if assets_table and len(assets_table[0]) > 1 else None
        assets_by_type: list[dict[str, Any]] = []
        fund_counts_by_type = {
            str(row[0]).strip(): self._safe_ici_number(row[1])
            for row in funds_table[1:]
            if row and len(row) > 1 and str(row[0]).strip()
        }
        for row in assets_table[1:]:
            if len(row) < 2 or not str(row[0]).strip():
                continue
            name = str(row[0]).strip()
            assets_by_type.append(
                {
                    "segment": name,
                    "segment_key": self._slug_key(name),
                    "reference_month": reference_label,
                    "assets_usd_mn": self._usd_bn_to_mn(row[1]),
                    "previous_assets_usd_mn": self._usd_bn_to_mn(row[2] if len(row) > 2 else None),
                    "year_ago_assets_usd_mn": self._usd_bn_to_mn(row[3] if len(row) > 3 else None),
                    "fund_count": int(fund_counts_by_type.get(name) or 0)
                    if fund_counts_by_type.get(name) is not None
                    else None,
                }
            )

        issuance: list[dict[str, Any]] = []
        for row in issuance_table[1:]:
            if len(row) < 2 or not str(row[0]).strip():
                continue
            issuance.append(
                {
                    "metric": str(row[0]).strip(),
                    "metric_key": self._slug_key(row[0]),
                    "reference_month": reference_label,
                    "current_usd_mn": self._usd_bn_to_mn(row[1]),
                    "previous_usd_mn": self._usd_bn_to_mn(row[2] if len(row) > 2 else None),
                    "ytd_current_usd_mn": self._usd_bn_to_mn(row[3] if len(row) > 3 else None),
                    "ytd_prior_usd_mn": self._usd_bn_to_mn(row[4] if len(row) > 4 else None),
                }
            )

        return {
            "status": "ok" if assets_by_type or issuance else "empty",
            "source_url": release_url,
            "cached_path": os.path.join(
                self.raw_dir, "ici", "monthly_etf", f"{release_url.rstrip('/').split('/')[-1]}.html"
            ),
            "reference_month": reference_label,
            "assets_by_type": assets_by_type,
            "issuance": issuance,
        }

    def _load_ici_worldwide_quarterly(self, *, force: bool) -> dict[str, Any]:
        page_html = self._download_text_cached(
            ICI_WORLDWIDE_PAGE_URL,
            os.path.join(self.raw_dir, "ici", "worldwide", "worldwide_page.html"),
            force=force,
        )
        report_url = self._first_ici_href(
            page_html,
            ICI_WORLDWIDE_PAGE_URL,
            r"/statistical-report/ww_q[1-4]_[0-9]{2}_public_report_us\.xls",
        )
        file_name = report_url.rstrip("/").split("/")[-1]
        cache_path = os.path.join(self.raw_dir, "ici", "worldwide", file_name)
        self._download(report_url, cache_path, force=force)

        assets = self._parse_ici_worldwide_sheet(cache_path, sheet_name="Table 2", prefix="assets")
        net_sales = self._parse_ici_worldwide_sheet(
            cache_path, sheet_name="Table 3", prefix="net_sales"
        )
        fund_counts = self._parse_ici_worldwide_sheet(
            cache_path, sheet_name="Table 4", prefix="fund_count"
        )
        merged = self._merge_ici_worldwide_rows([assets, net_sales, fund_counts])
        regions = [row for row in merged if row.get("level") == "region"]
        countries = [row for row in merged if row.get("level") == "country"]
        top_country_etf_net_sales = sorted(
            [row for row in countries if _safe_float(row.get("net_sales_etfs_usd_mn")) is not None],
            key=lambda row: _safe_float(row.get("net_sales_etfs_usd_mn")) or 0,
            reverse=True,
        )[:12]
        bottom_country_etf_net_sales = sorted(
            [row for row in countries if _safe_float(row.get("net_sales_etfs_usd_mn")) is not None],
            key=lambda row: _safe_float(row.get("net_sales_etfs_usd_mn")) or 0,
        )[:12]
        brazil = next((row for row in countries if str(row.get("country")) == "Brazil"), None)
        quarter = self._extract_ici_worldwide_quarter(cache_path)
        return {
            "status": "ok" if regions or countries else "empty",
            "source_url": report_url,
            "cached_path": cache_path,
            "quarter": quarter,
            "currency": "USD",
            "regions": regions,
            "countries": countries,
            "top_country_etf_net_sales": top_country_etf_net_sales,
            "bottom_country_etf_net_sales": bottom_country_etf_net_sales,
            "brazil": brazil,
        }

    def _parse_ici_worldwide_sheet(
        self, cache_path: str, *, sheet_name: str, prefix: str
    ) -> list[dict[str, Any]]:
        df = pd.read_excel(cache_path, sheet_name=sheet_name, header=None)
        rows: list[dict[str, Any]] = []
        current_region: str | None = None
        for idx, row in df.iterrows():
            if idx < 7:
                continue
            region_cell = row.get(0)
            country_cell = row.get(1)
            region_text = str(region_cell).strip() if pd.notna(region_cell) else ""
            country_text = str(country_cell).strip() if pd.notna(country_cell) else ""
            if self._is_ici_non_data_label(region_text) or self._is_ici_non_data_label(
                country_text
            ):
                continue
            if region_text:
                current_region = self._clean_ici_location_label(region_text)
                location_key = region_text
                level = "region"
                country = None
            elif country_text and current_region:
                country_text = self._clean_ici_location_label(country_text)
                location_key = f"{current_region}|{country_text}"
                level = "country"
                country = country_text
            else:
                continue
            item: dict[str, Any] = {
                "key": location_key,
                "level": level,
                "region": current_region if current_region else region_text,
                "country": country,
            }
            for col_idx, key, _label in ICI_WORLDWIDE_COLUMNS:
                value = _safe_float(row.get(col_idx), 2)
                if value is not None:
                    suffix = "usd_mn" if prefix != "fund_count" else "count"
                    item[f"{prefix}_{key}_{suffix}"] = value
            rows.append(item)
        return rows

    def _merge_ici_worldwide_rows(
        self, row_groups: list[list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for rows in row_groups:
            for row in rows:
                key = str(row.get("key"))
                current = merged.setdefault(
                    key,
                    {
                        "level": row.get("level"),
                        "region": row.get("region"),
                        "country": row.get("country"),
                    },
                )
                current.update({k: v for k, v in row.items() if k != "key"})
        return list(merged.values())

    def _extract_ici_worldwide_quarter(self, cache_path: str) -> str | None:
        try:
            df = pd.read_excel(cache_path, sheet_name="Table of Contents", header=None, nrows=3)
            text = " ".join(str(value) for value in df.astype(str).values.flatten().tolist())
            match = re.search(r"(\d{4}:Q[1-4])", text)
            if match:
                return match.group(1)
        except Exception:
            pass
        file_match = re.search(r"ww_q([1-4])_(\d{2})_", os.path.basename(cache_path), re.I)
        if file_match:
            return f"20{file_match.group(2)}:Q{file_match.group(1)}"
        return None

    @staticmethod
    def _is_ici_non_data_label(value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        normalized = text.lower()
        if re.match(r"^\d+\.\s+", text):
            return True
        return normalized.startswith(
            ("note:", "source:", "components may", "institutional funds are", "na ")
        )

    @staticmethod
    def _clean_ici_location_label(value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return re.sub(r"(?<=[A-Za-z)])\d+$", "", text).strip()

    def _download_text_cached(self, url: str, cache_path: str, *, force: bool) -> str:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0 and not force:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return handle.read()
        response = requests.get(url, timeout=max(self.timeout_seconds, 45))
        response.raise_for_status()
        text: str = response.text
        temp_path = f"{cache_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, cache_path)
        return text

    @staticmethod
    def _first_ici_href(html_text: str, base_url: str, pattern: str) -> str:
        regex = re.compile(r'href=["\']([^"\']*' + pattern + r'[^"\']*)["\']', re.I)
        match = regex.search(html_text)
        if not match:
            raise RuntimeError(f"ICI link not found for pattern {pattern}")
        return urljoin(base_url, html.unescape(match.group(1)))

    @staticmethod
    def _html_tables(html_text: str) -> list[list[list[str]]]:
        soup = BeautifulSoup(html_text, "html.parser")
        tables: list[list[list[str]]] = []
        for table in soup.find_all("table"):
            table_rows: list[list[str]] = []
            for tr in table.find_all("tr"):
                cells = [
                    re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
                    for cell in tr.find_all(["th", "td"])
                ]
                if any(cells):
                    table_rows.append(cells)
            if table_rows:
                tables.append(table_rows)
        return tables

    @staticmethod
    def _ici_vehicle_label(vehicle: str) -> str:
        return {
            "mutual_fund": "Mutual Funds",
            "etf": "ETFs",
            "combined": "MF + ETF",
        }.get(vehicle, vehicle)

    @staticmethod
    def _slug_key(value: Any) -> str:
        normalized = _normalize_text(value)
        normalized = normalized.replace("/", " ")
        return re.sub(r"[^A-Z0-9]+", "_", normalized).strip("_").lower()

    @staticmethod
    def _usd_bn_to_mn(value: Any) -> float | None:
        parsed = IciFundsFlowAdapter._safe_ici_number(value)
        return round(parsed * 1_000, 2) if parsed is not None else None

    @staticmethod
    def _safe_ici_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float, np.integer, np.floating)):
            return _safe_float(value)
        text = str(value or "").strip()
        if not text or text.lower() == "nan":
            return None
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", ""))
        except Exception:
            return _safe_float(text)
