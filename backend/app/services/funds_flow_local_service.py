from __future__ import annotations

import base64
import copy
import csv
import html
import io
import json
import os
import re
import threading
import time
import zipfile
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from ..config import Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger
from .funds_flow_cftc import FundsFlowCftcMixin
from .funds_flow_contracts import (
    ANBIMA_BOLETIM_HOME_ENDPOINT,
    ANBIMA_BOLETIM_LIST_ENDPOINT,
    ANBIMA_CATEGORY_TO_MACRO,
    ANBIMA_CONSOLIDATED_DAILY_ENDPOINT,
    ANBIMA_PUBLICATION_POPULATE,
    ANBIMA_RANKING_ADMIN_ENDPOINT,
    ANBIMA_RANKING_MANAGER_ENDPOINT,
    ANBIMA_STRAPI_BASE_URL,
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
    BCB_PTAX_PERIOD_URL,
    BCB_SGS_BASE_URL,
    BCB_SGS_SERIES,
    CLASS_REGISTER_RENAME,
    CVM_CADASTRO_PACKAGE,
    CVM_CADASTRO_URL,
    CVM_CKAN_PACKAGE_URL,
    CVM_INFORME_PACKAGE,
    CVM_INFORME_PATTERN,
    CVM_REGISTRO_FUNDO_CLASSE_URL,
    FUND_REGISTER_RENAME,
    FUNDS_FLOW_LOCAL_SCHEMA_VERSION,
    ICI_MONTHLY_ETF_PAGE_URL,
    ICI_MUTUAL_FUND_WEEKLY_COLUMNS,
    ICI_SIMPLE_WEEKLY_COLUMNS,
    ICI_WEEKLY_FLOW_URLS,
    ICI_WORLDWIDE_COLUMNS,
    ICI_WORLDWIDE_PAGE_URL,
    INFORME_COLUMNS,
    INFORME_SOURCE_PRIORITY,
    MASTER_RENAME,
    SOURCE_INVENTORY,
    WINDOWS,
)
from .funds_flow_contracts import (
    CFTC_COT_EXTRA_DATASETS as CFTC_COT_EXTRA_DATASETS,
)
from .funds_flow_insights import FundsFlowInsightAgent
from .funds_flow_utils import (
    _classify_master_row,
    _clean_json,
    _local_now,
    _max_iso_date_value,
    _max_iso_datetime_value,
    _normalize_cnpj,
    _normalize_text,
    _now_iso,
    _parse_brazilian_date,
    _parse_date,
    _parse_iso,
    _path_mtime_iso,
    _period_to_window,
    _regime_from_pressure,
    _safe_div,
    _safe_float,
    _utc_now,
    _yyyymm_months,
    _zscore,
)

logger = get_logger("aquiles.funds_flow_local")

class FundsFlowLocalService(FundsFlowCftcMixin):
    """CVM-first Funds Flow Local data product and dashboard payload builder."""

    def __init__(self, root_dir: str | None = None, timeout_seconds: float | None = None) -> None:
        self.root_dir = root_dir or getattr(
            Config,
            "FUNDS_FLOW_LOCAL_DATA_DIR",
            os.path.join(Config.MACRO_DATA_DIR, "funds_flow_local"),
        )
        self.raw_dir = os.path.join(self.root_dir, "raw")
        self.derived_dir = os.path.join(self.root_dir, "derived")
        self.latest_path = os.path.join(self.root_dir, "latest.json")
        self.snapshots_path = os.path.join(self.root_dir, "snapshots.jsonl")
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(Config, "FUNDS_FLOW_LOCAL_TIMEOUT_SECONDS", 45)
        )
        self._lock = threading.RLock()
        self._ckan_cache: dict[str, dict[str, Any]] = {}
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.derived_dir, exist_ok=True)

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
        return self.collect(target_date=target_date, period=period, history_days=history_days, force=refresh)

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

            informe_df, informe_status = self._load_informe_diario(
                start_date=start_date,
                end_date=requested_end_date,
                force=force,
            )
            if informe_df.empty:
                raise RuntimeError("CVM Informe Diario returned no usable rows for the requested window.")

            actual_as_of = self._select_complete_as_of_date(informe_df, requested_end_date)
            if actual_as_of < requested_end_date:
                logger.info(
                    "Funds Flow Local using latest available CVM date %s before requested %s",
                    actual_as_of,
                    requested_end_date,
                )
            informe_df = informe_df[informe_df["dt"].dt.date <= actual_as_of].copy()

            master_df, master_status = self._load_cadastro(force=force)
            anbima_payload, anbima_status = self._load_anbima_funds(force=force)
            bcb_macro_payload, bcb_macro_status = self._load_bcb_macro(
                target_date=requested_end_date,
                history_days=resolved_history_days,
                force=force,
            )
            b3_etfs_payload, b3_etfs_status = self._load_b3_etfs(force=force)
            ici_payload, ici_status = self._load_ici_global_flows(force=force)
            cftc_payload, cftc_status = self._load_cftc_tff_positioning(force=force)
            b3_payload, b3_status = self._load_b3_investor_participation(
                target_date=requested_end_date,
                force=force,
            )
            b3_open_interest_payload, b3_open_interest_status = self._load_b3_open_interest(
                target_date=requested_end_date,
                force=force,
            )
            b3_monthly_payload, b3_monthly_status = self._load_b3_investor_participation_monthly(
                target_date=requested_end_date,
                force=force,
            )
            b3_market_data_payload, b3_market_data_status = self._load_b3_market_data_report(force=force)
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

            atomic_json_dump(self.latest_path, _clean_json(payload), indent=2)
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
        if parsed_target and str(report.get("requested_date") or report.get("as_of_date"))[:10] != parsed_target.isoformat():
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
            with open(self.latest_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None
        except Exception:
            logger.exception("Failed to read Funds Flow Local latest snapshot")
            return None

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

    def _load_informe_diario(
        self,
        *,
        start_date: date,
        end_date: date,
        force: bool,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        resources = self._discover_cvm_informe_resources()
        required_months = _yyyymm_months(start_date, end_date)
        frames: list[pd.DataFrame] = []
        statuses: list[dict[str, Any]] = []

        for yyyymm in required_months:
            if resources and yyyymm not in resources:
                logger.info(
                    "Skipping CVM Informe Diario %s because CKAN has not published this month yet",
                    yyyymm,
                )
                continue
            url = resources.get(yyyymm) or CVM_INFORME_PATTERN.format(yyyymm=yyyymm)
            frame, status = self._read_informe_month(yyyymm=yyyymm, url=url, force=force)
            statuses.append(status)
            if not frame.empty:
                frames.append(frame)

        if not frames and resources:
            for yyyymm in sorted(resources.keys(), reverse=True)[:4]:
                frame, status = self._read_informe_month(yyyymm=yyyymm, url=resources[yyyymm], force=force)
                statuses.append(status)
                if not frame.empty:
                    frames.append(frame)

        if not frames:
            return pd.DataFrame(columns=INFORME_COLUMNS.values()), statuses

        df = pd.concat(frames, ignore_index=True)
        filtered = df[(df["dt"].dt.date >= start_date) & (df["dt"].dt.date <= end_date)].copy()
        if filtered.empty and not df.empty:
            actual_end = df["dt"].max().date()
            fallback_start = actual_end - (end_date - start_date)
            filtered = df[(df["dt"].dt.date >= fallback_start) & (df["dt"].dt.date <= actual_end)].copy()
        df = filtered
        df = df.dropna(subset=["dt", "cnpj_fundo"])
        df = df[df["cnpj_fundo"] != ""]
        return df, statuses

    def _discover_cvm_informe_resources(self) -> dict[str, str]:
        package = self._fetch_ckan_package(CVM_INFORME_PACKAGE)
        resources: dict[str, str] = {}
        for resource in package.get("resources") or []:
            url = str(resource.get("url") or "")
            name = str(resource.get("name") or "")
            match = re.search(r"inf_diario_fi_(\d{6})\.zip", f"{url} {name}", flags=re.IGNORECASE)
            if match and url:
                resources[match.group(1)] = url
        return resources

    def _fetch_ckan_package(self, package_id: str) -> dict[str, Any]:
        cached = self._ckan_cache.get(package_id)
        if cached:
            return cached
        try:
            response = requests.get(
                CVM_CKAN_PACKAGE_URL,
                params={"id": package_id},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result") or {}
            self._ckan_cache[package_id] = result
            return result
        except Exception as exc:
            logger.warning("Failed to discover CVM CKAN resources for %s: %s", package_id, exc)
            return {}

    def _read_informe_month(self, *, yyyymm: str, url: str, force: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
        started = time.monotonic()
        cache_path = os.path.join(self.raw_dir, "cvm_informe", f"inf_diario_fi_{yyyymm}.zip")
        status = {
            "id": f"cvm_informe_diario_{yyyymm}",
            "source": "CVM Informe Diario",
            "url": url,
            "month": yyyymm,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": cache_path,
        }
        try:
            self._download(url, cache_path, force=force)
            with zipfile.ZipFile(cache_path) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if not csv_names:
                    raise RuntimeError("ZIP has no CSV file")
                with archive.open(csv_names[0]) as handle:
                    raw = pd.read_csv(
                        handle,
                        sep=";",
                        encoding="latin1",
                        dtype={"CNPJ_FUNDO": str},
                        low_memory=False,
                        usecols=lambda column: str(column).strip().upper() in INFORME_COLUMNS,
                    )
            frame = self._normalize_informe(raw)
            status["ok"] = not frame.empty
            status["rows"] = int(len(frame))
            status["latest_data_date"] = frame["dt"].max().date().isoformat() if not frame.empty else None
            return frame, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load CVM Informe Diario %s: %s", yyyymm, exc)
            return pd.DataFrame(columns=INFORME_COLUMNS.values()), status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def _normalize_informe(self, raw: pd.DataFrame) -> pd.DataFrame:
        normalized: dict[str, pd.Series] = {}
        for source_column in raw.columns:
            target = INFORME_COLUMNS.get(str(source_column).strip().upper())
            if not target:
                continue
            if target in normalized:
                normalized[target] = normalized[target].where(normalized[target].notna(), raw[source_column])
            else:
                normalized[target] = raw[source_column]
        df = pd.DataFrame(index=raw.index)
        for column in sorted(set(INFORME_COLUMNS.values())):
            df[column] = normalized.get(column, pd.Series(np.nan, index=raw.index))
        df["cnpj_fundo"] = df["cnpj_fundo"].map(_normalize_cnpj)
        df["id_subclasse"] = df["id_subclasse"].fillna("").astype(str).str.strip()
        df["tp_fundo_classe"] = df["tp_fundo_classe"].fillna("").astype(str).str.strip()
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        for column in ["vl_total", "vl_quota", "pl", "captacao", "resgate", "cotistas"]:
            df[column] = pd.to_numeric(
                df[column].astype(str).str.replace(",", ".", regex=False).str.strip(),
                errors="coerce",
            )
        df[["captacao", "resgate", "cotistas"]] = df[["captacao", "resgate", "cotistas"]].fillna(0.0)
        df = df.dropna(subset=["dt", "cnpj_fundo"]).copy()
        df["_source_priority"] = (
            df["tp_fundo_classe"].str.upper().map(INFORME_SOURCE_PRIORITY).fillna(99).astype(int)
        )
        df = (
            df.sort_values(["dt", "cnpj_fundo", "id_subclasse", "_source_priority", "pl"], ascending=[True, True, True, True, False])
            .drop_duplicates(["dt", "cnpj_fundo", "id_subclasse"], keep="first")
            .reset_index(drop=True)
        )
        df["series_id"] = np.where(
            df["id_subclasse"].ne(""),
            df["cnpj_fundo"].astype(str) + "::" + df["id_subclasse"].astype(str),
            df["cnpj_fundo"].astype(str),
        )
        return df.drop(columns=["_source_priority"], errors="ignore")

    def _load_cadastro(self, *, force: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
        legacy_master, legacy_status = self._load_cadastro_legacy(force=force)
        class_master, class_status = self._load_cadastro_rcvm175(force=force)
        frames = []
        if not legacy_master.empty:
            legacy_master = legacy_master.copy()
            legacy_master["_priority"] = 1
            frames.append(legacy_master)
        if not class_master.empty:
            class_master = class_master.copy()
            class_master["_priority"] = 2
            frames.append(class_master)
        if frames:
            master = (
                pd.concat(frames, ignore_index=True, sort=False)
                .sort_values(["cnpj_fundo", "_priority"])
                .drop_duplicates("cnpj_fundo", keep="last")
                .drop(columns=["_priority"], errors="ignore")
            )
        else:
            master = pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "macro_classe"])

        status = {
            "id": "cvm_cadastro_fi",
            "source": "CVM Cadastro FI",
            "url": CVM_REGISTRO_FUNDO_CLASSE_URL,
            "ok": bool(legacy_status.get("ok") or class_status.get("ok")),
            "rows": int(len(master)),
            "error": class_status.get("error") or legacy_status.get("error"),
            "latency_ms": int(legacy_status.get("latency_ms") or 0) + int(class_status.get("latency_ms") or 0),
            "children": [legacy_status, class_status],
        }
        return master, status

    def _load_cadastro_legacy(self, *, force: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
        started = time.monotonic()
        resources = self._fetch_ckan_package(CVM_CADASTRO_PACKAGE)
        url = CVM_CADASTRO_URL
        for resource in resources.get("resources") or []:
            candidate = str(resource.get("url") or "")
            if candidate.lower().endswith("/cad_fi.csv") or candidate.lower().endswith("cad_fi.csv"):
                url = candidate
                break

        cache_path = os.path.join(self.raw_dir, "cvm_cadastro", "cad_fi.csv")
        status = {
            "id": "cvm_cadastro_fi",
            "source": "CVM Cadastro FI",
            "url": url,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": cache_path,
        }
        try:
            self._download(url, cache_path, force=force)
            raw = pd.read_csv(
                cache_path,
                sep=";",
                encoding="latin1",
                dtype={"CNPJ_FUNDO": str},
                low_memory=False,
                usecols=lambda column: str(column).strip().upper() in MASTER_RENAME,
            )
            master = self._normalize_master(raw)
            status["ok"] = not master.empty
            status["rows"] = int(len(master))
            return master, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load CVM Cadastro FI: %s", exc)
            return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "macro_classe"]), status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def _load_cadastro_rcvm175(self, *, force: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
        started = time.monotonic()
        resources = self._fetch_ckan_package(CVM_CADASTRO_PACKAGE)
        url = CVM_REGISTRO_FUNDO_CLASSE_URL
        for resource in resources.get("resources") or []:
            candidate = str(resource.get("url") or "")
            candidate_lower = candidate.lower()
            if candidate_lower.endswith("/dados/registro_fundo_classe.zip") or (
                candidate_lower.endswith("registro_fundo_classe.zip") and "/meta/" not in candidate_lower
            ):
                url = candidate
                break

        cache_path = os.path.join(self.raw_dir, "cvm_cadastro", "registro_fundo_classe.zip")
        status = {
            "id": "cvm_cadastro_fi_rcvm175",
            "source": "CVM Cadastro FI RCVM175",
            "url": url,
            "ok": False,
            "rows": 0,
            "error": None,
            "latency_ms": None,
            "cached_path": cache_path,
        }
        try:
            self._download(url, cache_path, force=force)
            with zipfile.ZipFile(cache_path) as archive:
                with archive.open("registro_classe.csv") as handle:
                    classes = pd.read_csv(handle, sep=";", encoding="latin1", dtype=str, low_memory=False)
                with archive.open("registro_fundo.csv") as handle:
                    funds = pd.read_csv(handle, sep=";", encoding="latin1", dtype=str, low_memory=False)

            classes = classes.rename(columns={column: CLASS_REGISTER_RENAME.get(str(column).strip(), column) for column in classes.columns})
            funds = funds.rename(columns={column: FUND_REGISTER_RENAME.get(str(column).strip(), column) for column in funds.columns})
            keep_funds = [column for column in ["id_registro_fundo", "administrador", "gestor"] if column in funds.columns]
            if keep_funds:
                classes = classes.merge(funds[keep_funds].drop_duplicates("id_registro_fundo"), on="id_registro_fundo", how="left")

            for column in [
                "cnpj_fundo",
                "nome_fundo",
                "classe_cvm",
                "classe_anbima",
                "tipo_fundo",
                "administrador",
                "gestor",
                "situacao",
                "data_registro",
                "data_inicio",
                "condominio",
                "fundo_exclusivo",
                "publico_alvo",
            ]:
                if column not in classes.columns:
                    classes[column] = None
            master = classes[
                [
                    "cnpj_fundo",
                    "nome_fundo",
                    "classe_cvm",
                    "classe_anbima",
                    "tipo_fundo",
                    "administrador",
                    "gestor",
                    "situacao",
                    "data_registro",
                    "data_inicio",
                    "condominio",
                    "fundo_exclusivo",
                    "publico_alvo",
                ]
            ].copy()
            master["cnpj_fundo"] = master["cnpj_fundo"].map(_normalize_cnpj)
            master = master[master["cnpj_fundo"] != ""].drop_duplicates("cnpj_fundo", keep="last")
            classified = master.apply(_classify_master_row, axis=1, result_type="expand")
            classified.columns = ["macro_classe", "subclasse", "strategy_tag", "classification_confidence"]
            master = pd.concat([master, classified], axis=1)
            master["is_active"] = ~master["situacao"].astype(str).str.upper().str.contains("CANCEL|ENCERR", regex=True, na=False)
            status["ok"] = not master.empty
            status["rows"] = int(len(master))
            return master, status
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("Failed to load CVM Cadastro FI RCVM175: %s", exc)
            return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "macro_classe"]), status
        finally:
            status["latency_ms"] = int((time.monotonic() - started) * 1000)

    def _normalize_master(self, raw: pd.DataFrame) -> pd.DataFrame:
        raw = raw.rename(columns={column: MASTER_RENAME.get(str(column).strip().upper(), column) for column in raw.columns})
        for column in MASTER_RENAME.values():
            if column not in raw.columns:
                raw[column] = None
        master = raw[list(MASTER_RENAME.values())].copy()
        master["cnpj_fundo"] = master["cnpj_fundo"].map(_normalize_cnpj)
        master = master[master["cnpj_fundo"] != ""].drop_duplicates("cnpj_fundo", keep="last")

        classified = master.apply(_classify_master_row, axis=1, result_type="expand")
        classified.columns = ["macro_classe", "subclasse", "strategy_tag", "classification_confidence"]
        master = pd.concat([master, classified], axis=1)
        master["is_active"] = ~master["situacao"].astype(str).str.upper().str.contains("CANCEL|ENCERR", regex=True, na=False)
        return master

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
        parsed = FundsFlowLocalService._safe_ici_number(value)
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

    def _load_b3_investor_participation(
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
            for candidate_date in self._candidate_bdi_dates(target_date, limit=max(45, min_points * 3)):
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
                    self._download(url, cache_path, force=force and candidate_date >= recent_refresh_cutoff)
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
                raise RuntimeError("No B3 BDI investor participation table found in the candidate window.")

            records = self._dedupe_b3_records(records)
            latest = records[-1]
            history, trend_by_participant = self._build_b3_investor_history(records, min_points=min_points)
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

    def _load_b3_open_interest(
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

            for candidate_date in self._candidate_bdi_dates(target_date, limit=max(45, min_points * 3)):
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
                sample_errors = "; ".join(errors[:3]) if errors else "nenhuma linha publicada no intervalo consultado"
                raise RuntimeError(
                    "B3 retornou a tabela OpenPositionsEquities sem linhas publicadas no intervalo consultado. "
                    f"Amostra: {sample_errors}"
                )

            records = sorted(records, key=lambda item: str(item.get("date") or ""))
            latest = records[-1]
            history, product_summary, latest_contracts, futures_summary = self._build_b3_open_interest_history(
                records,
                tracked_assets=tracked_assets,
                min_points=min_points,
            )
            cache_path = self._b3_table_cache_path(B3_DERIVATIVE_OPEN_INTEREST_TABLE, _parse_date(latest.get("date")) or target_date)
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

    def _load_b3_investor_participation_monthly(
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
                        period_label = period_label or self._extract_b3_monthly_period_label_from_text(csv_text)
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
            sample_errors = "; ".join(errors[:3]) if errors else "nenhuma linha publicada no intervalo consultado"
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

    def _load_b3_market_data_report(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
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
                response = requests.get(B3_MARKET_DATA_REPORT_URL, timeout=max(self.timeout_seconds, 60))
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
            row_count = sum(len(payload.get(name) or []) for name in [
                "trading_volume_monthly",
                "average_daily_trading_value",
                "total_trades",
                "daily_average_trades",
                "investor_participation_monthly",
                "foreign_investor_flow_monthly",
            ])
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

    def _load_b3_etfs(self, *, force: bool) -> tuple[dict[str, Any], dict[str, Any]]:
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
                rows = self._normalize_b3_funds_listed(raw, fund_type=fund_type, category_label=category_label)
                all_rows.extend(rows)
                categories.append(
                    {
                        "fund_type": fund_type,
                        "category": category_label,
                        "count": len(rows),
                        "total_records": int((raw.get("page") or {}).get("totalRecords") or len(rows) or 0),
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
                return json.load(handle)

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
        return response.json()

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
                rows, cache_path = self._fetch_bcb_sgs_series(definition, start_date, target_date, force=force)
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
            if current is None or str(record.get("timestamp") or "") >= str(current.get("timestamp") or ""):
                by_date[day] = record
        rows = [by_date[key] for key in sorted(by_date)]
        return rows, cache_path

    def _normalize_b3_investor_participation_monthly(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
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
                if row and any(cell.strip() in {"Investor types", "Tipos de investidores"} for cell in row)
            ),
            None,
        )
        if header_idx is None:
            return []

        parsed: list[dict[str, Any]] = []
        for row in rows_raw[header_idx + 1:]:
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
                ["period", "cash_brl_million", "forward_brl_million", "options_brl_million", "blocks_brl_million", "total_brl_million"],
            ),
            "average_daily_trading_value": self._parse_b3_market_table(
                lines,
                "Volume M",
                ["period", "brl_million", "variation_pct", "usd_million", "usd_variation_pct"],
            ),
            "total_trades": self._parse_b3_market_table(
                lines,
                "Nº de Negócios Total",
                ["period", "cash_trades", "forward_trades", "options_trades", "blocks_trades", "total_trades"],
            ),
            "daily_average_trades": self._parse_b3_market_table(
                lines,
                "Nº de Negócios Médio Diário",
                ["period", "trades", "variation_pct"],
            ),
            "investor_participation_monthly": self._parse_b3_market_table(
                lines,
                "Fatia de investidores",
                ["period", "individuals_pct", "institutions_pct", "foreign_pct", "financial_institutions_pct", "others_pct"],
                skip_header_rows=2,
            ),
            "foreign_investor_flow_monthly": self._parse_b3_market_table(
                lines,
                "Movimentação dos Investidores Estrangeiros Mensal",
                ["period", "buy_brl_million", "sell_brl_million", "ipo_follow_on_brl_million", "balance_brl_million"],
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
            for col, value in zip(columns[1:], parts[1:]):
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

    def _load_b3_table_export(self, table_name: str, table_date: date, *, force: bool) -> dict[str, Any]:
        cache_path = self._b3_table_cache_path(table_name, table_date)
        if os.path.exists(cache_path) and not force and os.path.getsize(cache_path) > 0:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return json.load(handle)

        payload = {
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
        data = response.json()
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        atomic_json_dump(cache_path, _clean_json(data), indent=2)
        return data

    def _load_b3_table_export_csv(self, table_name: str, table_date: date, *, force: bool, lang: str = "en-US") -> str:
        cache_path = self._b3_table_csv_cache_path(table_name, table_date, lang)
        if os.path.exists(cache_path) and not force and os.path.getsize(cache_path) > 0:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return handle.read()

        payload = {
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

    def _b3_table_csv_cache_path(self, table_name: str, table_date: date, lang: str = "en-US") -> str:
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
                if row and any(cell.strip() in {"Ticker symbol", "Instrumento financeiro"} for cell in row)
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
            "variation_open_interest": {"Variation open interest", "Variação de contratos em aberto"},
            "locked_contracts": {"Commodities locked qty", "Contratos travados"},
            "unlocked_transfer_contracts": {"Unlocked qty by transfer", "Contratos baixados por transferência"},
        }
        index_by_field: dict[str, int] = {}
        for field, options in aliases.items():
            for idx, name in enumerate(header):
                if name in options:
                    index_by_field[field] = idx
                    break

        tracked = {asset.upper() for asset in tracked_assets}
        rows: list[dict[str, Any]] = []
        for row in rows_raw[header_idx + 1:]:
            if not row or not any(str(cell).strip() for cell in row):
                continue
            ticker = str(row[index_by_field.get("ticker", -1)] if index_by_field.get("ticker") is not None else "").strip().upper()
            asset = str(row[index_by_field.get("asset", -1)] if index_by_field.get("asset") is not None else "").strip().upper()
            if not ticker or not asset:
                continue
            if not self._is_b3_future_contract(ticker, asset):
                continue
            rows.append(
                {
                    "date": request_date.isoformat(),
                    "ticker": ticker,
                    "isin": row[index_by_field["isin"]].strip() if "isin" in index_by_field and index_by_field["isin"] < len(row) else None,
                    "asset": asset,
                    "expiration_code": row[index_by_field["expiration_code"]].strip() if "expiration_code" in index_by_field and index_by_field["expiration_code"] < len(row) else None,
                    "segment": row[index_by_field["segment"]].strip() if "segment" in index_by_field and index_by_field["segment"] < len(row) else None,
                    "contract_type": "future",
                    "open_interest": int(self._parse_b3_csv_number(row[index_by_field["open_interest"]]) or 0) if "open_interest" in index_by_field and index_by_field["open_interest"] < len(row) else 0,
                    "variation_open_interest": int(self._parse_b3_csv_number(row[index_by_field["variation_open_interest"]]) or 0) if "variation_open_interest" in index_by_field and index_by_field["variation_open_interest"] < len(row) else 0,
                    "locked_contracts": int(self._parse_b3_csv_number(row[index_by_field["locked_contracts"]]) or 0) if "locked_contracts" in index_by_field and index_by_field["locked_contracts"] < len(row) else 0,
                    "unlocked_transfer_contracts": int(self._parse_b3_csv_number(row[index_by_field["unlocked_transfer_contracts"]]) or 0) if "unlocked_transfer_contracts" in index_by_field and index_by_field["unlocked_transfer_contracts"] < len(row) else 0,
                    "tracked": asset in tracked,
                }
            )
        return rows

    @staticmethod
    def _is_b3_future_contract(ticker: str, asset: str) -> bool:
        suffix = ticker[len(asset):] if ticker.startswith(asset) else ""
        return bool(
            len(suffix) == 3
            and suffix[0] in B3_FUTURES_MONTH_CODES
            and suffix[1:].isdigit()
        )

    def _build_b3_open_interest_history(
        self,
        records: list[dict[str, Any]],
        *,
        tracked_assets: list[str],
        min_points: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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

        history = sorted(history, key=lambda row: (str(row.get("date") or ""), str(row.get("asset") or "")))

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
            leader = max(latest_asset_contracts, key=lambda row: int(row.get("open_interest") or 0), default={})
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
                    "leader_variation_open_interest": int(leader.get("variation_open_interest") or 0),
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
        return history[-(min_points * max(len(tracked_assets), 1)):], product_summary, latest_contracts, futures_summary

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
        date_match = re.search(r"Dados acumulados do in[ií]cio do m[eê]s at[eé] o dia\s+(\d{2}/\d{2}/\d{4})", text, re.I)
        date_match = re.search(r"Dados acumulados.+?(\d{2}/\d{2}/\d{4})", text, re.I | re.S) or date_match
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
            key=lambda record: str(record.get("data_until") or record.get("publication_date") or ""),
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
                    daily_buy = (participant.get("buy_brl") or 0) - (previous.get("buy_brl_mtd") or 0)
                    daily_sell = (participant.get("sell_brl") or 0) - (previous.get("sell_brl_mtd") or 0)
                    daily_net = (participant.get("net_flow_brl") or 0) - (previous.get("net_flow_brl_mtd") or 0)

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

        rows = sorted(rows, key=lambda row: (str(row.get("date") or ""), str(row.get("participant_type") or "")))
        trend_by_participant: list[dict[str, Any]] = []
        participant_types = sorted({str(row.get("participant_type")) for row in rows if row.get("participant_type")})
        for participant_type in participant_types:
            participant_rows = [row for row in rows if row.get("participant_type") == participant_type]
            latest = participant_rows[-1] if participant_rows else {}
            daily_values = [
                row
                for row in participant_rows
                if row.get("daily_net_flow_brl") is not None
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
        return rows[-(min_points * 5):], trend_by_participant

    @staticmethod
    def _same_month(left: Any, right: Any) -> bool:
        left_date = _parse_date(left)
        right_date = _parse_date(right)
        return bool(left_date and right_date and left_date.year == right_date.year and left_date.month == right_date.month)

    def _parse_b3_economic_indicators(self, text: str) -> list[dict[str, Any]]:
        section_match = re.search(r"Indicadores econ[oô]micos(.+?)Participa[cç][aã]o dos investidores", text, re.S | re.I)
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
                "fields": ["buy_brl", "sell_brl", "net_flow_brl", "participation_pct", "history_21d"],
            },
            {
                "id": "derivatives_open_interest",
                "label": "Posicoes em aberto de derivativos",
                "status": "active",
                "priority": "high",
                "use": "Contratos em aberto por ativo/vencimento em DI, DOL, WDO, WIN, IND, DAP, DDI e demais futuros listados.",
                "fields": ["ticker", "asset", "expiration_code", "open_interest", "variation_open_interest", "history_21d"],
            },
            {
                "id": "participant_positioning_by_contract",
                "label": "Categoria de investidor por contrato",
                "status": "configured_not_public_bdi",
                "priority": "high",
                "use": "Comprado/vendido por Estrangeiro, Institucional, Financeiras e Individuais em DI/WDO/WIN; fonte esperada e separada da B3/UP2DATA.",
                "fields": ["long_contracts", "short_contracts", "net_contracts", "participant_type", "contract"],
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

    def _download(self, url: str, target_path: str, *, force: bool) -> None:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if os.path.exists(target_path) and not force and os.path.getsize(target_path) > 0:
            return
        response = requests.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        temp_path = f"{target_path}.tmp"
        with open(temp_path, "wb") as handle:
            handle.write(response.content)
        os.replace(temp_path, target_path)

    def _build_dashboard(
        self,
        *,
        informe_df: pd.DataFrame,
        master_df: pd.DataFrame,
        as_of_date: date,
        requested_end_date: date,
        period: str,
        history_days: int,
        started_at: datetime,
        source_status: list[dict[str, Any]],
        anbima_funds: dict[str, Any] | None = None,
        ici_global_flows: dict[str, Any] | None = None,
        cftc_positioning: dict[str, Any] | None = None,
        b3_investor_participation: dict[str, Any] | None = None,
        b3_open_interest: dict[str, Any] | None = None,
        b3_investor_participation_monthly: dict[str, Any] | None = None,
        b3_market_data_report: dict[str, Any] | None = None,
        b3_etfs: dict[str, Any] | None = None,
        bcb_macro: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fund_df = self._build_fund_daily(informe_df, master_df)
        class_daily = self._build_class_daily(fund_df)
        industry_daily = self._build_industry_daily(fund_df)

        if industry_daily.empty:
            raise RuntimeError("Funds Flow Local analytics produced no industry rows.")

        industry_latest = industry_daily[industry_daily["dt"].dt.date <= as_of_date].tail(1)
        if industry_latest.empty:
            industry_latest = industry_daily.tail(1)
        latest = industry_latest.iloc[0]
        as_of_date = latest["dt"].date()

        kpis = self._build_kpis(industry_daily, latest=latest, as_of_date=as_of_date)
        class_latest = class_daily[class_daily["dt"].dt.date == as_of_date].copy()
        top_inflows = self._ranking_by_class(class_latest, ascending=False, top_n=5)
        top_outflows = self._ranking_by_class(class_latest, ascending=True, top_n=5)
        anbima_payload = copy.deepcopy(anbima_funds) if anbima_funds else {"status": "not_loaded"}
        anbima_payload["validation"] = self._build_anbima_validation(
            class_latest,
            anbima_payload,
            as_of_date=as_of_date,
        )

        payload: dict[str, Any] = {
            "ok": True,
            "generated_at": _now_iso(),
            "report": {
                "name": "Funds Flow Local",
                "as_of_date": as_of_date.isoformat(),
                "requested_date": requested_end_date.isoformat(),
                "period": period,
                "history_days": history_days,
                "schema_version": FUNDS_FLOW_LOCAL_SCHEMA_VERSION,
                "currency": "BRL",
                "sources": [
                    "CVM Informe Diario",
                    "CVM Cadastro FI",
                    "ANBIMA Estatisticas",
                    "BCB",
                    "ICI",
                    "FRED",
                    "B3",
                    "CFTC COT",
                ],
                "primary_source": "CVM Informe Diario FI",
                "last_updated_at": _now_iso(),
                "started_at": started_at.isoformat(),
                "completed_at": _now_iso(),
                "lineage": {
                    "raw_dir": self.raw_dir,
                    "derived_dir": self.derived_dir,
                    "informe_months": sorted(
                        {
                            str(item.get("month"))
                            for item in source_status
                            if str(item.get("id", "")).startswith("cvm_informe_diario_")
                        }
                    ),
                },
            },
            "kpis": kpis,
            "top_inflows": top_inflows,
            "top_outflows": top_outflows,
            "timeseries": {
                "flow_by_class": self._records_flow_by_class(class_daily, as_of_date=as_of_date),
                "industry_flow": self._records_industry_flow(industry_daily, as_of_date=as_of_date),
                "monthly_stacked_flow": self._records_monthly_flow(class_daily, as_of_date=as_of_date),
            },
            "heatmap": self._build_heatmap(class_daily, as_of_date=as_of_date),
            "rankings": {
                "by_fund": self._ranking_by_fund(fund_df, as_of_date=as_of_date),
                "by_class": self._ranking_by_class(class_latest, ascending=False, top_n=20),
                "by_manager": self._ranking_by_dimension(fund_df, as_of_date=as_of_date, dimension="gestor"),
                "by_strategy_tag": self._ranking_by_dimension(fund_df, as_of_date=as_of_date, dimension="strategy_tag"),
            },
            "anbima_funds": anbima_payload,
            "brazil_vs_global": self._build_brazil_vs_global_shell(
                class_daily,
                as_of_date=as_of_date,
                ici_global_flows=ici_global_flows,
                cftc_positioning=cftc_positioning,
            ),
            "b3_investor_participation": b3_investor_participation
            or {
                "status": "not_loaded",
                "participants": [],
            },
            "b3_open_interest": b3_open_interest
            or {
                "status": "not_loaded",
                "product_summary": [],
                "history": [],
            },
            "b3_investor_participation_monthly": b3_investor_participation_monthly
            or {
                "status": "not_loaded",
                "rows": [],
            },
            "b3_market_data_report": b3_market_data_report
            or {
                "status": "not_loaded",
                "summary": {},
            },
            "b3_etfs": b3_etfs
            or {
                "status": "not_loaded",
                "summary": {},
                "funds": [],
            },
            "bcb_macro": bcb_macro
            or {
                "status": "not_loaded",
                "series": [],
                "ptax_usd": [],
                "summary": {},
            },
            "etf_panel": self._build_etf_panel(
                fund_df,
                class_daily,
                as_of_date=as_of_date,
                b3_etfs=b3_etfs,
                anbima_funds=anbima_payload,
                ici_global_flows=ici_global_flows,
            ),
            "stress_panel": self._build_stress_panel(fund_df, as_of_date=as_of_date, latest_pressure=kpis.get("pressure_index")),
            "source_inventory": [item.as_dict() for item in SOURCE_INVENTORY],
            "source_status": self._merge_source_status(source_status),
        }
        payload["ai_insights"] = FundsFlowInsightAgent().generate(payload)
        return _clean_json(payload)

    def _build_fund_daily(self, informe_df: pd.DataFrame, master_df: pd.DataFrame) -> pd.DataFrame:
        df = informe_df.copy()
        if not master_df.empty:
            keep_cols = [
                column
                for column in [
                    "cnpj_fundo",
                    "nome_fundo",
                    "classe_cvm",
                    "macro_classe",
                    "subclasse",
                    "strategy_tag",
                    "administrador",
                    "gestor",
                    "situacao",
                    "data_registro",
                    "data_inicio",
                    "is_active",
                    "classification_confidence",
                ]
                if column in master_df.columns
            ]
            df = df.merge(master_df[keep_cols], on="cnpj_fundo", how="left")
        for column, fallback in {
            "nome_fundo": "",
            "classe_cvm": "",
            "macro_classe": "Unclassified",
            "subclasse": "unclassified",
            "strategy_tag": "unclassified",
            "administrador": "",
            "gestor": "",
            "situacao": "",
            "is_active": True,
            "classification_confidence": 0.25,
        }.items():
            if column not in df.columns:
                df[column] = fallback
            df[column] = df[column].where(df[column].notna(), fallback)
            if isinstance(fallback, bool):
                df[column] = df[column].astype(bool)

        df.loc[df["nome_fundo"].astype(str).str.strip() == "", "nome_fundo"] = (
            "Fundo " + df["cnpj_fundo"].astype(str)
        )
        if "id_subclasse" not in df.columns:
            df["id_subclasse"] = ""
        df["id_subclasse"] = df["id_subclasse"].fillna("").astype(str).str.strip()
        if "series_id" not in df.columns:
            df["series_id"] = np.where(
                df["id_subclasse"].ne(""),
                df["cnpj_fundo"].astype(str) + "::" + df["id_subclasse"].astype(str),
                df["cnpj_fundo"].astype(str),
            )
        df["captacao_liquida"] = df["captacao"].fillna(0.0) - df["resgate"].fillna(0.0)
        df = df.sort_values(["series_id", "dt"]).reset_index(drop=True)
        grouped = df.groupby("series_id", sort=False)
        df["pl_lag"] = grouped["pl"].shift(1)
        df["quota_lag"] = grouped["vl_quota"].shift(1)
        df["cotistas_lag"] = grouped["cotistas"].shift(1)
        df["flow_pct_pl"] = np.where(df["pl_lag"] > 0, df["captacao_liquida"] / df["pl_lag"], np.nan)
        df["delta_cotistas"] = df["cotistas"] - df["cotistas_lag"]
        df["quota_return"] = np.nan
        valid_quota = (df["vl_quota"] > 0) & (df["quota_lag"] > 0)
        df.loc[valid_quota, "quota_return"] = np.log(df.loc[valid_quota, "vl_quota"] / df.loc[valid_quota, "quota_lag"])
        for window in WINDOWS:
            df[f"rolling_flow_{window}d"] = grouped["captacao_liquida"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            df[f"rolling_flow_pct_pl_{window}d"] = np.where(
                grouped["pl"].shift(window) > 0,
                df[f"rolling_flow_{window}d"] / grouped["pl"].shift(window),
                np.nan,
            )
        return df

    def _build_class_daily(self, fund_df: pd.DataFrame) -> pd.DataFrame:
        df = fund_df.copy()
        df["weighted_quota_return"] = df["quota_return"].fillna(0.0) * df["pl_lag"].fillna(0.0)
        class_daily = (
            df.groupby(["dt", "macro_classe"], as_index=False)
            .agg(
                pl_total=("pl", "sum"),
                captacao_total=("captacao", "sum"),
                resgate_total=("resgate", "sum"),
                captacao_liquida_total=("captacao_liquida", "sum"),
                cotistas_total=("cotistas", "sum"),
                delta_cotistas_total=("delta_cotistas", "sum"),
                num_fundos=("cnpj_fundo", "nunique"),
                pl_lag_sum=("pl_lag", "sum"),
                weighted_quota_return=("weighted_quota_return", "sum"),
            )
            .sort_values(["macro_classe", "dt"])
            .reset_index(drop=True)
        )
        class_daily["quota_return"] = np.where(
            class_daily["pl_lag_sum"] > 0,
            class_daily["weighted_quota_return"] / class_daily["pl_lag_sum"],
            np.nan,
        )
        class_daily["pl_lag"] = class_daily.groupby("macro_classe", sort=False)["pl_total"].shift(1)
        class_daily["flow_pct_pl"] = np.where(
            class_daily["pl_lag"] > 0,
            class_daily["captacao_liquida_total"] / class_daily["pl_lag"],
            np.nan,
        )
        for window in WINDOWS:
            group = class_daily.groupby("macro_classe", sort=False)
            class_daily[f"rolling_flow_{window}d"] = group["captacao_liquida_total"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            base_pl = group["pl_total"].shift(window)
            class_daily[f"rolling_flow_pct_pl_{window}d"] = np.where(
                base_pl > 0,
                class_daily[f"rolling_flow_{window}d"] / base_pl,
                np.nan,
            )
            class_daily[f"quota_return_{window}d"] = group["quota_return"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            class_daily[f"delta_cotistas_{window}d"] = group["delta_cotistas_total"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
        class_daily["flow_zscore_21d"] = class_daily.groupby("macro_classe", sort=False)["flow_pct_pl"].transform(
            lambda series: _zscore(series.fillna(0.0), 21)
        )
        class_daily["flow_zscore_63d"] = class_daily.groupby("macro_classe", sort=False)["flow_pct_pl"].transform(
            lambda series: _zscore(series.fillna(0.0), 63)
        )
        class_daily["share_pl_industria"] = class_daily["pl_total"] / class_daily.groupby("dt")["pl_total"].transform("sum")
        daily_abs_flow = class_daily.groupby("dt")["captacao_liquida_total"].transform(lambda series: series.abs().sum())
        class_daily["share_flow_industria"] = np.where(
            daily_abs_flow > 0,
            class_daily["captacao_liquida_total"] / daily_abs_flow,
            0.0,
        )
        class_daily["delta_cotistas_zscore_21d"] = class_daily.groupby("macro_classe", sort=False)[
            "delta_cotistas_21d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 21))
        class_daily["quota_return_zscore_21d"] = class_daily.groupby("macro_classe", sort=False)[
            "quota_return_21d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 21))
        class_daily["flow_pct_pl_21d_zscore"] = class_daily.groupby("macro_classe", sort=False)[
            "rolling_flow_pct_pl_21d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 21))
        class_daily["rolling_flow_pct_pl_63d_zscore"] = class_daily.groupby("macro_classe", sort=False)[
            "rolling_flow_pct_pl_63d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 63))
        class_daily["pressure_index"] = (
            0.35 * class_daily["flow_pct_pl_21d_zscore"]
            + 0.25 * class_daily["rolling_flow_pct_pl_63d_zscore"]
            + 0.20 * class_daily["delta_cotistas_zscore_21d"]
            + 0.20 * class_daily["quota_return_zscore_21d"]
        ).fillna(0.0)
        return class_daily

    def _build_industry_daily(self, fund_df: pd.DataFrame) -> pd.DataFrame:
        df = fund_df.copy()
        df["weighted_quota_return"] = df["quota_return"].fillna(0.0) * df["pl_lag"].fillna(0.0)
        industry = (
            df.groupby("dt", as_index=False)
            .agg(
                pl_total=("pl", "sum"),
                captacao_total=("captacao", "sum"),
                resgate_total=("resgate", "sum"),
                captacao_liquida_total=("captacao_liquida", "sum"),
                cotistas_total=("cotistas", "sum"),
                delta_cotistas_total=("delta_cotistas", "sum"),
                num_fundos=("cnpj_fundo", "nunique"),
                pl_lag_sum=("pl_lag", "sum"),
                weighted_quota_return=("weighted_quota_return", "sum"),
            )
            .sort_values("dt")
            .reset_index(drop=True)
        )
        industry["quota_return"] = np.where(
            industry["pl_lag_sum"] > 0,
            industry["weighted_quota_return"] / industry["pl_lag_sum"],
            np.nan,
        )
        industry["pl_lag"] = industry["pl_total"].shift(1)
        industry["flow_pct_pl"] = np.where(
            industry["pl_lag"] > 0,
            industry["captacao_liquida_total"] / industry["pl_lag"],
            np.nan,
        )
        for window in WINDOWS:
            industry[f"rolling_flow_{window}d"] = industry["captacao_liquida_total"].rolling(
                window,
                min_periods=1,
            ).sum()
            base_pl = industry["pl_total"].shift(window)
            industry[f"rolling_flow_pct_pl_{window}d"] = np.where(
                base_pl > 0,
                industry[f"rolling_flow_{window}d"] / base_pl,
                np.nan,
            )
            industry[f"quota_return_{window}d"] = industry["quota_return"].rolling(window, min_periods=1).sum()
            industry[f"delta_cotistas_{window}d"] = industry["delta_cotistas_total"].rolling(window, min_periods=1).sum()
        industry["flow_zscore_21d"] = _zscore(industry["flow_pct_pl"].fillna(0.0), 21)
        industry["flow_zscore_63d"] = _zscore(industry["flow_pct_pl"].fillna(0.0), 63)
        industry["delta_cotistas_zscore_21d"] = _zscore(industry["delta_cotistas_21d"].fillna(0.0), 21)
        industry["quota_return_zscore_21d"] = _zscore(industry["quota_return_21d"].fillna(0.0), 21)
        industry["flow_pct_pl_21d_zscore"] = _zscore(industry["rolling_flow_pct_pl_21d"].fillna(0.0), 21)
        industry["rolling_flow_pct_pl_63d_zscore"] = _zscore(industry["rolling_flow_pct_pl_63d"].fillna(0.0), 63)
        industry["pressure_index"] = (
            0.35 * industry["flow_pct_pl_21d_zscore"]
            + 0.25 * industry["rolling_flow_pct_pl_63d_zscore"]
            + 0.20 * industry["delta_cotistas_zscore_21d"]
            + 0.20 * industry["quota_return_zscore_21d"]
        ).fillna(0.0)
        return industry

    def _build_etf_panel(
        self,
        fund_df: pd.DataFrame,
        class_daily: pd.DataFrame,
        *,
        as_of_date: date,
        b3_etfs: dict[str, Any] | None,
        anbima_funds: dict[str, Any] | None,
        ici_global_flows: dict[str, Any] | None,
    ) -> dict[str, Any]:
        etf_class = class_daily[
            class_daily["macro_classe"].astype(str).str.upper().eq("ETF")
        ].copy()
        latest_class = etf_class[etf_class["dt"].dt.date == as_of_date].tail(1)
        if latest_class.empty and not etf_class.empty:
            latest_class = etf_class.tail(1)

        local_summary: dict[str, Any] = {"status": "not_available"}
        if not latest_class.empty:
            row = latest_class.iloc[0]
            row_date = row.get("dt")
            local_summary = {
                "status": "ok",
                "date": row_date.date().isoformat() if hasattr(row_date, "date") else str(row_date or as_of_date),
                "aum": _safe_float(row.get("pl_total"), 2),
                "net_flow_1d": _safe_float(row.get("captacao_liquida_total"), 2),
                "net_flow_5d": _safe_float(row.get("rolling_flow_5d"), 2),
                "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                "net_flow_63d": _safe_float(row.get("rolling_flow_63d"), 2),
                "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 8),
                "zscore_21d": _safe_float(row.get("flow_zscore_21d"), 4),
                "pressure_index": _safe_float(row.get("pressure_index"), 4),
                "cotistas": _safe_float(row.get("cotistas_total"), 0),
                "delta_cotistas_21d": _safe_float(row.get("delta_cotistas_21d"), 0),
                "num_funds": int(row.get("num_fundos") or 0),
            }

        latest_funds = fund_df[
            (fund_df["dt"].dt.date == as_of_date)
            & fund_df["macro_classe"].astype(str).str.upper().eq("ETF")
        ].copy()
        if latest_funds.empty:
            top_funds: list[dict[str, Any]] = []
        else:
            latest_funds["abs_flow"] = latest_funds["rolling_flow_21d"].abs()
            top_funds = [
                {
                    "rank": rank,
                    "name": row.get("nome_fundo"),
                    "cnpj_fundo": row.get("cnpj_fundo"),
                    "net_flow_1d": _safe_float(row.get("captacao_liquida"), 2),
                    "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                    "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 6),
                    "aum": _safe_float(row.get("pl"), 2),
                    "cotistas": _safe_float(row.get("cotistas"), 0),
                    "gestor": row.get("gestor"),
                }
                for rank, (_, row) in enumerate(
                    latest_funds.sort_values("abs_flow", ascending=False).head(12).iterrows(),
                    start=1,
                )
            ]

        start = as_of_date - timedelta(days=180)
        timeseries = [
            {
                "date": row.dt.date().isoformat(),
                "net_flow": _safe_float(row.captacao_liquida_total, 2),
                "rolling_flow_21d": _safe_float(row.rolling_flow_21d, 2),
                "flow_pct_pl_21d": _safe_float(row.rolling_flow_pct_pl_21d, 8),
                "zscore_21d": _safe_float(row.flow_zscore_21d, 4),
                "aum": _safe_float(row.pl_total, 2),
            }
            for row in etf_class[etf_class["dt"].dt.date >= start].sort_values("dt").itertuples()
        ]

        anbima_daily = (anbima_funds or {}).get("consolidated_daily") or {}
        anbima_categories = [
            item
            for item in anbima_daily.get("categories") or []
            if str(item.get("macro_classe") or "").upper() == "ETF"
            or str(item.get("normalized_name") or "").upper() == "ETF"
        ]
        anbima_types = [
            item
            for item in anbima_daily.get("types") or []
            if str(item.get("macro_classe") or "").upper() == "ETF"
            or "ETF" in str(item.get("normalized_name") or "").upper()
        ]

        ici_weekly = ((ici_global_flows or {}).get("weekly") or {})
        ici_latest = (ici_weekly.get("latest_by_vehicle") or {}).get("etf") or {}
        ici_monthly = (ici_global_flows or {}).get("monthly_etf") or {}

        return {
            "status": "ok",
            "as_of_date": as_of_date.isoformat(),
            "local": {
                "summary": local_summary,
                "timeseries": timeseries,
                "top_funds": top_funds,
            },
            "b3": {
                "status": (b3_etfs or {}).get("status") or "not_loaded",
                "summary": (b3_etfs or {}).get("summary") or {},
                "categories": (b3_etfs or {}).get("categories") or [],
                "funds": (b3_etfs or {}).get("funds") or [],
            },
            "anbima": {
                "reference_date": anbima_daily.get("reference_date"),
                "categories": anbima_categories,
                "types": anbima_types[:24],
            },
            "ici": {
                "latest_weekly": ici_latest,
                "weekly_categories": (ici_latest.get("categories") or [])[:16],
                "monthly_assets_by_type": (ici_monthly.get("assets_by_type") or [])[:16],
                "monthly_issuance": (ici_monthly.get("issuance") or [])[:16],
            },
        }

    def _build_kpis(self, industry_daily: pd.DataFrame, *, latest: pd.Series, as_of_date: date) -> dict[str, Any]:
        year_rows = industry_daily[industry_daily["dt"].dt.year == as_of_date.year]
        idx = latest.name
        start_21_idx = max(0, int(idx) - 21)
        start_21_pl = industry_daily.iloc[start_21_idx]["pl_total"] if len(industry_daily) else None
        pressure = _safe_float(latest.get("pressure_index"), 4) or 0.0
        return {
            "industry_aum": _safe_float(latest.get("pl_total"), 2),
            "net_flow_1d": _safe_float(latest.get("captacao_liquida_total"), 2),
            "net_flow_5d": _safe_float(latest.get("rolling_flow_5d"), 2),
            "net_flow_21d": _safe_float(latest.get("rolling_flow_21d"), 2),
            "net_flow_63d": _safe_float(latest.get("rolling_flow_63d"), 2),
            "net_flow_ytd": _safe_float(year_rows["captacao_liquida_total"].sum() if not year_rows.empty else 0.0, 2),
            "flow_pct_pl_21d": _safe_div(latest.get("rolling_flow_21d"), start_21_pl),
            "total_shareholders": _safe_float(latest.get("cotistas_total"), 0),
            "delta_shareholders_21d": _safe_float(latest.get("delta_cotistas_21d"), 0),
            "num_funds": int(latest.get("num_fundos") or 0),
            "pressure_index": pressure,
            "regime": _regime_from_pressure(pressure),
        }

    def _ranking_by_class(self, class_latest: pd.DataFrame, *, ascending: bool, top_n: int) -> list[dict[str, Any]]:
        if class_latest.empty:
            return []
        ranked = class_latest.sort_values("rolling_flow_21d", ascending=ascending).head(top_n)
        records: list[dict[str, Any]] = []
        for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
            records.append(
                {
                    "rank": rank,
                    "name": row.get("macro_classe"),
                    "level": "macro_classe",
                    "net_flow_1d": _safe_float(row.get("captacao_liquida_total"), 2),
                    "net_flow_5d": _safe_float(row.get("rolling_flow_5d"), 2),
                    "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                    "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 6),
                    "zscore_21d": _safe_float(row.get("flow_zscore_21d"), 4),
                    "aum": _safe_float(row.get("pl_total"), 2),
                    "share_pl_industry": _safe_float(row.get("share_pl_industria"), 6),
                    "pressure_index": _safe_float(row.get("pressure_index"), 4),
                    "num_funds": int(row.get("num_fundos") or 0),
                }
            )
        return records

    def _ranking_by_fund(self, fund_df: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        latest = fund_df[fund_df["dt"].dt.date == as_of_date].copy()
        if latest.empty:
            return []
        latest["abs_flow"] = latest["rolling_flow_21d"].abs()
        ranked = latest.sort_values("abs_flow", ascending=False).head(20)
        records: list[dict[str, Any]] = []
        for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
            records.append(
                {
                    "rank": rank,
                    "name": row.get("nome_fundo"),
                    "cnpj_fundo": row.get("cnpj_fundo"),
                    "series_id": row.get("series_id"),
                    "id_subclasse": row.get("id_subclasse"),
                    "level": "fundo",
                    "macro_classe": row.get("macro_classe"),
                    "net_flow_1d": _safe_float(row.get("captacao_liquida"), 2),
                    "net_flow_5d": _safe_float(row.get("rolling_flow_5d"), 2),
                    "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                    "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 6),
                    "aum": _safe_float(row.get("pl"), 2),
                    "cotistas": _safe_float(row.get("cotistas"), 0),
                    "delta_cotistas": _safe_float(row.get("delta_cotistas"), 0),
                    "classification_confidence": _safe_float(row.get("classification_confidence"), 3),
                }
            )
        return records

    def _ranking_by_dimension(self, fund_df: pd.DataFrame, *, as_of_date: date, dimension: str) -> list[dict[str, Any]]:
        latest = fund_df[fund_df["dt"].dt.date == as_of_date].copy()
        if latest.empty or dimension not in latest.columns:
            return []
        latest[dimension] = latest[dimension].fillna("").astype(str).str.strip()
        latest.loc[latest[dimension] == "", dimension] = "unclassified"
        grouped = (
            latest.groupby(dimension, as_index=False)
            .agg(
                net_flow_21d=("rolling_flow_21d", "sum"),
                net_flow_1d=("captacao_liquida", "sum"),
                aum=("pl", "sum"),
                cotistas=("cotistas", "sum"),
                num_funds=("cnpj_fundo", "nunique"),
            )
            .sort_values("net_flow_21d", ascending=False)
            .head(20)
        )
        return [
            {
                "rank": rank,
                "name": row.get(dimension),
                "level": dimension,
                "net_flow_1d": _safe_float(row.get("net_flow_1d"), 2),
                "net_flow_21d": _safe_float(row.get("net_flow_21d"), 2),
                "aum": _safe_float(row.get("aum"), 2),
                "cotistas": _safe_float(row.get("cotistas"), 0),
                "num_funds": int(row.get("num_funds") or 0),
            }
            for rank, (_, row) in enumerate(grouped.iterrows(), start=1)
        ]

    def _records_flow_by_class(self, class_daily: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        start = as_of_date - timedelta(days=180)
        rows = class_daily[class_daily["dt"].dt.date >= start].sort_values(["dt", "macro_classe"])
        return [
            {
                "date": row.dt.date().isoformat(),
                "macro_classe": row.macro_classe,
                "net_flow": _safe_float(row.captacao_liquida_total, 2),
                "rolling_flow_5d": _safe_float(row.rolling_flow_5d, 2),
                "rolling_flow_21d": _safe_float(row.rolling_flow_21d, 2),
                "rolling_flow_63d": _safe_float(row.rolling_flow_63d, 2),
                "flow_pct_pl": _safe_float(row.flow_pct_pl, 8),
                "flow_pct_pl_21d": _safe_float(row.rolling_flow_pct_pl_21d, 8),
                "zscore": _safe_float(row.flow_zscore_21d, 4),
                "pressure_index": _safe_float(row.pressure_index, 4),
                "aum": _safe_float(row.pl_total, 2),
                "num_funds": int(row.num_fundos or 0),
            }
            for row in rows.itertuples(index=False)
        ]

    def _records_industry_flow(self, industry_daily: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        start = as_of_date - timedelta(days=180)
        rows = industry_daily[industry_daily["dt"].dt.date >= start].sort_values("dt")
        return [
            {
                "date": row.dt.date().isoformat(),
                "net_flow": _safe_float(row.captacao_liquida_total, 2),
                "rolling_flow_5d": _safe_float(row.rolling_flow_5d, 2),
                "rolling_flow_21d": _safe_float(row.rolling_flow_21d, 2),
                "rolling_flow_63d": _safe_float(row.rolling_flow_63d, 2),
                "pressure_index": _safe_float(row.pressure_index, 4),
                "aum": _safe_float(row.pl_total, 2),
                "cotistas": _safe_float(row.cotistas_total, 0),
            }
            for row in rows.itertuples(index=False)
        ]

    def _records_monthly_flow(self, class_daily: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        start = as_of_date - timedelta(days=395)
        rows = class_daily[class_daily["dt"].dt.date >= start].copy()
        if rows.empty:
            return []
        rows["month"] = rows["dt"].dt.to_period("M").astype(str)
        monthly = (
            rows.groupby(["month", "macro_classe"], as_index=False)
            .agg(
                net_flow_month=("captacao_liquida_total", "sum"),
                aum=("pl_total", "last"),
            )
            .sort_values(["month", "macro_classe"])
        )
        return [
            {
                "month": row.month,
                "macro_classe": row.macro_classe,
                "net_flow_month": _safe_float(row.net_flow_month, 2),
                "aum": _safe_float(row.aum, 2),
            }
            for row in monthly.itertuples(index=False)
        ]

    def _build_heatmap(self, class_daily: pd.DataFrame, *, as_of_date: date) -> dict[str, Any]:
        start = as_of_date - timedelta(days=90)
        rows = class_daily[class_daily["dt"].dt.date >= start].copy()
        if rows.empty:
            return {"x": [], "y": [], "z": [], "metric": "flow_zscore_21d", "cells": []}
        rows["week"] = rows["dt"].dt.to_period("W-FRI").apply(lambda period: period.end_time.date().isoformat())
        weekly = (
            rows.groupby(["week", "macro_classe"], as_index=False)
            .agg(
                zscore=("flow_zscore_21d", "last"),
                net_flow=("captacao_liquida_total", "sum"),
                flow_pct_pl=("rolling_flow_pct_pl_21d", "last"),
                num_funds=("num_fundos", "last"),
                aum=("pl_total", "last"),
            )
            .sort_values(["week", "macro_classe"])
        )
        x_values = sorted(weekly["week"].unique().tolist())
        y_values = sorted(weekly["macro_classe"].unique().tolist())
        z: list[list[float | None]] = []
        cells: list[dict[str, Any]] = []
        index = {
            (row.week, row.macro_classe): row
            for row in weekly.itertuples(index=False)
        }
        for macro in y_values:
            row_values: list[float | None] = []
            for week in x_values:
                item = index.get((week, macro))
                if item is None:
                    row_values.append(None)
                    continue
                z_value = _safe_float(item.zscore, 4)
                row_values.append(z_value)
                cells.append(
                    {
                        "date": week,
                        "macro_classe": macro,
                        "zscore": z_value,
                        "net_flow": _safe_float(item.net_flow, 2),
                        "flow_pct_pl": _safe_float(item.flow_pct_pl, 8),
                        "num_funds": int(item.num_funds or 0),
                        "aum": _safe_float(item.aum, 2),
                    }
                )
            z.append(row_values)
        return {"x": x_values, "y": y_values, "z": z, "metric": "flow_zscore_21d", "cells": cells}

    def _build_brazil_vs_global_shell(
        self,
        class_daily: pd.DataFrame,
        *,
        as_of_date: date,
        ici_global_flows: dict[str, Any] | None = None,
        cftc_positioning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start = as_of_date - timedelta(days=140)
        rows = class_daily[class_daily["dt"].dt.date >= start].copy()
        if rows.empty:
            local = []
        else:
            rows["week"] = rows["dt"].dt.to_period("W-FRI").apply(lambda period: period.end_time.date().isoformat())
            weekly = (
                rows.groupby(["week", "macro_classe"], as_index=False)
                .agg(net_flow=("captacao_liquida_total", "sum"), flow_pct_pl=("rolling_flow_pct_pl_21d", "last"))
                .sort_values(["week", "macro_classe"])
            )
            local = [
                {
                    "date": row.week,
                    "category": row.macro_classe,
                    "net_flow": _safe_float(row.net_flow, 2),
                    "flow_pct_pl": _safe_float(row.flow_pct_pl, 8),
                    "frequency": "W",
                    "source": "CVM Informe Diario",
                }
                for row in weekly.itertuples(index=False)
            ]
        ici_payload = copy.deepcopy(ici_global_flows) if ici_global_flows else {"status": "not_loaded"}
        ici_weekly = ici_payload.get("weekly") or {}
        global_rows = [
            {
                "date": row.get("date"),
                "category": row.get("category"),
                "category_key": row.get("category_key"),
                "category_group": row.get("category_group"),
                "vehicle": row.get("vehicle"),
                "vehicle_label": row.get("vehicle_label"),
                "net_flow": row.get("flow_usd_mn"),
                "currency": "USD",
                "unit": "USD millions",
                "frequency": row.get("frequency"),
                "data_kind": row.get("data_kind"),
                "source": "ICI",
            }
            for row in (ici_weekly.get("weekly_series") or [])
        ]
        cftc_payload = copy.deepcopy(cftc_positioning) if cftc_positioning else {"status": "not_loaded"}
        return {
            "local": local,
            "global": global_rows,
            "macro": [],
            "ici_global_flows": ici_payload,
            "cftc_positioning": cftc_payload,
            "status": {
                "ici": "active" if ici_payload.get("status") == "ok" else ici_payload.get("status") or "configured_not_loaded",
                "cftc": "active" if cftc_payload.get("status") == "ok" else cftc_payload.get("status") or "configured_not_loaded",
                "fred": "configured_not_loaded",
                "bcb": "configured_not_loaded",
                "note": "Local CVM flow is live; ICI loads fund flows; CFTC loads weekly TFF positioning as of Tuesday with usual Friday release.",
            },
        }

    def _build_stress_panel(self, fund_df: pd.DataFrame, *, as_of_date: date, latest_pressure: Any) -> dict[str, Any]:
        latest = fund_df[fund_df["dt"].dt.date == as_of_date].copy()
        if latest.empty:
            return {
                "pct_funds_negative": 0,
                "pct_aum_negative": 0,
                "hhi_redemptions": 0,
                "largest_redemption_share": 0,
                "stress_level": "low",
            }
        negative = latest[latest["captacao_liquida"] < 0]
        total_funds = len(latest)
        total_aum = latest["pl"].sum()
        redemptions = negative["captacao_liquida"].abs()
        total_redemptions = redemptions.sum()
        hhi = float(((redemptions / total_redemptions) ** 2).sum()) if total_redemptions > 0 else 0.0
        largest = float(redemptions.max() / total_redemptions) if total_redemptions > 0 else 0.0
        pct_funds_negative = float(len(negative) / total_funds) if total_funds else 0.0
        pct_aum_negative = float(negative["pl"].sum() / total_aum) if total_aum > 0 else 0.0
        pressure = _safe_float(latest_pressure) or 0.0
        if pressure <= -2 or (pct_funds_negative > 0.65 and pct_aum_negative > 0.65):
            stress_level = "high"
        elif pressure <= -1 or pct_funds_negative > 0.55 or hhi > 0.25:
            stress_level = "medium"
        else:
            stress_level = "low"
        return {
            "pct_funds_negative": _safe_float(pct_funds_negative, 6),
            "pct_aum_negative": _safe_float(pct_aum_negative, 6),
            "hhi_redemptions": _safe_float(hhi, 6),
            "largest_redemption_share": _safe_float(largest, 6),
            "funds_with_negative_flow": int(len(negative)),
            "total_funds": int(total_funds),
            "stress_level": stress_level,
        }

    def _merge_source_status(self, runtime_status: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {item.id: item.as_dict() for item in SOURCE_INVENTORY}
        for status in runtime_status:
            source_id = str(status.get("id") or "")
            if source_id.startswith("cvm_informe_diario_"):
                key = "cvm_informe_diario"
            elif source_id == "cvm_cadastro_fi":
                key = "cvm_cadastro_fi"
            else:
                key = source_id
            current = by_id.get(key, {"id": key})
            status_capture = _max_iso_datetime_value(
                status.get("last_captured_at"),
                _path_mtime_iso(status.get("cached_path")),
                *[_path_mtime_iso(path) for path in (status.get("cached_paths") or [])],
            )
            current_capture = _max_iso_datetime_value(
                current.get("last_captured_at"),
                _path_mtime_iso(current.get("cached_path")),
                *[_path_mtime_iso(path) for path in (current.get("cached_paths") or [])],
            )
            current_ok = bool(current.get("ok"))
            status_ok = bool(status.get("ok"))
            combined_ok = current_ok or status_ok
            current.update(
                {
                    "ok": combined_ok,
                    "status": "active" if combined_ok else current.get("status", "configured"),
                    "rows": int(status.get("rows") or 0) + int(current.get("rows") or 0),
                    "latest_error": None if combined_ok else (status.get("error") or current.get("latest_error")),
                    "latency_ms": int(status.get("latency_ms") or 0) + int(current.get("latency_ms") or 0),
                    "cached_path": status.get("cached_path") if status_ok or not current.get("cached_path") else current.get("cached_path"),
                    "cached_paths": status.get("cached_paths") or current.get("cached_paths"),
                    "url": status.get("url") or current.get("url"),
                    "latest_data_date": _max_iso_date_value(
                        current.get("latest_data_date"),
                        status.get("latest_data_date"),
                    ),
                    "reference_label": status.get("reference_label") or current.get("reference_label"),
                    "report_date": status.get("report_date") or current.get("report_date"),
                    "publication_date": status.get("publication_date") or current.get("publication_date"),
                    "last_captured_at": _max_iso_datetime_value(current_capture, status_capture),
                }
            )
            by_id[key] = current
        return list(by_id.values())

    def _write_derived_files(self, payload: dict[str, Any]) -> None:
        os.makedirs(self.derived_dir, exist_ok=True)
        atomic_json_dump(os.path.join(self.derived_dir, "dashboard_payload.schema_sample.json"), payload, indent=2)
        for name in ["flow_by_class", "industry_flow", "monthly_stacked_flow"]:
            rows = payload.get("timeseries", {}).get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"{name}.csv"), index=False)
        for name in ["by_fund", "by_class", "by_manager", "by_strategy_tag"]:
            rows = payload.get("rankings", {}).get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ranking_{name}.csv"), index=False)
        anbima_payload = payload.get("anbima_funds") or {}
        anbima_daily = anbima_payload.get("consolidated_daily") or {}
        for name in ["categories", "types", "top_type_inflows_mtd", "top_type_outflows_mtd"]:
            rows = anbima_daily.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"anbima_{name}.csv"), index=False)
        validation_rows = (anbima_payload.get("validation") or {}).get("rows") or []
        if validation_rows:
            pd.DataFrame(validation_rows).to_csv(os.path.join(self.derived_dir, "anbima_cvm_validation.csv"), index=False)
        for name, ranking in (anbima_payload.get("rankings") or {}).items():
            rows = ranking.get("top_aum") or []
            if rows:
                normalized_rows = [
                    {key: value for key, value in row.items() if key != "values_by_class"}
                    for row in rows
                ]
                pd.DataFrame(normalized_rows).to_csv(
                    os.path.join(self.derived_dir, f"anbima_ranking_{name}.csv"),
                    index=False,
                )
        articles = ((anbima_payload.get("bulletin") or {}).get("latest_articles") or [])
        if articles:
            pd.DataFrame(articles).to_csv(os.path.join(self.derived_dir, "anbima_bulletin_articles.csv"), index=False)
        ici_payload = ((payload.get("brazil_vs_global") or {}).get("ici_global_flows") or {})
        ici_weekly = ici_payload.get("weekly") or {}
        for name in ["weekly_series", "monthly_series"]:
            rows = ici_weekly.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ici_{name}.csv"), index=False)
        ici_monthly_etf = ici_payload.get("monthly_etf") or {}
        for name in ["assets_by_type", "issuance"]:
            rows = ici_monthly_etf.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ici_monthly_etf_{name}.csv"), index=False)
        ici_worldwide = ici_payload.get("worldwide_quarterly") or {}
        for name in ["regions", "countries", "top_country_etf_net_sales", "bottom_country_etf_net_sales"]:
            rows = ici_worldwide.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ici_worldwide_{name}.csv"), index=False)
        cftc_payload = ((payload.get("brazil_vs_global") or {}).get("cftc_positioning") or {})
        for name in ["latest_contracts", "focus_contracts", "weekly_series", "participant_summary", "asset_bucket_summary"]:
            rows = cftc_payload.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"cftc_tff_{name}.csv"), index=False)
        for name in [
            "datasets",
            "family_summaries",
            "extended_participant_summary",
            "extended_asset_bucket_summary",
            "extended_contracts",
            "position_matrix",
        ]:
            rows = cftc_payload.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"cftc_cot_{name}.csv"), index=False)
        b3_payload = payload.get("b3_investor_participation") or {}
        for name in ["history", "trend_by_participant", "daily_reports", "economic_indicators"]:
            rows = b3_payload.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_{name}.csv"), index=False)
        b3_monthly = payload.get("b3_investor_participation_monthly") or {}
        if b3_monthly.get("rows"):
            pd.DataFrame(b3_monthly["rows"]).to_csv(
                os.path.join(self.derived_dir, "b3_investor_participation_monthly.csv"),
                index=False,
            )
        b3_market_data = payload.get("b3_market_data_report") or {}
        for name in [
            "trading_volume_monthly",
            "average_daily_trading_value",
            "total_trades",
            "daily_average_trades",
            "investor_participation_monthly",
            "foreign_investor_flow_monthly",
        ]:
            rows = b3_market_data.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_market_data_{name}.csv"), index=False)
        b3_open_interest = payload.get("b3_open_interest") or {}
        for name in ["history", "product_summary", "latest_contracts", "futures_summary"]:
            rows = b3_open_interest.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_open_interest_{name}.csv"), index=False)
        b3_etfs = payload.get("b3_etfs") or {}
        for name in ["funds", "categories"]:
            rows = b3_etfs.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_etfs_{name}.csv"), index=False)
        bcb_macro = payload.get("bcb_macro") or {}
        for name in ["series", "ptax_usd"]:
            rows = bcb_macro.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"bcb_macro_{name}.csv"), index=False)
        etf_panel = payload.get("etf_panel") or {}
        etf_local = etf_panel.get("local") or {}
        if etf_local.get("timeseries"):
            pd.DataFrame(etf_local["timeseries"]).to_csv(os.path.join(self.derived_dir, "etf_local_timeseries.csv"), index=False)
        if etf_local.get("top_funds"):
            pd.DataFrame(etf_local["top_funds"]).to_csv(os.path.join(self.derived_dir, "etf_local_top_funds.csv"), index=False)

    def _append_snapshot_summary(self, payload: dict[str, Any]) -> None:
        report = payload.get("report") or {}
        kpis = payload.get("kpis") or {}
        summary = {
            "generated_at": payload.get("generated_at"),
            "as_of_date": report.get("as_of_date"),
            "period": report.get("period"),
            "industry_aum": kpis.get("industry_aum"),
            "net_flow_21d": kpis.get("net_flow_21d"),
            "pressure_index": kpis.get("pressure_index"),
            "regime": kpis.get("regime"),
        }
        os.makedirs(os.path.dirname(self.snapshots_path), exist_ok=True)
        with open(self.snapshots_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(_clean_json(summary), ensure_ascii=False) + "\n")
