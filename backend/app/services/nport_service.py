from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.nport")

NPORT_SCHEMA_VERSION = 1
SEC_NPORT_CATALOG_URL = "https://catalog.data.gov/dataset/form-n-port-data-sets"
SEC_NPORT_DOWNLOAD_URL = "https://www.sec.gov/files/dera/data/form-n-port-data-sets/{quarter}_nport.zip"

CORE_TABLES = (
    "nport_submission_core",
    "nport_registrant_core",
    "nport_fund_info_core",
    "nport_holding_core",
    "nport_identifier_core",
    "nport_debt_core",
)

NPORT_TARGET_COUNTRIES = {
    "brazil": ("BR",),
    "china": ("CN", "HK"),
    "emerging": (
        "BR",
        "CN",
        "HK",
        "TW",
        "KR",
        "IN",
        "MX",
        "ZA",
        "SA",
        "AE",
        "QA",
        "KW",
        "ID",
        "MY",
        "PH",
        "TH",
        "TR",
        "CL",
        "CO",
        "PE",
        "EG",
        "GR",
        "CZ",
        "HU",
        "PL",
        "RO",
    ),
}

NPORT_TARGET_LABELS = {
    "brazil": "Brasil",
    "china": "China/HK",
    "emerging": "Emergentes",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_table_name(name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]+", "_", str(name or "").strip()).strip("_").lower()
    if not cleaned:
        cleaned = "table"
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _num_expr(column: str) -> str:
    ident = _quote_ident(column)
    return f"CAST(NULLIF(REPLACE(TRIM({ident}), ',', ''), '') AS REAL)"


def _int_expr(column: str) -> str:
    ident = _quote_ident(column)
    return f"CAST(NULLIF(TRIM({ident}), '') AS INTEGER)"


def _norm_label(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _norm_key(value: Any) -> str:
    text = _norm_label(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_sec_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text.upper(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        value_float = float(text)
    except ValueError:
        return None
    if not math.isfinite(value_float):
        return None
    return value_float


def _quarter_from_path(path: str | os.PathLike[str]) -> str | None:
    text = str(path)
    match = re.search(r"(20\d{2}q[1-4])", text, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _quarter_end_date(quarter: str) -> str | None:
    match = re.fullmatch(r"(20\d{2})q([1-4])", str(quarter or "").lower())
    if not match:
        return None
    year = int(match.group(1))
    q = int(match.group(2))
    month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
    return f"{year}-{month_day}"


def _maturity_bucket(maturity_date: str | None, quarter: str) -> str:
    parsed = _parse_sec_date(maturity_date)
    as_of = _quarter_end_date(quarter)
    if not parsed or not as_of:
        return "sem vencimento"
    try:
        years = (
            datetime.fromisoformat(parsed).date() - datetime.fromisoformat(as_of).date()
        ).days / 365.25
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


class NportService:
    def __init__(self, data_dir: str | None = None) -> None:
        self.root_dir = Path(data_dir or getattr(Config, "NPORT_DATA_DIR", "") or Path(Config.MACRO_DATA_DIR) / "nport")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = self.root_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root_dir / "nport.sqlite"

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=120)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")
        con.execute("PRAGMA cache_size=-200000")
        return con

    def init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS nport_quarters (
                    quarter TEXT PRIMARY KEY,
                    source_dir TEXT,
                    source_url TEXT,
                    zip_path TEXT,
                    imported_at TEXT,
                    status TEXT,
                    schema_version INTEGER,
                    file_count INTEGER,
                    total_rows INTEGER,
                    latest_report_date TEXT,
                    metadata_json TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS nport_table_manifest (
                    quarter TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    raw_table_name TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    row_count INTEGER,
                    column_count INTEGER,
                    file_size_bytes INTEGER,
                    loaded_at TEXT,
                    columns_json TEXT,
                    PRIMARY KEY (quarter, table_name)
                );

                CREATE TABLE IF NOT EXISTS nport_ingest_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quarter TEXT,
                    event_at TEXT,
                    level TEXT,
                    message TEXT,
                    detail_json TEXT
                );

                CREATE TABLE IF NOT EXISTS nport_submission_core (
                    quarter TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    filing_date TEXT,
                    file_num TEXT,
                    sub_type TEXT,
                    report_ending_period TEXT,
                    report_date TEXT,
                    is_last_filing TEXT,
                    PRIMARY KEY (quarter, accession_number)
                );

                CREATE TABLE IF NOT EXISTS nport_registrant_core (
                    quarter TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    cik TEXT,
                    registrant_name TEXT,
                    file_num TEXT,
                    lei TEXT,
                    city TEXT,
                    state TEXT,
                    country TEXT,
                    phone TEXT,
                    PRIMARY KEY (quarter, accession_number)
                );

                CREATE TABLE IF NOT EXISTS nport_fund_info_core (
                    quarter TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    series_name TEXT,
                    series_id TEXT,
                    series_lei TEXT,
                    total_assets REAL,
                    total_liabilities REAL,
                    net_assets REAL,
                    sales_flow_3m REAL,
                    reinvestment_flow_3m REAL,
                    redemption_flow_3m REAL,
                    net_flow_3m REAL,
                    PRIMARY KEY (quarter, accession_number)
                );

                CREATE TABLE IF NOT EXISTS nport_holding_core (
                    quarter TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    holding_id TEXT NOT NULL,
                    issuer_name TEXT,
                    issuer_norm TEXT,
                    issuer_title TEXT,
                    issuer_cusip TEXT,
                    security_key TEXT,
                    balance REAL,
                    unit TEXT,
                    currency_code TEXT,
                    currency_value REAL,
                    exchange_rate REAL,
                    percentage REAL,
                    payoff_profile TEXT,
                    asset_cat TEXT,
                    issuer_type TEXT,
                    investment_country TEXT,
                    is_restricted_security TEXT,
                    fair_value_level TEXT,
                    derivative_cat TEXT,
                    PRIMARY KEY (quarter, holding_id)
                );

                CREATE TABLE IF NOT EXISTS nport_identifier_core (
                    quarter TEXT NOT NULL,
                    holding_id TEXT NOT NULL,
                    identifiers_id TEXT NOT NULL,
                    identifier_isin TEXT,
                    identifier_ticker TEXT,
                    other_identifier TEXT,
                    other_identifier_desc TEXT,
                    PRIMARY KEY (quarter, holding_id, identifiers_id)
                );

                CREATE TABLE IF NOT EXISTS nport_debt_core (
                    quarter TEXT NOT NULL,
                    holding_id TEXT NOT NULL,
                    maturity_date TEXT,
                    maturity_date_iso TEXT,
                    maturity_bucket TEXT,
                    coupon_type TEXT,
                    annualized_rate REAL,
                    is_default TEXT,
                    are_any_interest_payment TEXT,
                    is_any_portion_interest_paid TEXT,
                    PRIMARY KEY (quarter, holding_id)
                );

                CREATE TABLE IF NOT EXISTS nport_summary_group (
                    quarter TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    key TEXT NOT NULL,
                    label TEXT,
                    row_count INTEGER,
                    fund_count INTEGER,
                    value REAL,
                    abs_value REAL,
                    share_value_pct REAL,
                    extra_json TEXT,
                    PRIMARY KEY (quarter, dimension, key)
                );

                CREATE TABLE IF NOT EXISTS nport_fund_summary (
                    quarter TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    series_name TEXT,
                    registrant_name TEXT,
                    report_date TEXT,
                    net_assets REAL,
                    holding_count INTEGER,
                    holding_value REAL,
                    max_holding_pct REAL,
                    pct_hhi REAL,
                    restricted_value REAL,
                    derivative_value REAL,
                    level3_value REAL,
                    short_value REAL,
                    net_flow_3m REAL,
                    PRIMARY KEY (quarter, accession_number)
                );

                CREATE TABLE IF NOT EXISTS nport_registrant_summary (
                    quarter TEXT NOT NULL,
                    registrant_name TEXT NOT NULL,
                    filings INTEGER,
                    funds INTEGER,
                    net_assets REAL,
                    holding_value REAL,
                    holding_count INTEGER,
                    net_flow_3m REAL,
                    PRIMARY KEY (quarter, registrant_name)
                );

                CREATE TABLE IF NOT EXISTS nport_debt_maturity_summary (
                    quarter TEXT NOT NULL,
                    maturity_bucket TEXT NOT NULL,
                    row_count INTEGER,
                    value REAL,
                    abs_value REAL,
                    weighted_coupon REAL,
                    default_value REAL,
                    PRIMARY KEY (quarter, maturity_bucket)
                );

                CREATE TABLE IF NOT EXISTS nport_fund_performance (
                    quarter TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    series_name TEXT,
                    registrant_name TEXT,
                    report_date TEXT,
                    net_assets REAL,
                    return_m1_pct REAL,
                    return_m2_pct REAL,
                    return_m3_pct REAL,
                    return_3m_pct REAL,
                    aum_weighted_return REAL,
                    class_count INTEGER,
                    PRIMARY KEY (quarter, accession_number)
                );

                CREATE TABLE IF NOT EXISTS nport_fund_region_exposure (
                    quarter TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    target TEXT NOT NULL,
                    target_label TEXT,
                    series_name TEXT,
                    registrant_name TEXT,
                    report_date TEXT,
                    net_assets REAL,
                    long_value REAL,
                    short_value REAL,
                    net_value REAL,
                    gross_value REAL,
                    long_pct_aum REAL,
                    short_pct_aum REAL,
                    net_pct_aum REAL,
                    holdings_count INTEGER,
                    countries_count INTEGER,
                    securities_count INTEGER,
                    top_country TEXT,
                    top_asset_cat TEXT,
                    return_3m_pct REAL,
                    PRIMARY KEY (quarter, accession_number, target)
                );

                CREATE TABLE IF NOT EXISTS nport_security_region_exposure (
                    quarter TEXT NOT NULL,
                    target TEXT NOT NULL,
                    security_key TEXT NOT NULL,
                    issuer_name TEXT,
                    issuer_title TEXT,
                    asset_cat TEXT,
                    investment_country TEXT,
                    long_value REAL,
                    short_value REAL,
                    net_value REAL,
                    gross_value REAL,
                    fund_count INTEGER,
                    holding_count INTEGER,
                    PRIMARY KEY (quarter, target, security_key, asset_cat, investment_country)
                );

                CREATE TABLE IF NOT EXISTS nport_country_asset_exposure (
                    quarter TEXT NOT NULL,
                    target TEXT NOT NULL,
                    investment_country TEXT NOT NULL,
                    asset_cat TEXT NOT NULL,
                    long_value REAL,
                    short_value REAL,
                    net_value REAL,
                    gross_value REAL,
                    fund_count INTEGER,
                    holding_count INTEGER,
                    PRIMARY KEY (quarter, target, investment_country, asset_cat)
                );
                """
            )

    def _log(self, con: sqlite3.Connection, quarter: str, level: str, message: str, detail: dict[str, Any] | None = None) -> None:
        con.execute(
            "INSERT INTO nport_ingest_logs (quarter, event_at, level, message, detail_json) VALUES (?, ?, ?, ?, ?)",
            (quarter, _utc_now(), level, message, json.dumps(detail or {}, ensure_ascii=False)),
        )
        logger.info("N-PORT %s %s: %s", quarter, level, message)

    def status(self) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            quarters = [dict(row) for row in con.execute(
                "SELECT * FROM nport_quarters ORDER BY quarter DESC"
            ).fetchall()]
            latest = quarters[0] if quarters else None
            return {
                "ok": True,
                "db_path": str(self.db_path),
                "data_dir": str(self.root_dir),
                "latest_quarter": latest,
                "quarters": quarters,
            }

    def _raw_table_name(self, source_table_name: str) -> str:
        return f"nport_raw_{_safe_table_name(source_table_name)}"

    def _reset_quarter(self, con: sqlite3.Connection, quarter: str) -> None:
        for table in CORE_TABLES + (
            "nport_summary_group",
            "nport_fund_summary",
            "nport_registrant_summary",
            "nport_debt_maturity_summary",
            "nport_fund_performance",
            "nport_fund_region_exposure",
            "nport_security_region_exposure",
            "nport_country_asset_exposure",
            "nport_table_manifest",
            "nport_ingest_logs",
        ):
            con.execute(f"DELETE FROM {_quote_ident(table)} WHERE quarter = ?", (quarter,))

        raw_tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'nport_raw_%'"
        ).fetchall()
        for row in raw_tables:
            con.execute(f"DELETE FROM {_quote_ident(row['name'])} WHERE quarter = ?", (quarter,))

    def ingest_local_directory(self, source_dir: str, quarter: str | None = None, force: bool = False) -> dict[str, Any]:
        self.init_db()
        source_path = Path(source_dir).expanduser().resolve()
        if not source_path.exists() or not source_path.is_dir():
            raise FileNotFoundError(f"N-PORT source directory not found: {source_path}")

        quarter = (quarter or _quarter_from_path(source_path) or "").lower()
        if not quarter:
            raise ValueError("Could not infer quarter. Use quarter like 2026q1.")

        tsv_files = sorted(source_path.glob("*.tsv"))
        if not tsv_files:
            raise FileNotFoundError(f"No TSV files found in {source_path}")

        started = time.time()
        with self._connect() as con:
            con.execute("PRAGMA synchronous=OFF")
            if force:
                self._reset_quarter(con, quarter)
            elif con.execute("SELECT 1 FROM nport_quarters WHERE quarter = ? AND status = 'ready'", (quarter,)).fetchone():
                return {"ok": True, "quarter": quarter, "status": "already_ready", "dashboard": self.get_dashboard(quarter)}

            con.execute(
                """
                INSERT INTO nport_quarters (
                    quarter, source_dir, imported_at, status, schema_version, file_count, total_rows, metadata_json
                ) VALUES (?, ?, ?, 'importing', ?, ?, 0, ?)
                ON CONFLICT(quarter) DO UPDATE SET
                    source_dir = excluded.source_dir,
                    imported_at = excluded.imported_at,
                    status = 'importing',
                    schema_version = excluded.schema_version,
                    file_count = excluded.file_count,
                    error = NULL
                """,
                (
                    quarter,
                    str(source_path),
                    _utc_now(),
                    NPORT_SCHEMA_VERSION,
                    len(tsv_files),
                    json.dumps({"source_files": [p.name for p in tsv_files]}, ensure_ascii=False),
                ),
            )
            self._log(con, quarter, "info", "Starting local N-PORT import", {"source_dir": str(source_path), "files": len(tsv_files)})
            con.commit()

            total_rows = 0
            for tsv_path in tsv_files:
                row_count = self._import_tsv(con, quarter, tsv_path)
                total_rows += row_count
                con.execute("UPDATE nport_quarters SET total_rows = ? WHERE quarter = ?", (total_rows, quarter))
                con.commit()

            self._build_core_tables(con, quarter, source_path)
            self._build_analytics(con, quarter)
            latest_report_date = con.execute(
                "SELECT MAX(report_date) AS latest_report_date FROM nport_submission_core WHERE quarter = ?",
                (quarter,),
            ).fetchone()["latest_report_date"]
            con.execute(
                """
                UPDATE nport_quarters
                   SET status = 'ready',
                       imported_at = ?,
                       total_rows = ?,
                       latest_report_date = ?,
                       error = NULL
                 WHERE quarter = ?
                """,
                (_utc_now(), total_rows, latest_report_date, quarter),
            )
            con.commit()

        elapsed = time.time() - started
        return {
            "ok": True,
            "quarter": quarter,
            "status": "ready",
            "db_path": str(self.db_path),
            "total_rows": total_rows,
            "elapsed_seconds": round(elapsed, 2),
            "dashboard": self.get_dashboard(quarter),
        }

    def _import_tsv(self, con: sqlite3.Connection, quarter: str, tsv_path: Path) -> int:
        source_name = tsv_path.stem
        raw_table = self._raw_table_name(source_name)
        loaded_at = _utc_now()
        row_count = 0

        try:
            csv.field_size_limit(sys.maxsize)
        except OverflowError:
            csv.field_size_limit(2_147_483_647)

        with tsv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh, delimiter="\t")
            try:
                raw_headers = next(reader)
            except StopIteration:
                raw_headers = []

            headers: list[str] = []
            seen: dict[str, int] = {}
            for raw in raw_headers:
                cleaned = _safe_table_name(raw)
                seen[cleaned] = seen.get(cleaned, 0) + 1
                if seen[cleaned] > 1:
                    cleaned = f"{cleaned}_{seen[cleaned]}"
                headers.append(cleaned)

            if not headers:
                con.execute(
                    """
                    INSERT OR REPLACE INTO nport_table_manifest (
                        quarter, table_name, raw_table_name, file_name, row_count, column_count, file_size_bytes, loaded_at, columns_json
                    ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?)
                    """,
                    (quarter, source_name, raw_table, tsv_path.name, tsv_path.stat().st_size, loaded_at, "[]"),
                )
                return 0

            col_defs = ", ".join([f"{_quote_ident(col)} TEXT" for col in headers])
            con.execute(f"CREATE TABLE IF NOT EXISTS {_quote_ident(raw_table)} (quarter TEXT NOT NULL, {col_defs})")
            existing_cols = [row["name"] for row in con.execute(f"PRAGMA table_info({_quote_ident(raw_table)})").fetchall()]
            for col in headers:
                if col not in existing_cols:
                    con.execute(f"ALTER TABLE {_quote_ident(raw_table)} ADD COLUMN {_quote_ident(col)} TEXT")
            con.execute(f"DELETE FROM {_quote_ident(raw_table)} WHERE quarter = ?", (quarter,))

            insert_cols = ["quarter"] + headers
            placeholders = ",".join(["?"] * len(insert_cols))
            insert_sql = f"INSERT INTO {_quote_ident(raw_table)} ({', '.join(_quote_ident(c) for c in insert_cols)}) VALUES ({placeholders})"

            batch: list[tuple[Any, ...]] = []
            batch_size = 20_000
            for row in reader:
                if len(row) < len(headers):
                    row = row + [""] * (len(headers) - len(row))
                elif len(row) > len(headers):
                    row = row[: len(headers)]
                batch.append((quarter, *row))
                row_count += 1
                if len(batch) >= batch_size:
                    con.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                con.executemany(insert_sql, batch)

        con.execute(
            """
            INSERT OR REPLACE INTO nport_table_manifest (
                quarter, table_name, raw_table_name, file_name, row_count, column_count, file_size_bytes, loaded_at, columns_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quarter,
                source_name,
                raw_table,
                tsv_path.name,
                row_count,
                len(headers),
                tsv_path.stat().st_size,
                loaded_at,
                json.dumps({"original": raw_headers, "normalized": headers}, ensure_ascii=False),
            ),
        )
        self._log(con, quarter, "info", f"Loaded {tsv_path.name}", {"rows": row_count, "columns": len(headers)})
        return row_count

    def _build_core_tables(self, con: sqlite3.Connection, quarter: str, source_path: Path) -> None:
        self._log(con, quarter, "info", "Building typed core tables")
        for table in CORE_TABLES:
            con.execute(f"DELETE FROM {_quote_ident(table)} WHERE quarter = ?", (quarter,))

        if self._table_exists(con, "nport_raw_submission"):
            con.create_function("nport_parse_sec_date", 1, _parse_sec_date)
            con.execute(
                """
                INSERT OR REPLACE INTO nport_submission_core
                SELECT
                    quarter,
                    accession_number,
                    nport_parse_sec_date(filing_date),
                    file_num,
                    sub_type,
                    nport_parse_sec_date(report_ending_period),
                    nport_parse_sec_date(report_date),
                    is_last_filing
                FROM nport_raw_submission
                WHERE quarter = ?
                """,
                (quarter,),
            )

        if self._table_exists(con, "nport_raw_registrant"):
            con.execute(
                """
                INSERT OR REPLACE INTO nport_registrant_core
                SELECT
                    quarter,
                    accession_number,
                    cik,
                    registrant_name,
                    file_num,
                    lei,
                    city,
                    state,
                    country,
                    phone
                FROM nport_raw_registrant
                WHERE quarter = ?
                """,
                (quarter,),
            )

        if self._table_exists(con, "nport_raw_fund_reported_info"):
            con.execute(
                f"""
                INSERT OR REPLACE INTO nport_fund_info_core
                SELECT
                    quarter,
                    accession_number,
                    series_name,
                    series_id,
                    series_lei,
                    {_num_expr('total_assets')} AS total_assets,
                    {_num_expr('total_liabilities')} AS total_liabilities,
                    {_num_expr('net_assets')} AS net_assets,
                    COALESCE({_num_expr('sales_flow_mon1')}, 0) + COALESCE({_num_expr('sales_flow_mon2')}, 0) + COALESCE({_num_expr('sales_flow_mon3')}, 0) AS sales_flow_3m,
                    COALESCE({_num_expr('reinvestment_flow_mon1')}, 0) + COALESCE({_num_expr('reinvestment_flow_mon2')}, 0) + COALESCE({_num_expr('reinvestment_flow_mon3')}, 0) AS reinvestment_flow_3m,
                    COALESCE({_num_expr('redemption_flow_mon1')}, 0) + COALESCE({_num_expr('redemption_flow_mon2')}, 0) + COALESCE({_num_expr('redemption_flow_mon3')}, 0) AS redemption_flow_3m,
                    COALESCE({_num_expr('sales_flow_mon1')}, 0) + COALESCE({_num_expr('sales_flow_mon2')}, 0) + COALESCE({_num_expr('sales_flow_mon3')}, 0)
                    + COALESCE({_num_expr('reinvestment_flow_mon1')}, 0) + COALESCE({_num_expr('reinvestment_flow_mon2')}, 0) + COALESCE({_num_expr('reinvestment_flow_mon3')}, 0)
                    - COALESCE({_num_expr('redemption_flow_mon1')}, 0) - COALESCE({_num_expr('redemption_flow_mon2')}, 0) - COALESCE({_num_expr('redemption_flow_mon3')}, 0) AS net_flow_3m
                FROM nport_raw_fund_reported_info
                WHERE quarter = ?
                """,
                (quarter,),
            )

        if self._table_exists(con, "nport_raw_fund_reported_holding"):
            con.create_function("nport_norm_key", 1, _norm_key)
            con.execute(
                f"""
                INSERT OR REPLACE INTO nport_holding_core
                SELECT
                    quarter,
                    accession_number,
                    holding_id,
                    issuer_name,
                    nport_norm_key(issuer_name) AS issuer_norm,
                    issuer_title,
                    issuer_cusip,
                    COALESCE(NULLIF(TRIM(issuer_cusip), ''), holding_id) AS security_key,
                    {_num_expr('balance')} AS balance,
                    unit,
                    currency_code,
                    {_num_expr('currency_value')} AS currency_value,
                    {_num_expr('exchange_rate')} AS exchange_rate,
                    {_num_expr('percentage')} AS percentage,
                    payoff_profile,
                    asset_cat,
                    issuer_type,
                    investment_country,
                    is_restricted_security,
                    fair_value_level,
                    derivative_cat
                FROM nport_raw_fund_reported_holding
                WHERE quarter = ?
                """,
                (quarter,),
            )

        if self._table_exists(con, "nport_raw_identifiers"):
            con.execute(
                """
                INSERT OR REPLACE INTO nport_identifier_core
                SELECT
                    quarter,
                    holding_id,
                    identifiers_id,
                    identifier_isin,
                    identifier_ticker,
                    other_identifier,
                    other_identifier_desc
                FROM nport_raw_identifiers
                WHERE quarter = ?
                """,
                (quarter,),
            )

        debt_path = source_path / "DEBT_SECURITY.tsv"
        if debt_path.exists():
            self._build_debt_core_from_file(con, quarter, debt_path)

        self._create_indexes(con)
        con.commit()

    def _build_debt_core_from_file(self, con: sqlite3.Connection, quarter: str, debt_path: Path) -> None:
        insert_sql = """
            INSERT OR REPLACE INTO nport_debt_core (
                quarter, holding_id, maturity_date, maturity_date_iso, maturity_bucket, coupon_type,
                annualized_rate, is_default, are_any_interest_payment, is_any_portion_interest_paid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with debt_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            batch: list[tuple[Any, ...]] = []
            for row in reader:
                maturity_date = row.get("MATURITY_DATE") or row.get("maturity_date")
                maturity_iso = _parse_sec_date(maturity_date)
                batch.append(
                    (
                        quarter,
                        row.get("HOLDING_ID") or row.get("holding_id") or "",
                        maturity_date or "",
                        maturity_iso,
                        _maturity_bucket(maturity_date, quarter),
                        row.get("COUPON_TYPE") or row.get("coupon_type") or "",
                        _parse_float(row.get("ANNUALIZED_RATE") or row.get("annualized_rate")),
                        row.get("IS_DEFAULT") or row.get("is_default") or "",
                        row.get("ARE_ANY_INTEREST_PAYMENT") or row.get("are_any_interest_payment") or "",
                        row.get("IS_ANY_PORTION_INTEREST_PAID") or row.get("is_any_portion_interest_paid") or "",
                    )
                )
                if len(batch) >= 50_000:
                    con.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                con.executemany(insert_sql, batch)

    def _create_indexes(self, con: sqlite3.Connection) -> None:
        statements = [
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_acc ON nport_holding_core(quarter, accession_number)",
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_asset ON nport_holding_core(quarter, asset_cat)",
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_country ON nport_holding_core(quarter, investment_country)",
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_currency ON nport_holding_core(quarter, currency_code)",
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_issuer ON nport_holding_core(quarter, issuer_norm)",
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_security ON nport_holding_core(quarter, security_key)",
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_deriv ON nport_holding_core(quarter, derivative_cat)",
            "CREATE INDEX IF NOT EXISTS idx_nport_holding_q_restricted ON nport_holding_core(quarter, is_restricted_security)",
            "CREATE INDEX IF NOT EXISTS idx_nport_fund_q_assets ON nport_fund_info_core(quarter, net_assets DESC)",
            "CREATE INDEX IF NOT EXISTS idx_nport_reg_q_name ON nport_registrant_core(quarter, registrant_name)",
            "CREATE INDEX IF NOT EXISTS idx_nport_debt_q_bucket ON nport_debt_core(quarter, maturity_bucket)",
        ]
        for stmt in statements:
            con.execute(stmt)

    def _table_exists(self, con: sqlite3.Connection, table_name: str) -> bool:
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone() is not None

    def _build_analytics(self, con: sqlite3.Connection, quarter: str) -> None:
        self._log(con, quarter, "info", "Building analytics materializations")
        for table in (
            "nport_summary_group",
            "nport_fund_summary",
            "nport_registrant_summary",
            "nport_debt_maturity_summary",
            "nport_fund_performance",
            "nport_fund_region_exposure",
            "nport_security_region_exposure",
            "nport_country_asset_exposure",
        ):
            con.execute(f"DELETE FROM {_quote_ident(table)} WHERE quarter = ?", (quarter,))

        total_value = con.execute(
            "SELECT COALESCE(SUM(currency_value), 0) AS value FROM nport_holding_core WHERE quarter = ?",
            (quarter,),
        ).fetchone()["value"] or 0

        dimensions = [
            ("asset_cat", "asset_cat", "asset_cat"),
            ("issuer_type", "issuer_type", "issuer_type"),
            ("country", "investment_country", "investment_country"),
            ("currency", "currency_code", "currency_code"),
            ("fair_value_level", "fair_value_level", "fair_value_level"),
            ("payoff_profile", "payoff_profile", "payoff_profile"),
            ("restricted", "is_restricted_security", "is_restricted_security"),
            ("derivative_cat", "derivative_cat", "derivative_cat"),
        ]
        for dimension, key_col, label_col in dimensions:
            con.execute(
                f"""
                INSERT OR REPLACE INTO nport_summary_group (
                    quarter, dimension, key, label, row_count, fund_count, value, abs_value, share_value_pct, extra_json
                )
                SELECT
                    quarter,
                    ? AS dimension,
                    COALESCE(NULLIF(TRIM({_quote_ident(key_col)}), ''), 'blank') AS key,
                    COALESCE(NULLIF(TRIM({_quote_ident(label_col)}), ''), 'blank') AS label,
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT accession_number) AS fund_count,
                    SUM(COALESCE(currency_value, 0)) AS value,
                    SUM(ABS(COALESCE(currency_value, 0))) AS abs_value,
                    CASE WHEN ? != 0 THEN SUM(COALESCE(currency_value, 0)) / ? * 100.0 ELSE 0 END AS share_value_pct,
                    NULL AS extra_json
                FROM nport_holding_core
                WHERE quarter = ?
                GROUP BY quarter, key, label
                """,
                (dimension, total_value, total_value, quarter),
            )

        self._insert_top_summary(con, quarter, "issuer", "issuer_norm", "issuer_name", total_value, limit=120)
        self._insert_top_summary(con, quarter, "security", "security_key", "issuer_title", total_value, limit=160)

        con.execute(
            """
            INSERT OR REPLACE INTO nport_fund_summary (
                quarter, accession_number, series_name, registrant_name, report_date, net_assets,
                holding_count, holding_value, max_holding_pct, pct_hhi, restricted_value,
                derivative_value, level3_value, short_value, net_flow_3m
            )
            WITH holding AS (
                SELECT
                    quarter,
                    accession_number,
                    COUNT(*) AS holding_count,
                    SUM(COALESCE(currency_value, 0)) AS holding_value,
                    MAX(COALESCE(percentage, 0)) AS max_holding_pct,
                    SUM(COALESCE(percentage, 0) * COALESCE(percentage, 0)) AS pct_hhi,
                    SUM(CASE WHEN UPPER(COALESCE(is_restricted_security, '')) = 'Y' THEN COALESCE(currency_value, 0) ELSE 0 END) AS restricted_value,
                    SUM(CASE WHEN COALESCE(TRIM(derivative_cat), '') != '' THEN COALESCE(currency_value, 0) ELSE 0 END) AS derivative_value,
                    SUM(CASE WHEN COALESCE(TRIM(fair_value_level), '') = '3' THEN COALESCE(currency_value, 0) ELSE 0 END) AS level3_value,
                    SUM(CASE WHEN UPPER(COALESCE(payoff_profile, '')) = 'SHORT' THEN COALESCE(currency_value, 0) ELSE 0 END) AS short_value
                FROM nport_holding_core
                WHERE quarter = ?
                GROUP BY quarter, accession_number
            )
            SELECT
                h.quarter,
                h.accession_number,
                f.series_name,
                r.registrant_name,
                s.report_date,
                f.net_assets,
                h.holding_count,
                h.holding_value,
                h.max_holding_pct,
                h.pct_hhi,
                h.restricted_value,
                h.derivative_value,
                h.level3_value,
                h.short_value,
                f.net_flow_3m
            FROM holding h
            LEFT JOIN nport_fund_info_core f
              ON f.quarter = h.quarter AND f.accession_number = h.accession_number
            LEFT JOIN nport_registrant_core r
              ON r.quarter = h.quarter AND r.accession_number = h.accession_number
            LEFT JOIN nport_submission_core s
              ON s.quarter = h.quarter AND s.accession_number = h.accession_number
            """,
            (quarter,),
        )

        con.execute(
            """
            INSERT OR REPLACE INTO nport_registrant_summary (
                quarter, registrant_name, filings, funds, net_assets, holding_value, holding_count, net_flow_3m
            )
            SELECT
                quarter,
                COALESCE(NULLIF(TRIM(registrant_name), ''), 'Unknown') AS registrant_name,
                COUNT(*) AS filings,
                COUNT(DISTINCT series_name) AS funds,
                SUM(COALESCE(net_assets, 0)) AS net_assets,
                SUM(COALESCE(holding_value, 0)) AS holding_value,
                SUM(COALESCE(holding_count, 0)) AS holding_count,
                SUM(COALESCE(net_flow_3m, 0)) AS net_flow_3m
            FROM nport_fund_summary
            WHERE quarter = ?
            GROUP BY quarter, COALESCE(NULLIF(TRIM(registrant_name), ''), 'Unknown')
            """,
            (quarter,),
        )

        if self._table_exists(con, "nport_debt_core"):
            con.execute(
                """
                INSERT OR REPLACE INTO nport_debt_maturity_summary (
                    quarter, maturity_bucket, row_count, value, abs_value, weighted_coupon, default_value
                )
                SELECT
                    h.quarter,
                    COALESCE(d.maturity_bucket, 'sem vencimento') AS maturity_bucket,
                    COUNT(*) AS row_count,
                    SUM(COALESCE(h.currency_value, 0)) AS value,
                    SUM(ABS(COALESCE(h.currency_value, 0))) AS abs_value,
                    CASE
                        WHEN SUM(ABS(COALESCE(h.currency_value, 0))) != 0
                        THEN SUM(COALESCE(d.annualized_rate, 0) * ABS(COALESCE(h.currency_value, 0))) / SUM(ABS(COALESCE(h.currency_value, 0)))
                        ELSE NULL
                    END AS weighted_coupon,
                    SUM(CASE WHEN UPPER(COALESCE(d.is_default, '')) = 'Y' THEN COALESCE(h.currency_value, 0) ELSE 0 END) AS default_value
                FROM nport_holding_core h
                JOIN nport_debt_core d
                  ON d.quarter = h.quarter AND d.holding_id = h.holding_id
                WHERE h.quarter = ?
                GROUP BY h.quarter, COALESCE(d.maturity_bucket, 'sem vencimento')
                """,
                (quarter,),
            )

        con.execute("CREATE INDEX IF NOT EXISTS idx_nport_summary_q_dim_value ON nport_summary_group(quarter, dimension, abs_value DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_nport_fund_summary_q_assets ON nport_fund_summary(quarter, net_assets DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_nport_reg_summary_q_assets ON nport_registrant_summary(quarter, net_assets DESC)")
        self._build_extended_positioning_analytics(con, quarter)

    def _build_extended_positioning_analytics(self, con: sqlite3.Connection, quarter: str) -> None:
        self._log(con, quarter, "info", "Building N-PORT performance and region positioning analytics")
        for table in (
            "nport_fund_performance",
            "nport_fund_region_exposure",
            "nport_security_region_exposure",
            "nport_country_asset_exposure",
        ):
            con.execute(f"DELETE FROM {_quote_ident(table)} WHERE quarter = ?", (quarter,))

        if self._table_exists(con, "nport_raw_monthly_total_return"):
            con.execute(
                """
                INSERT OR REPLACE INTO nport_fund_performance (
                    quarter, accession_number, series_name, registrant_name, report_date, net_assets,
                    return_m1_pct, return_m2_pct, return_m3_pct, return_3m_pct, aum_weighted_return, class_count
                )
                WITH class_returns AS (
                    SELECT
                        quarter,
                        accession_number,
                        CAST(NULLIF(TRIM(monthly_total_return1), '') AS REAL) AS r1,
                        CAST(NULLIF(TRIM(monthly_total_return2), '') AS REAL) AS r2,
                        CAST(NULLIF(TRIM(monthly_total_return3), '') AS REAL) AS r3
                    FROM nport_raw_monthly_total_return
                    WHERE quarter = ?
                ),
                perf AS (
                    SELECT
                        quarter,
                        accession_number,
                        AVG(r1) AS return_m1_pct,
                        AVG(r2) AS return_m2_pct,
                        AVG(r3) AS return_m3_pct,
                        AVG(((1 + COALESCE(r1, 0) / 100.0) * (1 + COALESCE(r2, 0) / 100.0) * (1 + COALESCE(r3, 0) / 100.0) - 1) * 100.0) AS return_3m_pct,
                        COUNT(*) AS class_count
                    FROM class_returns
                    GROUP BY quarter, accession_number
                )
                SELECT
                    p.quarter,
                    p.accession_number,
                    f.series_name,
                    r.registrant_name,
                    s.report_date,
                    f.net_assets,
                    p.return_m1_pct,
                    p.return_m2_pct,
                    p.return_m3_pct,
                    p.return_3m_pct,
                    p.return_3m_pct / 100.0 * COALESCE(f.net_assets, 0) AS aum_weighted_return,
                    p.class_count
                FROM perf p
                LEFT JOIN nport_fund_info_core f
                  ON f.quarter = p.quarter AND f.accession_number = p.accession_number
                LEFT JOIN nport_registrant_core r
                  ON r.quarter = p.quarter AND r.accession_number = p.accession_number
                LEFT JOIN nport_submission_core s
                  ON s.quarter = p.quarter AND s.accession_number = p.accession_number
                """,
                (quarter,),
            )

        for target, countries in NPORT_TARGET_COUNTRIES.items():
            self._build_target_region_analytics(con, quarter, target, countries)

        con.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_nport_perf_q_ret ON nport_fund_performance(quarter, return_3m_pct DESC);
            CREATE INDEX IF NOT EXISTS idx_nport_perf_q_weighted ON nport_fund_performance(quarter, aum_weighted_return DESC);
            CREATE INDEX IF NOT EXISTS idx_nport_region_q_target_long ON nport_fund_region_exposure(quarter, target, long_value DESC);
            CREATE INDEX IF NOT EXISTS idx_nport_region_q_target_short ON nport_fund_region_exposure(quarter, target, short_value DESC);
            CREATE INDEX IF NOT EXISTS idx_nport_asset_region_q_target_long ON nport_security_region_exposure(quarter, target, long_value DESC);
            CREATE INDEX IF NOT EXISTS idx_nport_asset_region_q_target_short ON nport_security_region_exposure(quarter, target, short_value DESC);
            CREATE INDEX IF NOT EXISTS idx_nport_country_asset_q_target ON nport_country_asset_exposure(quarter, target, investment_country, asset_cat);
            """
        )

    def _build_target_region_analytics(
        self,
        con: sqlite3.Connection,
        quarter: str,
        target: str,
        countries: tuple[str, ...],
    ) -> None:
        placeholders = ",".join(["?"] * len(countries))
        params: tuple[Any, ...] = (quarter, *countries)
        target_label = NPORT_TARGET_LABELS.get(target, target)
        short_condition = "UPPER(COALESCE(payoff_profile, '')) = 'SHORT' OR COALESCE(currency_value, 0) < 0"
        valid_security_filter = "COALESCE(NULLIF(TRIM(security_key), ''), 'blank') NOT IN ('blank', 'N/A', 'NA', '000000000', '999999999')"

        con.execute(
            f"""
            INSERT OR REPLACE INTO nport_fund_region_exposure (
                quarter, accession_number, target, target_label, series_name, registrant_name, report_date, net_assets,
                long_value, short_value, net_value, gross_value, long_pct_aum, short_pct_aum, net_pct_aum,
                holdings_count, countries_count, securities_count, top_country, top_asset_cat, return_3m_pct
            )
            WITH base AS (
                SELECT *
                FROM nport_holding_core
                WHERE quarter = ?
                  AND investment_country IN ({placeholders})
            ),
            agg AS (
                SELECT
                    quarter,
                    accession_number,
                    SUM(CASE WHEN {short_condition} THEN 0 ELSE COALESCE(currency_value, 0) END) AS long_value,
                    SUM(CASE WHEN {short_condition} THEN ABS(COALESCE(currency_value, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(currency_value, 0)) AS net_value,
                    SUM(ABS(COALESCE(currency_value, 0))) AS gross_value,
                    COUNT(*) AS holdings_count,
                    COUNT(DISTINCT investment_country) AS countries_count,
                    COUNT(DISTINCT security_key) AS securities_count
                FROM base
                GROUP BY quarter, accession_number
            ),
            top_country AS (
                SELECT quarter, accession_number, investment_country, value,
                       ROW_NUMBER() OVER (PARTITION BY quarter, accession_number ORDER BY value DESC) AS rn
                FROM (
                    SELECT quarter, accession_number, investment_country, SUM(ABS(COALESCE(currency_value, 0))) AS value
                    FROM base
                    GROUP BY quarter, accession_number, investment_country
                )
            ),
            top_asset AS (
                SELECT quarter, accession_number, asset_cat, value,
                       ROW_NUMBER() OVER (PARTITION BY quarter, accession_number ORDER BY value DESC) AS rn
                FROM (
                    SELECT quarter, accession_number, asset_cat, SUM(ABS(COALESCE(currency_value, 0))) AS value
                    FROM base
                    GROUP BY quarter, accession_number, asset_cat
                )
            )
            SELECT
                a.quarter,
                a.accession_number,
                ? AS target,
                ? AS target_label,
                f.series_name,
                r.registrant_name,
                s.report_date,
                f.net_assets,
                a.long_value,
                a.short_value,
                a.net_value,
                a.gross_value,
                CASE WHEN COALESCE(f.net_assets, 0) != 0 THEN a.long_value / f.net_assets * 100.0 ELSE NULL END AS long_pct_aum,
                CASE WHEN COALESCE(f.net_assets, 0) != 0 THEN a.short_value / f.net_assets * 100.0 ELSE NULL END AS short_pct_aum,
                CASE WHEN COALESCE(f.net_assets, 0) != 0 THEN a.net_value / f.net_assets * 100.0 ELSE NULL END AS net_pct_aum,
                a.holdings_count,
                a.countries_count,
                a.securities_count,
                tc.investment_country AS top_country,
                ta.asset_cat AS top_asset_cat,
                p.return_3m_pct
            FROM agg a
            LEFT JOIN nport_fund_info_core f
              ON f.quarter = a.quarter AND f.accession_number = a.accession_number
            LEFT JOIN nport_registrant_core r
              ON r.quarter = a.quarter AND r.accession_number = a.accession_number
            LEFT JOIN nport_submission_core s
              ON s.quarter = a.quarter AND s.accession_number = a.accession_number
            LEFT JOIN nport_fund_performance p
              ON p.quarter = a.quarter AND p.accession_number = a.accession_number
            LEFT JOIN top_country tc
              ON tc.quarter = a.quarter AND tc.accession_number = a.accession_number AND tc.rn = 1
            LEFT JOIN top_asset ta
              ON ta.quarter = a.quarter AND ta.accession_number = a.accession_number AND ta.rn = 1
            """,
            (*params, target, target_label),
        )

        con.execute(
            f"""
            INSERT OR REPLACE INTO nport_security_region_exposure (
                quarter, target, security_key, issuer_name, issuer_title, asset_cat, investment_country,
                long_value, short_value, net_value, gross_value, fund_count, holding_count
            )
            SELECT
                quarter,
                ? AS target,
                security_key,
                MAX(issuer_name) AS issuer_name,
                MAX(issuer_title) AS issuer_title,
                COALESCE(NULLIF(TRIM(asset_cat), ''), 'blank') AS asset_cat,
                COALESCE(NULLIF(TRIM(investment_country), ''), 'blank') AS investment_country,
                SUM(CASE WHEN {short_condition} THEN 0 ELSE COALESCE(currency_value, 0) END) AS long_value,
                SUM(CASE WHEN {short_condition} THEN ABS(COALESCE(currency_value, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(currency_value, 0)) AS net_value,
                SUM(ABS(COALESCE(currency_value, 0))) AS gross_value,
                COUNT(DISTINCT accession_number) AS fund_count,
                COUNT(*) AS holding_count
            FROM nport_holding_core
            WHERE quarter = ?
              AND investment_country IN ({placeholders})
              AND {valid_security_filter}
            GROUP BY quarter, security_key, COALESCE(NULLIF(TRIM(asset_cat), ''), 'blank'), COALESCE(NULLIF(TRIM(investment_country), ''), 'blank')
            """,
            (target, *params),
        )

        con.execute(
            f"""
            INSERT OR REPLACE INTO nport_country_asset_exposure (
                quarter, target, investment_country, asset_cat, long_value, short_value, net_value, gross_value, fund_count, holding_count
            )
            SELECT
                quarter,
                ? AS target,
                COALESCE(NULLIF(TRIM(investment_country), ''), 'blank') AS investment_country,
                COALESCE(NULLIF(TRIM(asset_cat), ''), 'blank') AS asset_cat,
                SUM(CASE WHEN {short_condition} THEN 0 ELSE COALESCE(currency_value, 0) END) AS long_value,
                SUM(CASE WHEN {short_condition} THEN ABS(COALESCE(currency_value, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(currency_value, 0)) AS net_value,
                SUM(ABS(COALESCE(currency_value, 0))) AS gross_value,
                COUNT(DISTINCT accession_number) AS fund_count,
                COUNT(*) AS holding_count
            FROM nport_holding_core
            WHERE quarter = ?
              AND investment_country IN ({placeholders})
            GROUP BY quarter, COALESCE(NULLIF(TRIM(investment_country), ''), 'blank'), COALESCE(NULLIF(TRIM(asset_cat), ''), 'blank')
            """,
            (target, *params),
        )

    def _insert_top_summary(
        self,
        con: sqlite3.Connection,
        quarter: str,
        dimension: str,
        key_col: str,
        label_col: str,
        total_value: float,
        limit: int,
    ) -> None:
        key_filter = ""
        if dimension == "security":
            key_filter = (
                "AND COALESCE(NULLIF(TRIM(security_key), ''), 'blank') "
                "NOT IN ('blank', 'N/A', 'NA', '000000000', '999999999')"
            )
        con.execute(
            f"""
            INSERT OR REPLACE INTO nport_summary_group (
                quarter, dimension, key, label, row_count, fund_count, value, abs_value, share_value_pct, extra_json
            )
            SELECT * FROM (
                SELECT
                    quarter,
                    ? AS dimension,
                    COALESCE(NULLIF(TRIM({_quote_ident(key_col)}), ''), 'blank') AS key,
                    COALESCE(NULLIF(TRIM(MAX({_quote_ident(label_col)})), ''), COALESCE(NULLIF(TRIM({_quote_ident(key_col)}), ''), 'blank')) AS label,
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT accession_number) AS fund_count,
                    SUM(COALESCE(currency_value, 0)) AS value,
                    SUM(ABS(COALESCE(currency_value, 0))) AS abs_value,
                    CASE WHEN ? != 0 THEN SUM(COALESCE(currency_value, 0)) / ? * 100.0 ELSE 0 END AS share_value_pct,
                    NULL AS extra_json
                FROM nport_holding_core
                WHERE quarter = ?
                  {key_filter}
                GROUP BY quarter, COALESCE(NULLIF(TRIM({_quote_ident(key_col)}), ''), 'blank')
                ORDER BY abs_value DESC
                LIMIT ?
            )
            """,
            (dimension, total_value, total_value, quarter, limit),
        )

    def get_dashboard(self, quarter: str | None = None) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_quarter(con, quarter)
            if not resolved:
                return {
                    "ok": False,
                    "success": False,
                    "error": "N-PORT database is empty. Ingest a quarterly package first.",
                    "report": {
                        "name": "N-Port",
                        "source": "SEC Form N-PORT Data Sets",
                        "status": "empty",
                    },
                }
            quarter = resolved
            quarter_row = con.execute("SELECT * FROM nport_quarters WHERE quarter = ?", (quarter,)).fetchone()
            manifest = [dict(row) for row in con.execute(
                "SELECT table_name, raw_table_name, file_name, row_count, column_count, file_size_bytes, loaded_at FROM nport_table_manifest WHERE quarter = ? ORDER BY file_name",
                (quarter,),
            ).fetchall()]

            kpi_row = con.execute(
                """
                SELECT
                    COUNT(*) AS holdings,
                    COUNT(DISTINCT accession_number) AS filings,
                    SUM(COALESCE(currency_value, 0)) AS total_value,
                    SUM(ABS(COALESCE(currency_value, 0))) AS total_abs_value,
                    SUM(CASE WHEN UPPER(COALESCE(payoff_profile, '')) = 'SHORT' THEN COALESCE(currency_value, 0) ELSE 0 END) AS short_value,
                    SUM(CASE WHEN COALESCE(TRIM(derivative_cat), '') != '' THEN COALESCE(currency_value, 0) ELSE 0 END) AS derivative_value,
                    SUM(CASE WHEN UPPER(COALESCE(is_restricted_security, '')) = 'Y' THEN COALESCE(currency_value, 0) ELSE 0 END) AS restricted_value,
                    SUM(CASE WHEN COALESCE(TRIM(fair_value_level), '') = '3' THEN COALESCE(currency_value, 0) ELSE 0 END) AS level3_value
                FROM nport_holding_core
                WHERE quarter = ?
                """,
                (quarter,),
            ).fetchone()
            fund_row = con.execute(
                """
                SELECT
                    COUNT(*) AS funds,
                    SUM(COALESCE(net_assets, 0)) AS net_assets,
                    SUM(COALESCE(net_flow_3m, 0)) AS net_flow_3m,
                    AVG(max_holding_pct) AS avg_max_holding_pct,
                    SUM(CASE WHEN max_holding_pct > 10 THEN 1 ELSE 0 END) AS funds_max_holding_gt_10,
                    SUM(CASE WHEN max_holding_pct > 25 THEN 1 ELSE 0 END) AS funds_max_holding_gt_25
                FROM nport_fund_summary
                WHERE quarter = ?
                """,
                (quarter,),
            ).fetchone()

            summaries = {
                dimension: self._summary_rows(con, quarter, dimension, 20)
                for dimension in (
                    "asset_cat",
                    "issuer_type",
                    "country",
                    "currency",
                    "fair_value_level",
                    "payoff_profile",
                    "restricted",
                    "derivative_cat",
                )
            }
            top_issuers = self._summary_rows(con, quarter, "issuer", 25)
            top_securities = self._summary_rows(con, quarter, "security", 25)
            top_funds = [dict(row) for row in con.execute(
                """
                SELECT accession_number, series_name, registrant_name, report_date, net_assets, holding_count,
                       max_holding_pct, restricted_value, derivative_value, level3_value, short_value, net_flow_3m
                FROM nport_fund_summary
                WHERE quarter = ?
                ORDER BY net_assets DESC
                LIMIT 25
                """,
                (quarter,),
            ).fetchall()]
            top_registrants = [dict(row) for row in con.execute(
                """
                SELECT registrant_name, filings, funds, net_assets, holding_value, holding_count, net_flow_3m
                FROM nport_registrant_summary
                WHERE quarter = ?
                ORDER BY net_assets DESC
                LIMIT 20
                """,
                (quarter,),
            ).fetchall()]
            debt_maturity = [dict(row) for row in con.execute(
                """
                SELECT maturity_bucket, row_count, value, abs_value, weighted_coupon, default_value
                FROM nport_debt_maturity_summary
                WHERE quarter = ?
                ORDER BY
                    CASE maturity_bucket
                        WHEN '0-1y' THEN 1
                        WHEN '1-3y' THEN 2
                        WHEN '3-5y' THEN 3
                        WHEN '5-7y' THEN 4
                        WHEN '7-10y' THEN 5
                        WHEN '10-30y' THEN 6
                        WHEN '30y+' THEN 7
                        WHEN 'vencido/indefinido' THEN 8
                        ELSE 9
                    END
                """,
                (quarter,),
            ).fetchall()]
            logs = [dict(row) for row in con.execute(
                """
                SELECT event_at, level, message, detail_json
                FROM nport_ingest_logs
                WHERE quarter = ?
                ORDER BY id DESC
                LIMIT 18
                """,
                (quarter,),
            ).fetchall()]

            report = {
                "name": "N-Port",
                "quarter": quarter,
                "as_of_date": quarter_row["latest_report_date"] if quarter_row else None,
                "source": "SEC Form N-PORT Data Sets",
                "source_url": SEC_NPORT_CATALOG_URL,
                "download_url": SEC_NPORT_DOWNLOAD_URL.format(quarter=quarter),
                "status": quarter_row["status"] if quarter_row else "unknown",
                "last_imported_at": quarter_row["imported_at"] if quarter_row else None,
                "db_path": str(self.db_path),
                "notes": [
                    "Dados publicados trimestralmente pela SEC em TSV/ZIP.",
                    "Conteudo as-filed: pode conter emendas, redundancias e diferencas de classificacao entre emissores.",
                    "A base representa holdings/reportes, nao fluxo diario de negociacao.",
                ],
            }

            kpis = {
                "holdings": kpi_row["holdings"] or 0,
                "filings": kpi_row["filings"] or 0,
                "funds": fund_row["funds"] or 0,
                "reported_value": kpi_row["total_value"] or 0,
                "reported_abs_value": kpi_row["total_abs_value"] or 0,
                "net_assets": fund_row["net_assets"] or 0,
                "net_flow_3m": fund_row["net_flow_3m"] or 0,
                "short_value": kpi_row["short_value"] or 0,
                "derivative_value": kpi_row["derivative_value"] or 0,
                "restricted_value": kpi_row["restricted_value"] or 0,
                "level3_value": kpi_row["level3_value"] or 0,
                "avg_max_holding_pct": fund_row["avg_max_holding_pct"] or 0,
                "funds_max_holding_gt_10": fund_row["funds_max_holding_gt_10"] or 0,
                "funds_max_holding_gt_25": fund_row["funds_max_holding_gt_25"] or 0,
            }

            return {
                "ok": True,
                "success": True,
                "report": report,
                "kpis": kpis,
                "summaries": summaries,
                "top_issuers": top_issuers,
                "top_securities": top_securities,
                "top_funds": top_funds,
                "top_registrants": top_registrants,
                "debt_maturity": debt_maturity,
                "manifest": manifest,
                "logs": logs,
                "ai_readiness": self._build_insights(report, kpis, summaries, top_issuers),
            }

    def _resolve_quarter(self, con: sqlite3.Connection, quarter: str | None) -> str | None:
        if quarter and str(quarter).lower() != "latest":
            return str(quarter).lower()
        row = con.execute(
            "SELECT quarter FROM nport_quarters WHERE status = 'ready' ORDER BY quarter DESC LIMIT 1"
        ).fetchone()
        if row:
            return row["quarter"]
        row = con.execute("SELECT quarter FROM nport_quarters ORDER BY quarter DESC LIMIT 1").fetchone()
        return row["quarter"] if row else None

    def _summary_rows(self, con: sqlite3.Connection, quarter: str, dimension: str, limit: int) -> list[dict[str, Any]]:
        return [dict(row) for row in con.execute(
            """
            SELECT key, label, row_count, fund_count, value, abs_value, share_value_pct, extra_json
            FROM nport_summary_group
            WHERE quarter = ? AND dimension = ?
            ORDER BY abs_value DESC
            LIMIT ?
            """,
            (quarter, dimension, limit),
        ).fetchall()]

    def rebuild_extended_analytics(self, quarter: str | None = None) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_quarter(con, quarter)
            if not resolved:
                return {"ok": False, "success": False, "error": "N-PORT database is empty."}
            started = time.time()
            self._build_extended_positioning_analytics(con, resolved)
            con.commit()
            counts = {
                "performance": con.execute(
                    "SELECT COUNT(*) AS total FROM nport_fund_performance WHERE quarter = ?",
                    (resolved,),
                ).fetchone()["total"],
                "fund_region_exposure": con.execute(
                    "SELECT COUNT(*) AS total FROM nport_fund_region_exposure WHERE quarter = ?",
                    (resolved,),
                ).fetchone()["total"],
                "security_region_exposure": con.execute(
                    "SELECT COUNT(*) AS total FROM nport_security_region_exposure WHERE quarter = ?",
                    (resolved,),
                ).fetchone()["total"],
                "country_asset_exposure": con.execute(
                    "SELECT COUNT(*) AS total FROM nport_country_asset_exposure WHERE quarter = ?",
                    (resolved,),
                ).fetchone()["total"],
            }
            return {
                "ok": True,
                "success": True,
                "quarter": resolved,
                "elapsed_ms": round((time.time() - started) * 1000),
                "counts": counts,
            }

    def list_fund_performance(
        self,
        quarter: str | None = None,
        page: int = 1,
        per_page: int = 25,
        weighted: bool = False,
    ) -> dict[str, Any]:
        self.init_db()
        page, per_page, offset = self._pagination(page, per_page, max_per_page=80)
        order_col = "aum_weighted_return" if weighted else "return_3m_pct"
        with self._connect() as con:
            resolved = self._resolve_quarter(con, quarter)
            if not resolved:
                return {"ok": False, "success": False, "error": "N-PORT database is empty.", "rows": []}
            total = con.execute(
                """
                SELECT COUNT(*) AS total
                FROM nport_fund_performance
                WHERE quarter = ? AND return_3m_pct IS NOT NULL
                """,
                (resolved,),
            ).fetchone()["total"]
            rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    accession_number, series_name, registrant_name, report_date, net_assets,
                    return_m1_pct, return_m2_pct, return_m3_pct, return_3m_pct,
                    aum_weighted_return, class_count,
                    {order_col} AS score
                FROM nport_fund_performance
                WHERE quarter = ? AND return_3m_pct IS NOT NULL
                ORDER BY {order_col} IS NULL, {order_col} DESC
                LIMIT ? OFFSET ?
                """,
                (resolved, per_page, offset),
            ).fetchall()]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "quarter": resolved,
                "page": page,
                "per_page": per_page,
                "total": total,
                "weighted": weighted,
                "sort_metric": order_col,
                "rows": rows,
            }

    def list_region_funds(
        self,
        target: str = "brazil",
        side: str = "long",
        quarter: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        self.init_db()
        target = self._normalize_target(target)
        side = self._normalize_side(side)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=80)
        order_col = {"long": "long_value", "short": "short_value", "net": "net_value"}[side]
        filter_sql = {
            "long": "AND COALESCE(long_value, 0) > 0",
            "short": "AND COALESCE(short_value, 0) > 0",
            "net": "AND ABS(COALESCE(net_value, 0)) > 0",
        }[side]
        with self._connect() as con:
            resolved = self._resolve_quarter(con, quarter)
            if not resolved:
                return {"ok": False, "success": False, "error": "N-PORT database is empty.", "rows": []}
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM nport_fund_region_exposure
                WHERE quarter = ? AND target = ?
                {filter_sql}
                """,
                (resolved, target),
            ).fetchone()["total"]
            rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    accession_number, target, target_label, series_name, registrant_name, report_date,
                    net_assets, long_value, short_value, net_value, gross_value,
                    long_pct_aum, short_pct_aum, net_pct_aum,
                    holdings_count, countries_count, securities_count, top_country, top_asset_cat,
                    return_3m_pct, {order_col} AS selected_value
                FROM nport_fund_region_exposure
                WHERE quarter = ? AND target = ?
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
                "quarter": resolved,
                "target": target,
                "target_label": NPORT_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "rows": rows,
            }

    def list_region_assets(
        self,
        target: str = "emerging",
        side: str = "long",
        quarter: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        self.init_db()
        target = self._normalize_target(target)
        side = self._normalize_side(side)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=80)
        order_col = {"long": "long_value", "short": "short_value", "net": "net_value"}[side]
        filter_sql = {
            "long": "AND COALESCE(long_value, 0) > 0",
            "short": "AND COALESCE(short_value, 0) > 0",
            "net": "AND ABS(COALESCE(net_value, 0)) > 0",
        }[side]
        with self._connect() as con:
            resolved = self._resolve_quarter(con, quarter)
            if not resolved:
                return {"ok": False, "success": False, "error": "N-PORT database is empty.", "rows": []}
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM nport_security_region_exposure
                WHERE quarter = ? AND target = ?
                {filter_sql}
                """,
                (resolved, target),
            ).fetchone()["total"]
            rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    security_key, issuer_name, issuer_title, asset_cat, investment_country,
                    long_value, short_value, net_value, gross_value, fund_count, holding_count,
                    {order_col} AS selected_value,
                    CASE WHEN COALESCE(gross_value, 0) != 0 THEN short_value / gross_value * 100.0 ELSE NULL END AS short_intensity_pct
                FROM nport_security_region_exposure
                WHERE quarter = ? AND target = ?
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
                "quarter": resolved,
                "target": target,
                "target_label": NPORT_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "rows": rows,
            }

    def list_fund_holdings(
        self,
        accession_number: str,
        target: str = "emerging",
        side: str = "all",
        quarter: str | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        self.init_db()
        accession_number = str(accession_number or "").strip()
        if not accession_number:
            raise ValueError("accession_number is required")
        target = self._normalize_target(target)
        side = self._normalize_side(side, allow_all=True)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=100)
        countries = NPORT_TARGET_COUNTRIES[target]
        placeholders = ",".join(["?"] * len(countries))
        short_condition = "UPPER(COALESCE(payoff_profile, '')) = 'SHORT' OR COALESCE(currency_value, 0) < 0"
        side_filter = ""
        if side == "short":
            side_filter = f"AND ({short_condition})"
        elif side == "long":
            side_filter = f"AND NOT ({short_condition}) AND COALESCE(currency_value, 0) > 0"
        with self._connect() as con:
            resolved = self._resolve_quarter(con, quarter)
            if not resolved:
                return {"ok": False, "success": False, "error": "N-PORT database is empty.", "rows": []}
            params: tuple[Any, ...] = (resolved, accession_number, *countries)
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM nport_holding_core
                WHERE quarter = ?
                  AND accession_number = ?
                  AND investment_country IN ({placeholders})
                  {side_filter}
                """,
                params,
            ).fetchone()["total"]
            fund = con.execute(
                """
                SELECT f.accession_number, f.series_name, r.registrant_name, s.report_date, f.net_assets
                FROM nport_fund_info_core f
                LEFT JOIN nport_registrant_core r
                  ON r.quarter = f.quarter AND r.accession_number = f.accession_number
                LEFT JOIN nport_submission_core s
                  ON s.quarter = f.quarter AND s.accession_number = f.accession_number
                WHERE f.quarter = ? AND f.accession_number = ?
                """,
                (resolved, accession_number),
            ).fetchone()
            rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    holding_id, security_key, issuer_name, issuer_title, asset_cat, issuer_type,
                    investment_country, currency_code, payoff_profile, derivative_cat,
                    currency_value, percentage,
                    CASE WHEN {short_condition} THEN 'short' ELSE 'long' END AS position_side
                FROM nport_holding_core
                WHERE quarter = ?
                  AND accession_number = ?
                  AND investment_country IN ({placeholders})
                  {side_filter}
                ORDER BY ABS(COALESCE(currency_value, 0)) DESC
                LIMIT ? OFFSET ?
                """,
                (*params, per_page, offset),
            ).fetchall()]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "quarter": resolved,
                "target": target,
                "target_label": NPORT_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "fund": dict(fund) if fund else {"accession_number": accession_number},
                "rows": rows,
            }

    def get_positioning_lab(self, quarter: str | None = None) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_quarter(con, quarter)
            if not resolved:
                return {"ok": False, "success": False, "error": "N-PORT database is empty."}
            countries = NPORT_TARGET_COUNTRIES["emerging"]
            placeholders = ",".join(["?"] * len(countries))
            short_condition = "UPPER(COALESCE(payoff_profile, '')) = 'SHORT' OR COALESCE(currency_value, 0) < 0"

            country_asset_rows = [dict(row) for row in con.execute(
                """
                SELECT investment_country, asset_cat, long_value, short_value, net_value, gross_value, fund_count, holding_count
                FROM nport_country_asset_exposure
                WHERE quarter = ? AND target = 'emerging'
                """,
                (resolved,),
            ).fetchall()]
            top_countries = [row["investment_country"] for row in con.execute(
                """
                SELECT investment_country
                FROM nport_country_asset_exposure
                WHERE quarter = ? AND target = 'emerging'
                GROUP BY investment_country
                ORDER BY SUM(COALESCE(gross_value, 0)) DESC
                LIMIT 18
                """,
                (resolved,),
            ).fetchall()]
            top_assets = [row["asset_cat"] for row in con.execute(
                """
                SELECT asset_cat
                FROM nport_country_asset_exposure
                WHERE quarter = ? AND target = 'emerging'
                GROUP BY asset_cat
                ORDER BY SUM(COALESCE(gross_value, 0)) DESC
                LIMIT 8
                """,
                (resolved,),
            ).fetchall()]
            by_cell = {
                (row["investment_country"], row["asset_cat"]): row
                for row in country_asset_rows
            }
            heatmap_cells = []
            heatmap_z = []
            for country in top_countries:
                row_values = []
                for asset in top_assets:
                    cell = by_cell.get((country, asset)) or {}
                    value = float(cell.get("net_value") or 0)
                    row_values.append(value)
                    heatmap_cells.append({
                        "country": country,
                        "asset_cat": asset,
                        "net_value": value,
                        "long_value": cell.get("long_value") or 0,
                        "short_value": cell.get("short_value") or 0,
                        "gross_value": cell.get("gross_value") or 0,
                        "fund_count": cell.get("fund_count") or 0,
                        "holding_count": cell.get("holding_count") or 0,
                    })
                heatmap_z.append(row_values)

            country_imbalance = [dict(row) for row in con.execute(
                f"""
                SELECT
                    investment_country,
                    SUM(CASE WHEN {short_condition} THEN 0 ELSE COALESCE(currency_value, 0) END) AS long_value,
                    SUM(CASE WHEN {short_condition} THEN ABS(COALESCE(currency_value, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(currency_value, 0)) AS net_value,
                    SUM(ABS(COALESCE(currency_value, 0))) AS gross_value,
                    COUNT(DISTINCT accession_number) AS fund_count,
                    COUNT(*) AS holding_count,
                    CASE WHEN SUM(ABS(COALESCE(currency_value, 0))) != 0
                         THEN SUM(COALESCE(currency_value, 0)) / SUM(ABS(COALESCE(currency_value, 0))) * 100.0
                         ELSE NULL END AS net_to_gross_pct,
                    CASE WHEN SUM(ABS(COALESCE(currency_value, 0))) != 0
                         THEN SUM(CASE WHEN {short_condition} THEN ABS(COALESCE(currency_value, 0)) ELSE 0 END) / SUM(ABS(COALESCE(currency_value, 0))) * 100.0
                         ELSE NULL END AS short_intensity_pct
                FROM nport_holding_core
                WHERE quarter = ? AND investment_country IN ({placeholders})
                GROUP BY investment_country
                ORDER BY gross_value DESC
                LIMIT 32
                """,
                (resolved, *countries),
            ).fetchall()]

            fund_quadrant = [dict(row) for row in con.execute(
                """
                SELECT
                    e.accession_number, e.series_name, e.registrant_name, e.net_assets,
                    e.long_value, e.short_value, e.net_value, e.gross_value,
                    e.long_pct_aum, e.short_pct_aum, e.net_pct_aum, e.return_3m_pct,
                    e.top_country, e.top_asset_cat, f.max_holding_pct, f.pct_hhi,
                    CASE WHEN COALESCE(e.net_assets, 0) != 0 THEN e.gross_value / e.net_assets * 100.0 ELSE NULL END AS gross_pct_aum
                FROM nport_fund_region_exposure e
                LEFT JOIN nport_fund_summary f
                  ON f.quarter = e.quarter AND f.accession_number = e.accession_number
                WHERE e.quarter = ? AND e.target = 'emerging' AND COALESCE(e.gross_value, 0) > 0
                ORDER BY e.gross_value DESC
                LIMIT 120
                """,
                (resolved,),
            ).fetchall()]

            edge_funds = [dict(row) for row in con.execute(
                """
                SELECT
                    accession_number, series_name, registrant_name, net_assets,
                    long_value, short_value, net_value, gross_value,
                    net_pct_aum, long_pct_aum, short_pct_aum, return_3m_pct,
                    top_country, top_asset_cat,
                    COALESCE(return_3m_pct, 0) * COALESCE(net_pct_aum, 0) AS edge_score
                FROM nport_fund_region_exposure
                WHERE quarter = ?
                  AND target = 'emerging'
                  AND COALESCE(return_3m_pct, 0) > 0
                  AND COALESCE(net_pct_aum, 0) > 0
                ORDER BY edge_score DESC
                LIMIT 24
                """,
                (resolved,),
            ).fetchall()]

            squeeze_radar = [dict(row) for row in con.execute(
                """
                SELECT
                    security_key, issuer_name, issuer_title, asset_cat, investment_country,
                    long_value, short_value, net_value, gross_value, fund_count, holding_count,
                    CASE WHEN COALESCE(gross_value, 0) != 0 THEN short_value / gross_value * 100.0 ELSE NULL END AS short_intensity_pct
                FROM nport_security_region_exposure
                WHERE quarter = ?
                  AND target = 'emerging'
                  AND COALESCE(short_value, 0) > 0
                ORDER BY short_value DESC
                LIMIT 24
                """,
                (resolved,),
            ).fetchall()]

            return {
                "ok": True,
                "success": True,
                "quarter": resolved,
                "heatmap": {
                    "x": top_assets,
                    "y": top_countries,
                    "z": heatmap_z,
                    "cells": heatmap_cells,
                    "metric": "net_value_usd",
                },
                "country_imbalance": country_imbalance,
                "fund_quadrant": fund_quadrant,
                "edge_funds": edge_funds,
                "squeeze_radar": squeeze_radar,
            }

    def _normalize_target(self, target: str) -> str:
        normalized = str(target or "emerging").strip().lower()
        aliases = {
            "br": "brazil",
            "brasil": "brazil",
            "brazil": "brazil",
            "cn": "china",
            "china": "china",
            "hk": "china",
            "em": "emerging",
            "ems": "emerging",
            "emergentes": "emerging",
            "emerging": "emerging",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in NPORT_TARGET_COUNTRIES:
            raise ValueError(f"Unknown N-PORT target: {target}")
        return normalized

    def _normalize_side(self, side: str, allow_all: bool = False) -> str:
        normalized = str(side or ("all" if allow_all else "long")).strip().lower()
        aliases = {
            "comprado": "long",
            "comprados": "long",
            "buy": "long",
            "bought": "long",
            "long": "long",
            "short": "short",
            "shorteado": "short",
            "shorteados": "short",
            "vendido": "short",
            "vendidos": "short",
            "net": "net",
            "liquido": "net",
            "líquido": "net",
            "all": "all",
            "todos": "all",
        }
        normalized = aliases.get(normalized, normalized)
        allowed = {"long", "short", "net"}
        if allow_all:
            allowed.add("all")
        if normalized not in allowed:
            raise ValueError(f"Unknown N-PORT side: {side}")
        return normalized

    def _pagination(self, page: int, per_page: int, max_per_page: int = 100) -> tuple[int, int, int]:
        try:
            page_int = int(page)
        except (TypeError, ValueError):
            page_int = 1
        try:
            per_page_int = int(per_page)
        except (TypeError, ValueError):
            per_page_int = 25
        page_int = max(page_int, 1)
        per_page_int = min(max(per_page_int, 1), max_per_page)
        return page_int, per_page_int, (page_int - 1) * per_page_int

    def _build_insights(
        self,
        report: dict[str, Any],
        kpis: dict[str, Any],
        summaries: dict[str, list[dict[str, Any]]],
        top_issuers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        top_asset = (summaries.get("asset_cat") or [{}])[0]
        top_country = (summaries.get("country") or [{}])[0]
        top_currency = (summaries.get("currency") or [{}])[0]
        top_issuer = (top_issuers or [{}])[0]
        reported = kpis.get("reported_value") or 0
        restricted_pct = (kpis.get("restricted_value") or 0) / reported * 100 if reported else 0
        level3_pct = (kpis.get("level3_value") or 0) / reported * 100 if reported else 0
        return {
            "quick_read": [
                f"Pacote {report.get('quarter')} importado com {int(kpis.get('holdings') or 0):,} holdings e {int(kpis.get('filings') or 0):,} filings.".replace(",", "."),
                f"Maior classe reportada: {top_asset.get('label', '-')} com {top_asset.get('share_value_pct', 0):.1f}% do valor.",
                f"País/moeda dominantes: {top_country.get('label', '-')} / {top_currency.get('label', '-')}."
            ],
            "risk_flags": [
                f"Restritos representam {restricted_pct:.2f}% do valor reportado.",
                f"Level 3 representa {level3_pct:.2f}% do valor reportado.",
                f"Maior emissor agregado: {top_issuer.get('label', '-')}."
            ],
            "recommended_views": [
                "Grafo fundo -> emissor -> pais -> classe de ativo para crowding global.",
                "Ranking por emissor/security_key para concentracao em mega caps, Treasuries e ETFs.",
                "Mapa pais x classe para exposicao geografica de fundos globais.",
                "Bucket de vencimento/cupom/default para camada de credito.",
            ],
        }

    def discover_remote_quarters(self) -> dict[str, Any]:
        headers = {"User-Agent": getattr(Config, "NPORT_SEC_USER_AGENT", "MiroFish NPORT research contato@example.com")}
        response = requests.get(SEC_NPORT_CATALOG_URL, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        urls: dict[str, str] = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            match = re.search(r"(20\d{2}q[1-4])_nport\.zip", href, flags=re.IGNORECASE)
            if match:
                quarter = match.group(1).lower()
                urls[quarter] = href if href.startswith("http") else f"https://www.sec.gov{href}"
        if not urls:
            for match in re.finditer(r"https://www\.sec\.gov/files/dera/data/form-n-port-data-sets/(20\d{2}q[1-4])_nport\.zip", response.text, flags=re.IGNORECASE):
                quarter = match.group(1).lower()
                urls[quarter] = match.group(0)
        quarters = [
            {"quarter": quarter, "url": urls[quarter]}
            for quarter in sorted(urls.keys(), reverse=True)
        ]
        with self._connect() as con:
            local = {row["quarter"]: row["status"] for row in con.execute("SELECT quarter, status FROM nport_quarters").fetchall()}
        for item in quarters:
            item["local_status"] = local.get(item["quarter"], "missing")
        return {
            "ok": True,
            "source_url": SEC_NPORT_CATALOG_URL,
            "latest_remote_quarter": quarters[0]["quarter"] if quarters else None,
            "quarters": quarters,
        }

    def download_quarter(self, quarter: str, force: bool = False, ingest: bool = False) -> dict[str, Any]:
        quarter = str(quarter or "").strip().lower()
        if not re.fullmatch(r"20\d{2}q[1-4]", quarter):
            raise ValueError("quarter must look like 2026q1")
        target_dir = self.raw_dir / quarter
        zip_path = target_dir / f"{quarter}_nport.zip"
        extract_dir = target_dir / f"{quarter}_nport"
        target_dir.mkdir(parents=True, exist_ok=True)
        if not zip_path.exists() or force:
            url = SEC_NPORT_DOWNLOAD_URL.format(quarter=quarter)
            headers = {"User-Agent": getattr(Config, "NPORT_SEC_USER_AGENT", "MiroFish NPORT research contato@example.com")}
            with requests.get(url, headers=headers, stream=True, timeout=120) as response:
                response.raise_for_status()
                tmp_path = zip_path.with_suffix(".zip.tmp")
                with tmp_path.open("wb") as fh:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            fh.write(chunk)
                tmp_path.replace(zip_path)
        if force and extract_dir.exists():
            shutil.rmtree(extract_dir)
        if not extract_dir.exists():
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        result = {
            "ok": True,
            "quarter": quarter,
            "zip_path": str(zip_path),
            "extract_dir": str(extract_dir),
            "ingested": False,
        }
        if ingest:
            result["ingest"] = self.ingest_local_directory(str(extract_dir), quarter=quarter, force=force)
            result["ingested"] = True
        return result
