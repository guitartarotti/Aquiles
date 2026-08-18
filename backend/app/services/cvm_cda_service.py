from __future__ import annotations

import csv
import json
import math
import os
import re
import sqlite3
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from ..config import Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger

logger = get_logger("mirofish.cvm_cda")

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
CVM_CDA_SCHEMA_VERSION = 2
CVM_CDA_PACKAGE = "fi-doc-cda"
CVM_CKAN_PACKAGE_URL = "https://dados.cvm.gov.br/api/3/action/package_show"
CVM_CDA_PATTERN = "https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{yyyymm}.zip"
CVM_CDA_DATASET_URL = "https://dados.cvm.gov.br/dataset/fi-doc-cda"

CDA_TARGET_LABELS = {
    "foreign": "Exterior",
    "public_bonds": "Titulos publicos",
    "private_credit": "Credito privado",
    "fund_quotas": "Cotas de fundos",
    "equity": "Acoes",
    "derivatives": "Derivativos",
    "confidential": "Confidencial",
}

CDA_TARGET_SQL = {
    "foreign": "is_foreign = 1",
    "public_bonds": "asset_class = 'Titulos Publicos'",
    "private_credit": "asset_class IN ('Credito Privado', 'Depositos e IF', 'Agronegocio/Credito')",
    "fund_quotas": "is_fund_quota = 1",
    "equity": "asset_class = 'Acoes'",
    "derivatives": "is_derivative = 1",
    "confidential": "is_confidential = 1",
}

HOLDING_NUMERIC_COLUMNS = (
    "qty_final",
    "value_market",
    "value_cost",
    "value_buy",
    "value_sell",
)

HOLDING_CORE_COLUMNS = (
    "month",
    "source_file",
    "source_block",
    "fund_type",
    "fund_cnpj",
    "fund_name",
    "dt_comptc",
    "tp_aplic",
    "tp_ativo",
    "tp_negoc",
    "asset_class",
    "asset_subclass",
    "asset_code",
    "asset_desc",
    "isin",
    "issuer_name",
    "issuer_doc",
    "risk_issuer",
    "country_code",
    "country",
    "market",
    "maturity_date",
    "maturity_bucket",
    "qty_final",
    "value_market",
    "value_cost",
    "value_buy",
    "value_sell",
    "is_confidential",
    "is_foreign",
    "is_fund_quota",
    "is_derivative",
    "is_related_issuer",
)

RADAR_BUCKET_META = {
    "Titulos Publicos": {
        "bucket": "sovereign_liquidity",
        "label": "Juros soberanos",
        "rank": 1,
        "saleability_share": 0.96,
    },
    "Depositos e IF": {
        "bucket": "cash_liquidity",
        "label": "Caixa e IF",
        "rank": 2,
        "saleability_share": 0.92,
    },
    "Acoes": {
        "bucket": "listed_equity",
        "label": "Bolsa local",
        "rank": 3,
        "saleability_share": 0.68,
    },
    "Investimento Exterior": {
        "bucket": "global_liquid",
        "label": "Exterior liquido",
        "rank": 4,
        "saleability_share": 0.58,
    },
    "Derivativos": {
        "bucket": "derivatives_overlay",
        "label": "Derivativos/margem",
        "rank": 5,
        "saleability_share": 0.32,
    },
    "Cotas de Fundos": {
        "bucket": "fund_quotas",
        "label": "Cotas de fundos",
        "rank": 6,
        "saleability_share": 0.38,
    },
    "Credito Privado": {
        "bucket": "private_credit",
        "label": "Credito privado",
        "rank": 7,
        "saleability_share": 0.24,
    },
    "Agronegocio/Credito": {
        "bucket": "structured_credit",
        "label": "Credito estruturado",
        "rank": 8,
        "saleability_share": 0.18,
    },
    "Fundos Estruturados": {
        "bucket": "structured_funds",
        "label": "Fundos estruturados",
        "rank": 9,
        "saleability_share": 0.14,
    },
    "Confidencial": {
        "bucket": "confidential",
        "label": "Confidencial",
        "rank": 10,
        "saleability_share": 0.05,
    },
    "Outros": {
        "bucket": "other_assets",
        "label": "Outros",
        "rank": 11,
        "saleability_share": 0.22,
    },
}

RADAR_DEFAULT_BUCKET = {
    "bucket": "other_assets",
    "label": "Outros",
    "rank": 11,
    "saleability_share": 0.20,
}

RADAR_DEFENSIVE_FLOOR = {
    "RENDA FIXA": 0.18,
    "MULTIMERCADO": 0.12,
    "ACOES": 0.38,
    "CAMBIAL": 0.32,
    "PREVIDENCIA": 0.18,
    "ETF": 0.48,
    "FII": 0.35,
    "FIDC": 0.45,
    "FIP": 0.62,
    "FIAGRO": 0.40,
    "OUTROS": 0.25,
    "UNCLASSIFIED": 0.25,
}

RADAR_SCENARIOS = (
    {
        "key": "base",
        "label": "Base",
        "description": "Usa a media de resgate bruto recente de 21 dias uteis.",
        "multiplier": 1.0,
    },
    {
        "key": "stress",
        "label": "Stress",
        "description": "Usa o pior ritmo bruto recente entre 5d e 21d, com margem adicional.",
        "multiplier": 1.2,
    },
    {
        "key": "extreme",
        "label": "Extremo",
        "description": "Amplifica o stress com ancora no dia mais forte de resgate bruto recente.",
        "multiplier": 1.55,
    },
)

RADAR_CONFIDENTIAL_SALEABILITY_DISCOUNT = 0.50
RADAR_PLAUSIBLE_HORIZON_DAYS = 30
RADAR_MIN_DAYS_SINCE_CDA = int(os.environ.get("CVM_CDA_RADAR_MIN_DAYS_SINCE_CDA", "29"))
RADAR_MIN_MONTH_ROWS = int(os.environ.get("CVM_CDA_RADAR_MIN_MONTH_ROWS", "100000"))
RADAR_PLAUSIBLE_BUCKET_SHARE = {
    "sovereign_liquidity": 0.18,
    "cash_liquidity": 0.70,
    "listed_equity": 0.14,
    "global_liquid": 0.12,
    "derivatives_overlay": 0.10,
    "fund_quotas": 0.06,
    "private_credit": 0.04,
    "structured_credit": 0.025,
    "structured_funds": 0.02,
    "confidential": 0.02,
    "other_assets": 0.05,
}

RADAR_CACHE_TTL_SECONDS = 1800


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    return value


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _month_from_text(value: str) -> str | None:
    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", str(value or ""))
    return "".join(match.groups()) if match else None


def _month_label(yyyymm: str | None) -> str:
    text = str(yyyymm or "")
    if not re.fullmatch(r"20\d{4}", text):
        return text or "-"
    return f"{text[:4]}-{text[4:6]}"


def _previous_months(month: str, count: int) -> list[str]:
    if not re.fullmatch(r"20\d{4}", str(month or "")):
        return []
    year = int(month[:4])
    month_num = int(month[4:6])
    result = []
    for _ in range(max(0, count)):
        result.append(f"{year:04d}{month_num:02d}")
        month_num -= 1
        if month_num <= 0:
            month_num = 12
            year -= 1
    return result


def _safe_float(value: Any) -> float:
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _safe_div(numerator: Any, denominator: Any, default: float = 0.0) -> float:
    den = _safe_float(denominator)
    if den == 0:
        return default
    return _safe_float(numerator) / den


def _clamp(value: Any, lower: float, upper: float) -> float:
    parsed = _safe_float(value)
    return max(lower, min(parsed, upper))


def _parse_date_text(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _norm_text(value: Any) -> str:
    text = str(value if value is not None else "").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", text)


def _norm_key(value: Any) -> str:
    text = _norm_text(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _first_nonempty(values: Any, default: str = "") -> str:
    for value in values:
        text = _norm_text(value)
        if text:
            return text
    return default


def _series_first_present(frame: pd.DataFrame, columns: tuple[str, ...] | list[str]) -> pd.Series:
    output = pd.Series([""] * len(frame), index=frame.index, dtype="object")
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column].astype(str).replace({"nan": "", "None": ""}).str.strip()
        output = output.mask(output.astype(str).str.strip() == "", values)
    return output


def _series_num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([0.0] * len(frame), index=frame.index, dtype="float64")
    values = frame[column].astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(values, errors="coerce").fillna(0.0)


def _series_str(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    return frame[column].astype(str).replace({"nan": "", "None": ""}).str.replace("\xa0", " ", regex=False).str.strip()


def _source_block(file_name: str) -> str:
    text = str(file_name or "").upper()
    if "CONFID" in text and "FIE" in text:
        return "FIE_CONFID"
    if "CONFID" in text:
        return "CONFID"
    match = re.search(r"_BLC_(\d)_", text)
    if match:
        return f"BLC_{match.group(1)}"
    if "CDA_FIE_" in text:
        return "FIE"
    return "CDA"


def _asset_class_for(block: str, tp_aplic: Any, tp_ativo: Any, asset_desc: Any) -> str:
    block_text = str(block or "").upper()
    text = _norm_key(f"{tp_aplic} {tp_ativo} {asset_desc} {block}")
    use_block_hint = block_text not in {"CONFID", "FIE", "FIE_CONFID"}
    if (use_block_hint and block_text == "BLC_1") or "TITULO PUBLICO" in text or "SELIC" in text or "COMPROMISSAD" in text:
        return "Titulos Publicos"
    if (use_block_hint and block_text == "BLC_2") or "COTAS DE FUNDOS" in text or "FUNDO" in text and "COTA" in text:
        return "Cotas de Fundos"
    if (
        (use_block_hint and block_text == "BLC_3")
        or "SWAP" in text
        or "MERCADO FUTURO" in text
        or "FUTURO" in text
        or "OPCO" in text
        or "TERMO" in text
    ):
        return "Derivativos"
    if "ACAO" in text or "ACOES" in text or "BDR" in text or "ETF" in text:
        return "Acoes"
    if (
        (use_block_hint and block_text == "BLC_5")
        or "DEPOSITO" in text
        or "CDB" in text
        or "LETRA FINANCEIRA" in text
        or "DISPONIBILIDADE" in text
    ):
        return "Depositos e IF"
    if (
        (use_block_hint and block_text == "BLC_6")
        or "AGRONEGOCIO" in text
        or "CRA" in text
        or "CRI" in text
        or "DIREITOS CREDITORIOS" in text
    ):
        return "Agronegocio/Credito"
    if (use_block_hint and block_text == "BLC_7") or "EXTERIOR" in text or "OFFSHORE" in text:
        return "Investimento Exterior"
    if "DEBENTURE" in text or "NOTA COMERCIAL" in text or "CREDITO PRIVADO" in text or "TITULOS DE CREDITO PRIVADO" in text:
        return "Credito Privado"
    return "Outros"


def _maturity_bucket(maturity_date: Any, as_of_date: Any) -> str:
    maturity = str(maturity_date or "").strip()[:10]
    as_of = str(as_of_date or "").strip()[:10]
    if not maturity or not as_of:
        return "sem vencimento"
    try:
        years = (datetime.fromisoformat(maturity).date() - datetime.fromisoformat(as_of).date()).days / 365.25
    except Exception:
        return "sem vencimento"
    if years < 0:
        return "vencido/indefinido"
    if years <= 1:
        return "0-1y"
    if years <= 3:
        return "1-3y"
    if years <= 5:
        return "3-5y"
    if years <= 7:
        return "5-7y"
    if years <= 10:
        return "7-10y"
    if years <= 30:
        return "10-30y"
    return "30y+"


@dataclass(frozen=True)
class CdaRemoteMonth:
    month: str
    url: str
    name: str = ""
    last_modified: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "label": _month_label(self.month),
            "url": self.url,
            "name": self.name,
            "last_modified": self.last_modified,
        }


class CvmCdaService:
    def __init__(self, data_dir: str | None = None) -> None:
        self.root_dir = Path(
            data_dir
            or getattr(Config, "CVM_CDA_DATA_DIR", "")
            or Path(Config.MACRO_DATA_DIR) / "cvm_cda"
        )
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = self.root_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root_dir / "cvm_cda.sqlite"
        self.radar_cache_path = self.root_dir / "radar_cda_latest.json"
        self._ckan_cache: tuple[float, dict[str, CdaRemoteMonth]] | None = None

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=180)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")
        con.execute("PRAGMA cache_size=-220000")
        return con

    def init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS cvm_cda_months (
                    month TEXT PRIMARY KEY,
                    source_url TEXT,
                    source_last_modified TEXT,
                    zip_path TEXT,
                    imported_at TEXT,
                    status TEXT,
                    schema_version INTEGER,
                    file_count INTEGER,
                    total_rows INTEGER,
                    latest_dt TEXT,
                    total_pl REAL,
                    total_position_value REAL,
                    total_confidential_value REAL,
                    metadata_json TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_file_manifest (
                    month TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    source_block TEXT,
                    row_count INTEGER,
                    column_count INTEGER,
                    file_size_bytes INTEGER,
                    loaded_at TEXT,
                    columns_json TEXT,
                    PRIMARY KEY (month, source_file)
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_ingest_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month TEXT,
                    event_at TEXT,
                    level TEXT,
                    message TEXT,
                    detail_json TEXT
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_holdings (
                    month TEXT NOT NULL,
                    source_file TEXT,
                    source_block TEXT,
                    fund_type TEXT,
                    fund_cnpj TEXT NOT NULL,
                    fund_name TEXT,
                    dt_comptc TEXT,
                    tp_aplic TEXT,
                    tp_ativo TEXT,
                    tp_negoc TEXT,
                    asset_class TEXT,
                    asset_subclass TEXT,
                    asset_code TEXT,
                    asset_desc TEXT,
                    isin TEXT,
                    issuer_name TEXT,
                    issuer_doc TEXT,
                    risk_issuer TEXT,
                    country_code TEXT,
                    country TEXT,
                    market TEXT,
                    maturity_date TEXT,
                    maturity_bucket TEXT,
                    qty_final REAL,
                    value_market REAL,
                    value_cost REAL,
                    value_buy REAL,
                    value_sell REAL,
                    is_confidential INTEGER,
                    is_foreign INTEGER,
                    is_fund_quota INTEGER,
                    is_derivative INTEGER,
                    is_related_issuer INTEGER
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_fund_pl (
                    month TEXT NOT NULL,
                    fund_type TEXT,
                    fund_cnpj TEXT NOT NULL,
                    fund_name TEXT,
                    dt_comptc TEXT,
                    pl REAL,
                    PRIMARY KEY (month, fund_cnpj, dt_comptc)
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_fund_summary (
                    month TEXT NOT NULL,
                    fund_cnpj TEXT NOT NULL,
                    fund_name TEXT,
                    fund_type TEXT,
                    dt_comptc TEXT,
                    pl REAL,
                    holding_count INTEGER,
                    issuer_count INTEGER,
                    asset_count INTEGER,
                    position_value REAL,
                    abs_position_value REAL,
                    foreign_value REAL,
                    public_bond_value REAL,
                    private_credit_value REAL,
                    fund_quota_value REAL,
                    equity_value REAL,
                    derivative_value REAL,
                    confidential_value REAL,
                    related_issuer_value REAL,
                    buy_value REAL,
                    sell_value REAL,
                    max_position_value REAL,
                    concentration_pct REAL,
                    foreign_pct_pl REAL,
                    private_credit_pct_pl REAL,
                    confidential_pct_pl REAL,
                    turnover_pct_pl REAL,
                    PRIMARY KEY (month, fund_cnpj)
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_summary_group (
                    month TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    key TEXT NOT NULL,
                    label TEXT,
                    row_count INTEGER,
                    fund_count INTEGER,
                    value REAL,
                    abs_value REAL,
                    share_value_pct REAL,
                    extra_json TEXT,
                    PRIMARY KEY (month, dimension, key)
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_fund_target_exposure (
                    month TEXT NOT NULL,
                    target TEXT NOT NULL,
                    target_label TEXT,
                    fund_cnpj TEXT NOT NULL,
                    fund_name TEXT,
                    fund_type TEXT,
                    dt_comptc TEXT,
                    pl REAL,
                    long_value REAL,
                    short_value REAL,
                    net_value REAL,
                    gross_value REAL,
                    target_pct_pl REAL,
                    holdings_count INTEGER,
                    issuers_count INTEGER,
                    assets_count INTEGER,
                    top_issuer TEXT,
                    top_asset_class TEXT,
                    concentration_pct REAL,
                    PRIMARY KEY (month, target, fund_cnpj)
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_asset_target_exposure (
                    month TEXT NOT NULL,
                    target TEXT NOT NULL,
                    target_label TEXT,
                    security_key TEXT NOT NULL,
                    issuer_name TEXT,
                    asset_desc TEXT,
                    asset_class TEXT,
                    country TEXT,
                    long_value REAL,
                    short_value REAL,
                    net_value REAL,
                    gross_value REAL,
                    fund_count INTEGER,
                    holding_count INTEGER,
                    PRIMARY KEY (month, target, security_key, asset_class)
                );

                CREATE TABLE IF NOT EXISTS cvm_cda_fund_type_asset_exposure (
                    month TEXT NOT NULL,
                    fund_type TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    value REAL,
                    abs_value REAL,
                    fund_count INTEGER,
                    holding_count INTEGER,
                    PRIMARY KEY (month, fund_type, asset_class)
                );

                CREATE INDEX IF NOT EXISTS idx_cvm_cda_holdings_month_fund ON cvm_cda_holdings(month, fund_cnpj);
                CREATE INDEX IF NOT EXISTS idx_cvm_cda_holdings_month_asset ON cvm_cda_holdings(month, asset_class, asset_code);
                CREATE INDEX IF NOT EXISTS idx_cvm_cda_holdings_month_issuer ON cvm_cda_holdings(month, issuer_name);
                CREATE INDEX IF NOT EXISTS idx_cvm_cda_holdings_month_country ON cvm_cda_holdings(month, country);
                CREATE INDEX IF NOT EXISTS idx_cvm_cda_summary_dim ON cvm_cda_summary_group(month, dimension);
                CREATE INDEX IF NOT EXISTS idx_cvm_cda_fund_target ON cvm_cda_fund_target_exposure(month, target);
                CREATE INDEX IF NOT EXISTS idx_cvm_cda_asset_target ON cvm_cda_asset_target_exposure(month, target);
                """
            )

    def status(self) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            months = [dict(row) for row in con.execute(
                "SELECT * FROM cvm_cda_months ORDER BY month DESC LIMIT 18"
            ).fetchall()]
            latest = con.execute(
                "SELECT * FROM cvm_cda_months WHERE status = 'ready' ORDER BY month DESC LIMIT 1"
            ).fetchone()
            logs = [dict(row) for row in con.execute(
                """
                SELECT month, event_at, level, message, detail_json
                FROM cvm_cda_ingest_logs
                ORDER BY id DESC
                LIMIT 20
                """
            ).fetchall()]
        return {
            "ok": bool(latest),
            "success": True,
            "db_path": str(self.db_path),
            "data_dir": str(self.root_dir),
            "latest_month": latest["month"] if latest else None,
            "latest_label": _month_label(latest["month"]) if latest else None,
            "months": months,
            "logs": logs,
            "schedule": {
                "cadence": "monthly_dataset_with_daily_representations",
                "recent_months": "M-1, M-2 e M-3 rechecados diariamente de terca a sabado apos 08:00 BRT",
                "older_months": "M-4 ate M-12 rechecados semanalmente",
                "collector_time": str(getattr(Config, "CVM_CDA_UPDATE_TIME", "08:25")),
                "lookback_months": int(getattr(Config, "CVM_CDA_RECENT_MONTH_LOOKBACK", 3)),
            },
        }

    def discover_remote_months(self, force: bool = False) -> dict[str, Any]:
        resources = self._discover_resources(force=force)
        months = [resource.as_dict() for _, resource in sorted(resources.items(), reverse=True)]
        return {
            "ok": True,
            "success": True,
            "source": CVM_CDA_DATASET_URL,
            "latest_remote_month": months[0]["month"] if months else None,
            "months": months,
        }

    def ingest_latest(self, *, force: bool = False, lookback_months: int = 1) -> dict[str, Any]:
        resources = self._discover_resources(force=force)
        if not resources:
            raise RuntimeError("No CVM CDA resources discovered through CKAN.")
        latest_month = sorted(resources.keys())[-1]
        months = _previous_months(latest_month, max(1, lookback_months))
        results = []
        for month in months:
            result = self.ingest_month(month=month, force=force)
            results.append(result)
        return {
            "ok": any(item.get("ok") for item in results),
            "success": True,
            "latest_month": latest_month,
            "months": results,
            "dashboard": self.get_dashboard("latest"),
        }

    def ingest_month(self, month: str | None = None, *, force: bool = False) -> dict[str, Any]:
        self.init_db()
        resources = self._discover_resources(force=force)
        if not resources:
            raise RuntimeError("No CVM CDA resources discovered through CKAN.")
        if not month or str(month).lower() == "latest":
            month = sorted(resources.keys())[-1]
        month = str(month)
        if not re.fullmatch(r"20\d{4}", month):
            raise ValueError("month must look like YYYYMM")
        resource = resources.get(month) or CdaRemoteMonth(month=month, url=CVM_CDA_PATTERN.format(yyyymm=month))

        with self._connect() as con:
            current = con.execute("SELECT * FROM cvm_cda_months WHERE month = ?", (month,)).fetchone()
            if (
                current
                and current["status"] == "ready"
                and not force
                and current["source_last_modified"]
                and current["source_last_modified"] == resource.last_modified
            ):
                return {
                    "ok": True,
                    "success": True,
                    "month": month,
                    "status": "skipped_current",
                    "dashboard": self.get_dashboard(month),
                }

        zip_path = self._download_month(resource, force=force)
        return self.ingest_zip(zip_path=zip_path, month=month, source_url=resource.url, source_last_modified=resource.last_modified, force=True)

    def ingest_zip(
        self,
        *,
        zip_path: str | os.PathLike[str],
        month: str | None = None,
        source_url: str | None = None,
        source_last_modified: str | None = None,
        force: bool = True,
    ) -> dict[str, Any]:
        started = time.monotonic()
        self.init_db()
        path = Path(zip_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"CVM CDA zip not found: {path}")
        month = month or _month_from_text(path.name)
        if not month:
            raise ValueError("Could not infer month from CDA zip path.")

        with zipfile.ZipFile(path) as archive:
            members = [info for info in archive.infolist() if info.filename.lower().endswith(".csv")]
            if not members:
                raise RuntimeError("CVM CDA zip does not contain CSV files.")

            with self._connect() as con:
                if force:
                    self._delete_month(con, month)
                self._log(con, month, "info", "Starting CVM CDA ingest", {"zip_path": str(path), "files": len(members)})
                con.execute(
                    """
                    INSERT OR REPLACE INTO cvm_cda_months (
                        month, source_url, source_last_modified, zip_path, imported_at, status,
                        schema_version, file_count, total_rows, metadata_json, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        month,
                        source_url,
                        source_last_modified,
                        str(path),
                        _utc_now(),
                        "importing",
                        CVM_CDA_SCHEMA_VERSION,
                        len(members),
                        0,
                        json.dumps({"members": [info.filename for info in members]}, ensure_ascii=False),
                        None,
                    ),
                )
                con.commit()

                total_rows = 0
                for info in members:
                    if info.filename.upper().endswith(f"PL_{month}.CSV"):
                        row_count = self._ingest_pl_member(con, archive, info, month)
                    else:
                        row_count = self._ingest_holding_member(con, archive, info, month)
                    total_rows += row_count
                    con.commit()

                self._build_analytics(con, month)
                totals = con.execute(
                    """
                    SELECT
                        MAX(dt_comptc) AS latest_dt,
                        SUM(value_market) AS total_position_value,
                        SUM(CASE WHEN is_confidential = 1 THEN value_market ELSE 0 END) AS total_confidential_value
                    FROM cvm_cda_holdings
                    WHERE month = ?
                    """,
                    (month,),
                ).fetchone()
                pl_row = con.execute(
                    "SELECT SUM(pl) AS total_pl FROM cvm_cda_fund_pl WHERE month = ?",
                    (month,),
                ).fetchone()
                con.execute(
                    """
                    UPDATE cvm_cda_months
                    SET imported_at = ?, status = 'ready', total_rows = ?, latest_dt = ?,
                        total_pl = ?, total_position_value = ?, total_confidential_value = ?,
                        error = NULL
                    WHERE month = ?
                    """,
                    (
                        _utc_now(),
                        total_rows,
                        totals["latest_dt"] if totals else None,
                        pl_row["total_pl"] if pl_row else None,
                        totals["total_position_value"] if totals else None,
                        totals["total_confidential_value"] if totals else None,
                        month,
                    ),
                )
                self._log(
                    con,
                    month,
                    "info",
                    "CVM CDA ingest completed",
                    {"rows": total_rows, "elapsed_ms": round((time.monotonic() - started) * 1000)},
                )
                con.commit()

        return {
            "ok": True,
            "success": True,
            "month": month,
            "rows": total_rows,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "dashboard": self.get_dashboard(month),
        }

    def get_dashboard(self, month: str | None = None) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {
                    "ok": False,
                    "success": False,
                    "error": "CVM CDA database is empty. Ingest a monthly package first.",
                    "report": {
                        "name": "CVM CDA Brasil",
                        "source": "CVM Composicao e Diversificacao das Aplicacoes",
                        "status": "empty",
                    },
                }
            month = resolved
            month_row = con.execute("SELECT * FROM cvm_cda_months WHERE month = ?", (month,)).fetchone()
            manifest = [dict(row) for row in con.execute(
                """
                SELECT source_file, source_block, row_count, column_count, file_size_bytes, loaded_at
                FROM cvm_cda_file_manifest
                WHERE month = ?
                ORDER BY source_file
                """,
                (month,),
            ).fetchall()]
            kpi_row = con.execute(
                """
                SELECT
                    COUNT(*) AS holdings,
                    COUNT(DISTINCT fund_cnpj) AS funds,
                    COUNT(DISTINCT issuer_name) AS issuers,
                    COUNT(DISTINCT asset_code) AS securities,
                    SUM(value_market) AS reported_value,
                    SUM(ABS(value_market)) AS reported_abs_value,
                    SUM(CASE WHEN is_foreign = 1 THEN value_market ELSE 0 END) AS foreign_value,
                    SUM(CASE WHEN is_confidential = 1 THEN value_market ELSE 0 END) AS confidential_value,
                    SUM(CASE WHEN is_related_issuer = 1 THEN value_market ELSE 0 END) AS related_issuer_value,
                    SUM(CASE WHEN is_derivative = 1 THEN value_market ELSE 0 END) AS derivative_value,
                    SUM(value_buy) AS buy_value,
                    SUM(value_sell) AS sell_value
                FROM cvm_cda_holdings
                WHERE month = ?
                """,
                (month,),
            ).fetchone()
            fund_row = con.execute(
                """
                SELECT
                    COUNT(*) AS funds_with_pl,
                    SUM(pl) AS total_pl,
                    AVG(concentration_pct) AS avg_concentration_pct,
                    SUM(CASE WHEN concentration_pct > 25 THEN 1 ELSE 0 END) AS funds_concentration_gt_25,
                    SUM(CASE WHEN confidential_pct_pl > 10 THEN 1 ELSE 0 END) AS funds_confidential_gt_10
                FROM cvm_cda_fund_summary
                WHERE month = ?
                """,
                (month,),
            ).fetchone()
            summaries = {
                dimension: self._summary_rows(con, month, dimension, 24)
                for dimension in (
                    "asset_class",
                    "asset_subclass",
                    "fund_type",
                    "country",
                    "issuer",
                    "security",
                    "maturity_bucket",
                    "related_issuer",
                )
            }
            top_funds = [dict(row) for row in con.execute(
                """
                SELECT *
                FROM cvm_cda_fund_summary
                WHERE month = ?
                ORDER BY pl DESC
                LIMIT 25
                """,
                (month,),
            ).fetchall()]
            top_issuers = self._summary_rows(con, month, "issuer", 25)
            top_assets = self._summary_rows(con, month, "security", 25)
            logs = [dict(row) for row in con.execute(
                """
                SELECT event_at, level, message, detail_json
                FROM cvm_cda_ingest_logs
                WHERE month = ?
                ORDER BY id DESC
                LIMIT 18
                """,
                (month,),
            ).fetchall()]

            report = {
                "name": "CVM CDA Brasil",
                "month": month,
                "period_label": _month_label(month),
                "as_of_date": month_row["latest_dt"] if month_row else None,
                "source": "CVM Composicao e Diversificacao das Aplicacoes",
                "source_url": CVM_CDA_DATASET_URL,
                "download_url": month_row["source_url"] if month_row else CVM_CDA_PATTERN.format(yyyymm=month),
                "status": month_row["status"] if month_row else "unknown",
                "last_imported_at": month_row["imported_at"] if month_row else None,
                "db_path": str(self.db_path),
                "notes": [
                    "Base mensal de carteira de fundos brasileiros publicada pela CVM.",
                    "Posicoes recentes podem aparecer agregadas como confidenciais ate o fim do prazo regulatorio.",
                    "Representa estoque de carteira e negociacoes reportadas no mes, nao fluxo diario de cotistas.",
                ],
            }
            kpis = {
                "holdings": kpi_row["holdings"] or 0,
                "funds": kpi_row["funds"] or 0,
                "funds_with_pl": fund_row["funds_with_pl"] or 0,
                "issuers": kpi_row["issuers"] or 0,
                "securities": kpi_row["securities"] or 0,
                "reported_value": kpi_row["reported_value"] or 0,
                "reported_abs_value": kpi_row["reported_abs_value"] or 0,
                "total_pl": fund_row["total_pl"] or 0,
                "foreign_value": kpi_row["foreign_value"] or 0,
                "confidential_value": kpi_row["confidential_value"] or 0,
                "related_issuer_value": kpi_row["related_issuer_value"] or 0,
                "derivative_value": kpi_row["derivative_value"] or 0,
                "buy_value": kpi_row["buy_value"] or 0,
                "sell_value": kpi_row["sell_value"] or 0,
                "avg_concentration_pct": fund_row["avg_concentration_pct"] or 0,
                "funds_concentration_gt_25": fund_row["funds_concentration_gt_25"] or 0,
                "funds_confidential_gt_10": fund_row["funds_confidential_gt_10"] or 0,
            }
            return {
                "ok": True,
                "success": True,
                "report": report,
                "kpis": kpis,
                "summaries": summaries,
                "top_funds": top_funds,
                "top_issuers": top_issuers,
                "top_assets": top_assets,
                "heatmap": self._build_heatmap(con, month),
                "manifest": manifest,
                "logs": logs,
                "source_status": self.status(),
                "ai_readiness": self._build_insights(report, kpis, summaries, top_issuers),
            }

    def list_funds(
        self,
        *,
        target: str = "foreign",
        side: str = "long",
        month: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        target = self._normalize_target(target)
        side = self._normalize_side(side)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=100)
        order_col = {"long": "long_value", "short": "short_value", "net": "net_value"}[side]
        filter_sql = {
            "long": "AND COALESCE(long_value, 0) > 0",
            "short": "AND COALESCE(short_value, 0) > 0",
            "net": "AND ABS(COALESCE(net_value, 0)) > 0",
        }[side]
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {"ok": False, "success": False, "error": "CVM CDA database is empty.", "rows": []}
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cvm_cda_fund_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                """,
                (resolved, target),
            ).fetchone()["total"]
            rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    fund_cnpj, target, target_label, fund_name, fund_type, dt_comptc, pl,
                    long_value, short_value, net_value, gross_value, target_pct_pl,
                    holdings_count, issuers_count, assets_count, top_issuer, top_asset_class,
                    concentration_pct, {order_col} AS selected_value
                FROM cvm_cda_fund_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                ORDER BY {order_col} DESC
                LIMIT ? OFFSET ?
                """,
                (resolved, target, per_page, offset),
            ).fetchall()]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "target": target,
                "target_label": CDA_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "rows": rows,
            }

    def list_assets(
        self,
        *,
        target: str = "foreign",
        side: str = "long",
        month: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        target = self._normalize_target(target)
        side = self._normalize_side(side)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=100)
        order_col = {"long": "long_value", "short": "short_value", "net": "net_value"}[side]
        filter_sql = {
            "long": "AND COALESCE(long_value, 0) > 0",
            "short": "AND COALESCE(short_value, 0) > 0",
            "net": "AND ABS(COALESCE(net_value, 0)) > 0",
        }[side]
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {"ok": False, "success": False, "error": "CVM CDA database is empty.", "rows": []}
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cvm_cda_asset_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                """,
                (resolved, target),
            ).fetchone()["total"]
            rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    security_key, issuer_name, asset_desc, asset_class, country,
                    long_value, short_value, net_value, gross_value, fund_count, holding_count,
                    {order_col} AS selected_value
                FROM cvm_cda_asset_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                ORDER BY {order_col} DESC
                LIMIT ? OFFSET ?
                """,
                (resolved, target, per_page, offset),
            ).fetchall()]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "target": target,
                "target_label": CDA_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "rows": rows,
            }

    def list_fund_holdings(
        self,
        fund_cnpj: str,
        *,
        target: str = "foreign",
        side: str = "all",
        month: str | None = None,
        page: int = 1,
        per_page: int = 40,
    ) -> dict[str, Any]:
        fund_cnpj = str(fund_cnpj or "").strip()
        if not fund_cnpj:
            raise ValueError("fund_cnpj is required")
        target = self._normalize_target(target)
        side = self._normalize_side(side, allow_all=True)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=120)
        condition = CDA_TARGET_SQL[target]
        side_filter = ""
        if side == "long":
            side_filter = "AND COALESCE(value_market, 0) > 0"
        elif side == "short":
            side_filter = "AND COALESCE(value_market, 0) < 0"
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {"ok": False, "success": False, "error": "CVM CDA database is empty.", "rows": []}
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cvm_cda_holdings
                WHERE month = ? AND fund_cnpj = ? AND ({condition}) {side_filter}
                """,
                (resolved, fund_cnpj),
            ).fetchone()["total"]
            fund = con.execute(
                "SELECT * FROM cvm_cda_fund_summary WHERE month = ? AND fund_cnpj = ?",
                (resolved, fund_cnpj),
            ).fetchone()
            rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    source_block, fund_cnpj, fund_name, dt_comptc, tp_aplic, tp_ativo,
                    asset_class, asset_subclass, asset_code, asset_desc, isin,
                    issuer_name, issuer_doc, country, maturity_date, maturity_bucket,
                    qty_final, value_market, value_cost, value_buy, value_sell,
                    is_confidential, is_foreign, is_related_issuer,
                    CASE WHEN COALESCE(value_market, 0) < 0 THEN 'short' ELSE 'long' END AS position_side
                FROM cvm_cda_holdings
                WHERE month = ? AND fund_cnpj = ? AND ({condition}) {side_filter}
                ORDER BY ABS(COALESCE(value_market, 0)) DESC
                LIMIT ? OFFSET ?
                """,
                (resolved, fund_cnpj, per_page, offset),
            ).fetchall()]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "target": target,
                "target_label": CDA_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "fund": dict(fund) if fund else {"fund_cnpj": fund_cnpj},
                "rows": rows,
            }

    def get_positioning_lab(self, month: str | None = None) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {"ok": False, "success": False, "error": "CVM CDA database is empty."}
            heatmap = self._build_heatmap(con, resolved)
            class_mix = self._summary_rows(con, resolved, "asset_class", 18)
            fund_type_mix = self._summary_rows(con, resolved, "fund_type", 18)
            concentration = [dict(row) for row in con.execute(
                """
                SELECT fund_cnpj, fund_name, fund_type, pl, max_position_value, concentration_pct,
                       foreign_pct_pl, private_credit_pct_pl, confidential_pct_pl, turnover_pct_pl
                FROM cvm_cda_fund_summary
                WHERE month = ?
                ORDER BY concentration_pct DESC
                LIMIT 80
                """,
                (resolved,),
            ).fetchall()]
            issuer_crowding = self._summary_rows(con, resolved, "issuer", 40)
            edge_funds = [dict(row) for row in con.execute(
                """
                SELECT fund_cnpj, fund_name, fund_type, pl, foreign_pct_pl, private_credit_pct_pl,
                       confidential_pct_pl, concentration_pct,
                       (COALESCE(foreign_pct_pl, 0) * 0.35
                        + COALESCE(private_credit_pct_pl, 0) * 0.25
                        + COALESCE(confidential_pct_pl, 0) * 0.25
                        + COALESCE(concentration_pct, 0) * 0.15) AS edge_score
                FROM cvm_cda_fund_summary
                WHERE month = ?
                ORDER BY edge_score DESC
                LIMIT 40
                """,
                (resolved,),
            ).fetchall()]
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "heatmap": heatmap,
                "class_mix": class_mix,
                "fund_type_mix": fund_type_mix,
                "concentration": concentration,
                "issuer_crowding": issuer_crowding,
                "edge_funds": edge_funds,
            }

    def get_redemption_radar(self, month: str | None = None, *, force: bool = False) -> dict[str, Any]:
        cached = self._read_radar_cache()
        if (
            cached
            and not force
        ):
            cached_month = str((cached.get("report") or {}).get("month") or "")
            requested_month = str(month or "").strip().lower()
            use_cached_latest = requested_month in {"", "latest"}
            use_cached_explicit = bool(requested_month and requested_month == cached_month)
            if use_cached_latest or use_cached_explicit:
                return cached
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_radar_month(con, month)
            if not resolved:
                return {"ok": False, "success": False, "error": "CVM CDA database is empty."}
            month_row = con.execute("SELECT * FROM cvm_cda_months WHERE month = ?", (resolved,)).fetchone()
        if (
            cached
            and not force
            and str((cached.get("report") or {}).get("month") or "") == resolved
        ):
            return cached
        payload = self._build_redemption_radar_payload(resolved, month_row)
        atomic_json_dump(str(self.radar_cache_path), _clean_json(payload), indent=2)
        return payload

    def _read_radar_cache(self) -> dict[str, Any] | None:
        try:
            with open(self.radar_cache_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None
        except Exception:
            logger.exception("Failed to read CVM CDA radar cache")
            return None

    def _build_redemption_radar_payload(self, month: str, month_row: sqlite3.Row | None) -> dict[str, Any]:
        with self._connect() as con:
            fund_summary = pd.read_sql_query(
                """
                SELECT
                    month, fund_cnpj, fund_name, fund_type, dt_comptc, pl,
                    holding_count, issuer_count, asset_count, position_value, abs_position_value,
                    foreign_value, public_bond_value, private_credit_value, fund_quota_value,
                    equity_value, derivative_value, confidential_value, related_issuer_value,
                    buy_value, sell_value, max_position_value, concentration_pct,
                    foreign_pct_pl, private_credit_pct_pl, confidential_pct_pl, turnover_pct_pl
                FROM cvm_cda_fund_summary
                WHERE month = ?
                """,
                con,
                params=[month],
            )
            holdings = pd.read_sql_query(
                """
                SELECT
                    fund_cnpj,
                    MAX(fund_name) AS fund_name,
                    MAX(fund_type) AS fund_type,
                    asset_class,
                    COALESCE(is_confidential, 0) AS is_confidential,
                    SUM(CASE WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(value_buy, 0)) AS buy_value,
                    SUM(COALESCE(value_sell, 0)) AS sell_value,
                    COUNT(*) AS holding_count
                FROM cvm_cda_holdings
                WHERE month = ?
                GROUP BY fund_cnpj, asset_class, COALESCE(is_confidential, 0)
                """,
                con,
                params=[month],
            )

        if fund_summary.empty:
            return {"ok": False, "success": False, "error": "Sem resumo de fundos no CDA."}

        for frame in (fund_summary, holdings):
            frame["fund_cnpj"] = frame["fund_cnpj"].astype(str).str.replace(r"\D", "", regex=True)
            frame["fund_name"] = frame.get("fund_name", "").astype(str).fillna("").str.strip() if "fund_name" in frame.columns else ""
            frame["fund_type"] = frame.get("fund_type", "").astype(str).fillna("").str.strip() if "fund_type" in frame.columns else ""

        cda_as_of_date = _parse_date_text(month_row["latest_dt"] if month_row else None) or _parse_date_text(fund_summary["dt_comptc"].max())
        cda_as_of_date = cda_as_of_date or _parse_date_text(f"{month[:4]}-{month[4:6]}-01") or _local_now().date()
        cda_funds = set(fund_summary["fund_cnpj"].astype(str).tolist())
        flow_as_of_date, flow_daily = self._load_flow_radar_context(cda_funds, cda_as_of_date=cda_as_of_date)
        if flow_daily.empty:
            return {
                "ok": False,
                "success": False,
                "error": "Nao foi possivel cruzar o CDA com o Informe Diario no momento.",
            }

        latest_flow = (
            flow_daily[flow_daily["dt"].dt.date <= flow_as_of_date]
            .sort_values(["cnpj_fundo", "dt"])
            .groupby("cnpj_fundo", as_index=False)
            .tail(1)
        )
        flow_since = flow_daily[
            (flow_daily["dt"].dt.date > cda_as_of_date) & (flow_daily["dt"].dt.date <= flow_as_of_date)
        ].copy()
        if flow_since.empty:
            flow_since = flow_daily[flow_daily["dt"].dt.date <= flow_as_of_date].copy()
        redemption_period_days = max((flow_as_of_date - cda_as_of_date).days, 1) if cda_as_of_date else 1
        since_agg = (
            flow_since.groupby("cnpj_fundo", as_index=False)
            .agg(
                net_flow_since_cda=("captacao_liquida", "sum"),
                gross_redemption_since_cda=("resgate", "sum"),
                gross_subscription_since_cda=("captacao", "sum"),
                negative_days=("captacao_liquida", lambda series: int((series < 0).sum())),
            )
        )
        latest_flow = latest_flow.merge(since_agg, on="cnpj_fundo", how="left")
        for column in [
            "net_flow_since_cda",
            "gross_redemption_since_cda",
            "gross_subscription_since_cda",
            "negative_days",
        ]:
            if column not in latest_flow.columns:
                latest_flow[column] = 0.0
            latest_flow[column] = latest_flow[column].fillna(0.0)

        flow_cols = [
            "cnpj_fundo",
            "fund_name",
            "macro_classe",
            "pl",
            "captacao_liquida",
            "rolling_flow_5d",
            "rolling_flow_21d",
            "rolling_flow_63d",
            "rolling_redemption_5d",
            "rolling_redemption_21d",
            "rolling_redemption_63d",
            "rolling_subscription_5d",
            "rolling_subscription_21d",
            "rolling_subscription_63d",
            "rolling_flow_pct_pl_21d",
            "classification_confidence",
            "net_flow_since_cda",
            "gross_redemption_since_cda",
            "gross_subscription_since_cda",
            "negative_days",
        ]
        flow_latest = latest_flow[[column for column in flow_cols if column in latest_flow.columns]].copy()
        flow_latest = flow_latest.rename(
            columns={
                "fund_name": "flow_fund_name",
                "pl": "latest_pl",
                "captacao_liquida": "net_flow_1d",
                "resgate": "gross_redemption_1d",
                "captacao": "gross_subscription_1d",
            }
        )
        fund_summary = fund_summary.merge(flow_latest, left_on="fund_cnpj", right_on="cnpj_fundo", how="left")
        if "cnpj_fundo" in fund_summary.columns:
            fund_summary = fund_summary.drop(columns=["cnpj_fundo"])
        fund_summary["flow_fund_name"] = fund_summary.get("flow_fund_name", "").fillna("").astype(str)
        fund_summary["fund_name"] = fund_summary["fund_name"].where(
            fund_summary["fund_name"].astype(str).str.strip() != "",
            fund_summary["flow_fund_name"],
        )
        fund_summary["macro_classe"] = fund_summary.apply(self._infer_macro_class, axis=1)
        fund_summary["macro_classe"] = fund_summary["macro_classe"].fillna("Unclassified").astype(str).replace({"nan": "Unclassified", "": "Unclassified"})
        fund_summary["fund_type_group"] = fund_summary.apply(self._infer_fund_type_group, axis=1)
        fund_summary["cda_pl"] = fund_summary["pl"].apply(_safe_float)
        fund_summary["latest_pl"] = fund_summary.get("latest_pl", 0.0).apply(_safe_float)
        fund_summary["estimated_current_pl"] = fund_summary.apply(
            lambda row: self._estimate_current_pl(row["cda_pl"], row["latest_pl"], row.get("net_flow_since_cda")),
            axis=1,
        )
        fund_summary["scale_ratio"] = fund_summary.apply(
            lambda row: _clamp(_safe_div(row["estimated_current_pl"], row["cda_pl"], default=1.0), 0.1, 3.0),
            axis=1,
        )
        fund_summary["redemption_period_days"] = redemption_period_days
        fund_summary["daily_gross_redemption_since_cda"] = fund_summary.apply(
            lambda row: _safe_float(row.get("gross_redemption_since_cda")) / max(redemption_period_days, 1),
            axis=1,
        )
        fund_summary["daily_outflow_base"] = fund_summary.apply(
            lambda row: max(0.0, _safe_float(row.get("daily_gross_redemption_since_cda"))),
            axis=1,
        )
        fund_summary["daily_outflow_stress"] = fund_summary.apply(
            lambda row: max(0.0, _safe_float(row.get("daily_gross_redemption_since_cda"))) * 1.2,
            axis=1,
        )
        fund_summary["daily_outflow_extreme"] = fund_summary.apply(
            lambda row: max(0.0, _safe_float(row.get("daily_gross_redemption_since_cda"))) * 1.55,
            axis=1,
        )

        holdings["asset_class"] = holdings["asset_class"].fillna("").astype(str).str.strip().replace("", "Outros")
        holdings = holdings.merge(
            fund_summary[
                [
                    "fund_cnpj",
                    "fund_name",
                    "fund_type",
                    "fund_type_group",
                    "macro_classe",
                    "cda_pl",
                    "estimated_current_pl",
                    "scale_ratio",
                    "net_flow_since_cda",
                    "gross_redemption_since_cda",
                    "redemption_period_days",
                    "daily_gross_redemption_since_cda",
                    "turnover_pct_pl",
                ]
            ],
            on="fund_cnpj",
            how="left",
        )
        bucket_rows = []
        for row in holdings.to_dict("records"):
            meta = self._bucket_meta(row.get("asset_class"))
            long_value = max(_safe_float(row.get("long_value")), 0.0)
            short_value = max(_safe_float(row.get("short_value")), 0.0)
            scaled_long = long_value * _clamp(row.get("scale_ratio") or 1.0, 0.1, 3.0)
            confidential_discount = RADAR_CONFIDENTIAL_SALEABILITY_DISCOUNT if int(row.get("is_confidential") or 0) else 1.0
            effective_saleability = _safe_float(meta["saleability_share"]) * confidential_discount
            plausible_saleability = self._plausible_saleability_share(
                bucket=meta["bucket"],
                effective_saleability=effective_saleability,
                turnover_pct_pl=row.get("turnover_pct_pl"),
                is_confidential=row.get("is_confidential"),
            )
            defensive_floor = self._defensive_floor_pct(row.get("macro_classe"))
            free_pre = scaled_long * effective_saleability * max(0.0, 1.0 - defensive_floor)
            plausible_pre = scaled_long * plausible_saleability * max(0.0, 1.0 - defensive_floor)
            bucket_rows.append(
                {
                    "fund_cnpj": row.get("fund_cnpj"),
                    "fund_name": row.get("fund_name"),
                    "fund_type": row.get("fund_type"),
                    "fund_type_group": row.get("fund_type_group") or row.get("fund_type") or row.get("macro_classe") or "Outros",
                    "macro_classe": row.get("macro_classe") or "Unclassified",
                    "asset_class": row.get("asset_class") or "Outros",
                    "bucket": meta["bucket"],
                    "bucket_label": meta["label"],
                    "liquidity_rank": int(meta["rank"]),
                    "is_confidential": int(row.get("is_confidential") or 0),
                    "base_saleability_share": _safe_float(meta["saleability_share"]),
                    "saleability_share": effective_saleability,
                    "plausible_saleability_share": plausible_saleability,
                    "defensive_floor_pct": defensive_floor,
                    "cda_long_value": long_value,
                    "estimated_long_value": scaled_long,
                    "short_value": short_value,
                    "buy_value": _safe_float(row.get("buy_value")),
                    "sell_value": _safe_float(row.get("sell_value")),
                    "holding_count": int(row.get("holding_count") or 0),
                    "free_inventory_pre": free_pre,
                    "plausible_inventory_pre": plausible_pre,
                    "net_flow_since_cda": _safe_float(row.get("net_flow_since_cda")),
                    "gross_redemption_since_cda": _safe_float(row.get("gross_redemption_since_cda")),
                    "redemption_period_days": int(row.get("redemption_period_days") or redemption_period_days),
                    "daily_gross_redemption_since_cda": _safe_float(row.get("daily_gross_redemption_since_cda")),
                }
            )
        bucket_df = pd.DataFrame(bucket_rows)
        if bucket_df.empty:
            return {"ok": False, "success": False, "error": "Sem buckets elegiveis para o radar CDA."}

        allocation_rows: list[dict[str, Any]] = []
        for fund_cnpj, group in bucket_df.sort_values(["fund_cnpj", "liquidity_rank"]).groupby("fund_cnpj", sort=False):
            redemption_pressure = max(
                0.0,
                _safe_float(group["gross_redemption_since_cda"].iloc[0]),
                -_safe_float(group["net_flow_since_cda"].iloc[0]),
            )
            remaining = redemption_pressure
            plausible_remaining = remaining
            touched_buckets: list[str] = []
            for _, row in group.iterrows():
                free_pre = _safe_float(row.get("free_inventory_pre"))
                plausible_pre = _safe_float(row.get("plausible_inventory_pre"))
                consumed = min(free_pre, remaining) if remaining > 0 else 0.0
                plausible_consumed = min(plausible_pre, plausible_remaining) if plausible_remaining > 0 else 0.0
                remaining -= consumed
                plausible_remaining -= plausible_consumed
                if consumed > 0:
                    touched_buckets.append(str(row.get("bucket_label") or row.get("asset_class") or ""))
                allocation_rows.append(
                    {
                        **row.to_dict(),
                        "consumed_since_cda": consumed,
                        "free_inventory_remaining": max(0.0, free_pre - consumed),
                        "plausible_consumed_since_cda": plausible_consumed,
                        "plausible_inventory_remaining": max(0.0, plausible_pre - plausible_consumed),
                        "bucket_touched": consumed > 0,
                    }
                )
        allocation_df = pd.DataFrame(allocation_rows)
        fund_bucket_agg = (
            allocation_df.groupby("fund_cnpj", as_index=False)
            .agg(
                sellable_inventory_pre=("free_inventory_pre", "sum"),
                sellable_inventory_remaining=("free_inventory_remaining", "sum"),
                plausible_inventory_pre=("plausible_inventory_pre", "sum"),
                plausible_inventory_remaining=("plausible_inventory_remaining", "sum"),
                quick_inventory_remaining=("free_inventory_remaining", lambda series: float(series.iloc[:0].sum())),
                consumed_since_cda=("consumed_since_cda", "sum"),
                plausible_consumed_since_cda=("plausible_consumed_since_cda", "sum"),
                quick_inventory_pre=("free_inventory_pre", "sum"),
            )
        )
        quick_by_fund = (
            allocation_df[allocation_df["liquidity_rank"] <= 2]
            .groupby("fund_cnpj", as_index=False)
            .agg(
                quick_inventory_pre=("free_inventory_pre", "sum"),
                quick_inventory_remaining=("free_inventory_remaining", "sum"),
            )
        )
        fund_bucket_agg = fund_bucket_agg.drop(columns=["quick_inventory_pre", "quick_inventory_remaining"]).merge(
            quick_by_fund,
            on="fund_cnpj",
            how="left",
        )
        touched = allocation_df[allocation_df["bucket_touched"]].copy()
        touched_rank = (
            touched.sort_values(["fund_cnpj", "liquidity_rank"])
            .groupby("fund_cnpj", as_index=False)
            .tail(1)[["fund_cnpj", "bucket_label"]]
            .rename(columns={"bucket_label": "bucket_at_risk"})
        )
        fund_radar = fund_summary.merge(fund_bucket_agg, on="fund_cnpj", how="left").merge(touched_rank, on="fund_cnpj", how="left")
        numeric_fill = [
            "sellable_inventory_pre",
            "sellable_inventory_remaining",
            "plausible_inventory_pre",
            "plausible_inventory_remaining",
            "quick_inventory_pre",
            "quick_inventory_remaining",
            "consumed_since_cda",
            "plausible_consumed_since_cda",
        ]
        for column in numeric_fill:
            if column not in fund_radar.columns:
                fund_radar[column] = 0.0
            fund_radar[column] = fund_radar[column].fillna(0.0)
        fund_radar["bucket_at_risk"] = fund_radar["bucket_at_risk"].fillna("Nao consumiu estoque")
        fund_radar["inventory_burn_pct"] = fund_radar.apply(
            lambda row: _safe_div(row.get("consumed_since_cda"), row.get("sellable_inventory_pre"), default=0.0),
            axis=1,
        )
        fund_radar["plausible_inventory_burn_pct"] = fund_radar.apply(
            lambda row: _safe_div(row.get("plausible_consumed_since_cda"), row.get("plausible_inventory_pre"), default=0.0),
            axis=1,
        )
        for scenario in RADAR_SCENARIOS:
            scenario_key = scenario["key"]
            scenario_mult = _safe_float(scenario.get("multiplier")) or 1.0
            daily_outflow = fund_radar.apply(
                lambda row: self._scenario_daily_outflow(
                    row,
                    scenario_key=scenario_key,
                    multiplier=scenario_mult,
                ),
                axis=1,
            )
            fund_radar[f"daily_outflow_{scenario_key}"] = daily_outflow
            fund_radar[f"runway_days_{scenario_key}"] = fund_radar.apply(
                lambda row: _safe_div(row.get("sellable_inventory_remaining"), row.get(f"daily_outflow_{scenario_key}"), default=999.0),
                axis=1,
            )
            fund_radar[f"plausible_runway_days_{scenario_key}"] = fund_radar.apply(
                lambda row: _safe_div(row.get("plausible_inventory_remaining"), row.get(f"daily_outflow_{scenario_key}"), default=999.0),
                axis=1,
            )
        fund_radar["coverage_flag"] = fund_radar.apply(self._radar_coverage_flag, axis=1)
        fund_radar["negative_21d"] = fund_radar.get("rolling_flow_21d", 0.0).apply(lambda value: _safe_float(value) < 0)

        matched_mask = fund_radar["latest_pl"].fillna(0.0) > 0
        total_cda_pl = float(fund_radar["cda_pl"].fillna(0.0).sum())
        matched_cda_pl = float(fund_radar.loc[matched_mask, "cda_pl"].fillna(0.0).sum())

        class_summary = (
            fund_radar.groupby("fund_type_group", as_index=False)
            .agg(
                fund_count=("fund_cnpj", "nunique"),
                macro_classe=("macro_classe", lambda series: _first_nonempty(series, default="Unclassified")),
                cda_pl=("cda_pl", "sum"),
                current_pl=("estimated_current_pl", "sum"),
                latest_pl=("latest_pl", "sum"),
                net_flow_since_cda=("net_flow_since_cda", "sum"),
                gross_redemption_since_cda=("gross_redemption_since_cda", "sum"),
                gross_subscription_since_cda=("gross_subscription_since_cda", "sum"),
                net_flow_21d=("rolling_flow_21d", "sum"),
                net_flow_5d=("rolling_flow_5d", "sum"),
                gross_redemption_21d=("rolling_redemption_21d", "sum"),
                gross_redemption_5d=("rolling_redemption_5d", "sum"),
                gross_redemption_63d=("rolling_redemption_63d", "sum"),
                gross_subscription_21d=("rolling_subscription_21d", "sum"),
                sellable_inventory_pre=("sellable_inventory_pre", "sum"),
                sellable_inventory_remaining=("sellable_inventory_remaining", "sum"),
                plausible_inventory_pre=("plausible_inventory_pre", "sum"),
                plausible_inventory_remaining=("plausible_inventory_remaining", "sum"),
                consumed_since_cda=("consumed_since_cda", "sum"),
                plausible_consumed_since_cda=("plausible_consumed_since_cda", "sum"),
                concentration_pct=("concentration_pct", "mean"),
                confidential_pct_pl=("confidential_pct_pl", "mean"),
                daily_outflow_base=("daily_outflow_base", "sum"),
                daily_outflow_stress=("daily_outflow_stress", "sum"),
                daily_outflow_extreme=("daily_outflow_extreme", "sum"),
                daily_gross_redemption_since_cda=("daily_gross_redemption_since_cda", "sum"),
            )
        )
        class_summary["radar_group"] = class_summary["fund_type_group"].fillna("Nao informado").astype(str)
        class_summary["macro_classe"] = class_summary["radar_group"]
        class_summary["inventory_burn_pct"] = class_summary.apply(
            lambda row: _safe_div(row.get("consumed_since_cda"), row.get("sellable_inventory_pre"), default=0.0),
            axis=1,
        )
        class_summary["plausible_inventory_burn_pct"] = class_summary.apply(
            lambda row: _safe_div(row.get("plausible_consumed_since_cda"), row.get("plausible_inventory_pre"), default=0.0),
            axis=1,
        )
        for scenario in RADAR_SCENARIOS:
            key = scenario["key"]
            class_summary[f"runway_days_{key}"] = class_summary.apply(
                lambda row: _safe_div(row.get("sellable_inventory_remaining"), row.get(f"daily_outflow_{key}"), default=999.0),
                axis=1,
            )
            class_summary[f"plausible_runway_days_{key}"] = class_summary.apply(
                lambda row: _safe_div(row.get("plausible_inventory_remaining"), row.get(f"daily_outflow_{key}"), default=999.0),
                axis=1,
            )
        class_summary = class_summary.sort_values(
            ["plausible_runway_days_stress", "runway_days_stress", "plausible_inventory_remaining"],
            ascending=[True, True, False],
        ).reset_index(drop=True)

        bucket_summary = (
            allocation_df.groupby(["bucket", "bucket_label", "liquidity_rank"], as_index=False)
            .agg(
                fund_count=("fund_cnpj", "nunique"),
                cda_long_value=("cda_long_value", "sum"),
                estimated_long_value=("estimated_long_value", "sum"),
                free_inventory_pre=("free_inventory_pre", "sum"),
                free_inventory_remaining=("free_inventory_remaining", "sum"),
                plausible_inventory_pre=("plausible_inventory_pre", "sum"),
                plausible_inventory_remaining=("plausible_inventory_remaining", "sum"),
                consumed_since_cda=("consumed_since_cda", "sum"),
                plausible_consumed_since_cda=("plausible_consumed_since_cda", "sum"),
                sell_value=("sell_value", "sum"),
                buy_value=("buy_value", "sum"),
            )
        )
        bucket_summary["inventory_burn_pct"] = bucket_summary.apply(
            lambda row: _safe_div(row.get("consumed_since_cda"), row.get("free_inventory_pre"), default=0.0),
            axis=1,
        )
        bucket_summary["plausible_inventory_burn_pct"] = bucket_summary.apply(
            lambda row: _safe_div(row.get("plausible_consumed_since_cda"), row.get("plausible_inventory_pre"), default=0.0),
            axis=1,
        )
        bucket_summary = bucket_summary.sort_values(["liquidity_rank", "free_inventory_remaining"], ascending=[True, False]).reset_index(drop=True)

        heatmap_x = [row["bucket_label"] for row in bucket_summary.to_dict("records")]
        heatmap_y = class_summary["radar_group"].astype(str).tolist()
        heatmap_group = (
            allocation_df.groupby(["fund_type_group", "bucket", "bucket_label"], as_index=False)
            .agg(
                remaining_inventory=("free_inventory_remaining", "sum"),
                plausible_remaining_inventory=("plausible_inventory_remaining", "sum"),
                consumed_since_cda=("consumed_since_cda", "sum"),
                plausible_consumed_since_cda=("plausible_consumed_since_cda", "sum"),
                free_inventory_pre=("free_inventory_pre", "sum"),
                plausible_inventory_pre=("plausible_inventory_pre", "sum"),
                current_value=("estimated_long_value", "sum"),
                fund_count=("fund_cnpj", "nunique"),
            )
        )
        heatmap_cells = []
        for row in heatmap_group.to_dict("records"):
            burn_pct = _safe_div(row.get("consumed_since_cda"), row.get("free_inventory_pre"), default=0.0)
            plausible_burn_pct = _safe_div(row.get("plausible_consumed_since_cda"), row.get("plausible_inventory_pre"), default=0.0)
            radar_group = str(row.get("fund_type_group") or "Nao informado")
            heatmap_cells.append(
                {
                    "macro_classe": radar_group,
                    "fund_type_group": radar_group,
                    "radar_group": radar_group,
                    "bucket": row.get("bucket"),
                    "bucket_label": row.get("bucket_label"),
                    "remaining_inventory": _safe_float(row.get("remaining_inventory")),
                    "plausible_remaining_inventory": _safe_float(row.get("plausible_remaining_inventory")),
                    "consumed_since_cda": _safe_float(row.get("consumed_since_cda")),
                    "plausible_consumed_since_cda": _safe_float(row.get("plausible_consumed_since_cda")),
                    "burn_pct": burn_pct,
                    "plausible_burn_pct": plausible_burn_pct,
                    "fund_count": int(row.get("fund_count") or 0),
                    "current_value": _safe_float(row.get("current_value")),
                    "score": burn_pct - _safe_div(row.get("remaining_inventory"), row.get("current_value"), default=0.0),
                }
            )

        scenario_rows = []
        for scenario in RADAR_SCENARIOS:
            key = scenario["key"]
            daily_total = float(fund_radar[f"daily_outflow_{key}"].fillna(0.0).sum())
            runway_days = _safe_div(
                fund_radar["sellable_inventory_remaining"].fillna(0.0).sum(),
                daily_total,
                default=999.0,
            )
            plausible_runway_days = _safe_div(
                fund_radar["plausible_inventory_remaining"].fillna(0.0).sum(),
                daily_total,
                default=999.0,
            )
            scenario_rows.append(
                {
                    **scenario,
                    "daily_outflow_brl": daily_total,
                    "runway_days": runway_days,
                    "plausible_runway_days": plausible_runway_days,
                    "funds_under_5d": int((fund_radar[f"runway_days_{key}"] <= 5).sum()),
                    "plausible_funds_under_5d": int((fund_radar[f"plausible_runway_days_{key}"] <= 5).sum()),
                    "funds_under_10d": int((fund_radar[f"runway_days_{key}"] <= 10).sum()),
                    "plausible_funds_under_10d": int((fund_radar[f"plausible_runway_days_{key}"] <= 10).sum()),
                }
            )

        top_pressure_class = "Unclassified"
        if not class_summary.empty:
            preferred = class_summary[
                class_summary["radar_group"].astype(str).str.strip().str.lower().ne("unclassified")
            ]
            source_frame = preferred if not preferred.empty else class_summary
            top_pressure_class = str(source_frame.iloc[0]["radar_group"])
        summary = {
            "total_cda_pl": total_cda_pl,
            "total_current_pl": float(fund_radar["estimated_current_pl"].fillna(0.0).sum()),
            "total_latest_pl": float(fund_radar["latest_pl"].fillna(0.0).sum()),
            "total_net_flow_since_cda": float(fund_radar["net_flow_since_cda"].fillna(0.0).sum()),
            "total_gross_redemption_since_cda": float(fund_radar["gross_redemption_since_cda"].fillna(0.0).sum()),
            "total_gross_redemption_5d": float(fund_radar.get("rolling_redemption_5d", pd.Series(dtype=float)).fillna(0.0).sum()),
            "total_gross_redemption_21d": float(fund_radar.get("rolling_redemption_21d", pd.Series(dtype=float)).fillna(0.0).sum()),
            "total_gross_redemption_63d": float(fund_radar.get("rolling_redemption_63d", pd.Series(dtype=float)).fillna(0.0).sum()),
            "total_gross_subscription_21d": float(fund_radar.get("rolling_subscription_21d", pd.Series(dtype=float)).fillna(0.0).sum()),
            "redemption_period_days": redemption_period_days,
            "daily_gross_redemption_since_cda": float(fund_radar["daily_gross_redemption_since_cda"].fillna(0.0).sum()),
            "sellable_inventory_pre": float(fund_radar["sellable_inventory_pre"].fillna(0.0).sum()),
            "sellable_inventory_remaining": float(fund_radar["sellable_inventory_remaining"].fillna(0.0).sum()),
            "plausible_inventory_pre": float(fund_radar["plausible_inventory_pre"].fillna(0.0).sum()),
            "plausible_inventory_remaining": float(fund_radar["plausible_inventory_remaining"].fillna(0.0).sum()),
            "quick_inventory_remaining": float(fund_radar["quick_inventory_remaining"].fillna(0.0).sum()),
            "inventory_burn_pct": _safe_div(
                fund_radar["consumed_since_cda"].fillna(0.0).sum(),
                fund_radar["sellable_inventory_pre"].fillna(0.0).sum(),
                default=0.0,
            ),
            "plausible_inventory_burn_pct": _safe_div(
                fund_radar["plausible_consumed_since_cda"].fillna(0.0).sum(),
                fund_radar["plausible_inventory_pre"].fillna(0.0).sum(),
                default=0.0,
            ),
            "top_pressure_class": top_pressure_class,
            "funds_with_negative_21d": int(fund_radar["negative_21d"].sum()),
            "funds_at_risk_stress_5d": int((fund_radar["runway_days_stress"] <= 5).sum()),
            "plausible_funds_at_risk_stress_5d": int((fund_radar["plausible_runway_days_stress"] <= 5).sum()),
            "plausible_horizon_days": RADAR_PLAUSIBLE_HORIZON_DAYS,
        }

        fund_rows = fund_radar.copy()
        fund_rows = fund_rows[
            (fund_rows["sellable_inventory_pre"] > 0)
            | (fund_rows["plausible_inventory_pre"] > 0)
            | (fund_rows["rolling_flow_21d"].fillna(0.0) < 0)
            | (fund_rows["net_flow_since_cda"].fillna(0.0) < 0)
        ]
        fund_rows = fund_rows.sort_values(
            ["plausible_runway_days_stress", "runway_days_stress", "inventory_burn_pct", "sellable_inventory_remaining"],
            ascending=[True, True, False, True],
        ).head(120)

        coverage = {
            "cda_funds": int(len(fund_summary)),
            "matched_flow_funds": int(matched_mask.sum()),
            "matched_flow_funds_pct": _safe_div(matched_mask.sum(), len(fund_summary), default=0.0),
            "total_cda_pl": total_cda_pl,
            "matched_cda_pl": matched_cda_pl,
            "matched_cda_pl_pct": _safe_div(matched_cda_pl, total_cda_pl, default=0.0),
            "flow_as_of_date": flow_as_of_date.isoformat(),
            "cda_as_of_date": cda_as_of_date.isoformat() if cda_as_of_date else None,
            "days_since_cda": max((flow_as_of_date - cda_as_of_date).days, 0) if cda_as_of_date else None,
        }

        return {
            "ok": True,
            "success": True,
            "generated_at": _utc_now(),
            "report": {
                "name": "Radar CDA",
                "month": month,
                "period_label": _month_label(month),
                "cda_as_of_date": cda_as_of_date.isoformat() if cda_as_of_date else None,
                "flow_as_of_date": flow_as_of_date.isoformat(),
                "source": "CVM CDA + CVM Informe Diario + Cadastro CVM",
                "source_url": CVM_CDA_DATASET_URL,
                "download_url": month_row["source_url"] if month_row else CVM_CDA_PATTERN.format(yyyymm=month),
                "db_path": str(self.db_path),
                "methodology": [
                    "Estoque parte do CDA mensal e eh reescalado pelo PL mais recente do Informe Diario.",
                    "A ordem de consumo assume waterfall de buckets mais liquidos para menos liquidos.",
                    "Os floors defensivos sao heuristicas por macro classe, nao limites regulatórios formais.",
                    f"Vendavel plausivel usa caps por bucket e giro observado para um horizonte de {RADAR_PLAUSIBLE_HORIZON_DAYS} dias.",
                ],
            },
            "coverage": coverage,
            "summary": summary,
            "default_scenario": "stress",
            "scenarios": scenario_rows,
            "class_summary": [
                {
                    **{key: (_safe_float(value, ) if isinstance(value, (int, float)) else value) for key, value in row.items()}
                }
                for row in class_summary.to_dict("records")
            ],
            "bucket_summary": [
                {
                    **{key: (_safe_float(value, ) if isinstance(value, (int, float)) else value) for key, value in row.items()}
                }
                for row in bucket_summary.to_dict("records")
            ],
            "heatmap": {
                "x": heatmap_x,
                "y": heatmap_y,
                "cells": heatmap_cells,
                "metric": "inventory_burn_pct",
            },
            "fund_rows": [
                {
                    "rank": index + 1,
                    "fund_cnpj": row.get("fund_cnpj"),
                    "fund_name": row.get("fund_name"),
                    "fund_type": row.get("fund_type"),
                    "fund_type_group": row.get("fund_type_group"),
                    "radar_group": row.get("fund_type_group") or row.get("macro_classe"),
                    "macro_classe": row.get("macro_classe"),
                    "cda_pl": _safe_float(row.get("cda_pl")),
                    "current_pl": _safe_float(row.get("estimated_current_pl")),
                    "latest_pl": _safe_float(row.get("latest_pl")),
                    "scale_ratio": _safe_float(row.get("scale_ratio")),
                    "net_flow_1d": _safe_float(row.get("net_flow_1d")),
                    "gross_redemption_1d": _safe_float(row.get("gross_redemption_1d")),
                    "gross_subscription_1d": _safe_float(row.get("gross_subscription_1d")),
                    "net_flow_5d": _safe_float(row.get("rolling_flow_5d")),
                    "net_flow_21d": _safe_float(row.get("rolling_flow_21d")),
                    "net_flow_63d": _safe_float(row.get("rolling_flow_63d")),
                    "gross_redemption_5d": _safe_float(row.get("rolling_redemption_5d")),
                    "gross_redemption_21d": _safe_float(row.get("rolling_redemption_21d")),
                    "gross_redemption_63d": _safe_float(row.get("rolling_redemption_63d")),
                    "gross_subscription_21d": _safe_float(row.get("rolling_subscription_21d")),
                    "redemption_period_days": int(row.get("redemption_period_days") or redemption_period_days),
                    "daily_gross_redemption_since_cda": _safe_float(row.get("daily_gross_redemption_since_cda")),
                    "net_flow_since_cda": _safe_float(row.get("net_flow_since_cda")),
                    "gross_redemption_since_cda": _safe_float(row.get("gross_redemption_since_cda")),
                    "sellable_inventory_pre": _safe_float(row.get("sellable_inventory_pre")),
                    "sellable_inventory_remaining": _safe_float(row.get("sellable_inventory_remaining")),
                    "plausible_inventory_pre": _safe_float(row.get("plausible_inventory_pre")),
                    "plausible_inventory_remaining": _safe_float(row.get("plausible_inventory_remaining")),
                    "quick_inventory_remaining": _safe_float(row.get("quick_inventory_remaining")),
                    "inventory_burn_pct": _safe_float(row.get("inventory_burn_pct")),
                    "plausible_inventory_burn_pct": _safe_float(row.get("plausible_inventory_burn_pct")),
                    "daily_outflow_base": _safe_float(row.get("daily_outflow_base")),
                    "daily_outflow_stress": _safe_float(row.get("daily_outflow_stress")),
                    "daily_outflow_extreme": _safe_float(row.get("daily_outflow_extreme")),
                    "runway_days_base": _safe_float(row.get("runway_days_base")),
                    "runway_days_stress": _safe_float(row.get("runway_days_stress")),
                    "runway_days_extreme": _safe_float(row.get("runway_days_extreme")),
                    "plausible_runway_days_base": _safe_float(row.get("plausible_runway_days_base")),
                    "plausible_runway_days_stress": _safe_float(row.get("plausible_runway_days_stress")),
                    "plausible_runway_days_extreme": _safe_float(row.get("plausible_runway_days_extreme")),
                    "concentration_pct": _safe_float(row.get("concentration_pct")),
                    "confidential_pct_pl": _safe_float(row.get("confidential_pct_pl")),
                    "turnover_pct_pl": _safe_float(row.get("turnover_pct_pl")),
                    "bucket_at_risk": row.get("bucket_at_risk"),
                    "coverage_flag": row.get("coverage_flag"),
                    "classification_confidence": _safe_float(row.get("classification_confidence")),
                }
                for index, row in enumerate(fund_rows.to_dict("records"))
            ],
        }

    def _load_flow_radar_context(self, cda_funds: set[str], cda_as_of_date: date | None = None) -> tuple[date, pd.DataFrame]:
        from .funds_flow_local_service import FundsFlowLocalService

        flow_service = FundsFlowLocalService()
        latest_snapshot = flow_service._read_latest() or {}
        latest_report = latest_snapshot.get("report") or {}
        requested_end = (
            _parse_date_text(latest_report.get("requested_date"))
            or _parse_date_text(latest_report.get("as_of_date"))
            or _local_now().date()
        )
        rolling_anchor = requested_end - timedelta(days=95)
        start_date = min(cda_as_of_date, rolling_anchor) if cda_as_of_date else rolling_anchor
        informe_df, _ = flow_service._load_informe_diario(start_date=start_date, end_date=requested_end, force=False)
        if informe_df.empty:
            return requested_end, pd.DataFrame()
        informe_df["cnpj_fundo"] = informe_df["cnpj_fundo"].astype(str).str.replace(r"\D", "", regex=True)
        flow_as_of_date = flow_service._select_complete_as_of_date(informe_df, requested_end)
        if cda_funds:
            informe_df = informe_df[informe_df["cnpj_fundo"].isin(cda_funds)].copy()
        if informe_df.empty:
            return requested_end, pd.DataFrame()
        master_df, _ = flow_service._load_cadastro(force=False)
        if not master_df.empty:
            master_df["cnpj_fundo"] = master_df["cnpj_fundo"].astype(str).str.replace(r"\D", "", regex=True)
            if cda_funds:
                master_df = master_df[master_df["cnpj_fundo"].isin(cda_funds)].copy()
        return flow_as_of_date, self._aggregate_informe_radar_daily(informe_df, master_df)

    def _aggregate_informe_radar_daily(self, informe_df: pd.DataFrame, master_df: pd.DataFrame) -> pd.DataFrame:
        if informe_df.empty:
            return pd.DataFrame()
        df = informe_df.copy()
        if "dt" not in df.columns:
            df["dt"] = pd.to_datetime(df.get("dt_comptc"), errors="coerce")
        else:
            df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        df = df[df["dt"].notna()].copy()
        if df.empty:
            return pd.DataFrame()
        df["cnpj_fundo"] = df["cnpj_fundo"].astype(str).str.replace(r"\D", "", regex=True)
        for column in ("pl", "captacao", "resgate", "captacao_liquida", "cotistas"):
            if column not in df.columns:
                df[column] = 0.0
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
        if float(df["captacao_liquida"].abs().sum() or 0.0) == 0.0 and float((df["captacao"].abs() + df["resgate"].abs()).sum() or 0.0) > 0.0:
            df["captacao_liquida"] = df["captacao"] - df["resgate"]
        daily = (
            df.groupby(["dt", "cnpj_fundo"], as_index=False)
            .agg(
                pl=("pl", "sum"),
                captacao=("captacao", "sum"),
                resgate=("resgate", "sum"),
                captacao_liquida=("captacao_liquida", "sum"),
                cotistas=("cotistas", "sum"),
            )
        )
        if not master_df.empty:
            identity = master_df.copy()
            identity["cnpj_fundo"] = identity["cnpj_fundo"].astype(str).str.replace(r"\D", "", regex=True)
            keep = [column for column in ("cnpj_fundo", "nome_fundo", "macro_classe", "classification_confidence") if column in identity.columns]
            identity = identity[keep].drop_duplicates("cnpj_fundo")
            daily = daily.merge(identity, on="cnpj_fundo", how="left")
        if "nome_fundo" not in daily.columns:
            daily["nome_fundo"] = ""
        if "macro_classe" not in daily.columns:
            daily["macro_classe"] = "Unclassified"
        if "classification_confidence" not in daily.columns:
            daily["classification_confidence"] = 0.0
        daily["delta_cotistas"] = (
            daily.sort_values(["cnpj_fundo", "dt"])
            .groupby("cnpj_fundo")["cotistas"]
            .diff()
            .fillna(0.0)
        )
        daily["fund_name"] = daily["nome_fundo"].fillna("").astype(str)
        daily["macro_classe"] = daily["macro_classe"].fillna("Unclassified").astype(str)
        daily["classification_confidence"] = pd.to_numeric(daily["classification_confidence"], errors="coerce").fillna(0.0)
        return self._aggregate_flow_fund_daily(daily)

    def _aggregate_flow_fund_daily(self, series_df: pd.DataFrame) -> pd.DataFrame:
        if series_df.empty:
            return pd.DataFrame()
        df = series_df.copy()
        identity = (
            df.sort_values(["dt", "cnpj_fundo", "pl"], ascending=[True, True, False])
            .groupby(["dt", "cnpj_fundo"], as_index=False)
            .agg(
                fund_name=("nome_fundo", lambda series: _first_nonempty(series, default="")),
                macro_classe=("macro_classe", lambda series: _first_nonempty(
                    [value for value in series.tolist() if _norm_key(value) not in {"", "UNCLASSIFIED"}],
                    default="Unclassified",
                )),
                classification_confidence=("classification_confidence", "max"),
            )
        )
        totals = (
            df.groupby(["dt", "cnpj_fundo"], as_index=False)
            .agg(
                pl=("pl", "sum"),
                captacao=("captacao", "sum"),
                resgate=("resgate", "sum"),
                captacao_liquida=("captacao_liquida", "sum"),
                cotistas=("cotistas", "sum"),
                delta_cotistas=("delta_cotistas", "sum"),
            )
        )
        daily = totals.merge(identity, on=["dt", "cnpj_fundo"], how="left")
        daily = daily.sort_values(["cnpj_fundo", "dt"]).reset_index(drop=True)
        grouped = daily.groupby("cnpj_fundo", sort=False)
        for window in (5, 21, 63):
            daily[f"rolling_flow_{window}d"] = grouped["captacao_liquida"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            daily[f"rolling_redemption_{window}d"] = grouped["resgate"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            daily[f"rolling_subscription_{window}d"] = grouped["captacao"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            base_pl = grouped["pl"].shift(window)
            daily[f"rolling_flow_pct_pl_{window}d"] = base_pl.where(base_pl > 0)
            daily[f"rolling_flow_pct_pl_{window}d"] = daily.apply(
                lambda row: _safe_div(row.get(f"rolling_flow_{window}d"), row.get(f"rolling_flow_pct_pl_{window}d"), default=0.0),
                axis=1,
            )
        return daily

    def _estimate_current_pl(self, cda_pl: Any, latest_pl: Any, net_flow_since_cda: Any) -> float:
        cda_value = _safe_float(cda_pl)
        latest_value = _safe_float(latest_pl)
        if latest_value > 0:
            return latest_value
        if cda_value > 0:
            return max(cda_value + _safe_float(net_flow_since_cda), cda_value * 0.15)
        return max(latest_value, 0.0)

    def _bucket_meta(self, asset_class: Any) -> dict[str, Any]:
        return RADAR_BUCKET_META.get(str(asset_class or "").strip(), RADAR_DEFAULT_BUCKET)

    def _defensive_floor_pct(self, macro_classe: Any) -> float:
        macro_key = _norm_key(macro_classe)
        return _safe_float(RADAR_DEFENSIVE_FLOOR.get(macro_key, RADAR_DEFENSIVE_FLOOR["UNCLASSIFIED"]))

    def _plausible_saleability_share(
        self,
        *,
        bucket: Any,
        effective_saleability: Any,
        turnover_pct_pl: Any,
        is_confidential: Any,
    ) -> float:
        bucket_key = str(bucket or "").strip()
        horizon_cap = _safe_float(RADAR_PLAUSIBLE_BUCKET_SHARE.get(bucket_key, 0.04))
        turnover_factor = _clamp(_safe_float(turnover_pct_pl) / 18.0, 0.45, 1.20)
        confidentiality_factor = 0.80 if int(is_confidential or 0) else 1.0
        capped_share = horizon_cap * turnover_factor * confidentiality_factor
        return min(_safe_float(effective_saleability), capped_share)

    def _infer_macro_class(self, row: pd.Series) -> str:
        existing = _norm_text(row.get("macro_classe"))
        if existing and _norm_key(existing) not in {"UNCLASSIFIED", ""}:
            return existing
        fund_type = _norm_key(row.get("fund_type"))
        if "FIDC" in fund_type:
            return "FIDC"
        if "FIP" in fund_type:
            return "FIP"
        if "FIAGRO" in fund_type:
            return "Fiagro"
        if "FIIM" in fund_type or "FII" in fund_type:
            return "FII"
        if "ETF" in fund_type:
            return "ETF"
        pl = max(_safe_float(row.get("cda_pl")), 1.0)
        equity_share = _safe_div(row.get("equity_value"), pl, default=0.0)
        public_share = _safe_div(row.get("public_bond_value"), pl, default=0.0)
        private_share = _safe_div(row.get("private_credit_value"), pl, default=0.0)
        foreign_share = _safe_div(row.get("foreign_value"), pl, default=0.0)
        derivative_share = _safe_div(row.get("derivative_value"), pl, default=0.0)
        fund_quota_share = _safe_div(row.get("fund_quota_value"), pl, default=0.0)
        if equity_share >= 0.5 and derivative_share < 0.2:
            return "Acoes"
        if foreign_share >= 0.45 and equity_share < 0.25:
            return "Cambial"
        if public_share + private_share >= 0.55 and equity_share < 0.2 and foreign_share < 0.25:
            return "Renda Fixa"
        if derivative_share >= 0.12 or foreign_share >= 0.15 or (equity_share >= 0.15 and public_share >= 0.15):
            return "Multimercado"
        if fund_quota_share >= 0.45:
            return "Outros"
        return "Unclassified"

    def _infer_fund_type_group(self, row: pd.Series) -> str:
        fund_type = _norm_text(row.get("fund_type"))
        fund_key = _norm_key(fund_type)
        macro = _norm_text(row.get("macro_classe"))
        if "FIF" in fund_key or "CLASSES" in fund_key:
            if macro and _norm_key(macro) not in {"", "UNCLASSIFIED"}:
                return f"FIF / {macro}"
            return "FIF"
        if "FIDC" in fund_key:
            return "FIDC"
        if "FIP" in fund_key:
            return "FIP"
        if "FIAGRO" in fund_key:
            return "FIAGRO"
        if "FII" in fund_key or "FIIM" in fund_key:
            return "FII"
        if "ETF" in fund_key:
            return "ETF"
        if "FMP" in fund_key:
            return "FMP"
        if "PREVID" in fund_key:
            return "Previdencia"
        if "RENDA FIXA" in fund_key or fund_key in {"FI", "FIC"}:
            if macro and _norm_key(macro) not in {"", "UNCLASSIFIED"}:
                return macro
        if fund_type and fund_key not in {"", "NAO INFORMADO", "NAN"}:
            return fund_type[:48]
        if macro and _norm_key(macro) not in {"", "UNCLASSIFIED"}:
            return macro
        return "Nao informado"

    def _scenario_daily_outflow(self, row: pd.Series, *, scenario_key: str, multiplier: float) -> float:
        base = max(0.0, _safe_float(row.get("daily_gross_redemption_since_cda")), _safe_float(row.get("daily_outflow_base")))
        if scenario_key == "base":
            return base * multiplier
        if scenario_key == "extreme":
            return base * multiplier
        return base * multiplier

    def _radar_coverage_flag(self, row: pd.Series) -> str:
        runway = _safe_float(row.get("runway_days_stress"))
        burn = _safe_float(row.get("inventory_burn_pct"))
        confidential = _safe_float(row.get("confidential_pct_pl"))
        if runway <= 5 or burn >= 0.8:
            return "critico"
        if runway <= 12 or confidential >= 15:
            return "atencao"
        return "confortavel"

    def _discover_resources(self, *, force: bool = False) -> dict[str, CdaRemoteMonth]:
        if self._ckan_cache and not force and time.time() - self._ckan_cache[0] < 900:
            return self._ckan_cache[1]
        try:
            response = requests.get(
                CVM_CKAN_PACKAGE_URL,
                params={"id": CVM_CDA_PACKAGE},
                timeout=30,
                headers={"User-Agent": "MiroFish Funds Flow Local CDA research"},
            )
            response.raise_for_status()
            package = response.json().get("result") or {}
        except Exception as exc:
            logger.warning("Failed to discover CVM CDA CKAN resources: %s", exc)
            package = {}
        resources: dict[str, CdaRemoteMonth] = {}
        for resource in package.get("resources") or []:
            url = str(resource.get("url") or "")
            name = str(resource.get("name") or "")
            month = _month_from_text(f"{url} {name}")
            if not month or not url.lower().endswith(".zip"):
                continue
            if "cda_fi_" not in url.lower():
                continue
            resources[month] = CdaRemoteMonth(
                month=month,
                url=url,
                name=name,
                last_modified=resource.get("last_modified") or resource.get("metadata_modified"),
            )
        self._ckan_cache = (time.time(), resources)
        return resources

    def _download_month(self, resource: CdaRemoteMonth, *, force: bool) -> Path:
        target_dir = self.raw_dir / resource.month
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / f"cda_fi_{resource.month}.zip"
        if zip_path.exists() and zip_path.stat().st_size > 0 and not force:
            return zip_path
        response = requests.get(
            resource.url,
            timeout=180,
            stream=True,
            headers={"User-Agent": "MiroFish Funds Flow Local CDA research"},
        )
        response.raise_for_status()
        tmp_path = zip_path.with_suffix(".zip.tmp")
        with open(tmp_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        os.replace(tmp_path, zip_path)
        return zip_path

    def _delete_month(self, con: sqlite3.Connection, month: str) -> None:
        for table in (
            "cvm_cda_file_manifest",
            "cvm_cda_holdings",
            "cvm_cda_fund_pl",
            "cvm_cda_fund_summary",
            "cvm_cda_summary_group",
            "cvm_cda_fund_target_exposure",
            "cvm_cda_asset_target_exposure",
            "cvm_cda_fund_type_asset_exposure",
            "cvm_cda_months",
        ):
            con.execute(f"DELETE FROM {table} WHERE month = ?", (month,))

    def _ingest_pl_member(self, con: sqlite3.Connection, archive: zipfile.ZipFile, info: zipfile.ZipInfo, month: str) -> int:
        row_count = 0
        columns: list[str] = []
        with archive.open(info) as handle:
            for chunk in pd.read_csv(
                handle,
                sep=";",
                dtype=str,
                encoding="latin1",
                chunksize=50000,
                keep_default_na=False,
                quoting=csv.QUOTE_NONE,
                on_bad_lines="skip",
            ):
                if not columns:
                    columns = list(chunk.columns)
                output = pd.DataFrame(
                    {
                        "month": month,
                        "fund_type": _series_str(chunk, "TP_FUNDO_CLASSE"),
                        "fund_cnpj": _series_str(chunk, "CNPJ_FUNDO_CLASSE"),
                        "fund_name": _series_str(chunk, "DENOM_SOCIAL"),
                        "dt_comptc": _series_str(chunk, "DT_COMPTC"),
                        "pl": _series_num(chunk, "VL_PATRIM_LIQ"),
                    }
                )
                output = output[output["fund_cnpj"].astype(str).str.strip() != ""]
                output.to_sql("cvm_cda_fund_pl", con, if_exists="append", index=False)
                row_count += len(output)
        con.execute(
            """
            INSERT OR REPLACE INTO cvm_cda_file_manifest (
                month, source_file, source_block, row_count, column_count, file_size_bytes, loaded_at, columns_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (month, info.filename, "PL", row_count, len(columns), info.file_size, _utc_now(), json.dumps(columns, ensure_ascii=False)),
        )
        self._log(con, month, "info", "Loaded CDA PL file", {"file": info.filename, "rows": row_count})
        return row_count

    def _ingest_holding_member(self, con: sqlite3.Connection, archive: zipfile.ZipFile, info: zipfile.ZipInfo, month: str) -> int:
        row_count = 0
        columns: list[str] = []
        block = _source_block(info.filename)
        with archive.open(info) as handle:
            for chunk in pd.read_csv(
                handle,
                sep=";",
                dtype=str,
                encoding="latin1",
                chunksize=50000,
                keep_default_na=False,
                quoting=csv.QUOTE_NONE,
                on_bad_lines="skip",
            ):
                if not columns:
                    columns = list(chunk.columns)
                output = self._normalize_holding_chunk(chunk, month=month, source_file=info.filename, block=block)
                output = output[output["fund_cnpj"].astype(str).str.strip() != ""]
                if not output.empty:
                    output.to_sql("cvm_cda_holdings", con, if_exists="append", index=False)
                    row_count += len(output)
        con.execute(
            """
            INSERT OR REPLACE INTO cvm_cda_file_manifest (
                month, source_file, source_block, row_count, column_count, file_size_bytes, loaded_at, columns_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (month, info.filename, block, row_count, len(columns), info.file_size, _utc_now(), json.dumps(columns, ensure_ascii=False)),
        )
        self._log(con, month, "info", "Loaded CDA holdings file", {"file": info.filename, "block": block, "rows": row_count})
        return row_count

    def _normalize_holding_chunk(self, frame: pd.DataFrame, *, month: str, source_file: str, block: str) -> pd.DataFrame:
        tp_aplic = _series_str(frame, "TP_APLIC")
        tp_ativo = _series_str(frame, "TP_ATIVO")
        asset_desc = _series_first_present(frame, ("DS_ATIVO", "DS_ATIVO_EXTERIOR", "NM_FUNDO_CLASSE_SUBCLASSE_COTA", "CD_SWAP"))
        asset_class = [
            _asset_class_for(block, aplic, ativo, desc)
            for aplic, ativo, desc in zip(tp_aplic.tolist(), tp_ativo.tolist(), asset_desc.tolist())
        ]
        country = _series_str(frame, "PAIS")
        country_code = _series_str(frame, "CD_PAIS")
        dt_comptc = _series_str(frame, "DT_COMPTC")
        maturity = _series_first_present(frame, ("DT_VENC", "DT_FIM_VIGENCIA"))
        output = pd.DataFrame(
            {
                "month": month,
                "source_file": source_file,
                "source_block": block,
                "fund_type": _series_str(frame, "TP_FUNDO_CLASSE"),
                "fund_cnpj": _series_str(frame, "CNPJ_FUNDO_CLASSE"),
                "fund_name": _series_str(frame, "DENOM_SOCIAL"),
                "dt_comptc": dt_comptc,
                "tp_aplic": tp_aplic,
                "tp_ativo": tp_ativo,
                "tp_negoc": _series_str(frame, "TP_NEGOC"),
                "asset_class": asset_class,
                "asset_subclass": tp_ativo.mask(tp_ativo.astype(str).str.strip() == "", tp_aplic),
                "asset_code": _series_first_present(
                    frame,
                    (
                        "CD_ATIVO",
                        "CD_ISIN",
                        "CD_SELIC",
                        "CD_SWAP",
                        "CD_ATIVO_BV_MERC",
                        "CNPJ_FUNDO_CLASSE_COTA",
                        "CPF_CNPJ_EMISSOR",
                        "CNPJ_EMISSOR",
                    ),
                ),
                "asset_desc": asset_desc,
                "isin": _series_str(frame, "CD_ISIN"),
                "issuer_name": _series_first_present(frame, ("EMISSOR", "INVEST_COLETIVO_GESTOR", "NM_FUNDO_CLASSE_SUBCLASSE_COTA")),
                "issuer_doc": _series_first_present(frame, ("CPF_CNPJ_EMISSOR", "CNPJ_EMISSOR", "CNPJ_FUNDO_CLASSE_COTA")),
                "risk_issuer": _series_str(frame, "RISCO_EMISSOR"),
                "country_code": country_code,
                "country": country,
                "market": _series_first_present(frame, ("BV_MERC", "CD_BV_MERC")),
                "maturity_date": maturity,
                "qty_final": _series_num(frame, "QT_POS_FINAL"),
                "value_market": _series_num(frame, "VL_MERC_POS_FINAL"),
                "value_cost": _series_num(frame, "VL_CUSTO_POS_FINAL"),
                "value_buy": _series_num(frame, "VL_AQUIS_NEGOC"),
                "value_sell": _series_num(frame, "VL_VENDA_NEGOC"),
            }
        )
        output["maturity_bucket"] = [
            _maturity_bucket(maturity_date, as_of_date)
            for maturity_date, as_of_date in zip(output["maturity_date"].tolist(), output["dt_comptc"].tolist())
        ]
        output["is_confidential"] = 1 if "CONFID" in block else 0
        output["is_foreign"] = (
            (output["source_block"] == "BLC_7")
            | (output["asset_class"] == "Investimento Exterior")
            | output["country"].astype(str).str.strip().ne("")
        ).astype(int)
        output["is_fund_quota"] = output["asset_class"].eq("Cotas de Fundos").astype(int)
        output["is_derivative"] = output["asset_class"].eq("Derivativos").astype(int)
        output["is_related_issuer"] = _series_str(frame, "EMISSOR_LIGADO").str.upper().eq("S").astype(int)
        output["country"] = output["country"].where(output["country"].astype(str).str.strip() != "", "BRASIL")
        output["country_code"] = output["country_code"].where(output["country_code"].astype(str).str.strip() != "", "BR")
        output["issuer_name"] = output["issuer_name"].where(output["issuer_name"].astype(str).str.strip() != "", output["asset_desc"])
        output["asset_code"] = output["asset_code"].where(output["asset_code"].astype(str).str.strip() != "", output["asset_desc"])
        return output[list(HOLDING_CORE_COLUMNS)]

    def _build_analytics(self, con: sqlite3.Connection, month: str) -> None:
        for table in (
            "cvm_cda_fund_summary",
            "cvm_cda_summary_group",
            "cvm_cda_fund_target_exposure",
            "cvm_cda_asset_target_exposure",
            "cvm_cda_fund_type_asset_exposure",
        ):
            con.execute(f"DELETE FROM {table} WHERE month = ?", (month,))

        con.execute(
            """
            INSERT INTO cvm_cda_fund_summary (
                month, fund_cnpj, fund_name, fund_type, dt_comptc, pl, holding_count,
                issuer_count, asset_count, position_value, abs_position_value, foreign_value,
                public_bond_value, private_credit_value, fund_quota_value, equity_value,
                derivative_value, confidential_value, related_issuer_value, buy_value, sell_value,
                max_position_value, concentration_pct, foreign_pct_pl, private_credit_pct_pl,
                confidential_pct_pl, turnover_pct_pl
            )
            SELECT
                h.month,
                h.fund_cnpj,
                MAX(h.fund_name) AS fund_name,
                MAX(h.fund_type) AS fund_type,
                MAX(h.dt_comptc) AS dt_comptc,
                MAX(p.pl) AS pl,
                COUNT(*) AS holding_count,
                COUNT(DISTINCT NULLIF(h.issuer_name, '')) AS issuer_count,
                COUNT(DISTINCT NULLIF(h.asset_code, '')) AS asset_count,
                SUM(COALESCE(h.value_market, 0)) AS position_value,
                SUM(ABS(COALESCE(h.value_market, 0))) AS abs_position_value,
                SUM(CASE WHEN h.is_foreign = 1 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS foreign_value,
                SUM(CASE WHEN h.asset_class = 'Titulos Publicos' THEN COALESCE(h.value_market, 0) ELSE 0 END) AS public_bond_value,
                SUM(CASE WHEN h.asset_class IN ('Credito Privado', 'Depositos e IF', 'Agronegocio/Credito') THEN COALESCE(h.value_market, 0) ELSE 0 END) AS private_credit_value,
                SUM(CASE WHEN h.is_fund_quota = 1 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS fund_quota_value,
                SUM(CASE WHEN h.asset_class = 'Acoes' THEN COALESCE(h.value_market, 0) ELSE 0 END) AS equity_value,
                SUM(CASE WHEN h.is_derivative = 1 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS derivative_value,
                SUM(CASE WHEN h.is_confidential = 1 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS confidential_value,
                SUM(CASE WHEN h.is_related_issuer = 1 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS related_issuer_value,
                SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                MAX(ABS(COALESCE(h.value_market, 0))) AS max_position_value,
                CASE WHEN SUM(ABS(COALESCE(h.value_market, 0))) != 0
                     THEN MAX(ABS(COALESCE(h.value_market, 0))) / SUM(ABS(COALESCE(h.value_market, 0))) * 100.0
                     ELSE NULL END AS concentration_pct,
                CASE WHEN MAX(p.pl) != 0 THEN SUM(CASE WHEN h.is_foreign = 1 THEN COALESCE(h.value_market, 0) ELSE 0 END) / MAX(p.pl) * 100.0 ELSE NULL END AS foreign_pct_pl,
                CASE WHEN MAX(p.pl) != 0 THEN SUM(CASE WHEN h.asset_class IN ('Credito Privado', 'Depositos e IF', 'Agronegocio/Credito') THEN COALESCE(h.value_market, 0) ELSE 0 END) / MAX(p.pl) * 100.0 ELSE NULL END AS private_credit_pct_pl,
                CASE WHEN MAX(p.pl) != 0 THEN SUM(CASE WHEN h.is_confidential = 1 THEN COALESCE(h.value_market, 0) ELSE 0 END) / MAX(p.pl) * 100.0 ELSE NULL END AS confidential_pct_pl,
                CASE WHEN MAX(p.pl) != 0 THEN (SUM(COALESCE(h.value_buy, 0)) + SUM(COALESCE(h.value_sell, 0))) / MAX(p.pl) * 100.0 ELSE NULL END AS turnover_pct_pl
            FROM cvm_cda_holdings h
            LEFT JOIN cvm_cda_fund_pl p
              ON p.month = h.month AND p.fund_cnpj = h.fund_cnpj
            WHERE h.month = ?
            GROUP BY h.month, h.fund_cnpj
            """,
            (month,),
        )

        total_abs = con.execute(
            "SELECT SUM(ABS(value_market)) AS total_abs FROM cvm_cda_holdings WHERE month = ?",
            (month,),
        ).fetchone()["total_abs"] or 0
        self._insert_summary(con, month, "asset_class", "asset_class", "asset_class", total_abs)
        self._insert_summary(con, month, "asset_subclass", "asset_subclass", "asset_subclass", total_abs)
        self._insert_summary(con, month, "fund_type", "fund_type", "fund_type", total_abs)
        self._insert_summary(con, month, "country", "country", "country", total_abs)
        self._insert_summary(con, month, "issuer", "issuer_name", "issuer_name", total_abs)
        self._insert_summary(con, month, "security", "COALESCE(NULLIF(asset_code, ''), asset_desc)", "COALESCE(NULLIF(asset_desc, ''), asset_code)", total_abs)
        self._insert_summary(con, month, "maturity_bucket", "maturity_bucket", "maturity_bucket", total_abs)
        self._insert_related_summary(con, month, total_abs)

        con.execute(
            """
            INSERT INTO cvm_cda_fund_type_asset_exposure (
                month, fund_type, asset_class, value, abs_value, fund_count, holding_count
            )
            SELECT month, COALESCE(NULLIF(fund_type, ''), 'Outros'), COALESCE(NULLIF(asset_class, ''), 'Outros'),
                   SUM(value_market), SUM(ABS(value_market)), COUNT(DISTINCT fund_cnpj), COUNT(*)
            FROM cvm_cda_holdings
            WHERE month = ?
            GROUP BY month, COALESCE(NULLIF(fund_type, ''), 'Outros'), COALESCE(NULLIF(asset_class, ''), 'Outros')
            """,
            (month,),
        )

        for target, condition in CDA_TARGET_SQL.items():
            label = CDA_TARGET_LABELS[target]
            con.execute(
                f"""
                INSERT INTO cvm_cda_fund_target_exposure (
                    month, target, target_label, fund_cnpj, fund_name, fund_type, dt_comptc, pl,
                    long_value, short_value, net_value, gross_value, target_pct_pl,
                    holdings_count, issuers_count, assets_count, top_issuer, top_asset_class, concentration_pct
                )
                SELECT
                    h.month,
                    ? AS target,
                    ? AS target_label,
                    h.fund_cnpj,
                    MAX(h.fund_name),
                    MAX(h.fund_type),
                    MAX(h.dt_comptc),
                    MAX(p.pl),
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    CASE WHEN MAX(p.pl) != 0 THEN SUM(COALESCE(h.value_market, 0)) / MAX(p.pl) * 100.0 ELSE NULL END AS target_pct_pl,
                    COUNT(*) AS holdings_count,
                    COUNT(DISTINCT NULLIF(h.issuer_name, '')) AS issuers_count,
                    COUNT(DISTINCT NULLIF(h.asset_code, '')) AS assets_count,
                    MAX(h.issuer_name) AS top_issuer,
                    MAX(h.asset_class) AS top_asset_class,
                    CASE WHEN SUM(ABS(COALESCE(h.value_market, 0))) != 0
                         THEN MAX(ABS(COALESCE(h.value_market, 0))) / SUM(ABS(COALESCE(h.value_market, 0))) * 100.0
                         ELSE NULL END AS concentration_pct
                FROM cvm_cda_holdings h
                LEFT JOIN cvm_cda_fund_pl p
                  ON p.month = h.month AND p.fund_cnpj = h.fund_cnpj
                WHERE h.month = ? AND ({condition})
                GROUP BY h.month, h.fund_cnpj
                """,
                (target, label, month),
            )
            con.execute(
                f"""
                INSERT INTO cvm_cda_asset_target_exposure (
                    month, target, target_label, security_key, issuer_name, asset_desc, asset_class, country,
                    long_value, short_value, net_value, gross_value, fund_count, holding_count
                )
                SELECT
                    h.month,
                    ? AS target,
                    ? AS target_label,
                    COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), 'UNCLASSIFIED') AS security_key,
                    MAX(h.issuer_name),
                    MAX(h.asset_desc),
                    COALESCE(NULLIF(h.asset_class, ''), 'Outros'),
                    MAX(h.country),
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    COUNT(DISTINCT h.fund_cnpj) AS fund_count,
                    COUNT(*) AS holding_count
                FROM cvm_cda_holdings h
                WHERE h.month = ? AND ({condition})
                GROUP BY h.month, COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), 'UNCLASSIFIED'), COALESCE(NULLIF(h.asset_class, ''), 'Outros')
                """,
                (target, label, month),
            )

    def _insert_summary(
        self,
        con: sqlite3.Connection,
        month: str,
        dimension: str,
        key_expr: str,
        label_expr: str,
        total_abs: float,
    ) -> None:
        con.execute(
            f"""
            INSERT INTO cvm_cda_summary_group (
                month, dimension, key, label, row_count, fund_count, value, abs_value, share_value_pct, extra_json
            )
            SELECT
                month,
                ? AS dimension,
                COALESCE(NULLIF({key_expr}, ''), 'UNCLASSIFIED') AS key,
                MAX(COALESCE(NULLIF({label_expr}, ''), 'Unclassified')) AS label,
                COUNT(*) AS row_count,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                SUM(value_market) AS value,
                SUM(ABS(value_market)) AS abs_value,
                CASE WHEN ? != 0 THEN SUM(ABS(value_market)) / ? * 100.0 ELSE NULL END AS share_value_pct,
                NULL AS extra_json
            FROM cvm_cda_holdings
            WHERE month = ?
            GROUP BY month, COALESCE(NULLIF({key_expr}, ''), 'UNCLASSIFIED')
            """,
            (dimension, total_abs, total_abs, month),
        )

    def _insert_related_summary(self, con: sqlite3.Connection, month: str, total_abs: float) -> None:
        con.execute(
            """
            INSERT INTO cvm_cda_summary_group (
                month, dimension, key, label, row_count, fund_count, value, abs_value, share_value_pct, extra_json
            )
            SELECT
                month,
                'related_issuer',
                CASE WHEN is_related_issuer = 1 THEN 'related' ELSE 'not_related' END,
                CASE WHEN is_related_issuer = 1 THEN 'Emissor ligado' ELSE 'Nao ligado' END,
                COUNT(*),
                COUNT(DISTINCT fund_cnpj),
                SUM(value_market),
                SUM(ABS(value_market)),
                CASE WHEN ? != 0 THEN SUM(ABS(value_market)) / ? * 100.0 ELSE NULL END,
                NULL
            FROM cvm_cda_holdings
            WHERE month = ?
            GROUP BY month, is_related_issuer
            """,
            (total_abs, total_abs, month),
        )

    def _summary_rows(self, con: sqlite3.Connection, month: str, dimension: str, limit: int) -> list[dict[str, Any]]:
        return [dict(row) for row in con.execute(
            """
            SELECT key, label, row_count, fund_count, value, abs_value, share_value_pct, extra_json
            FROM cvm_cda_summary_group
            WHERE month = ? AND dimension = ?
            ORDER BY abs_value DESC
            LIMIT ?
            """,
            (month, dimension, limit),
        ).fetchall()]

    def _build_heatmap(self, con: sqlite3.Connection, month: str) -> dict[str, Any]:
        top_fund_types = [row["fund_type"] for row in con.execute(
            """
            SELECT fund_type
            FROM cvm_cda_fund_type_asset_exposure
            WHERE month = ?
            GROUP BY fund_type
            ORDER BY SUM(abs_value) DESC
            LIMIT 14
            """,
            (month,),
        ).fetchall()]
        top_assets = [row["asset_class"] for row in con.execute(
            """
            SELECT asset_class
            FROM cvm_cda_fund_type_asset_exposure
            WHERE month = ?
            GROUP BY asset_class
            ORDER BY SUM(abs_value) DESC
            LIMIT 10
            """,
            (month,),
        ).fetchall()]
        rows = [dict(row) for row in con.execute(
            """
            SELECT fund_type, asset_class, value, abs_value, fund_count, holding_count
            FROM cvm_cda_fund_type_asset_exposure
            WHERE month = ?
            """,
            (month,),
        ).fetchall()]
        by_cell = {(row["fund_type"], row["asset_class"]): row for row in rows}
        matrix: list[list[float]] = []
        cells: list[dict[str, Any]] = []
        for fund_type in top_fund_types:
            row_values = []
            for asset_class in top_assets:
                cell = by_cell.get((fund_type, asset_class)) or {}
                value = float(cell.get("value") or 0)
                row_values.append(value)
                cells.append(
                    {
                        "fund_type": fund_type,
                        "asset_class": asset_class,
                        "value": value,
                        "abs_value": cell.get("abs_value") or 0,
                        "fund_count": cell.get("fund_count") or 0,
                        "holding_count": cell.get("holding_count") or 0,
                    }
                )
            matrix.append(row_values)
        return {
            "x": top_assets,
            "y": top_fund_types,
            "z": matrix,
            "cells": cells,
            "metric": "valor de mercado por tipo de fundo x classe de ativo",
        }

    def _resolve_month(self, con: sqlite3.Connection, month: str | None) -> str | None:
        if month and str(month).lower() != "latest":
            return str(month)
        row = con.execute(
            "SELECT month FROM cvm_cda_months WHERE status = 'ready' ORDER BY month DESC LIMIT 1"
        ).fetchone()
        if row:
            return row["month"]
        row = con.execute("SELECT month FROM cvm_cda_months ORDER BY month DESC LIMIT 1").fetchone()
        return row["month"] if row else None

    def _resolve_radar_month(self, con: sqlite3.Connection, month: str | None) -> str | None:
        if month and str(month).strip().lower() != "latest":
            return str(month)
        flow_as_of_date = self._latest_flow_as_of_date()
        rows = con.execute(
            """
            SELECT month, latest_dt, total_rows
            FROM cvm_cda_months
            WHERE status = 'ready'
            ORDER BY month DESC
            """
        ).fetchall()
        if not rows:
            return self._resolve_month(con, month)
        for row in rows:
            cda_date = _parse_date_text(row["latest_dt"])
            if not cda_date or not flow_as_of_date:
                continue
            days_since = (flow_as_of_date - cda_date).days
            total_rows = int(row["total_rows"] or 0)
            if days_since >= RADAR_MIN_DAYS_SINCE_CDA and total_rows >= RADAR_MIN_MONTH_ROWS:
                return row["month"]
        for row in rows:
            total_rows = int(row["total_rows"] or 0)
            if total_rows >= RADAR_MIN_MONTH_ROWS:
                return row["month"]
        return rows[0]["month"]

    def _latest_flow_as_of_date(self) -> date | None:
        try:
            from .funds_flow_local_service import FundsFlowLocalService

            flow_service = FundsFlowLocalService()
            latest_snapshot = flow_service._read_latest() or {}
            latest_report = latest_snapshot.get("report") or {}
            requested_end = (
                _parse_date_text(latest_report.get("requested_date"))
                or _parse_date_text(latest_report.get("as_of_date"))
                or _local_now().date()
            )
            informe_df, _ = flow_service._load_informe_diario(
                start_date=requested_end - timedelta(days=10),
                end_date=requested_end,
                force=False,
            )
            if informe_df.empty:
                return requested_end
            return flow_service._select_complete_as_of_date(informe_df, requested_end)
        except Exception:
            logger.exception("Failed to resolve latest flow date for CDA radar")
            return _local_now().date()

    def _normalize_target(self, target: str) -> str:
        target = str(target or "foreign").strip().lower()
        if target not in CDA_TARGET_LABELS:
            return "foreign"
        return target

    def _normalize_side(self, side: str, *, allow_all: bool = False) -> str:
        side = str(side or "long").strip().lower()
        valid = {"long", "short", "net"}
        if allow_all:
            valid.add("all")
        return side if side in valid else ("all" if allow_all else "long")

    def _pagination(self, page: int, per_page: int, *, max_per_page: int) -> tuple[int, int, int]:
        try:
            page = int(page)
        except Exception:
            page = 1
        try:
            per_page = int(per_page)
        except Exception:
            per_page = 25
        page = max(page, 1)
        per_page = max(1, min(per_page, max_per_page))
        return page, per_page, (page - 1) * per_page

    def _log(self, con: sqlite3.Connection, month: str, level: str, message: str, detail: dict[str, Any] | None = None) -> None:
        con.execute(
            """
            INSERT INTO cvm_cda_ingest_logs (month, event_at, level, message, detail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (month, _utc_now(), level, message, json.dumps(_clean_json(detail or {}), ensure_ascii=False)),
        )

    def _build_insights(
        self,
        report: dict[str, Any],
        kpis: dict[str, Any],
        summaries: dict[str, list[dict[str, Any]]],
        top_issuers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        asset_leader = (summaries.get("asset_class") or [{}])[0]
        country_leader = (summaries.get("country") or [{}])[0]
        issuer_leader = top_issuers[0] if top_issuers else {}
        return {
            "agent": "CvmCdaInsightAgent-ready",
            "quick_read": [
                f"Carteira CDA {report.get('period_label')} cobre {int(kpis.get('funds') or 0):,} fundos e {int(kpis.get('holdings') or 0):,} posicoes reportadas.".replace(",", "."),
                f"Maior classe por valor absoluto: {asset_leader.get('label') or '-'} ({(asset_leader.get('share_value_pct') or 0):.1f}% do valor reportado).",
                f"Maior pais declarado: {country_leader.get('label') or '-'}; maior emissor/agregado: {issuer_leader.get('label') or '-'}."
            ],
            "risk_flags": [
                "Separar leitura de estoque de carteira de fluxo de cotistas: CDA e Informe Diario se complementam.",
                "Monitorar posicoes confidenciais porque elas podem distorcer rankings recentes por fundo e emissor.",
                "Usar emissor ligado, concentracao de maior posicao e exposicao exterior como filtros de fragilidade.",
            ],
            "recommended_views": [
                "Mapa fund_type x asset_class para detectar rotação estrutural de alocação.",
                "Ranking de fundos por exterior, credito privado, confidencial e concentracao.",
                "Drilldown fundo -> ativo -> emissor -> pais para alimentar o grafo deterministico.",
            ],
        }
