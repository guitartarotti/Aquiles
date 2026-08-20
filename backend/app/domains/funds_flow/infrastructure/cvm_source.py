"""CVM download, cache and parsing adapter for Funds Flow."""

from __future__ import annotations

import os
import re
import time
import zipfile
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import requests

from ....utils.funds_flow_source_values import (
    _classify_master_row,
    _normalize_cnpj,
    _yyyymm_months,
)
from ....utils.logger import get_logger
from ..contracts.source_catalog import (
    CLASS_REGISTER_RENAME,
    CVM_CADASTRO_PACKAGE,
    CVM_CADASTRO_URL,
    CVM_CKAN_PACKAGE_URL,
    CVM_INFORME_PACKAGE,
    CVM_INFORME_PATTERN,
    CVM_REGISTRO_FUNDO_CLASSE_URL,
    FUND_REGISTER_RENAME,
    INFORME_COLUMNS,
    INFORME_SOURCE_PRIORITY,
    MASTER_RENAME,
)
from .source_http import CachedHttpSource

logger = get_logger("aquiles.funds_flow.sources.cvm")


class CvmFundsFlowAdapter(CachedHttpSource):
    provider = "cvm"

    def __init__(self, *, raw_dir: str, timeout_seconds: float) -> None:
        super().__init__(raw_dir=raw_dir, timeout_seconds=timeout_seconds)
        self._ckan_cache: dict[str, dict[str, Any]] = {}

    def load_informe_diario(
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
                frame, status = self._read_informe_month(
                    yyyymm=yyyymm, url=resources[yyyymm], force=force
                )
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
            filtered = df[
                (df["dt"].dt.date >= fallback_start) & (df["dt"].dt.date <= actual_end)
            ].copy()
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

    def _read_informe_month(
        self, *, yyyymm: str, url: str, force: bool
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
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
            status["latest_data_date"] = (
                frame["dt"].max().date().isoformat() if not frame.empty else None
            )
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
                normalized[target] = normalized[target].where(
                    normalized[target].notna(), raw[source_column]
                )
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
        df[["captacao", "resgate", "cotistas"]] = df[["captacao", "resgate", "cotistas"]].fillna(
            0.0
        )
        df = df.dropna(subset=["dt", "cnpj_fundo"]).copy()
        df["_source_priority"] = (
            df["tp_fundo_classe"].str.upper().map(INFORME_SOURCE_PRIORITY).fillna(99).astype(int)
        )
        df = (
            df.sort_values(
                ["dt", "cnpj_fundo", "id_subclasse", "_source_priority", "pl"],
                ascending=[True, True, True, True, False],
            )
            .drop_duplicates(["dt", "cnpj_fundo", "id_subclasse"], keep="first")
            .reset_index(drop=True)
        )
        df["series_id"] = np.where(
            df["id_subclasse"].ne(""),
            df["cnpj_fundo"].astype(str) + "::" + df["id_subclasse"].astype(str),
            df["cnpj_fundo"].astype(str),
        )
        return df.drop(columns=["_source_priority"], errors="ignore")

    def load_fund_registry(self, *, force: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
        legacy_master, legacy_status = self._load_legacy_registry(force=force)
        class_master, class_status = self._load_rcvm175_registry(force=force)
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
            "latency_ms": int(legacy_status.get("latency_ms") or 0)
            + int(class_status.get("latency_ms") or 0),
            "children": [legacy_status, class_status],
        }
        return master, status

    def _load_legacy_registry(self, *, force: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
        started = time.monotonic()
        resources = self._fetch_ckan_package(CVM_CADASTRO_PACKAGE)
        url = CVM_CADASTRO_URL
        for resource in resources.get("resources") or []:
            candidate = str(resource.get("url") or "")
            if candidate.lower().endswith("/cad_fi.csv") or candidate.lower().endswith(
                "cad_fi.csv"
            ):
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

    def _load_rcvm175_registry(self, *, force: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
        started = time.monotonic()
        resources = self._fetch_ckan_package(CVM_CADASTRO_PACKAGE)
        url = CVM_REGISTRO_FUNDO_CLASSE_URL
        for resource in resources.get("resources") or []:
            candidate = str(resource.get("url") or "")
            candidate_lower = candidate.lower()
            if candidate_lower.endswith("/dados/registro_fundo_classe.zip") or (
                candidate_lower.endswith("registro_fundo_classe.zip")
                and "/meta/" not in candidate_lower
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
                    classes = pd.read_csv(
                        handle, sep=";", encoding="latin1", dtype=str, low_memory=False
                    )
                with archive.open("registro_fundo.csv") as handle:
                    funds = pd.read_csv(
                        handle, sep=";", encoding="latin1", dtype=str, low_memory=False
                    )

            classes = classes.rename(
                columns={
                    column: CLASS_REGISTER_RENAME.get(str(column).strip(), column)
                    for column in classes.columns
                }
            )
            funds = funds.rename(
                columns={
                    column: FUND_REGISTER_RENAME.get(str(column).strip(), column)
                    for column in funds.columns
                }
            )
            keep_funds = [
                column
                for column in ["id_registro_fundo", "administrador", "gestor"]
                if column in funds.columns
            ]
            if keep_funds:
                classes = classes.merge(
                    funds[keep_funds].drop_duplicates("id_registro_fundo"),
                    on="id_registro_fundo",
                    how="left",
                )

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
            classified.columns = [
                "macro_classe",
                "subclasse",
                "strategy_tag",
                "classification_confidence",
            ]
            master = pd.concat([master, classified], axis=1)
            master["is_active"] = ~master["situacao"].astype(str).str.upper().str.contains(
                "CANCEL|ENCERR", regex=True, na=False
            )
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
        raw = raw.rename(
            columns={
                column: MASTER_RENAME.get(str(column).strip().upper(), column)
                for column in raw.columns
            }
        )
        for column in MASTER_RENAME.values():
            if column not in raw.columns:
                raw[column] = None
        master = raw[list(MASTER_RENAME.values())].copy()
        master["cnpj_fundo"] = master["cnpj_fundo"].map(_normalize_cnpj)
        master = master[master["cnpj_fundo"] != ""].drop_duplicates("cnpj_fundo", keep="last")

        classified = master.apply(_classify_master_row, axis=1, result_type="expand")
        classified.columns = [
            "macro_classe",
            "subclasse",
            "strategy_tag",
            "classification_confidence",
        ]
        master = pd.concat([master, classified], axis=1)
        master["is_active"] = ~master["situacao"].astype(str).str.upper().str.contains(
            "CANCEL|ENCERR", regex=True, na=False
        )
        return master
