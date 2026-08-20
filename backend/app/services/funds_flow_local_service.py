from __future__ import annotations

import copy
import json
import os
import threading
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

from ..config import Config
from ..domains.funds_flow.application.repositories import FundsFlowSnapshotRepository
from ..domains.funds_flow.application.source_ports import (
    AnbimaSource,
    B3Source,
    CvmSource,
    IciSource,
)
from ..domains.funds_flow.contracts import FundFlowSnapshot
from ..domains.funds_flow.contracts.source_catalog import (
    BCB_PTAX_PERIOD_URL,
    BCB_SGS_BASE_URL,
    BCB_SGS_SERIES,
    FUNDS_FLOW_LOCAL_SCHEMA_VERSION,
)
from ..domains.funds_flow.infrastructure import (
    AnbimaFundsFlowAdapter,
    B3FundsFlowAdapter,
    CvmFundsFlowAdapter,
    IciFundsFlowAdapter,
    JsonFundsFlowSnapshotRepository,
)
from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger
from .funds_flow_analytics import FundsFlowAnalyticsMixin
from .funds_flow_cftc import FundsFlowCftcMixin
from .funds_flow_utils import (
    _clean_json,
    _local_now,
    _max_iso_date_value,
    _parse_brazilian_date,
    _parse_date,
    _parse_iso,
    _period_to_window,
    _safe_float,
    _utc_now,
)

logger = get_logger("aquiles.funds_flow_local")


class FundsFlowLocalService(FundsFlowAnalyticsMixin, FundsFlowCftcMixin):
    """CVM-first Funds Flow Local data product and dashboard payload builder."""

    def __init__(
        self,
        root_dir: str | None = None,
        timeout_seconds: float | None = None,
        snapshot_repository: FundsFlowSnapshotRepository | None = None,
        cvm_source: CvmSource | None = None,
        anbima_source: AnbimaSource | None = None,
        b3_source: B3Source | None = None,
        ici_source: IciSource | None = None,
    ) -> None:
        self.root_dir: str = str(
            root_dir
            or getattr(
                Config,
                "FUNDS_FLOW_LOCAL_DATA_DIR",
                os.path.join(Config.MACRO_DATA_DIR, "funds_flow_local"),
            )
        )
        self.raw_dir = os.path.join(self.root_dir, "raw")
        self.derived_dir = os.path.join(self.root_dir, "derived")
        self.latest_path = os.path.join(self.root_dir, "latest.json")
        self.snapshots_path = os.path.join(self.root_dir, "snapshots.jsonl")
        self.snapshot_repository = snapshot_repository or JsonFundsFlowSnapshotRepository(
            self.root_dir
        )
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(Config, "FUNDS_FLOW_LOCAL_TIMEOUT_SECONDS", 45)
        )
        self._lock = threading.RLock()
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.derived_dir, exist_ok=True)
        source_options = {
            "raw_dir": self.raw_dir,
            "timeout_seconds": self.timeout_seconds,
        }
        self.cvm_source = cvm_source or CvmFundsFlowAdapter(**source_options)
        self.anbima_source = anbima_source or AnbimaFundsFlowAdapter(**source_options)
        self.b3_source = b3_source or B3FundsFlowAdapter(**source_options)
        self.ici_source = ici_source or IciFundsFlowAdapter(**source_options)

    def get_dashboard(
        self,
        *,
        target_date: str | date | None = None,
        period: str | None = "21d",
        history_days: int | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if not refresh:
            cached = self._fresh_cached_dashboard(
                target_date=target_date,
                period=period,
                history_days=history_days,
                allow_stale=True,
            )
            if cached is not None:
                return cached
        return self.collect(
            target_date=target_date, period=period, history_days=history_days, force=refresh
        )

    def collect(
        self,
        *,
        target_date: str | date | None = None,
        period: str | None = "21d",
        history_days: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if not force:
                cached = self._fresh_cached_dashboard(
                    target_date=target_date,
                    period=period,
                    history_days=history_days,
                )
                if cached is not None:
                    return cached

            started_at = _utc_now()
            resolved_period = str(period or "21d").strip() or "21d"
            requested_end_date = _parse_date(target_date) or _local_now().date()
            resolved_history_days = self._resolve_history_days(history_days, period=resolved_period)
            start_date = requested_end_date - timedelta(days=resolved_history_days + 10)

            informe_df, informe_status = self.cvm_source.load_informe_diario(
                start_date=start_date,
                end_date=requested_end_date,
                force=force,
            )
            if informe_df.empty:
                raise RuntimeError(
                    "CVM Informe Diario returned no usable rows for the requested window."
                )

            actual_as_of = self._select_complete_as_of_date(informe_df, requested_end_date)
            if actual_as_of < requested_end_date:
                logger.info(
                    "Funds Flow Local using latest available CVM date %s before requested %s",
                    actual_as_of,
                    requested_end_date,
                )
            informe_df = informe_df[informe_df["dt"].dt.date <= actual_as_of].copy()

            master_df, master_status = self.cvm_source.load_fund_registry(force=force)
            anbima_payload, anbima_status = self.anbima_source.load_funds(force=force)
            bcb_macro_payload, bcb_macro_status = self._load_bcb_macro(
                target_date=requested_end_date,
                history_days=resolved_history_days,
                force=force,
            )
            b3_etfs_payload, b3_etfs_status = self.b3_source.load_etfs(force=force)
            ici_payload, ici_status = self.ici_source.load_global_flows(force=force)
            cftc_payload, cftc_status = self._load_cftc_tff_positioning(force=force)
            b3_payload, b3_status = self.b3_source.load_investor_participation(
                target_date=requested_end_date,
                force=force,
            )
            b3_open_interest_payload, b3_open_interest_status = self.b3_source.load_open_interest(
                target_date=requested_end_date,
                force=force,
            )
            b3_monthly_payload, b3_monthly_status = (
                self.b3_source.load_monthly_investor_participation(
                    target_date=requested_end_date,
                    force=force,
                )
            )
            b3_market_data_payload, b3_market_data_status = self.b3_source.load_market_data_report(
                force=force
            )
            payload = self._build_dashboard(
                informe_df=informe_df,
                master_df=master_df,
                as_of_date=actual_as_of,
                requested_end_date=requested_end_date,
                period=resolved_period,
                history_days=resolved_history_days,
                started_at=started_at,
                source_status=[
                    *informe_status,
                    master_status,
                    anbima_status,
                    bcb_macro_status,
                    b3_etfs_status,
                    ici_status,
                    cftc_status,
                    b3_status,
                    b3_open_interest_status,
                    b3_monthly_status,
                    b3_market_data_status,
                ],
                anbima_funds=anbima_payload,
                ici_global_flows=ici_payload,
                cftc_positioning=cftc_payload,
                b3_investor_participation=b3_payload,
                b3_open_interest=b3_open_interest_payload,
                b3_investor_participation_monthly=b3_monthly_payload,
                b3_market_data_report=b3_market_data_payload,
                b3_etfs=b3_etfs_payload,
                bcb_macro=bcb_macro_payload,
            )

            self.snapshot_repository.save_latest(
                FundFlowSnapshot.model_validate(_clean_json(payload))
            )
            self._write_derived_files(payload)
            self._append_snapshot_summary(payload)
            return payload

    def _resolve_history_days(self, value: int | None, *, period: str | None) -> int:
        default_days = int(getattr(Config, "FUNDS_FLOW_LOCAL_HISTORY_DAYS", 95))
        try:
            days = int(value if value is not None else default_days)
        except Exception:
            days = default_days
        days = max(days, _period_to_window(period) + 15, 30)
        return max(30, min(days, 540))

    def _fresh_cached_dashboard(
        self,
        *,
        target_date: str | date | None,
        period: str | None,
        history_days: int | None,
        allow_stale: bool = False,
    ) -> dict[str, Any] | None:
        snapshot = self._read_latest()
        if not snapshot:
            return None
        report = snapshot.get("report") or {}
        if int(report.get("schema_version") or 0) < FUNDS_FLOW_LOCAL_SCHEMA_VERSION:
            return None
        required_payload_keys = ("etf_panel", "b3_etfs", "bcb_macro", "brazil_vs_global")
        if any(key not in snapshot for key in required_payload_keys):
            return None
        brazil_vs_global = snapshot.get("brazil_vs_global") or {}
        if "ici_global_flows" not in brazil_vs_global or "cftc_positioning" not in brazil_vs_global:
            return None
        if str(report.get("period") or "").lower() != str(period or "21d").lower():
            return None
        if history_days is not None and int(report.get("history_days") or 0) < int(history_days):
            return None
        parsed_target = _parse_date(target_date)
        if (
            parsed_target
            and str(report.get("requested_date") or report.get("as_of_date"))[:10]
            != parsed_target.isoformat()
        ):
            return None
        generated_at = _parse_iso(report.get("last_updated_at") or snapshot.get("generated_at"))
        if not generated_at:
            return None
        max_age_seconds = int(getattr(Config, "FUNDS_FLOW_LOCAL_CACHE_SECONDS", 900))
        cache_age_seconds = (_utc_now() - generated_at).total_seconds()
        if cache_age_seconds > max_age_seconds and not allow_stale:
            return None
        snapshot = copy.deepcopy(snapshot)
        report = snapshot.setdefault("report", {})
        report["cache_status"] = "stale" if cache_age_seconds > max_age_seconds else "fresh"
        report["cache_age_seconds"] = int(max(0, cache_age_seconds))
        report["cache_max_age_seconds"] = max_age_seconds
        return snapshot

    def _read_latest(self) -> dict[str, Any] | None:
        try:
            snapshot = self.snapshot_repository.load_latest()
            return snapshot.model_dump(mode="json") if snapshot else None
        except Exception:
            logger.exception("Failed to read Funds Flow Local latest snapshot")
            return None

    def read_latest_snapshot(self) -> dict[str, Any] | None:
        """Return the latest snapshot through the configured persistence port."""
        return self._read_latest()

    def _select_complete_as_of_date(self, df: pd.DataFrame, requested_end_date: date) -> date:
        rows = df[df["dt"].dt.date <= requested_end_date]
        if rows.empty:
            return df["dt"].max().date()
        counts = rows.groupby("dt")["cnpj_fundo"].count().sort_index()
        if counts.empty:
            return rows["dt"].max().date()
        recent = counts.tail(12)
        median_recent = float(recent.median()) if not recent.empty else float(counts.median())
        threshold = max(100.0, median_recent * 0.55)
        eligible = counts[counts >= threshold]
        if not eligible.empty:
            return eligible.index.max().date()
        return counts.idxmax().date()

    def _load_bcb_macro(
        self,
        *,
        target_date: date,
        history_days: int,
        force: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        status = {
            "id": "bcb_macro",
            "source": "BCB SGS/OData",
            "url": "https://dadosabertos.bcb.gov.br/",
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": None,
        }
        try:
            series_rows: list[dict[str, Any]] = []
            latest_by_series: dict[str, Any] = {}
            cache_paths: list[str] = []
            for definition in BCB_SGS_SERIES:
                min_days = int(definition.get("min_history_days") or history_days + 45)
                lookback_days = max(history_days + 45, min_days)
                start_date = target_date - timedelta(days=lookback_days)
                rows, cache_path = self._fetch_bcb_sgs_series(
                    definition, start_date, target_date, force=force
                )
                cache_paths.append(cache_path)
                series_rows.extend(rows)
                if rows:
                    latest_by_series[str(definition["key"])] = rows[-1]

            ptax_rows, ptax_cache = self._fetch_bcb_ptax_usd(
                target_date - timedelta(days=max(history_days + 45, 120)),
                target_date,
                force=force,
            )
            cache_paths.append(ptax_cache)
            latest_ptax = ptax_rows[-1] if ptax_rows else {}
            summary = {
                "latest_usdbrl_sgs": latest_by_series.get("usdbrl_sgs"),
                "latest_usdbrl_ptax": latest_ptax,
                "latest_selic_daily": latest_by_series.get("selic_daily"),
                "latest_selic_target": latest_by_series.get("selic_target"),
                "latest_ipca_monthly": latest_by_series.get("ipca_monthly"),
                "series_count": len(BCB_SGS_SERIES),
                "ptax_rows": len(ptax_rows),
            }
            payload = {
                "status": "ok",
                "source": "Banco Central do Brasil",
                "url": "https://dadosabertos.bcb.gov.br/",
                "sgs_endpoint": BCB_SGS_BASE_URL,
                "ptax_endpoint": BCB_PTAX_PERIOD_URL,
                "frequency": "daily_monthly",
                "series": series_rows,
                "latest_by_series": latest_by_series,
                "ptax_usd": ptax_rows,
                "summary": summary,
                "cached_paths": cache_paths,
            }
            status.update(
                {
                    "ok": True,
                    "rows": len(series_rows) + len(ptax_rows),
                    "cached_path": os.path.join(self.raw_dir, "bcb"),
                    "latest_data_date": _max_iso_date_value(
                        *(row.get("date") for row in latest_by_series.values()),
                        latest_ptax.get("date"),
                    ),
                }
            )
            return payload, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load BCB SGS/OData macro series: %s", exc)
            return {
                "status": "error",
                "source": "Banco Central do Brasil",
                "url": "https://dadosabertos.bcb.gov.br/",
                "error": str(exc),
                "series": [],
                "ptax_usd": [],
            }, status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def _fetch_bcb_sgs_series(
        self,
        definition: dict[str, Any],
        start_date: date,
        end_date: date,
        *,
        force: bool,
    ) -> tuple[list[dict[str, Any]], str]:
        code = int(definition["code"])
        key = str(definition["key"])
        cache_path = os.path.join(
            self.raw_dir,
            "bcb",
            "sgs",
            f"{key}_{code}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json",
        )
        if os.path.exists(cache_path) and not force and os.path.getsize(cache_path) > 0:
            with open(cache_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        else:
            params = {
                "formato": "json",
                "dataInicial": start_date.strftime("%d/%m/%Y"),
                "dataFinal": end_date.strftime("%d/%m/%Y"),
            }
            response = requests.get(
                BCB_SGS_BASE_URL.format(code=code),
                params=params,
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=max(self.timeout_seconds, 60),
            )
            if response.status_code == 404:
                raw = []
            else:
                response.raise_for_status()
                raw = response.json()
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            atomic_json_dump(cache_path, raw, indent=2)

        rows: list[dict[str, Any]] = []
        for item in raw or []:
            parsed_date = _parse_brazilian_date(item.get("data"))
            if not parsed_date:
                continue
            rows.append(
                {
                    "date": parsed_date.isoformat(),
                    "series_key": key,
                    "code": code,
                    "label": definition.get("label"),
                    "value": _safe_float(item.get("valor"), 8),
                    "unit": definition.get("unit"),
                    "frequency": definition.get("frequency"),
                    "group": definition.get("group"),
                    "source": "BCB SGS",
                }
            )
        rows.sort(key=lambda row: row["date"])
        return rows, cache_path

    def _fetch_bcb_ptax_usd(
        self,
        start_date: date,
        end_date: date,
        *,
        force: bool,
    ) -> tuple[list[dict[str, Any]], str]:
        cache_path = os.path.join(
            self.raw_dir,
            "bcb",
            "ptax",
            f"usd_ptax_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json",
        )
        if os.path.exists(cache_path) and not force and os.path.getsize(cache_path) > 0:
            with open(cache_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        else:
            params = {
                "@moeda": "'USD'",
                "@dataInicial": f"'{start_date.strftime('%m-%d-%Y')}'",
                "@dataFinalCotacao": f"'{end_date.strftime('%m-%d-%Y')}'",
                "$format": "json",
            }
            response = requests.get(
                BCB_PTAX_PERIOD_URL,
                params=params,
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=max(self.timeout_seconds, 60),
            )
            response.raise_for_status()
            raw = response.json()
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            atomic_json_dump(cache_path, raw, indent=2)

        by_date: dict[str, dict[str, Any]] = {}
        for item in (raw.get("value") if isinstance(raw, dict) else []) or []:
            timestamp = str(item.get("dataHoraCotacao") or "")
            day = timestamp[:10]
            if not day:
                continue
            record = {
                "date": day,
                "timestamp": timestamp,
                "cotacao_compra": _safe_float(item.get("cotacaoCompra"), 8),
                "cotacao_venda": _safe_float(item.get("cotacaoVenda"), 8),
                "paridade_compra": _safe_float(item.get("paridadeCompra"), 8),
                "paridade_venda": _safe_float(item.get("paridadeVenda"), 8),
                "tipo_boletim": item.get("tipoBoletim"),
                "source": "BCB PTAX OData",
            }
            current = by_date.get(day)
            if current is None or str(record.get("timestamp") or "") >= str(
                current.get("timestamp") or ""
            ):
                by_date[day] = record
        rows = [by_date[key] for key in sorted(by_date)]
        return rows, cache_path
