from __future__ import annotations

import html
import os
import re
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from ..utils.logger import get_logger
from .funds_flow_contracts import (
    ANBIMA_BOLETIM_HOME_ENDPOINT,
    ANBIMA_BOLETIM_LIST_ENDPOINT,
    ANBIMA_CATEGORY_TO_MACRO,
    ANBIMA_CONSOLIDATED_DAILY_ENDPOINT,
    ANBIMA_PUBLICATION_POPULATE,
    ANBIMA_RANKING_ADMIN_ENDPOINT,
    ANBIMA_RANKING_MANAGER_ENDPOINT,
    ANBIMA_STRAPI_BASE_URL,
    ICI_MONTHLY_ETF_PAGE_URL,
    ICI_MUTUAL_FUND_WEEKLY_COLUMNS,
    ICI_SIMPLE_WEEKLY_COLUMNS,
    ICI_WEEKLY_FLOW_URLS,
    ICI_WORLDWIDE_COLUMNS,
    ICI_WORLDWIDE_PAGE_URL,
)
from .funds_flow_utils import (
    _local_now,
    _normalize_text,
    _parse_iso,
    _safe_div,
    _safe_float,
)

logger = get_logger("aquiles.funds_flow.anbima_ici")


class FundsFlowAnbimaIciMixin:
    def _load_anbima_funds(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "anbima_fundos",
            "source": "ANBIMA Estatisticas de Fundos",
            "url": f"{ANBIMA_STRAPI_BASE_URL}{ANBIMA_CONSOLIDATED_DAILY_ENDPOINT}",
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        try:
            consolidated_page = self._fetch_anbima_publication(ANBIMA_CONSOLIDATED_DAILY_ENDPOINT)
            admin_page = self._fetch_anbima_publication(ANBIMA_RANKING_ADMIN_ENDPOINT)
            manager_page = self._fetch_anbima_publication(ANBIMA_RANKING_MANAGER_ENDPOINT)
            boletim_home = self._fetch_anbima_publication(ANBIMA_BOLETIM_HOME_ENDPOINT)
            boletim_articles = self._fetch_anbima_boletim_articles()

            consolidated_daily = {
                "status": "not_loaded",
                "documents": consolidated_page.get("documents") or [],
                "title": consolidated_page.get("title"),
                "updated_at": consolidated_page.get("updated_at"),
                "source_url": consolidated_page.get("source_url"),
            }
            documents = consolidated_page.get("documents") or []
            if documents:
                doc = documents[0]
                cache_path = self._download_anbima_document(doc, subdir="consolidado_diario", force=force)
                parsed = self._parse_anbima_consolidated_daily(cache_path)
                consolidated_daily.update(parsed)
                consolidated_daily.update(
                    {
                        "status": "ok",
                        "document": doc,
                        "cached_path": cache_path,
                    }
                )
                status["cached_path"] = cache_path

            rankings = {
                "administrators": self._load_anbima_ranking(
                    admin_page,
                    subdir="ranking_administradores",
                    entity_key="administrator",
                    entity_label="Administrador",
                    force=force,
                ),
                "managers": self._load_anbima_ranking(
                    manager_page,
                    subdir="ranking_gestores",
                    entity_key="manager",
                    entity_label="Gestor",
                    force=force,
                ),
            }

            row_count = (
                len(consolidated_daily.get("categories") or [])
                + len(consolidated_daily.get("types") or [])
                + len(rankings["administrators"].get("top_aum") or [])
                + len(rankings["managers"].get("top_aum") or [])
                + len(boletim_articles)
            )
            payload = {
                "status": "ok" if row_count else "empty",
                "source": "ANBIMA Data",
                "source_url": "https://data.anbima.com.br/publicacoes/consolidado-diario-de-fundos-de-investimento",
                "strapi_base_url": ANBIMA_STRAPI_BASE_URL,
                "consolidated_daily": consolidated_daily,
                "rankings": rankings,
                "bulletin": {
                    "status": "ok" if boletim_articles else "configured",
                    "home": {
                        "title": boletim_home.get("title"),
                        "content": boletim_home.get("content_text"),
                        "updated_at": boletim_home.get("updated_at"),
                        "source_url": boletim_home.get("source_url"),
                    },
                    "latest_articles": boletim_articles,
                },
                "opportunities": [
                    "Benchmark diario por tipo ANBIMA: PL, rentabilidade e captacao liquida.",
                    "Classificacao granular para abrir Renda Fixa, Acoes, Multi e Previdencia em subtipos.",
                    "Rankings mensais por administrador e gestor para medir concentracao de PL e captacao.",
                    "Boletim mensal para fechamento executivo e contexto textual auditavel.",
                ],
            }
            status.update(
                {
                    "ok": row_count > 0,
                    "rows": row_count,
                    "latest_data_date": consolidated_daily.get("reference_date"),
                }
            )
            return payload, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load ANBIMA funds layer: %s", exc)
            return {
                "status": "error",
                "source": "ANBIMA Data",
                "error": str(exc),
                "consolidated_daily": {"status": "error", "categories": [], "types": []},
                "rankings": {},
                "bulletin": {"latest_articles": []},
            }, status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def _fetch_anbima_publication(self, endpoint: str) -> dict[str, Any]:
        response = requests.get(
            f"{ANBIMA_STRAPI_BASE_URL}{endpoint}",
            params={"populate": ANBIMA_PUBLICATION_POPULATE},
            timeout=max(self.timeout_seconds, 45),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        attributes = data.get("attributes") or {}
        template = attributes.get("template") or {}
        return {
            "endpoint": endpoint,
            "source_url": response.url,
            "title": template.get("title"),
            "content_text": self._html_to_text(template.get("content")),
            "updated_at": attributes.get("updatedAt"),
            "published_at": attributes.get("publishedAt"),
            "documents": self._extract_anbima_documents(template.get("publication_document") or []),
            "connected_documents": self._extract_anbima_documents(template.get("connected_documents") or []),
            "more_content": template.get("more_content") or [],
        }

    def _fetch_anbima_boletim_articles(self, limit: int = 5) -> list[dict[str, Any]]:
        response = requests.get(
            f"{ANBIMA_STRAPI_BASE_URL}{ANBIMA_BOLETIM_LIST_ENDPOINT}",
            params={"populate": "template", "sort": "template.display_date:DESC"},
            timeout=max(self.timeout_seconds, 45),
        )
        response.raise_for_status()
        rows = response.json().get("data") or []
        articles: list[dict[str, Any]] = []
        for item in rows[:limit]:
            template = ((item.get("attributes") or {}).get("template") or {})
            text = self._html_to_text(template.get("content"))
            articles.append(
                {
                    "title": template.get("title"),
                    "slug": template.get("slug"),
                    "display_date": _parse_iso(template.get("display_date")),
                    "display_date_text": _parse_iso(template.get("display_date")).date().isoformat()
                    if _parse_iso(template.get("display_date"))
                    else None,
                    "url": f"https://data.anbima.com.br/publicacoes/boletim-de-fundos-de-investimento/{template.get('slug')}"
                    if template.get("slug")
                    else "https://data.anbima.com.br/publicacoes/boletim-de-fundos-de-investimento",
                    "summary": text[:850],
                }
            )
        return articles

    def _extract_anbima_documents(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for item in values:
            file_items = (((item.get("file") or {}).get("data")) or [])
            file_attrs = (file_items[0].get("attributes") or {}) if file_items else {}
            relative_url = file_attrs.get("url") or item.get("alternative_file_url")
            if not relative_url:
                continue
            file_url = relative_url if str(relative_url).startswith("http") else f"{ANBIMA_STRAPI_BASE_URL}{relative_url}"
            display_dt = _parse_iso(item.get("display_date"))
            documents.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "display_date": display_dt.date().isoformat() if display_dt else None,
                    "file_name": file_attrs.get("name") or os.path.basename(str(relative_url)),
                    "file_url": file_url,
                    "mime": file_attrs.get("mime"),
                    "size_kb": file_attrs.get("size"),
                }
            )
        return documents

    def _download_anbima_document(self, document: dict[str, Any], *, subdir: str, force: bool) -> str:
        file_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(document.get("file_name") or "anbima_file")).strip()
        if not file_name:
            file_name = "anbima_file"
        cache_path = os.path.join(self.raw_dir, "anbima", subdir, file_name)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0 and not force:
            return cache_path
        response = requests.get(str(document.get("file_url")), timeout=max(self.timeout_seconds, 60))
        response.raise_for_status()
        temp_path = f"{cache_path}.tmp"
        with open(temp_path, "wb") as handle:
            handle.write(response.content)
        os.replace(temp_path, cache_path)
        return cache_path

    def _parse_anbima_consolidated_daily(self, cache_path: str) -> dict[str, Any]:
        workbook = pd.ExcelFile(cache_path)
        category_sheet = self._find_anbima_sheet(
            workbook.sheet_names,
            required_tokens=["CLASSE ANBIMA", "CATEGORIA"],
            preferred="Classe ANBIMA - Categoria",
        )
        type_sheet = self._find_anbima_sheet(
            workbook.sheet_names,
            required_tokens=["TIPO ANBIMA"],
            preferred="Tipo ANBIMA",
        )
        if not category_sheet:
            raise RuntimeError(f"ANBIMA consolidated daily category sheet not found in {workbook.sheet_names}")
        if not type_sheet:
            raise RuntimeError(f"ANBIMA consolidated daily type sheet not found in {workbook.sheet_names}")
        category_df = pd.read_excel(cache_path, sheet_name=category_sheet, header=None)
        type_df = pd.read_excel(cache_path, sheet_name=type_sheet, header=None)
        reference_date = self._extract_anbima_date(category_df, "Data de Referência")
        emission_date = self._extract_anbima_date(category_df, "Data de Emissão")
        categories = self._parse_anbima_consolidated_rows(category_df, kind="category", first_block_only=True)
        types = self._parse_anbima_consolidated_rows(type_df, kind="type", first_block_only=False)
        total = self._find_anbima_total(category_df)
        return {
            "reference_date": reference_date.isoformat() if reference_date else None,
            "emission_date": emission_date.isoformat() if emission_date else None,
            "unit": "BRL",
            "source_file": os.path.basename(cache_path),
            "category_sheet": category_sheet,
            "type_sheet": type_sheet,
            "summary": total,
            "categories": categories,
            "types": types,
            "top_type_inflows_mtd": sorted(
                [row for row in types if _safe_float(row.get("net_flow_month_brl")) is not None],
                key=lambda row: _safe_float(row.get("net_flow_month_brl")) or 0,
                reverse=True,
            )[:10],
            "top_type_outflows_mtd": sorted(
                [row for row in types if _safe_float(row.get("net_flow_month_brl")) is not None],
                key=lambda row: _safe_float(row.get("net_flow_month_brl")) or 0,
            )[:10],
        }

    def _parse_anbima_consolidated_rows(
        self,
        df: pd.DataFrame,
        *,
        kind: str,
        first_block_only: bool,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for idx, row in df.iterrows():
            if first_block_only and idx > 33:
                break
            name = str(row.get(0) or "").strip()
            normalized = _normalize_text(name)
            if not name or normalized in seen:
                continue
            if any(token in normalized for token in ["ANBIMA", "CLASSES DE", "SUB TOTAL", "TOTAL DOMESTICO", "TOTAL GERAL"]):
                continue
            aum = _safe_float(row.get(2))
            share = _safe_float(row.get(3))
            if aum is None or share is None:
                continue
            seen.add(normalized)
            item = {
                "name": name,
                "normalized_name": normalized,
                "kind": kind,
                "aum_previous_brl": self._million_to_brl(row.get(1)),
                "aum_brl": self._million_to_brl(row.get(2)),
                "share_pct": _safe_float(row.get(3), 6),
                "net_flow_day_brl": self._million_to_brl(row.get(8)),
                "net_flow_month_brl": self._million_to_brl(row.get(9)),
                "net_flow_ytd_brl": self._million_to_brl(row.get(10)),
                "net_flow_12m_brl": self._million_to_brl(row.get(11)),
                "macro_classe": self._anbima_macro_from_name(name),
            }
            if kind == "type":
                item.update(
                    {
                        "return_day_pct": _safe_float(row.get(4), 6),
                        "return_month_pct": _safe_float(row.get(5), 6),
                        "return_ytd_pct": _safe_float(row.get(6), 6),
                        "return_12m_pct": _safe_float(row.get(7), 6),
                    }
                )
            rows.append(item)
        return rows

    @staticmethod
    def _find_anbima_sheet(
        sheet_names: list[str],
        *,
        required_tokens: list[str],
        preferred: str | None = None,
    ) -> str | None:
        if preferred and preferred in sheet_names:
            return preferred
        normalized = [(sheet, _normalize_text(sheet)) for sheet in sheet_names]
        for sheet, name in normalized:
            if all(token in name for token in required_tokens):
                return sheet
        return None

    def _find_anbima_total(self, df: pd.DataFrame) -> dict[str, Any]:
        for _, row in df.iterrows():
            if _normalize_text(row.get(0)) == "TOTAL GERAL":
                return {
                    "name": "Total Geral",
                    "aum_brl": self._million_to_brl(row.get(2)),
                    "share_pct": _safe_float(row.get(3), 6),
                    "net_flow_day_brl": self._million_to_brl(row.get(8)),
                    "net_flow_month_brl": self._million_to_brl(row.get(9)),
                    "net_flow_ytd_brl": self._million_to_brl(row.get(10)),
                    "net_flow_12m_brl": self._million_to_brl(row.get(11)),
                }
        return {}

    def _load_anbima_ranking(
        self,
        page: dict[str, Any],
        *,
        subdir: str,
        entity_key: str,
        entity_label: str,
        force: bool,
    ) -> dict[str, Any]:
        documents = page.get("documents") or []
        payload = {
            "status": "configured",
            "title": page.get("title"),
            "updated_at": page.get("updated_at"),
            "source_url": page.get("source_url"),
            "documents": documents,
            "top_aum": [],
        }
        if not documents:
            return payload
        doc = documents[0]
        cache_path = self._download_anbima_document(doc, subdir=subdir, force=force)
        top_aum, period_label = self._parse_anbima_ranking_file(cache_path, entity_key=entity_key, entity_label=entity_label)
        payload.update(
            {
                "status": "ok",
                "period_label": period_label,
                "document": doc,
                "cached_path": cache_path,
                "top_aum": top_aum,
            }
        )
        return payload

    def _parse_anbima_ranking_file(
        self,
        cache_path: str,
        *,
        entity_key: str,
        entity_label: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        xls = pd.ExcelFile(cache_path)
        sheet = next((item for item in xls.sheet_names if "PL por Categoria" in item), xls.sheet_names[0])
        df = pd.read_excel(cache_path, sheet_name=sheet, header=None)
        period_label = self._extract_anbima_period_label(df)
        header_idx = None
        for idx, row in df.iterrows():
            values = [_normalize_text(value) for value in row.tolist()]
            if "ORDEM" in values and _normalize_text(entity_label) in values:
                header_idx = idx
                break
        if header_idx is None:
            return [], period_label
        header = [_normalize_text(value) for value in df.iloc[header_idx].tolist()]
        name_col = header.index(_normalize_text(entity_label))
        total_col = max([idx for idx, value in enumerate(header) if value.startswith("TOTAL")] or [len(header) - 1])
        class_columns = {
            idx: str(df.iloc[header_idx, idx]).strip()
            for idx in range(name_col + 1, total_col)
            if str(df.iloc[header_idx, idx]).strip() and str(df.iloc[header_idx, idx]).lower() != "nan"
        }
        rows: list[dict[str, Any]] = []
        for _, row in df.iloc[header_idx + 1 :].iterrows():
            rank = _safe_float(row.get(0))
            name = str(row.get(name_col) or "").strip()
            if rank is None or not name or name.lower() == "nan":
                if rows:
                    break
                continue
            values_by_class = {
                class_name: self._million_to_brl(row.get(idx))
                for idx, class_name in class_columns.items()
                if _safe_float(row.get(idx)) is not None
            }
            rows.append(
                {
                    "rank": int(rank),
                    entity_key: name,
                    "name": name,
                    "total_aum_brl": self._million_to_brl(row.get(total_col)),
                    "values_by_class": values_by_class,
                    "dominant_class": max(values_by_class.items(), key=lambda item: item[1] or 0)[0]
                    if values_by_class
                    else None,
                }
            )
            if len(rows) >= 20:
                break
        return rows, period_label

    def _build_anbima_validation(
        self,
        class_latest: pd.DataFrame,
        anbima_payload: dict[str, Any],
        *,
        as_of_date: date,
    ) -> dict[str, Any]:
        consolidated = anbima_payload.get("consolidated_daily") or {}
        categories = consolidated.get("categories") or []
        if not categories:
            return {"status": "not_available", "rows": []}
        cvm_by_macro = {
            str(row.macro_classe): row
            for row in class_latest.itertuples(index=False)
        }
        rows: list[dict[str, Any]] = []
        for item in categories:
            macro = item.get("macro_classe")
            if not macro:
                continue
            cvm_row = cvm_by_macro.get(macro)
            if cvm_row is None:
                continue
            anbima_aum = _safe_float(item.get("aum_brl"))
            cvm_aum = _safe_float(getattr(cvm_row, "pl_total", None))
            anbima_flow = _safe_float(item.get("net_flow_day_brl"))
            cvm_flow = _safe_float(getattr(cvm_row, "captacao_liquida_total", None))
            rows.append(
                {
                    "macro_classe": macro,
                    "anbima_name": item.get("name"),
                    "cvm_date": as_of_date.isoformat(),
                    "anbima_date": consolidated.get("reference_date"),
                    "cvm_aum_brl": _safe_float(cvm_aum, 2),
                    "anbima_aum_brl": _safe_float(anbima_aum, 2),
                    "aum_diff_brl": _safe_float((cvm_aum or 0) - (anbima_aum or 0), 2),
                    "aum_diff_pct": _safe_float(_safe_div((cvm_aum or 0) - (anbima_aum or 0), anbima_aum), 6),
                    "cvm_net_flow_1d_brl": _safe_float(cvm_flow, 2),
                    "anbima_net_flow_day_brl": _safe_float(anbima_flow, 2),
                    "flow_diff_brl": _safe_float((cvm_flow or 0) - (anbima_flow or 0), 2),
                }
            )
        return {
            "status": "available" if rows else "not_matched",
            "cvm_date": as_of_date.isoformat(),
            "anbima_date": consolidated.get("reference_date"),
            "note": "ANBIMA esta em R$ convertidos de R$ milhoes; datas podem diferir da ultima data CVM disponivel.",
            "rows": rows,
        }

    @staticmethod
    def _html_to_text(value: Any) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _million_to_brl(value: Any) -> float | None:
        parsed = _safe_float(value)
        return round(parsed * 1_000_000, 2) if parsed is not None else None

    @staticmethod
    def _extract_anbima_date(df: pd.DataFrame, label: str) -> date | None:
        label_normalized = _normalize_text(label)
        date_pattern = re.compile(r"(\d{2}/\d{2}/\d{4})")
        for value in df.astype(str).values.flatten().tolist():
            text = str(value)
            if label_normalized not in _normalize_text(text):
                continue
            match = date_pattern.search(text)
            if match:
                try:
                    return datetime.strptime(match.group(1), "%d/%m/%Y").date()
                except Exception:
                    return None
        return None

    @staticmethod
    def _extract_anbima_period_label(df: pd.DataFrame) -> str | None:
        month_pattern = re.compile(
            r"(Jan(?:eiro)?|Fev(?:ereiro)?|Mar(?:co|ço)?|Abr(?:il)?|Mai(?:o)?|Jun(?:ho)?|Jul(?:ho)?|Ago(?:sto)?|Set(?:embro)?|Out(?:ubro)?|Nov(?:embro)?|Dez(?:embro)?)[/\s-]*(\d{2,4})",
            re.I,
        )
        for value in df.astype(str).values.flatten().tolist():
            text = str(value).strip()
            match = month_pattern.search(text)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _anbima_macro_from_name(name: Any) -> str | None:
        normalized = _normalize_text(name)
        for token, macro in ANBIMA_CATEGORY_TO_MACRO.items():
            if normalized == token or normalized.startswith(f"{token} ") or normalized.startswith(f"{token} ("):
                return macro
        return None

    def _load_ici_global_flows(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
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
        for vehicle in sorted({str(row.get("vehicle")) for row in weekly_series if row.get("vehicle")}):
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

        latest_date = max([str(row.get("date")) for row in weekly_series], default=None)
        return {
            "status": "ok" if weekly_series else "empty",
            "year": year,
            "cached_paths": cached_paths,
            "weekly_series": weekly_series[-900:],
            "monthly_series": monthly_series[-360:],
            "latest_date": latest_date,
            "latest_by_vehicle": latest_by_vehicle,
        }

    def _parse_ici_weekly_file(self, cache_path: str, *, vehicle: str, source_url: str) -> list[dict[str, Any]]:
        df = pd.read_excel(cache_path, header=None)
        weekly_header_idx = None
        for idx, value in enumerate(df.iloc[:, 0].astype(str).tolist()):
            if "estimated weekly" in value.lower():
                weekly_header_idx = idx
                break
        columns = ICI_MUTUAL_FUND_WEEKLY_COLUMNS if vehicle == "mutual_fund" else ICI_SIMPLE_WEEKLY_COLUMNS
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
        release_url = self._first_ici_href(page_html, ICI_MONTHLY_ETF_PAGE_URL, r"/research/stats/etf/etfs_[0-9]{2}_[0-9]{2}")
        release_html = self._download_text_cached(
            release_url,
            os.path.join(self.raw_dir, "ici", "monthly_etf", f"{release_url.rstrip('/').split('/')[-1]}.html"),
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
                    "fund_count": int(fund_counts_by_type.get(name) or 0) if fund_counts_by_type.get(name) is not None else None,
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
            "cached_path": os.path.join(self.raw_dir, "ici", "monthly_etf", f"{release_url.rstrip('/').split('/')[-1]}.html"),
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
        report_url = self._first_ici_href(page_html, ICI_WORLDWIDE_PAGE_URL, r"/statistical-report/ww_q[1-4]_[0-9]{2}_public_report_us\.xls")
        file_name = report_url.rstrip("/").split("/")[-1]
        cache_path = os.path.join(self.raw_dir, "ici", "worldwide", file_name)
        self._download(report_url, cache_path, force=force)

        assets = self._parse_ici_worldwide_sheet(cache_path, sheet_name="Table 2", prefix="assets")
        net_sales = self._parse_ici_worldwide_sheet(cache_path, sheet_name="Table 3", prefix="net_sales")
        fund_counts = self._parse_ici_worldwide_sheet(cache_path, sheet_name="Table 4", prefix="fund_count")
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

    def _parse_ici_worldwide_sheet(self, cache_path: str, *, sheet_name: str, prefix: str) -> list[dict[str, Any]]:
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
            if self._is_ici_non_data_label(region_text) or self._is_ici_non_data_label(country_text):
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
            item = {
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

    def _merge_ici_worldwide_rows(self, row_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
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
        return normalized.startswith(("note:", "source:", "components may", "institutional funds are", "na "))

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
        text = response.text
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
        parsed = FundsFlowAnbimaIciMixin._safe_ici_number(value)
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

