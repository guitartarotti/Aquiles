"""B3 download, cache and parsing adapter for Funds Flow."""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import time
from datetime import date, timedelta
from typing import Any, cast

import requests

from ....config import Config
from ....utils.atomic_io import atomic_json_dump
from ....utils.funds_flow_source_values import (
    _clean_json,
    _normalize_text,
    _now_iso,
    _parse_date,
    _safe_float,
)
from ....utils.logger import get_logger
from ..contracts.source_catalog import (
    B3_BDI_PATTERN,
    B3_BDI_STRUCTURED_TABLES_START_DATE,
    B3_BDI_TABLE_EXPORT_CSV_URL,
    B3_BDI_TABLE_EXPORT_URL,
    B3_DEFAULT_OPEN_INTEREST_ASSETS,
    B3_DERIVATIVE_OPEN_INTEREST_TABLE,
    B3_ETF_FUND_TYPES,
    B3_FUNDS_LISTED_PAGE_URL,
    B3_FUNDS_LISTED_SEARCH_URL,
    B3_FUTURES_MONTH_CODES,
    B3_INVESTOR_PARTICIPATION_MONTHLY_TABLE,
    B3_MARKET_DATA_REPORT_URL,
)
from .source_http import CachedHttpSource

logger = get_logger("aquiles.funds_flow.sources.b3")


class B3FundsFlowAdapter(CachedHttpSource):
    provider = "b3"

    def load_investor_participation(
        self,
        *,
        target_date: date,
        force: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "b3_market",
            "source": "B3 BDI Participacao dos Investidores",
            "url": None,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        try:
            min_points = max(1, int(getattr(Config, "FUNDS_FLOW_LOCAL_B3_HISTORY_DAYS", 21)))
            records: list[dict[str, Any]] = []
            errors: list[str] = []
            recent_refresh_cutoff = target_date - timedelta(days=4)
            for candidate_date in self._candidate_bdi_dates(
                target_date, limit=max(45, min_points * 3)
            ):
                url = B3_BDI_PATTERN.format(
                    iso_date=candidate_date.isoformat(),
                    yyyymmdd=candidate_date.strftime("%Y%m%d"),
                )
                cache_path = os.path.join(
                    self.raw_dir,
                    "b3_bdi",
                    f"BDI_02_{candidate_date.strftime('%Y%m%d')}.pdf",
                )
                try:
                    self._download(
                        url, cache_path, force=force and candidate_date >= recent_refresh_cutoff
                    )
                    parsed = self._parse_b3_bdi_investor_participation(cache_path)
                    if parsed.get("participants"):
                        parsed.update(
                            {
                                "status": "ok",
                                "source": "B3 BDI Participacao dos Investidores",
                                "publication_date": candidate_date.isoformat(),
                                "url": url,
                                "cached_path": cache_path,
                            }
                        )
                        records.append(parsed)
                        unique_dates = {
                            record.get("data_until") or record.get("publication_date")
                            for record in records
                            if record.get("data_until") or record.get("publication_date")
                        }
                        if len(unique_dates) >= min_points:
                            break
                except Exception as exc:
                    status["error"] = str(exc)
                    errors.append(f"{candidate_date.isoformat()}: {exc}")
                    continue

            if not records:
                raise RuntimeError(
                    "No B3 BDI investor participation table found in the candidate window."
                )

            records = self._dedupe_b3_records(records)
            latest = records[-1]
            history, trend_by_participant = self._build_b3_investor_history(
                records, min_points=min_points
            )
            latest.update(
                {
                    "history": history,
                    "trend_by_participant": trend_by_participant,
                    "daily_reports": [
                        {
                            "publication_date": record.get("publication_date"),
                            "data_until": record.get("data_until"),
                            "participants": len(record.get("participants") or []),
                            "url": record.get("url"),
                            "cached_path": record.get("cached_path"),
                        }
                        for record in records[-min_points:]
                    ],
                    "coverage": {
                        "target_days": min_points,
                        "reports_loaded": len(records),
                        "history_points": len(history),
                        "first_data_until": records[0].get("data_until"),
                        "last_data_until": latest.get("data_until"),
                        "errors": errors[-8:],
                    },
                    "bdi_opportunities": self._build_b3_bdi_opportunities(latest),
                }
            )
            status.update(
                {
                    "url": latest.get("url"),
                    "ok": True,
                    "rows": len(history),
                    "cached_path": latest.get("cached_path"),
                    "latest_data_date": latest.get("data_until") or latest.get("publication_date"),
                }
            )
            return latest, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load B3 investor participation from BDI: %s", exc)
            return {
                "status": "error",
                "source": "B3 BDI Participacao dos Investidores",
                "error": str(exc),
                "participants": [],
            }, status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def load_open_interest(
        self,
        *,
        target_date: date,
        force: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "b3_derivatives_open_interest",
            "source": "B3 BDI Posicoes em Aberto",
            "url": B3_BDI_TABLE_EXPORT_URL,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        try:
            if target_date < B3_BDI_STRUCTURED_TABLES_START_DATE:
                raise RuntimeError(
                    "Tabela estruturada B3/BDI indisponivel para datas anteriores a 2025-12-15. "
                    f"O corte solicitado foi {target_date.isoformat()}."
                )
            min_points = max(1, int(getattr(Config, "FUNDS_FLOW_LOCAL_B3_HISTORY_DAYS", 21)))
            tracked_assets = self._b3_open_interest_assets()
            records: list[dict[str, Any]] = []
            errors: list[str] = []
            recent_refresh_cutoff = target_date - timedelta(days=4)

            for candidate_date in self._candidate_bdi_dates(
                target_date, limit=max(45, min_points * 3)
            ):
                try:
                    raw = self._load_b3_table_export(
                        B3_DERIVATIVE_OPEN_INTEREST_TABLE,
                        candidate_date,
                        force=force and candidate_date >= recent_refresh_cutoff,
                    )
                    rows = self._normalize_b3_open_interest_table(
                        raw,
                        request_date=candidate_date,
                        tracked_assets=tracked_assets,
                    )
                    if not rows:
                        csv_text = self._load_b3_table_export_csv(
                            B3_DERIVATIVE_OPEN_INTEREST_TABLE,
                            candidate_date,
                            force=force and candidate_date >= recent_refresh_cutoff,
                        )
                        rows = self._normalize_b3_open_interest_csv(
                            csv_text,
                            request_date=candidate_date,
                            tracked_assets=tracked_assets,
                        )
                    if not rows:
                        errors.append(f"{candidate_date.isoformat()}: tabela sem linhas publicadas")
                        continue
                    records.append(
                        {
                            "date": candidate_date.isoformat(),
                            "request_date": candidate_date.isoformat(),
                            "rows": rows,
                            "raw_rows": len(raw.get("values") or []),
                            "version": raw.get("version"),
                            "table": raw.get("name") or B3_DERIVATIVE_OPEN_INTEREST_TABLE,
                        }
                    )
                    if len({record["date"] for record in records}) >= min_points:
                        break
                except Exception as exc:
                    status["error"] = str(exc)
                    errors.append(f"{candidate_date.isoformat()}: {exc}")
                    continue

            if not records:
                sample_errors = (
                    "; ".join(errors[:3])
                    if errors
                    else "nenhuma linha publicada no intervalo consultado"
                )
                raise RuntimeError(
                    "B3 retornou a tabela OpenPositionsEquities sem linhas publicadas no intervalo consultado. "
                    f"Amostra: {sample_errors}"
                )

            records = sorted(records, key=lambda item: str(item.get("date") or ""))
            latest = records[-1]
            history, product_summary, latest_contracts, futures_summary = (
                self._build_b3_open_interest_history(
                    records,
                    tracked_assets=tracked_assets,
                    min_points=min_points,
                )
            )
            cache_path = self._b3_table_cache_path(
                B3_DERIVATIVE_OPEN_INTEREST_TABLE, _parse_date(latest.get("date")) or target_date
            )
            payload = {
                "status": "ok",
                "source": "B3 BDI API",
                "table": B3_DERIVATIVE_OPEN_INTEREST_TABLE,
                "label": "Posicoes em aberto - derivativos de bolsa",
                "date": latest.get("date"),
                "unit": "contracts",
                "tracked_assets": tracked_assets,
                "coverage": {
                    "target_days": min_points,
                    "reports_loaded": len(records),
                    "coverage_complete": len(records) >= min_points,
                    "history_points": len(history),
                    "first_date": records[0].get("date"),
                    "last_date": latest.get("date"),
                    "recent_skips": errors[:10],
                    "older_skips": errors[-5:] if len(errors) > 10 else [],
                    "note": None
                    if len(records) >= min_points
                    else "BDI API returned empty OpenPositionsEquities tables before the first available date.",
                },
                "product_summary": product_summary,
                "latest_contracts": latest_contracts,
                "futures_summary": futures_summary,
                "history": history,
                "participant_positioning": self._build_b3_participant_positioning_status(),
            }
            status.update(
                {
                    "ok": True,
                    "rows": len(history),
                    "cached_path": cache_path,
                    "latest_data_date": latest.get("date"),
                }
            )
            return payload, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load B3 derivatives open interest from BDI API: %s", exc)
            return {
                "status": "error",
                "source": "B3 BDI API",
                "table": B3_DERIVATIVE_OPEN_INTEREST_TABLE,
                "error": str(exc),
                "product_summary": [],
                "history": [],
            }, status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def load_monthly_investor_participation(
        self,
        *,
        target_date: date,
        force: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "b3_investor_participation_monthly",
            "source": "B3 BDI Participacao dos Investidores Mensal",
            "url": B3_BDI_TABLE_EXPORT_URL,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        try:
            if target_date < B3_BDI_STRUCTURED_TABLES_START_DATE:
                raise RuntimeError(
                    "Tabela estruturada B3/BDI indisponivel para datas anteriores a 2025-12-15. "
                    f"O corte solicitado foi {target_date.isoformat()}."
                )
            errors: list[str] = []
            recent_refresh_cutoff = target_date - timedelta(days=4)
            for candidate_date in self._candidate_bdi_dates(target_date, limit=20):
                try:
                    raw = self._load_b3_table_export(
                        B3_INVESTOR_PARTICIPATION_MONTHLY_TABLE,
                        candidate_date,
                        force=force and candidate_date >= recent_refresh_cutoff,
                    )
                    rows = self._normalize_b3_investor_participation_monthly(raw)
                    period_label = self._extract_b3_monthly_period_label(raw)
                    if not rows:
                        csv_text = self._load_b3_table_export_csv(
                            B3_INVESTOR_PARTICIPATION_MONTHLY_TABLE,
                            candidate_date,
                            force=force and candidate_date >= recent_refresh_cutoff,
                        )
                        rows = self._normalize_b3_investor_participation_monthly_csv(csv_text)
                        period_label = (
                            period_label
                            or self._extract_b3_monthly_period_label_from_text(csv_text)
                        )
                    if not rows:
                        errors.append(f"{candidate_date.isoformat()}: tabela sem linhas publicadas")
                        continue
                    payload = {
                        "status": "ok",
                        "source": "B3 BDI API",
                        "table": B3_INVESTOR_PARTICIPATION_MONTHLY_TABLE,
                        "label": "Participacao dos investidores mensal",
                        "date": candidate_date.isoformat(),
                        "period_label": period_label,
                        "unit": "BRL",
                        "note": "Valores em R$; participacao por mercado considera compras + vendas.",
                        "rows": rows,
                        "coverage": {
                            "request_date": target_date.isoformat(),
                            "publication_date": candidate_date.isoformat(),
                            "rows": len(rows),
                            "recent_skips": errors[-6:],
                        },
                    }
                    status.update(
                        {
                            "ok": True,
                            "rows": len(rows),
                            "cached_path": self._b3_table_cache_path(
                                B3_INVESTOR_PARTICIPATION_MONTHLY_TABLE,
                                candidate_date,
                            ),
                            "latest_data_date": payload.get("date"),
                            "reference_label": period_label,
                        }
                    )
                    return payload, status
                except Exception as exc:
                    status["error"] = str(exc)
                    errors.append(f"{candidate_date.isoformat()}: {exc}")
                    continue
            sample_errors = (
                "; ".join(errors[:3])
                if errors
                else "nenhuma linha publicada no intervalo consultado"
            )
            raise RuntimeError(
                "B3 retornou a tabela SharesInvesVolumMonthly sem linhas publicadas no intervalo consultado. "
                f"Amostra: {sample_errors}"
            )
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load B3 monthly investor participation from BDI API: %s", exc)
            return {
                "status": "error",
                "source": "B3 BDI API",
                "table": B3_INVESTOR_PARTICIPATION_MONTHLY_TABLE,
                "error": str(exc),
                "rows": [],
            }, status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def load_market_data_report(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "b3_market_data_report",
            "source": "B3 Relatorio Dados de Mercado",
            "url": B3_MARKET_DATA_REPORT_URL,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        cache_path = os.path.join(self.raw_dir, "b3_market_data", "RELATORIO_DADOS_DE_MERCADO.csv")
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            if force or not os.path.exists(cache_path) or os.path.getsize(cache_path) == 0:
                response = requests.get(
                    B3_MARKET_DATA_REPORT_URL, timeout=max(self.timeout_seconds, 60)
                )
                response.raise_for_status()
                temp_path = f"{cache_path}.tmp"
                with open(temp_path, "wb") as handle:
                    handle.write(response.content)
                os.replace(temp_path, cache_path)

            with open(cache_path, "rb") as handle:
                content = handle.read()
            text = content.decode("latin1", errors="replace").replace("\ufeff", "")
            payload = self._parse_b3_market_data_report(text)
            payload.update(
                {
                    "status": "ok",
                    "source": "B3 Relatorio Dados de Mercado",
                    "url": B3_MARKET_DATA_REPORT_URL,
                    "cached_path": cache_path,
                }
            )
            row_count = sum(
                len(payload.get(name) or [])
                for name in [
                    "trading_volume_monthly",
                    "average_daily_trading_value",
                    "total_trades",
                    "daily_average_trades",
                    "investor_participation_monthly",
                    "foreign_investor_flow_monthly",
                ]
            )
            status.update(
                {
                    "ok": True,
                    "rows": row_count,
                    "cached_path": cache_path,
                    "latest_data_date": payload.get("data_until"),
                }
            )
            return payload, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load B3 market data report CSV: %s", exc)
            return {
                "status": "error",
                "source": "B3 Relatorio Dados de Mercado",
                "url": B3_MARKET_DATA_REPORT_URL,
                "error": str(exc),
            }, status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def load_etfs(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "b3_etfs",
            "source": "B3 ETFs Listados",
            "url": B3_FUNDS_LISTED_PAGE_URL,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        try:
            all_rows: list[dict[str, Any]] = []
            categories: list[dict[str, Any]] = []
            raw_paths: list[str] = []
            for fund_type, category_label in B3_ETF_FUND_TYPES:
                raw = self._fetch_b3_funds_listed(fund_type, force=force)
                raw_paths.append(self._b3_funds_cache_path(fund_type))
                rows = self._normalize_b3_funds_listed(
                    raw, fund_type=fund_type, category_label=category_label
                )
                all_rows.extend(rows)
                categories.append(
                    {
                        "fund_type": fund_type,
                        "category": category_label,
                        "count": len(rows),
                        "total_records": int(
                            (raw.get("page") or {}).get("totalRecords") or len(rows) or 0
                        ),
                    }
                )

            all_rows = sorted(
                all_rows,
                key=lambda row: (str(row.get("category") or ""), str(row.get("ticker") or "")),
            )
            summary = {
                "total_listed": len(all_rows),
                "categories": categories,
                "category_count": len([item for item in categories if item.get("count")]),
                "source_page": B3_FUNDS_LISTED_PAGE_URL,
                "search_endpoint": f"{B3_FUNDS_LISTED_SEARCH_URL}/GetListFunds",
            }
            payload = {
                "status": "ok",
                "source": "B3 Fundos Listados",
                "url": B3_FUNDS_LISTED_PAGE_URL,
                "frequency": "daily",
                "summary": summary,
                "categories": categories,
                "funds": all_rows,
                "raw_paths": raw_paths,
                "note": "Lista oficial B3 de fundos listados; valores de fluxo seguem vindo de CVM/ANBIMA/ICI.",
            }
            status.update(
                {
                    "ok": True,
                    "rows": len(all_rows),
                    "cached_path": os.path.join(self.raw_dir, "b3_etfs"),
                }
            )
            return payload, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load B3 listed ETFs: %s", exc)
            return {
                "status": "error",
                "source": "B3 Fundos Listados",
                "url": B3_FUNDS_LISTED_PAGE_URL,
                "error": str(exc),
                "funds": [],
                "categories": [],
            }, status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def _fetch_b3_funds_listed(self, fund_type: str, *, force: bool) -> dict[str, Any]:
        cache_path = self._b3_funds_cache_path(fund_type)
        if os.path.exists(cache_path) and not force and os.path.getsize(cache_path) > 0:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return cast(dict[str, Any], json.load(handle))

        page_size = 120
        first_payload = {
            "language": "pt-br",
            "typeFund": fund_type,
            "pageNumber": 1,
            "pageSize": page_size,
        }
        first = self._request_b3_funds_listed(first_payload)
        total_pages = int((first.get("page") or {}).get("totalPages") or 1)
        results = list(first.get("results") or [])
        for page_number in range(2, total_pages + 1):
            page_payload = dict(first_payload)
            page_payload["pageNumber"] = page_number
            page = self._request_b3_funds_listed(page_payload)
            results.extend(page.get("results") or [])

        combined = {
            "page": {
                **(first.get("page") or {}),
                "pageSize": page_size,
                "totalPages": total_pages,
            },
            "results": results,
            "fund_type": fund_type,
            "fetched_at": _now_iso(),
        }
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        atomic_json_dump(cache_path, _clean_json(combined), indent=2)
        return combined

    def _request_b3_funds_listed(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = base64.b64encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        url = f"{B3_FUNDS_LISTED_SEARCH_URL}/GetListFunds/{encoded}"
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=max(self.timeout_seconds, 60),
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def _b3_funds_cache_path(self, fund_type: str) -> str:
        safe_type = re.sub(r"[^A-Za-z0-9_-]+", "_", fund_type).strip("_") or "ETF"
        return os.path.join(self.raw_dir, "b3_etfs", f"{safe_type}.json")

    @staticmethod
    def _normalize_b3_funds_listed(
        raw: dict[str, Any],
        *,
        fund_type: str,
        category_label: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in raw.get("results") or []:
            ticker = str(item.get("acronym") or "").strip().upper()
            if not ticker:
                continue
            rows.append(
                {
                    "b3_id": item.get("id"),
                    "fund_type": fund_type,
                    "category": category_label,
                    "ticker": ticker,
                    "fund_name": str(item.get("fundName") or "").strip(),
                    "trading_name": str(item.get("tradingName") or "").strip(),
                    "type_name": item.get("typeName"),
                    "source": "B3 Fundos Listados",
                }
            )
        return rows

    def _normalize_b3_investor_participation_monthly(
        self, raw: dict[str, Any]
    ) -> list[dict[str, Any]]:
        values = raw.get("values") or []
        rows: list[dict[str, Any]] = []
        for row in values:
            if len(row) < 13:
                continue
            rows.append(
                {
                    "participant_type": self._normalize_b3_participant_label(str(row[0] or "")),
                    "cash_brl": _safe_float(row[1], 2),
                    "cash_participation_pct": _safe_float(row[2], 4),
                    "forward_brl": _safe_float(row[3], 2),
                    "forward_participation_pct": _safe_float(row[4], 4),
                    "options_brl": _safe_float(row[5], 2),
                    "options_participation_pct": _safe_float(row[6], 4),
                    "options_exercise_brl": _safe_float(row[7], 2),
                    "options_exercise_participation_pct": _safe_float(row[8], 4),
                    "blocks_brl": _safe_float(row[9], 2),
                    "blocks_participation_pct": _safe_float(row[10], 4),
                    "total_brl": _safe_float(row[11], 2),
                    "total_participation_pct": _safe_float(row[12], 4),
                }
            )
        return rows

    def _normalize_b3_investor_participation_monthly_csv(self, text: str) -> list[dict[str, Any]]:
        normalized = str(text or "").replace("\ufeff", "")
        if "No results found" in normalized or "Nenhum resultado" in normalized:
            return []

        rows_raw = [row for row in csv.reader(io.StringIO(normalized), delimiter=";")]
        header_idx = next(
            (
                idx
                for idx, row in enumerate(rows_raw)
                if row
                and any(cell.strip() in {"Investor types", "Tipos de investidores"} for cell in row)
            ),
            None,
        )
        if header_idx is None:
            return []

        parsed: list[dict[str, Any]] = []
        for row in rows_raw[header_idx + 1 :]:
            if not row or not any(str(cell).strip() for cell in row):
                continue
            label = str(row[0] or "").strip()
            if not label or label.lower() in {"no results found", "nenhum resultado"}:
                continue
            if len(row) < 13:
                continue
            parsed.append(
                {
                    "participant_type": self._normalize_b3_participant_label(label),
                    "cash_brl": _safe_float(row[1], 2),
                    "cash_participation_pct": _safe_float(row[2], 4),
                    "forward_brl": _safe_float(row[3], 2),
                    "forward_participation_pct": _safe_float(row[4], 4),
                    "options_brl": _safe_float(row[5], 2),
                    "options_participation_pct": _safe_float(row[6], 4),
                    "options_exercise_brl": _safe_float(row[7], 2),
                    "options_exercise_participation_pct": _safe_float(row[8], 4),
                    "blocks_brl": _safe_float(row[9], 2),
                    "blocks_participation_pct": _safe_float(row[10], 4),
                    "total_brl": _safe_float(row[11], 2),
                    "total_participation_pct": _safe_float(row[12], 4),
                }
            )
        return parsed

    @staticmethod
    def _extract_b3_monthly_period_label(raw: dict[str, Any]) -> str | None:
        text = " ".join(str(item.get("textPt") or "") for item in raw.get("texts") or [])
        match = re.search(r"m[eê]s anterior\s+\(([^)]+)\)", text, re.I)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_b3_monthly_period_label_from_text(text: str) -> str | None:
        normalized = str(text or "").replace("\ufeff", "")
        match = re.search(r"previous month\s+\(([^)]+)\)", normalized, re.I)
        if match:
            return match.group(1).strip().rstrip(".")
        match = re.search(r"m[eê]s anterior\s+\(([^)]+)\)", normalized, re.I)
        if match:
            return match.group(1).strip().rstrip(".")
        return None

    def _parse_b3_market_data_report(self, text: str) -> dict[str, Any]:
        lines = [line.strip().replace("\x1a", "") for line in text.splitlines()]
        lines = [line for line in lines if line]
        payload = {
            "label": "Relatorio Dados de Mercado",
            "unit": {
                "trading_volume": "BRL million",
                "foreign_flow": "BRL million",
                "trades": "count",
                "participation": "percent",
            },
            "data_until": self._extract_b3_market_data_until(lines),
            "trading_volume_monthly": self._parse_b3_market_table(
                lines,
                "Volume Total",
                [
                    "period",
                    "cash_brl_million",
                    "forward_brl_million",
                    "options_brl_million",
                    "blocks_brl_million",
                    "total_brl_million",
                ],
            ),
            "average_daily_trading_value": self._parse_b3_market_table(
                lines,
                "Volume M",
                ["period", "brl_million", "variation_pct", "usd_million", "usd_variation_pct"],
            ),
            "total_trades": self._parse_b3_market_table(
                lines,
                "Nº de Negócios Total",
                [
                    "period",
                    "cash_trades",
                    "forward_trades",
                    "options_trades",
                    "blocks_trades",
                    "total_trades",
                ],
            ),
            "daily_average_trades": self._parse_b3_market_table(
                lines,
                "Nº de Negócios Médio Diário",
                ["period", "trades", "variation_pct"],
            ),
            "investor_participation_monthly": self._parse_b3_market_table(
                lines,
                "Fatia de investidores",
                [
                    "period",
                    "individuals_pct",
                    "institutions_pct",
                    "foreign_pct",
                    "financial_institutions_pct",
                    "others_pct",
                ],
                skip_header_rows=2,
            ),
            "foreign_investor_flow_monthly": self._parse_b3_market_table(
                lines,
                "Movimentação dos Investidores Estrangeiros Mensal",
                [
                    "period",
                    "buy_brl_million",
                    "sell_brl_million",
                    "ipo_follow_on_brl_million",
                    "balance_brl_million",
                ],
            ),
        }
        payload["summary"] = self._build_b3_market_data_summary(payload)
        return payload

    def _parse_b3_market_table(
        self,
        lines: list[str],
        marker: str,
        columns: list[str],
        *,
        occurrence: int = 0,
        skip_header_rows: int = 1,
    ) -> list[dict[str, Any]]:
        marker_indexes = [idx for idx, line in enumerate(lines) if marker.lower() in line.lower()]
        if len(marker_indexes) <= occurrence:
            return []
        idx = marker_indexes[occurrence] + 1 + skip_header_rows
        rows: list[dict[str, Any]] = []
        while idx < len(lines):
            line = lines[idx]
            if ";" not in line:
                break
            parts = [part.strip() for part in line.split(";")]
            if len(parts) < len(columns):
                break
            period = parts[0]
            if period.lower().startswith(("ano ", "year ", "month ", "mês")):
                idx += 1
                continue
            row: dict[str, Any] = {columns[0]: period}
            for col, value in zip(columns[1:], parts[1:], strict=False):
                row[col] = self._parse_b3_csv_number(value)
            rows.append(row)
            idx += 1
        return rows

    @staticmethod
    def _parse_b3_csv_number(value: Any) -> float | None:
        text = str(value or "").strip().replace("%", "")
        if not text:
            return None
        text = text.replace(".", "").replace(",", ".")
        try:
            return float(text)
        except Exception:
            return None

    @staticmethod
    def _extract_b3_market_data_until(lines: list[str]) -> str | None:
        for line in lines:
            match = re.search(r"At[eé] dia\s+(.+?)\s+-", line, re.I)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _build_b3_market_data_summary(payload: dict[str, Any]) -> dict[str, Any]:
        def latest_regular(rows: list[dict[str, Any]]) -> dict[str, Any]:
            regular = [row for row in rows if not str(row.get("period") or "").startswith("2026(")]
            return regular[-1] if regular else (rows[-1] if rows else {})

        latest_volume = latest_regular(payload.get("trading_volume_monthly") or [])
        latest_adv = latest_regular(payload.get("average_daily_trading_value") or [])
        latest_trades = latest_regular(payload.get("total_trades") or [])
        latest_foreign = latest_regular(payload.get("foreign_investor_flow_monthly") or [])
        return {
            "period": latest_volume.get("period"),
            "data_until": payload.get("data_until"),
            "total_volume_brl_million": latest_volume.get("total_brl_million"),
            "cash_volume_brl_million": latest_volume.get("cash_brl_million"),
            "options_volume_brl_million": latest_volume.get("options_brl_million"),
            "blocks_volume_brl_million": latest_volume.get("blocks_brl_million"),
            "average_daily_brl_million": latest_adv.get("brl_million"),
            "total_trades": latest_trades.get("total_trades"),
            "foreign_buy_brl_million": latest_foreign.get("buy_brl_million"),
            "foreign_sell_brl_million": latest_foreign.get("sell_brl_million"),
            "foreign_balance_brl_million": latest_foreign.get("balance_brl_million"),
        }

    def _load_b3_table_export(
        self, table_name: str, table_date: date, *, force: bool
    ) -> dict[str, Any]:
        cache_path = self._b3_table_cache_path(table_name, table_date)
        if os.path.exists(cache_path) and not force and os.path.getsize(cache_path) > 0:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return cast(dict[str, Any], json.load(handle))

        payload: dict[str, Any] = {
            "Name": table_name,
            "Date": table_date.isoformat(),
            "FinalDate": table_date.isoformat(),
            "ClientId": "",
            "Filters": {},
        }
        response = requests.post(
            B3_BDI_TABLE_EXPORT_URL,
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=max(self.timeout_seconds, 60),
        )
        response.raise_for_status()
        data = cast(dict[str, Any], response.json())
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        atomic_json_dump(cache_path, _clean_json(data), indent=2)
        return data

    def _load_b3_table_export_csv(
        self, table_name: str, table_date: date, *, force: bool, lang: str = "en-US"
    ) -> str:
        cache_path = self._b3_table_csv_cache_path(table_name, table_date, lang)
        if os.path.exists(cache_path) and not force and os.path.getsize(cache_path) > 0:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return handle.read()

        payload: dict[str, Any] = {
            "Name": table_name,
            "Date": table_date.isoformat(),
            "FinalDate": table_date.isoformat(),
            "ClientId": "",
            "Filters": {},
        }
        response = requests.post(
            f"{B3_BDI_TABLE_EXPORT_CSV_URL}?lang={lang}",
            json=payload,
            headers={"Accept": "text/csv,application/json", "Content-Type": "application/json"},
            timeout=max(self.timeout_seconds, 60),
        )
        response.raise_for_status()
        text = response.content.decode("utf-8", "replace")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return text

    def _b3_table_cache_path(self, table_name: str, table_date: date) -> str:
        return os.path.join(
            self.raw_dir,
            "b3_api",
            table_name,
            f"{table_name}_{table_date.strftime('%Y%m%d')}.json",
        )

    def _b3_table_csv_cache_path(
        self, table_name: str, table_date: date, lang: str = "en-US"
    ) -> str:
        safe_lang = lang.replace("-", "_")
        return os.path.join(
            self.raw_dir,
            "b3_api_csv",
            table_name,
            f"{table_name}_{table_date.strftime('%Y%m%d')}_{safe_lang}.csv",
        )

    def _normalize_b3_open_interest_table(
        self,
        raw: dict[str, Any],
        *,
        request_date: date,
        tracked_assets: list[str],
    ) -> list[dict[str, Any]]:
        values = raw.get("values") or []
        columns = raw.get("columns") or []
        if not values or not columns:
            return []

        index_by_name = {str(column.get("name")): idx for idx, column in enumerate(columns)}

        def item(row: list[Any], name: str) -> Any:
            idx = index_by_name.get(name)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        tracked = {asset.upper() for asset in tracked_assets}
        rows: list[dict[str, Any]] = []
        for row in values:
            ticker = str(item(row, "TckrSymb") or "").strip().upper()
            asset = str(item(row, "Asst") or "").strip().upper()
            if not ticker or not asset:
                continue
            is_future = self._is_b3_future_contract(ticker, asset)
            is_tracked = asset in tracked
            if not is_future:
                continue
            rows.append(
                {
                    "date": request_date.isoformat(),
                    "ticker": ticker,
                    "isin": item(row, "ISIN"),
                    "asset": asset,
                    "expiration_code": item(row, "XprtnCd"),
                    "segment": item(row, "SgmtNm"),
                    "contract_type": "future",
                    "open_interest": int(item(row, "OpnIntrst") or 0),
                    "variation_open_interest": int(item(row, "VartnOpnIntrst") or 0),
                    "locked_contracts": int(item(row, "LockedQty") or 0),
                    "unlocked_transfer_contracts": int(item(row, "UnlockedQty") or 0),
                    "tracked": is_tracked,
                }
            )
        return rows

    def _normalize_b3_open_interest_csv(
        self,
        text: str,
        *,
        request_date: date,
        tracked_assets: list[str],
    ) -> list[dict[str, Any]]:
        normalized = str(text or "").replace("\ufeff", "")
        if "No results found" in normalized or "Nenhum resultado" in normalized:
            return []

        rows_raw = [row for row in csv.reader(io.StringIO(normalized), delimiter=";")]
        header_idx = next(
            (
                idx
                for idx, row in enumerate(rows_raw)
                if row
                and any(cell.strip() in {"Ticker symbol", "Instrumento financeiro"} for cell in row)
            ),
            None,
        )
        if header_idx is None:
            return []

        header = [cell.strip() for cell in rows_raw[header_idx]]
        aliases = {
            "ticker": {"Ticker symbol", "Instrumento financeiro"},
            "isin": {"ISIN code", "Código ISIN"},
            "asset": {"Asset", "Ativo"},
            "expiration_code": {"Expiration code", "Código de expiração"},
            "segment": {"Segment", "Segmento"},
            "open_interest": {"Open interest", "Contratos em aberto"},
            "variation_open_interest": {
                "Variation open interest",
                "Variação de contratos em aberto",
            },
            "locked_contracts": {"Commodities locked qty", "Contratos travados"},
            "unlocked_transfer_contracts": {
                "Unlocked qty by transfer",
                "Contratos baixados por transferência",
            },
        }
        index_by_field: dict[str, int] = {}
        for field, options in aliases.items():
            for idx, name in enumerate(header):
                if name in options:
                    index_by_field[field] = idx
                    break

        tracked = {asset.upper() for asset in tracked_assets}
        rows: list[dict[str, Any]] = []
        for row in rows_raw[header_idx + 1 :]:
            if not row or not any(str(cell).strip() for cell in row):
                continue
            ticker = (
                str(
                    row[index_by_field.get("ticker", -1)]
                    if index_by_field.get("ticker") is not None
                    else ""
                )
                .strip()
                .upper()
            )
            asset = (
                str(
                    row[index_by_field.get("asset", -1)]
                    if index_by_field.get("asset") is not None
                    else ""
                )
                .strip()
                .upper()
            )
            if not ticker or not asset:
                continue
            if not self._is_b3_future_contract(ticker, asset):
                continue
            rows.append(
                {
                    "date": request_date.isoformat(),
                    "ticker": ticker,
                    "isin": row[index_by_field["isin"]].strip()
                    if "isin" in index_by_field and index_by_field["isin"] < len(row)
                    else None,
                    "asset": asset,
                    "expiration_code": row[index_by_field["expiration_code"]].strip()
                    if "expiration_code" in index_by_field
                    and index_by_field["expiration_code"] < len(row)
                    else None,
                    "segment": row[index_by_field["segment"]].strip()
                    if "segment" in index_by_field and index_by_field["segment"] < len(row)
                    else None,
                    "contract_type": "future",
                    "open_interest": int(
                        self._parse_b3_csv_number(row[index_by_field["open_interest"]]) or 0
                    )
                    if "open_interest" in index_by_field
                    and index_by_field["open_interest"] < len(row)
                    else 0,
                    "variation_open_interest": int(
                        self._parse_b3_csv_number(row[index_by_field["variation_open_interest"]])
                        or 0
                    )
                    if "variation_open_interest" in index_by_field
                    and index_by_field["variation_open_interest"] < len(row)
                    else 0,
                    "locked_contracts": int(
                        self._parse_b3_csv_number(row[index_by_field["locked_contracts"]]) or 0
                    )
                    if "locked_contracts" in index_by_field
                    and index_by_field["locked_contracts"] < len(row)
                    else 0,
                    "unlocked_transfer_contracts": int(
                        self._parse_b3_csv_number(
                            row[index_by_field["unlocked_transfer_contracts"]]
                        )
                        or 0
                    )
                    if "unlocked_transfer_contracts" in index_by_field
                    and index_by_field["unlocked_transfer_contracts"] < len(row)
                    else 0,
                    "tracked": asset in tracked,
                }
            )
        return rows

    @staticmethod
    def _is_b3_future_contract(ticker: str, asset: str) -> bool:
        suffix = ticker[len(asset) :] if ticker.startswith(asset) else ""
        return bool(
            len(suffix) == 3 and suffix[0] in B3_FUTURES_MONTH_CODES and suffix[1:].isdigit()
        )

    def _build_b3_open_interest_history(
        self,
        records: list[dict[str, Any]],
        *,
        tracked_assets: list[str],
        min_points: int,
    ) -> tuple[
        list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
    ]:
        tracked = {asset.upper() for asset in tracked_assets}
        history: list[dict[str, Any]] = []
        latest_rows = records[-1].get("rows") or []

        for record in records:
            date_text = str(record.get("date") or "")
            rows = [
                row
                for row in (record.get("rows") or [])
                if row.get("asset") in tracked and row.get("contract_type") == "future"
            ]
            by_asset: dict[str, dict[str, Any]] = {}
            for row in rows:
                asset = str(row.get("asset") or "")
                current = by_asset.setdefault(
                    asset,
                    {
                        "date": date_text,
                        "asset": asset,
                        "segment": row.get("segment"),
                        "open_interest": 0,
                        "variation_open_interest": 0,
                        "contracts": 0,
                        "futures_contracts": 0,
                    },
                )
                current["open_interest"] += int(row.get("open_interest") or 0)
                current["variation_open_interest"] += int(row.get("variation_open_interest") or 0)
                current["contracts"] += 1
                if row.get("contract_type") == "future":
                    current["futures_contracts"] += 1
            history.extend(by_asset.values())

        history = sorted(
            history, key=lambda row: (str(row.get("date") or ""), str(row.get("asset") or ""))
        )

        product_summary: list[dict[str, Any]] = []
        for asset in tracked_assets:
            rows = [row for row in history if row.get("asset") == asset]
            if not rows:
                continue
            latest = rows[-1]
            last_5 = rows[-5:]
            last_n = rows[-min_points:]
            latest_asset_contracts = [
                row
                for row in latest_rows
                if row.get("asset") == asset and row.get("contract_type") == "future"
            ]
            leader: dict[str, Any] = max(
                latest_asset_contracts,
                key=lambda row: int(row.get("open_interest") or 0),
                default={},
            )
            product_summary.append(
                {
                    "asset": asset,
                    "date": latest.get("date"),
                    "open_interest": int(latest.get("open_interest") or 0),
                    "variation_open_interest": int(latest.get("variation_open_interest") or 0),
                    "rolling_5d_variation_open_interest": int(
                        sum(int(row.get("variation_open_interest") or 0) for row in last_5)
                    ),
                    "rolling_21d_variation_open_interest": int(
                        sum(int(row.get("variation_open_interest") or 0) for row in last_n)
                    ),
                    "contracts": int(latest.get("contracts") or 0),
                    "leader_contract": leader.get("ticker"),
                    "leader_open_interest": int(leader.get("open_interest") or 0),
                    "leader_variation_open_interest": int(
                        leader.get("variation_open_interest") or 0
                    ),
                }
            )

        latest_contracts = sorted(
            [
                {
                    "date": row.get("date"),
                    "ticker": row.get("ticker"),
                    "asset": row.get("asset"),
                    "expiration_code": row.get("expiration_code"),
                    "segment": row.get("segment"),
                    "open_interest": row.get("open_interest"),
                    "variation_open_interest": row.get("variation_open_interest"),
                }
                for row in latest_rows
                if row.get("asset") in tracked and row.get("contract_type") == "future"
            ],
            key=lambda row: abs(int(row.get("open_interest") or 0)),
            reverse=True,
        )

        futures_by_asset: dict[str, dict[str, Any]] = {}
        for row in latest_rows:
            if row.get("contract_type") != "future":
                continue
            asset = str(row.get("asset") or "")
            current = futures_by_asset.setdefault(
                asset,
                {
                    "asset": asset,
                    "segment": row.get("segment"),
                    "open_interest": 0,
                    "variation_open_interest": 0,
                    "contracts": 0,
                },
            )
            current["open_interest"] += int(row.get("open_interest") or 0)
            current["variation_open_interest"] += int(row.get("variation_open_interest") or 0)
            current["contracts"] += 1

        futures_summary = sorted(
            futures_by_asset.values(),
            key=lambda row: abs(int(row.get("open_interest") or 0)),
            reverse=True,
        )[:25]
        return (
            history[-(min_points * max(len(tracked_assets), 1)) :],
            product_summary,
            latest_contracts,
            futures_summary,
        )

    def _b3_open_interest_assets(self) -> list[str]:
        raw = str(getattr(Config, "FUNDS_FLOW_LOCAL_B3_OPEN_INTEREST_ASSETS", "") or "")
        assets = [item.strip().upper() for item in raw.split(",") if item.strip()]
        if not assets:
            assets = list(B3_DEFAULT_OPEN_INTEREST_ASSETS)
        return list(dict.fromkeys(assets))

    @staticmethod
    def _build_b3_participant_positioning_status() -> dict[str, Any]:
        return {
            "status": "configured_not_public_bdi",
            "label": "Categoria de investidor por contrato",
            "source": "B3 UP2DATA Categoria de investidor",
            "note": (
                "O BDI publico traz participacao agregada por tipo de investidor e open interest por contrato. "
                "Comprado/vendido por Estrangeiro, Institucional, PF e Financeiras em DI/WDO/WIN exige a fonte "
                "Categoria de investidor/UP2DATA ou outro arquivo oficial credenciado."
            ),
            "fields_expected": [
                "date",
                "asset",
                "contract",
                "participant_type",
                "long_contracts",
                "short_contracts",
                "net_contracts",
            ],
        }

    def _candidate_bdi_dates(self, target_date: date, *, limit: int = 10) -> list[date]:
        candidates: list[date] = []
        cursor = target_date
        while len(candidates) < max(limit, 1):
            if cursor.weekday() < 5:
                candidates.append(cursor)
            cursor -= timedelta(days=1)
        return candidates

    def _parse_b3_bdi_investor_participation(self, pdf_path: str) -> dict[str, Any]:
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise RuntimeError("pypdf is required to parse B3 BDI PDFs") from exc

        reader = PdfReader(pdf_path)
        first_pages_text = "\n".join((page.extract_text() or "") for page in reader.pages[:3])
        daily_text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            normalized_page = _normalize_text(page_text)
            if (
                "TIPOS DE INVESTIDORES COMPRAS" in normalized_page
                and "DADOS ACUMULADOS" in normalized_page
                and "INVESTIDOR ESTRANGEIRO" in normalized_page
            ):
                daily_text = page_text
                break
        text = daily_text or first_pages_text
        data_until = None
        date_match = re.search(
            r"Dados acumulados do in[ií]cio do m[eê]s at[eé] o dia\s+(\d{2}/\d{2}/\d{4})",
            text,
            re.I,
        )
        date_match = (
            re.search(r"Dados acumulados.+?(\d{2}/\d{2}/\d{4})", text, re.I | re.S) or date_match
        )
        if date_match:
            day, month, year = date_match.group(1).split("/")
            data_until = f"{year}-{month}-{day}"

        participant_pattern = re.compile(
            r"(Institucionais|Institui[cç][oõ]es Financeiras|Investidor Estrangeiro|Investidores Individuais|Outros)\s+"
            r"([\d.]+)\s+([\d,]+)\s+([\d.]+)\s+([\d,]+)",
            re.I,
        )
        participants: list[dict[str, Any]] = []
        for match in participant_pattern.finditer(text):
            label = self._normalize_b3_participant_label(match.group(1))
            if any(item.get("participant_type") == label for item in participants):
                continue
            buy_brl = self._parse_b3_number(match.group(2)) * 1000
            buy_pct = self._parse_b3_decimal(match.group(3))
            sell_brl = self._parse_b3_number(match.group(4)) * 1000
            sell_pct = self._parse_b3_decimal(match.group(5))
            participants.append(
                {
                    "participant_type": label,
                    "raw_label": match.group(1),
                    "buy_brl": _safe_float(buy_brl, 2),
                    "buy_participation_pct": _safe_float(buy_pct, 4),
                    "sell_brl": _safe_float(sell_brl, 2),
                    "sell_participation_pct": _safe_float(sell_pct, 4),
                    "net_flow_brl": _safe_float(buy_brl - sell_brl, 2),
                    "turnover_brl": _safe_float(buy_brl + sell_brl, 2),
                }
            )

        total_buy = sum(float(item["buy_brl"] or 0) for item in participants)
        total_sell = sum(float(item["sell_brl"] or 0) for item in participants)
        return {
            "data_until": data_until,
            "unit": "BRL",
            "note": "Tabela B3 em R$ mil; payload converte para BRL. Saldo = compras - vendas.",
            "economic_indicators": self._parse_b3_economic_indicators(first_pages_text),
            "participants": participants,
            "totals": {
                "buy_brl": _safe_float(total_buy, 2),
                "sell_brl": _safe_float(total_sell, 2),
                "net_flow_brl": _safe_float(total_buy - total_sell, 2),
                "turnover_brl": _safe_float(total_buy + total_sell, 2),
            },
        }

    def _dedupe_b3_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_key: dict[str, dict[str, Any]] = {}
        for record in records:
            key = str(record.get("data_until") or record.get("publication_date") or "")
            if not key:
                continue
            by_key[key] = record
        return sorted(
            by_key.values(),
            key=lambda record: str(
                record.get("data_until") or record.get("publication_date") or ""
            ),
        )

    def _build_b3_investor_history(
        self,
        records: list[dict[str, Any]],
        *,
        min_points: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        previous_by_type: dict[str, dict[str, Any]] = {}
        for record in records:
            data_until = record.get("data_until") or record.get("publication_date")
            for participant in record.get("participants") or []:
                participant_type = participant.get("participant_type")
                previous = previous_by_type.get(str(participant_type))
                daily_buy = None
                daily_sell = None
                daily_net = None
                if previous and self._same_month(previous.get("date"), data_until):
                    daily_buy = (participant.get("buy_brl") or 0) - (
                        previous.get("buy_brl_mtd") or 0
                    )
                    daily_sell = (participant.get("sell_brl") or 0) - (
                        previous.get("sell_brl_mtd") or 0
                    )
                    daily_net = (participant.get("net_flow_brl") or 0) - (
                        previous.get("net_flow_brl_mtd") or 0
                    )

                row = {
                    "date": data_until,
                    "publication_date": record.get("publication_date"),
                    "participant_type": participant_type,
                    "buy_brl_mtd": participant.get("buy_brl"),
                    "sell_brl_mtd": participant.get("sell_brl"),
                    "net_flow_brl_mtd": participant.get("net_flow_brl"),
                    "turnover_brl_mtd": participant.get("turnover_brl"),
                    "daily_buy_brl": _safe_float(daily_buy, 2),
                    "daily_sell_brl": _safe_float(daily_sell, 2),
                    "daily_net_flow_brl": _safe_float(daily_net, 2),
                    "buy_participation_pct": participant.get("buy_participation_pct"),
                    "sell_participation_pct": participant.get("sell_participation_pct"),
                }
                rows.append(row)
                previous_by_type[str(participant_type)] = row

        rows = sorted(
            rows,
            key=lambda row: (str(row.get("date") or ""), str(row.get("participant_type") or "")),
        )
        trend_by_participant: list[dict[str, Any]] = []
        participant_types = sorted(
            {str(row.get("participant_type")) for row in rows if row.get("participant_type")}
        )
        for participant_type in participant_types:
            participant_rows = [
                row for row in rows if row.get("participant_type") == participant_type
            ]
            latest = participant_rows[-1] if participant_rows else {}
            daily_values = [
                row for row in participant_rows if row.get("daily_net_flow_brl") is not None
            ]
            last_5 = daily_values[-5:]
            last_n = daily_values[-min_points:]
            trend_by_participant.append(
                {
                    "participant_type": participant_type,
                    "date": latest.get("date"),
                    "net_flow_brl_mtd": latest.get("net_flow_brl_mtd"),
                    "daily_net_flow_brl": latest.get("daily_net_flow_brl"),
                    "rolling_5d_net_flow_brl": _safe_float(
                        sum(float(row.get("daily_net_flow_brl") or 0) for row in last_5),
                        2,
                    ),
                    "rolling_21d_net_flow_brl": _safe_float(
                        sum(float(row.get("daily_net_flow_brl") or 0) for row in last_n),
                        2,
                    ),
                    "history_points": len(participant_rows),
                    "daily_points": len(daily_values),
                    "buy_participation_pct": latest.get("buy_participation_pct"),
                    "sell_participation_pct": latest.get("sell_participation_pct"),
                }
            )
        return rows[-(min_points * 5) :], trend_by_participant

    @staticmethod
    def _same_month(left: Any, right: Any) -> bool:
        left_date = _parse_date(left)
        right_date = _parse_date(right)
        return bool(
            left_date
            and right_date
            and left_date.year == right_date.year
            and left_date.month == right_date.month
        )

    def _parse_b3_economic_indicators(self, text: str) -> list[dict[str, Any]]:
        section_match = re.search(
            r"Indicadores econ[oô]micos(.+?)Participa[cç][aã]o dos investidores", text, re.S | re.I
        )
        if not section_match:
            return []
        indicators: list[dict[str, Any]] = []
        for raw_line in section_match.group(1).splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or line.startswith("Dá publicidade") or line.startswith("Ativo "):
                continue
            value_match = re.search(r"([\d.]+,\d+)$", line)
            symbol_match = re.search(r"\b([A-Z]{2,}[A-Z0-9]{2,})\b", line)
            if not value_match or not symbol_match:
                continue
            indicators.append(
                {
                    "raw": line,
                    "asset": line.split(" ", 1)[0],
                    "symbol": symbol_match.group(1),
                    "value": _safe_float(self._parse_b3_decimal(value_match.group(1)), 8),
                }
            )
        return indicators[:20]

    def _build_b3_bdi_opportunities(self, latest: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": "investor_participation",
                "label": "Participacao dos investidores",
                "status": "active",
                "priority": "high",
                "use": "Saldos por Estrangeiro, Institucionais, Individuais, Financeiras e Outros; bom para cruzar com fluxo CVM.",
                "fields": [
                    "buy_brl",
                    "sell_brl",
                    "net_flow_brl",
                    "participation_pct",
                    "history_21d",
                ],
            },
            {
                "id": "derivatives_open_interest",
                "label": "Posicoes em aberto de derivativos",
                "status": "active",
                "priority": "high",
                "use": "Contratos em aberto por ativo/vencimento em DI, DOL, WDO, WIN, IND, DAP, DDI e demais futuros listados.",
                "fields": [
                    "ticker",
                    "asset",
                    "expiration_code",
                    "open_interest",
                    "variation_open_interest",
                    "history_21d",
                ],
            },
            {
                "id": "participant_positioning_by_contract",
                "label": "Categoria de investidor por contrato",
                "status": "configured_not_public_bdi",
                "priority": "high",
                "use": "Comprado/vendido por Estrangeiro, Institucional, Financeiras e Individuais em DI/WDO/WIN; fonte esperada e separada da B3/UP2DATA.",
                "fields": [
                    "long_contracts",
                    "short_contracts",
                    "net_contracts",
                    "participant_type",
                    "contract",
                ],
            },
            {
                "id": "economic_indicators",
                "label": "Indicadores economicos B3",
                "status": "extractable" if latest.get("economic_indicators") else "candidate",
                "priority": "medium",
                "use": "Indicadores usados para precificar futuros/opcoes, como IPCA pro rata, IDI/CDI e commodities quando publicados.",
                "fields": ["asset", "symbol", "value"],
            },
            {
                "id": "auction_notices",
                "label": "Leiloes, OPAs e comunicados",
                "status": "text_extractable",
                "priority": "medium",
                "use": "Calendario e eventos especiais que podem contaminar volume/fluxo de acoes especificas.",
                "fields": ["issuer", "ticker", "auction_date", "offer_price", "event_type"],
            },
            {
                "id": "secondary_market_context",
                "label": "Contexto de mercado secundario",
                "status": "candidate",
                "priority": "low",
                "use": "Aproveitar apenas se houver tabela estruturada estavel no BDI do dia; evitar parse fragil de anexos longos.",
                "fields": ["traded_volume", "auction_volume", "notices"],
            },
        ]

    @staticmethod
    def _normalize_b3_participant_label(value: str) -> str:
        normalized = _normalize_text(value)
        if "INSTITUICOES FINANCEIRAS" in normalized:
            return "Instituicoes Financeiras"
        if "INVESTIDOR ESTRANGEIRO" in normalized:
            return "Investidor Estrangeiro"
        if "INVESTIDORES INDIVIDUAIS" in normalized:
            return "Investidores Individuais"
        if "INSTITUCIONAIS" in normalized:
            return "Institucionais"
        return "Outros"

    @staticmethod
    def _parse_b3_number(value: str) -> float:
        text = str(value or "").replace(".", "").replace(",", ".")
        return float(text or 0)

    @staticmethod
    def _parse_b3_decimal(value: str) -> float:
        text = str(value or "").replace(".", "").replace(",", ".")
        return float(text or 0)
