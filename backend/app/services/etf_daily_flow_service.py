from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import traceback
from datetime import datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..config import Config
from ..utils.logger import get_logger
from .etf_daily_flow_catalog import (
    DEFAULT_ETF_UNIVERSE,
    DEFAULT_PROVIDER_ORDER,
    ETF_DAILY_FLOW_SCHEMA_VERSION,
)
from .etf_daily_flow_provider_base import GenericHtmlEtfProvider
from .etf_daily_flow_providers_a import (
    ISharesEtfProvider,
    SchwabEtfProvider,
    StateStreetEtfProvider,
    VanEckEtfProvider,
)
from .etf_daily_flow_providers_b import DimensionalEtfProvider, VanguardEtfProvider
from .etf_daily_flow_providers_c import (
    GlobalXEtfProvider,
    InvescoEtfProvider,
    ProSharesEtfProvider,
)
from .etf_daily_flow_types import (
    EtfObservation,
    EtfScrapeError,
    _anchor_snippet,
    _classify_aum_bucket,
    _classify_country_focus,
    _classify_development,
    _classify_segment,
    _classify_type,
    _coalesce,
    _compact_text,
    _extract_first_regex,
    _finite_float,
    _fund_text_blob,
    _json_dumps,
    _json_loads,
    _meta_float,
    _meta_text,
    _parse_date,
    _provider_label,
    _row_text_for_label,
    _safe_provider,
    _safe_ticker,
    _sha256,
    _slugify,
    _text_by_data_id,
    _utc_now,
    _utc_now_iso,
    _value_after_label,
    _walk_json,
)

logger = get_logger("aquiles.etf_daily_flow")

__all__ = [
    "EtfDailyFlowManager",
    "EtfDailyFlowService",
    "EtfObservation",
    "EtfScrapeError",
    "GenericHtmlEtfProvider",
    "_anchor_snippet",
    "_classify_aum_bucket",
    "_classify_country_focus",
    "_classify_development",
    "_classify_segment",
    "_classify_type",
    "_coalesce",
    "_compact_text",
    "_extract_first_regex",
    "_finite_float",
    "_fund_text_blob",
    "_json_dumps",
    "_json_loads",
    "_meta_float",
    "_meta_text",
    "_parse_date",
    "_provider_label",
    "_row_text_for_label",
    "_safe_provider",
    "_safe_ticker",
    "_sha256",
    "_slugify",
    "_text_by_data_id",
    "_value_after_label",
    "_walk_json",
]

PROVIDER_CLASSES = {
    "schwab": SchwabEtfProvider,
    "state_street": StateStreetEtfProvider,
    "vaneck": VanEckEtfProvider,
    "ishares": ISharesEtfProvider,
    "dimensional": DimensionalEtfProvider,
    "vanguard": VanguardEtfProvider,
    "invesco": InvescoEtfProvider,
    "proshares": ProSharesEtfProvider,
    "global_x": GlobalXEtfProvider,
}


class EtfDailyFlowService:
    def __init__(self, data_dir: str | os.PathLike[str] | None = None):
        self.data_dir = Path(data_dir or Config.ETF_DAILY_FLOW_DATA_DIR).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "etf_daily_flows.sqlite"
        self.tz = ZoneInfo(Config.ETF_DAILY_FLOW_TIMEZONE)
        self.timeout_seconds = float(Config.ETF_DAILY_FLOW_REQUEST_TIMEOUT_SECONDS)
        self.max_attempts = int(Config.ETF_DAILY_FLOW_REQUEST_MAX_ATTEMPTS)
        self.retry_backoff_seconds = float(Config.ETF_DAILY_FLOW_RETRY_BACKOFF_SECONDS)
        self.contract_failure_threshold = int(Config.ETF_DAILY_FLOW_CONTRACT_FAILURE_THRESHOLD)
        self.max_stale_hours = float(Config.ETF_DAILY_FLOW_MAX_STALE_HOURS)
        self.user_agent = Config.ETF_DAILY_FLOW_USER_AGENT
        self._providers: dict[str, GenericHtmlEtfProvider] = {}
        self._lock = threading.RLock()
        self._ensure_schema()
        if Config.ETF_DAILY_FLOW_SEED_DEFAULT_UNIVERSE:
            self.seed_default_universe()
        self.seed_universe_from_env()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS service_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS etf_universe (
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT,
                    url TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    active INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 100,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, ticker)
                );

                CREATE TABLE IF NOT EXISTS etf_source_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    provider TEXT,
                    tickers_json TEXT,
                    funds_attempted INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    observations_count INTEGER NOT NULL DEFAULT 0,
                    flows_count INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT
                );

                CREATE TABLE IF NOT EXISTS etf_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    nav REAL,
                    shares_outstanding REAL,
                    total_net_assets REAL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    confidence REAL NOT NULL DEFAULT 0,
                    field_hash TEXT,
                    extraction_method TEXT,
                    raw_payload_json TEXT,
                    warnings_json TEXT,
                    run_id TEXT,
                    UNIQUE(provider, ticker, as_of_date)
                );

                CREATE TABLE IF NOT EXISTS etf_daily_flows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    nav REAL NOT NULL,
                    shares_outstanding REAL NOT NULL,
                    previous_as_of_date TEXT NOT NULL,
                    previous_nav REAL NOT NULL,
                    previous_shares_outstanding REAL NOT NULL,
                    share_delta REAL NOT NULL,
                    flow_usd REAL NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    method TEXT NOT NULL,
                    warnings_json TEXT,
                    run_id TEXT,
                    UNIQUE(provider, ticker, as_of_date)
                );

                CREATE TABLE IF NOT EXISTS etf_source_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    provider TEXT,
                    ticker TEXT,
                    source_url TEXT,
                    stage TEXT,
                    error_type TEXT,
                    error TEXT,
                    traceback TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS etf_scrape_contracts (
                    provider TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_field_hash TEXT,
                    previous_field_hash TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, ticker)
                );

                CREATE INDEX IF NOT EXISTS idx_etf_observations_lookup
                    ON etf_observations(provider, ticker, as_of_date DESC);
                CREATE INDEX IF NOT EXISTS idx_etf_flows_lookup
                    ON etf_daily_flows(provider, ticker, as_of_date DESC);
                CREATE INDEX IF NOT EXISTS idx_etf_errors_created
                    ON etf_source_errors(created_at DESC);
                """
            )
            self._set_state(conn, "schema_version", str(ETF_DAILY_FLOW_SCHEMA_VERSION))

    def _set_state(self, conn: sqlite3.Connection, key: str, value: Any) -> None:
        conn.execute(
            """
            INSERT INTO service_state(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, str(value), _utc_now_iso()),
        )

    def _get_state(self, conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute("SELECT value FROM service_state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def seed_default_universe(self) -> dict[str, Any]:
        inserted = 0
        updated = 0
        skipped_existing = 0
        with self._connect() as conn:
            existing_keys = {
                (_safe_provider(row["provider"]), _safe_ticker(row["ticker"]))
                for row in conn.execute("SELECT provider, ticker FROM etf_universe").fetchall()
            }
        for item in DEFAULT_ETF_UNIVERSE:
            key = (_safe_provider(item.get("provider")), _safe_ticker(item.get("ticker")))
            if key in existing_keys:
                skipped_existing += 1
                continue
            result = self.upsert_fund(item)
            existing_keys.add(key)
            inserted += 1 if result.get("created") else 0
            updated += 1 if not result.get("created") else 0
        return {
            "ok": True,
            "inserted": inserted,
            "updated": updated,
            "skipped_existing": skipped_existing,
            "total": len(DEFAULT_ETF_UNIVERSE),
        }

    def seed_universe_from_env(self) -> dict[str, Any]:
        raw = str(getattr(Config, "ETF_DAILY_FLOW_UNIVERSE_JSON", "") or "").strip()
        if not raw:
            return {"ok": True, "inserted": 0, "updated": 0}
        try:
            payload = json.loads(raw)
        except Exception as exc:
            logger.warning("ETF_DAILY_FLOW_UNIVERSE_JSON is invalid: %s", exc)
            return {"ok": False, "error": str(exc)}
        items = payload if isinstance(payload, list) else payload.get("funds", [])
        inserted = 0
        updated = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            result = self.upsert_fund(item)
            inserted += 1 if result.get("created") else 0
            updated += 1 if not result.get("created") else 0
        return {"ok": True, "inserted": inserted, "updated": updated}

    def discover_provider(
        self,
        provider: str,
        source_url: str | None = None,
        seed_universe: bool = True,
        reset_provider: bool = False,
        max_funds: int | None = None,
    ) -> dict[str, Any]:
        provider = _safe_provider(provider)
        if not provider:
            raise ValueError("provider is required")
        run_id = f"etf-catalog-{provider}-{_utc_now().strftime('%Y%m%dT%H%M%S')}-{_sha256(str(time.time()))[:8]}"
        started_at = _utc_now_iso()
        try:
            result = self._provider_instance(provider).discover_funds(source_url=source_url, max_funds=max_funds)
            funds = result.get("funds") if isinstance(result.get("funds"), list) else []
            inserted = 0
            updated = 0
            deactivated = 0
            if seed_universe:
                discovered_tickers = {_safe_ticker(fund.get("ticker")) for fund in funds if isinstance(fund, dict)}
                previous_active_tickers: set[str] = set()
                if reset_provider:
                    with self._connect() as conn:
                        previous_active_tickers = {
                            _safe_ticker(row["ticker"])
                            for row in conn.execute(
                                "SELECT ticker FROM etf_universe WHERE provider = ? AND active = 1",
                                (provider,),
                            ).fetchall()
                        }
                        conn.execute(
                            "UPDATE etf_universe SET active = 0, updated_at = ? WHERE provider = ?",
                            (_utc_now_iso(), provider),
                        )
                    deactivated = len(previous_active_tickers - discovered_tickers)
                for fund in funds:
                    outcome = self.upsert_fund(fund)
                    inserted += 1 if outcome.get("created") else 0
                    updated += 1 if not outcome.get("created") else 0
            completed_at = _utc_now_iso()
            if max_funds is None:
                with self._connect() as conn:
                    self._set_state(conn, f"catalog:{provider}:last_run_id", run_id)
                    self._set_state(conn, f"catalog:{provider}:last_completed_at", completed_at)
                    self._set_state(conn, f"catalog:{provider}:last_count", len(funds))
                    self._set_state(conn, f"catalog:{provider}:last_hash", result.get("catalog_hash") or "")
                    self._set_state(conn, f"catalog:{provider}:last_status", "ok")
                    self._set_state(conn, f"catalog:{provider}:last_error", "")
            return {
                "ok": True,
                "run_id": run_id,
                "provider": provider,
                "started_at": started_at,
                "completed_at": completed_at,
                "source_url": result.get("source_url") or source_url,
                "catalog_count": len(funds),
                "inserted": inserted,
                "updated": updated,
                "deactivated": deactivated,
                "seed_universe": seed_universe,
                "reset_provider": reset_provider,
                "funds": funds,
            }
        except Exception as exc:
            self._record_error(
                run_id,
                {"provider": provider, "ticker": "", "url": source_url or ""},
                "discover",
                exc,
            )
            with self._connect() as conn:
                self._set_state(conn, f"catalog:{provider}:last_run_id", run_id)
                self._set_state(conn, f"catalog:{provider}:last_completed_at", _utc_now_iso())
                self._set_state(conn, f"catalog:{provider}:last_status", "failed")
                self._set_state(conn, f"catalog:{provider}:last_error", str(exc))
            raise

    def refresh_universe(
        self,
        provider: str | None = None,
        providers: list[str] | None = None,
        reset_provider: bool = True,
    ) -> dict[str, Any]:
        if provider:
            provider_order = [_safe_provider(provider)]
        elif providers:
            provider_order = [_safe_provider(item) for item in providers if _safe_provider(item)]
        else:
            configured = [
                _safe_provider(item)
                for item in str(getattr(Config, "ETF_DAILY_FLOW_CATALOG_PROVIDERS", "") or "").split(",")
                if _safe_provider(item)
            ]
            provider_order = configured or list(DEFAULT_PROVIDER_ORDER)

        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for item in dict.fromkeys(provider_order):
            if not item:
                continue
            try:
                result = self.discover_provider(item, reset_provider=reset_provider)
                results.append(
                    {
                        "provider": item,
                        "ok": True,
                        "catalog_count": result.get("catalog_count"),
                        "inserted": result.get("inserted"),
                        "updated": result.get("updated"),
                        "deactivated": result.get("deactivated"),
                        "run_id": result.get("run_id"),
                    }
                )
            except Exception as exc:
                failures.append({"provider": item, "ok": False, "error": str(exc)})
                logger.warning("ETF catalog refresh failed: provider=%s error=%s", item, exc)
        return {
            "ok": not failures,
            "status": "ok" if not failures else "partial" if results else "failed",
            "providers_attempted": len(results) + len(failures),
            "success_count": len(results),
            "failure_count": len(failures),
            "results": results,
            "failures": failures,
        }

    def upsert_fund(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = _safe_provider(payload.get("provider"))
        ticker = _safe_ticker(payload.get("ticker"))
        url = str(payload.get("url") or "").strip()
        if not provider or not ticker or not url:
            raise ValueError("provider, ticker and url are required")
        now = _utc_now_iso()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        active = 1 if payload.get("active", True) else 0
        priority = int(payload.get("priority") or 100)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT provider, ticker FROM etf_universe WHERE provider = ? AND ticker = ?",
                (provider, ticker),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO etf_universe(
                    provider, ticker, name, url, currency, active, priority, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, ticker) DO UPDATE SET
                    name=excluded.name,
                    url=excluded.url,
                    currency=excluded.currency,
                    active=excluded.active,
                    priority=excluded.priority,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    provider,
                    ticker,
                    str(payload.get("name") or ticker).strip(),
                    url,
                    str(payload.get("currency") or "USD").strip().upper(),
                    active,
                    priority,
                    _json_dumps(metadata),
                    now,
                    now,
                ),
            )
        return {"ok": True, "provider": provider, "ticker": ticker, "created": existing is None}

    def list_universe(self, active: bool | None = None, provider: str | None = None, limit: int | None = None) -> dict[str, Any]:
        sql = "SELECT * FROM etf_universe"
        params: list[Any] = []
        clauses: list[str] = []
        if active is not None:
            clauses.append("active = ?")
            params.append(1 if active else 0)
        if provider:
            clauses.append("provider = ?")
            params.append(_safe_provider(provider))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY priority ASC, provider ASC, ticker ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(max(1, min(int(limit), 5000)))
        with self._connect() as conn:
            rows = [self._row_to_fund(row) for row in conn.execute(sql, params).fetchall()]
        return {"ok": True, "count": len(rows), "funds": rows}

    def _row_to_fund(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["active"] = bool(item.get("active"))
        item["metadata"] = _json_loads(item.pop("metadata_json", None), {})
        return item

    def _provider_instance(self, provider: str) -> GenericHtmlEtfProvider:
        provider = _safe_provider(provider)
        if provider not in self._providers:
            cls = PROVIDER_CLASSES.get(provider, GenericHtmlEtfProvider)
            self._providers[provider] = cls(timeout_seconds=self.timeout_seconds, user_agent=self.user_agent)
        return self._providers[provider]

    def collect(
        self,
        provider: str | None = None,
        tickers: list[str] | None = None,
        force: bool = False,
        limit: int | None = None,
        refresh_universe: bool | None = None,
    ) -> dict[str, Any]:
        provider = _safe_provider(provider) if provider else None
        ticker_set = {_safe_ticker(ticker) for ticker in tickers or [] if _safe_ticker(ticker)}
        refresh_result: dict[str, Any] | None = None
        should_refresh_universe = (
            Config.ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT
            if refresh_universe is None
            else bool(refresh_universe)
        )
        if should_refresh_universe:
            refresh_result = self.refresh_universe(provider=provider, reset_provider=True)
        funds = self._select_funds(provider=provider, tickers=sorted(ticker_set) if ticker_set else None, limit=limit)
        run_id = f"etf-flow-{_utc_now().strftime('%Y%m%dT%H%M%S')}-{_sha256(str(time.time()))[:8]}"
        started_at = _utc_now_iso()
        errors: list[dict[str, Any]] = []
        success_count = 0
        observations_count = 0
        flows_count = 0

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO etf_source_runs(
                    run_id, started_at, status, provider, tickers_json, funds_attempted, errors_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    started_at,
                    "running",
                    provider,
                    _json_dumps(sorted(ticker_set)) if ticker_set else None,
                    len(funds),
                    "[]",
                ),
            )

        logger.info("ETF daily flow collection started: run_id=%s funds=%s", run_id, len(funds))
        for fund in funds:
            try:
                observation = self._collect_one_with_retries(fund, run_id)
                flow = self._save_observation_and_flow(observation, run_id, force=force)
                self._record_contract_success(observation)
                success_count += 1
                observations_count += 1
                flows_count += 1 if flow.get("created") else 0
            except Exception as exc:
                error_payload = self._record_error(run_id, fund, "collect", exc)
                errors.append(error_payload)
                self._record_contract_failure(fund, exc)

        failure_count = len(funds) - success_count
        status = "ok" if failure_count == 0 else "partial" if success_count else "failed"
        completed_at = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE etf_source_runs
                SET completed_at = ?, status = ?, success_count = ?, failure_count = ?,
                    observations_count = ?, flows_count = ?, errors_json = ?
                WHERE run_id = ?
                """,
                (
                    completed_at,
                    status,
                    success_count,
                    failure_count,
                    observations_count,
                    flows_count,
                    _json_dumps(errors[:50]),
                    run_id,
                ),
            )
            self._set_state(conn, "last_run_id", run_id)
            self._set_state(conn, "last_run_completed_at", completed_at)

        logger.info(
            "ETF daily flow collection finished: run_id=%s status=%s success=%s failure=%s",
            run_id,
            status,
            success_count,
            failure_count,
        )
        return {
            "ok": success_count > 0 and status != "failed",
            "run_id": run_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "funds_attempted": len(funds),
            "success_count": success_count,
            "failure_count": failure_count,
            "observations_count": observations_count,
            "flows_count": flows_count,
            "catalog_refresh": refresh_result,
            "errors": errors[:20],
        }

    def _select_funds(
        self,
        provider: str | None = None,
        tickers: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM etf_universe WHERE active = 1"
        params: list[Any] = []
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if tickers:
            placeholders = ",".join("?" for _ in tickers)
            sql += f" AND ticker IN ({placeholders})"
            params.extend(tickers)
        sql += " ORDER BY priority ASC, provider ASC, ticker ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(max(1, min(int(limit), 5000)))
        with self._connect() as conn:
            return [self._row_to_fund(row) for row in conn.execute(sql, params).fetchall()]

    def _collect_one_with_retries(self, fund: dict[str, Any], run_id: str) -> EtfObservation:
        provider = self._provider_instance(fund["provider"])
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                observation = provider.fetch_observation(fund, self.tz)
                if not observation.ticker:
                    raise EtfScrapeError("empty ticker after normalization")
                return observation
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "ETF scrape attempt failed: run_id=%s provider=%s ticker=%s attempt=%s/%s error=%s",
                    run_id,
                    fund.get("provider"),
                    fund.get("ticker"),
                    attempt,
                    self.max_attempts,
                    exc,
                )
                if attempt < self.max_attempts:
                    time.sleep(self.retry_backoff_seconds * attempt)
        assert last_exc is not None
        raise last_exc

    def _save_observation_and_flow(self, observation: EtfObservation, run_id: str, force: bool = False) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO etf_observations(
                    provider, ticker, as_of_date, captured_at, source_url, nav, shares_outstanding,
                    total_net_assets, currency, confidence, field_hash, extraction_method,
                    raw_payload_json, warnings_json, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, ticker, as_of_date) DO UPDATE SET
                    captured_at=excluded.captured_at,
                    source_url=excluded.source_url,
                    nav=excluded.nav,
                    shares_outstanding=excluded.shares_outstanding,
                    total_net_assets=excluded.total_net_assets,
                    currency=excluded.currency,
                    confidence=excluded.confidence,
                    field_hash=excluded.field_hash,
                    extraction_method=excluded.extraction_method,
                    raw_payload_json=excluded.raw_payload_json,
                    warnings_json=excluded.warnings_json,
                    run_id=excluded.run_id
                """,
                (
                    observation.provider,
                    observation.ticker,
                    observation.as_of_date,
                    observation.captured_at,
                    observation.source_url,
                    observation.nav,
                    observation.shares_outstanding,
                    observation.total_net_assets,
                    observation.currency,
                    observation.confidence,
                    observation.field_hash,
                    observation.extraction_method,
                    _json_dumps(observation.raw_payload),
                    _json_dumps(observation.warnings),
                    run_id,
                ),
            )
            prev = conn.execute(
                """
                SELECT *
                FROM etf_observations
                WHERE provider = ? AND ticker = ? AND as_of_date < ?
                    AND nav IS NOT NULL AND shares_outstanding IS NOT NULL
                ORDER BY as_of_date DESC
                LIMIT 1
                """,
                (observation.provider, observation.ticker, observation.as_of_date),
            ).fetchone()
            if not prev:
                return {"ok": True, "created": False, "reason": "no_previous_observation"}
            if observation.nav is None or observation.shares_outstanding is None:
                return {"ok": False, "created": False, "reason": "missing_current_observation_fields"}

            warnings = list(observation.warnings)
            share_delta = float(observation.shares_outstanding) - float(prev["shares_outstanding"])
            flow_usd = share_delta * float(observation.nav)
            method = "shares_delta_x_nav"
            if "shares_outstanding_inferred_from_assets_and_nav" in warnings:
                method = "assets_nav_implied_share_delta_x_nav"

            split_like = self._looks_like_split(
                prev_shares=float(prev["shares_outstanding"]),
                current_shares=float(observation.shares_outstanding),
                prev_nav=float(prev["nav"]),
                current_nav=float(observation.nav),
            )
            if split_like:
                warnings.append("probable_split_or_share_class_event_flow_requires_review")
                method = "review_required_probable_split"
                flow_usd = 0.0

            confidence = min(float(prev["confidence"] or 0.0), observation.confidence)
            if split_like:
                confidence = min(confidence, 0.25)
            conn.execute(
                """
                INSERT INTO etf_daily_flows(
                    provider, ticker, as_of_date, captured_at, nav, shares_outstanding,
                    previous_as_of_date, previous_nav, previous_shares_outstanding,
                    share_delta, flow_usd, confidence, method, warnings_json, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, ticker, as_of_date) DO UPDATE SET
                    captured_at=excluded.captured_at,
                    nav=excluded.nav,
                    shares_outstanding=excluded.shares_outstanding,
                    previous_as_of_date=excluded.previous_as_of_date,
                    previous_nav=excluded.previous_nav,
                    previous_shares_outstanding=excluded.previous_shares_outstanding,
                    share_delta=excluded.share_delta,
                    flow_usd=excluded.flow_usd,
                    confidence=excluded.confidence,
                    method=excluded.method,
                    warnings_json=excluded.warnings_json,
                    run_id=excluded.run_id
                """,
                (
                    observation.provider,
                    observation.ticker,
                    observation.as_of_date,
                    observation.captured_at,
                    observation.nav,
                    observation.shares_outstanding,
                    prev["as_of_date"],
                    prev["nav"],
                    prev["shares_outstanding"],
                    share_delta,
                    flow_usd,
                    confidence,
                    method,
                    _json_dumps(warnings),
                    run_id,
                ),
            )
            return {"ok": True, "created": True, "method": method, "flow_usd": flow_usd}

    def _looks_like_split(self, prev_shares: float, current_shares: float, prev_nav: float, current_nav: float) -> bool:
        if prev_shares <= 0 or current_shares <= 0 or prev_nav <= 0 or current_nav <= 0:
            return False
        share_ratio = current_shares / prev_shares
        nav_ratio = current_nav / prev_nav
        if 0.55 <= share_ratio <= 1.8:
            return False
        return abs((share_ratio * nav_ratio) - 1.0) <= 0.18

    def _record_contract_success(self, observation: EtfObservation) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT last_field_hash FROM etf_scrape_contracts WHERE provider = ? AND ticker = ?",
                (observation.provider, observation.ticker),
            ).fetchone()
            previous_hash = existing["last_field_hash"] if existing else None
            status = "ok"
            if previous_hash and previous_hash != observation.field_hash:
                status = "contract_changed"
            conn.execute(
                """
                INSERT INTO etf_scrape_contracts(
                    provider, ticker, status, last_field_hash, previous_field_hash,
                    consecutive_failures, last_success_at, last_failure_at, last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, NULL, NULL, ?)
                ON CONFLICT(provider, ticker) DO UPDATE SET
                    status=excluded.status,
                    previous_field_hash=excluded.previous_field_hash,
                    last_field_hash=excluded.last_field_hash,
                    consecutive_failures=0,
                    last_success_at=excluded.last_success_at,
                    last_error=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    observation.provider,
                    observation.ticker,
                    status,
                    observation.field_hash,
                    previous_hash,
                    now,
                    now,
                ),
            )

    def _record_contract_failure(self, fund: dict[str, Any], exc: Exception) -> None:
        provider = _safe_provider(fund.get("provider"))
        ticker = _safe_ticker(fund.get("ticker"))
        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT consecutive_failures FROM etf_scrape_contracts WHERE provider = ? AND ticker = ?",
                (provider, ticker),
            ).fetchone()
            consecutive = int(existing["consecutive_failures"] if existing else 0) + 1
            status = "broken_contract" if consecutive >= self.contract_failure_threshold else "degraded"
            conn.execute(
                """
                INSERT INTO etf_scrape_contracts(
                    provider, ticker, status, last_field_hash, previous_field_hash,
                    consecutive_failures, last_success_at, last_failure_at, last_error, updated_at
                )
                VALUES (?, ?, ?, NULL, NULL, ?, NULL, ?, ?, ?)
                ON CONFLICT(provider, ticker) DO UPDATE SET
                    status=excluded.status,
                    consecutive_failures=excluded.consecutive_failures,
                    last_failure_at=excluded.last_failure_at,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (provider, ticker, status, consecutive, now, str(exc), now),
            )

    def _record_error(self, run_id: str, fund: dict[str, Any], stage: str, exc: Exception) -> dict[str, Any]:
        payload = {
            "provider": _safe_provider(fund.get("provider")),
            "ticker": _safe_ticker(fund.get("ticker")),
            "source_url": str(fund.get("url") or ""),
            "stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "created_at": _utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO etf_source_errors(
                    run_id, provider, ticker, source_url, stage, error_type, error, traceback, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    payload["provider"],
                    payload["ticker"],
                    payload["source_url"],
                    stage,
                    payload["error_type"],
                    payload["error"],
                    traceback.format_exc(),
                    payload["created_at"],
                ),
            )
        return payload

    def health(self, manager_status: dict[str, Any] | None = None) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            last_run = conn.execute(
                "SELECT * FROM etf_source_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            latest_obs = conn.execute(
                "SELECT MAX(captured_at) AS captured_at, COUNT(*) AS count FROM etf_observations"
            ).fetchone()
            contracts = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT c.*
                    FROM etf_scrape_contracts c
                    JOIN etf_universe u
                        ON u.provider = c.provider
                        AND u.ticker = c.ticker
                        AND u.active = 1
                    ORDER BY c.provider, c.ticker
                    """
                ).fetchall()
            ]
            active_count = conn.execute("SELECT COUNT(*) AS count FROM etf_universe WHERE active = 1").fetchone()["count"]
            flow_count = conn.execute("SELECT COUNT(*) AS count FROM etf_daily_flows").fetchone()["count"]
            universe_by_provider = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT provider, COUNT(*) AS funds
                    FROM etf_universe
                    WHERE active = 1
                    GROUP BY provider
                    ORDER BY provider
                    """
                ).fetchall()
            ]
            observations_by_provider = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT provider, COUNT(DISTINCT ticker) AS funds, COUNT(*) AS observations, MAX(captured_at) AS latest_captured_at
                    FROM etf_observations
                    GROUP BY provider
                    ORDER BY provider
                    """
                ).fetchall()
            ]
            catalog_state = {
                str(row["key"]): str(row["value"])
                for row in conn.execute("SELECT key, value FROM service_state WHERE key LIKE 'catalog:%'").fetchall()
            }

        latest_captured_at = latest_obs["captured_at"] if latest_obs else None
        stale = True
        if latest_captured_at:
            try:
                age_hours = (now - datetime.fromisoformat(latest_captured_at)).total_seconds() / 3600
                stale = age_hours > self.max_stale_hours
            except Exception:
                age_hours = None
                stale = True
        else:
            age_hours = None

        broken = [item for item in contracts if item.get("status") == "broken_contract"]
        degraded = [item for item in contracts if item.get("status") in {"degraded", "contract_changed"}]
        service_status = "ok"
        if broken or degraded or stale:
            service_status = "degraded"
        if active_count and len(broken) >= active_count:
            service_status = "down"

        return {
            "ok": service_status == "ok",
            "status": service_status,
            "schema_version": ETF_DAILY_FLOW_SCHEMA_VERSION,
            "db_path": str(self.db_path),
            "timezone": str(self.tz),
            "capture_times": Config.ETF_DAILY_FLOW_CAPTURE_TIMES,
            "active_funds": active_count,
            "universe_by_provider": universe_by_provider,
            "observations_by_provider": observations_by_provider,
            "catalog_state": catalog_state,
            "observations": int(latest_obs["count"] or 0) if latest_obs else 0,
            "flows": int(flow_count or 0),
            "latest_captured_at": latest_captured_at,
            "latest_age_hours": age_hours,
            "stale": stale,
            "last_run": dict(last_run) if last_run else None,
            "contract_summary": {
                "total": len(contracts),
                "broken": len(broken),
                "degraded": len(degraded),
                "failure_threshold": self.contract_failure_threshold,
            },
            "contracts": contracts,
            "manager": manager_status or {},
        }

    def list_runs(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(int(limit or 20), 200))
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_source_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()]
        for row in rows:
            row["tickers"] = _json_loads(row.pop("tickers_json", None), [])
            row["errors"] = _json_loads(row.pop("errors_json", None), [])
        return {"ok": True, "count": len(rows), "runs": rows}

    def list_errors(self, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit or 50), 500))
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_source_errors ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()]
        return {"ok": True, "count": len(rows), "errors": rows}

    def list_observations(self, provider: str | None = None, ticker: str | None = None, limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit or 200), 1000))
        sql = "SELECT * FROM etf_observations WHERE 1=1"
        params: list[Any] = []
        if provider:
            sql += " AND provider = ?"
            params.append(_safe_provider(provider))
        if ticker:
            sql += " AND ticker = ?"
            params.append(_safe_ticker(ticker))
        sql += " ORDER BY as_of_date DESC, captured_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        for row in rows:
            row["raw_payload"] = _json_loads(row.pop("raw_payload_json", None), {})
            row["warnings"] = _json_loads(row.pop("warnings_json", None), [])
        return {"ok": True, "count": len(rows), "observations": rows}

    def list_flows(self, provider: str | None = None, ticker: str | None = None, limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit or 200), 1000))
        sql = "SELECT * FROM etf_daily_flows WHERE 1=1"
        params: list[Any] = []
        if provider:
            sql += " AND provider = ?"
            params.append(_safe_provider(provider))
        if ticker:
            sql += " AND ticker = ?"
            params.append(_safe_ticker(ticker))
        sql += " ORDER BY as_of_date DESC, captured_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        for row in rows:
            row["warnings"] = _json_loads(row.pop("warnings_json", None), [])
        return {"ok": True, "count": len(rows), "flows": rows}

    def dashboard(self, top_n: int = 20) -> dict[str, Any]:
        top_n = max(5, min(int(top_n or 20), 50))
        with self._connect() as conn:
            universe_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_universe WHERE active = 1 ORDER BY provider, ticker"
            ).fetchall()]
            observation_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_observations ORDER BY provider, ticker, as_of_date DESC, captured_at DESC"
            ).fetchall()]
            flow_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM etf_daily_flows ORDER BY provider, ticker, as_of_date DESC, captured_at DESC"
            ).fetchall()]
            last_run = conn.execute(
                "SELECT * FROM etf_source_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()

        latest_observation_by_fund: dict[tuple[str, str], dict[str, Any]] = {}
        for row in observation_rows:
            key = (_safe_provider(row.get("provider")), _safe_ticker(row.get("ticker")))
            if key not in latest_observation_by_fund:
                item = dict(row)
                item["raw_payload"] = _json_loads(item.pop("raw_payload_json", None), {})
                item["warnings"] = _json_loads(item.pop("warnings_json", None), [])
                latest_observation_by_fund[key] = item

        latest_flow_by_fund: dict[tuple[str, str], dict[str, Any]] = {}
        for row in flow_rows:
            key = (_safe_provider(row.get("provider")), _safe_ticker(row.get("ticker")))
            if key not in latest_flow_by_fund:
                item = dict(row)
                item["warnings"] = _json_loads(item.pop("warnings_json", None), [])
                latest_flow_by_fund[key] = item

        funds: list[dict[str, Any]] = []
        for row in universe_rows:
            key = (_safe_provider(row.get("provider")), _safe_ticker(row.get("ticker")))
            metadata = _json_loads(row.get("metadata_json"), {})
            observation = latest_observation_by_fund.get(key)
            flow = latest_flow_by_fund.get(key)
            name = str(row.get("name") or key[1] or "").strip()
            aum_usd = _coalesce(
                _finite_float(observation.get("total_net_assets")) if observation else None,
                _meta_float(metadata, "catalog_total_net_assets_usd"),
            )
            expense_ratio = _meta_float(metadata, "catalog_net_expense_ratio", "catalog_gross_expense_ratio")
            segment = _classify_segment(name, metadata)
            country_focus = _classify_country_focus(name, metadata)
            development = _classify_development(name, metadata)
            type_label = _classify_type(name, metadata, segment, country_focus)
            funds.append({
                "provider": key[0],
                "issuer": _provider_label(key[0]),
                "ticker": key[1],
                "name": name,
                "url": row.get("url"),
                "aum_usd": aum_usd,
                "expense_ratio": expense_ratio,
                "observation_date": observation.get("as_of_date") if observation else None,
                "captured_at": observation.get("captured_at") if observation else None,
                "flow_as_of_date": flow.get("as_of_date") if flow else None,
                "flow_usd": _finite_float(flow.get("flow_usd")) if flow else None,
                "share_delta": _finite_float(flow.get("share_delta")) if flow else None,
                "confidence": _coalesce(_finite_float(flow.get("confidence")) if flow else None, _finite_float(observation.get("confidence")) if observation else None),
                "segment": segment,
                "country_focus": country_focus,
                "development": development,
                "type_label": type_label,
                "aum_bucket": _classify_aum_bucket(aum_usd),
                "nav_only": bool(observation and observation.get("nav") is not None and observation.get("shares_outstanding") is None),
                "flow_ready": bool(observation and observation.get("nav") is not None and observation.get("shares_outstanding") is not None),
                "has_flow": bool(flow),
            })

        def aggregate(rows: list[dict[str, Any]], field: str, include_diversified: bool = True) -> list[dict[str, Any]]:
            grouped: dict[str, dict[str, Any]] = {}
            for item in rows:
                key = str(item.get(field) or "Sem classificacao")
                if not include_diversified and key in {"Diversificado", "Outros", "Global", "International"}:
                    continue
                bucket = grouped.setdefault(key, {
                    "key": key,
                    "label": key,
                    "funds": 0,
                    "flow_funds": 0,
                    "nav_only_funds": 0,
                    "net_flow_usd": 0.0,
                    "inflow_usd": 0.0,
                    "outflow_usd": 0.0,
                    "total_aum_usd": 0.0,
                    "expense_ratio_sum": 0.0,
                    "expense_ratio_count": 0,
                })
                bucket["funds"] += 1
                if item.get("has_flow"):
                    bucket["flow_funds"] += 1
                    flow_usd = float(item.get("flow_usd") or 0.0)
                    bucket["net_flow_usd"] += flow_usd
                    if flow_usd >= 0:
                        bucket["inflow_usd"] += flow_usd
                    else:
                        bucket["outflow_usd"] += flow_usd
                if item.get("nav_only"):
                    bucket["nav_only_funds"] += 1
                if item.get("aum_usd") is not None:
                    bucket["total_aum_usd"] += float(item["aum_usd"])
                if item.get("expense_ratio") is not None:
                    bucket["expense_ratio_sum"] += float(item["expense_ratio"])
                    bucket["expense_ratio_count"] += 1
            rows_out = []
            for bucket in grouped.values():
                bucket["avg_expense_ratio"] = (
                    bucket["expense_ratio_sum"] / bucket["expense_ratio_count"]
                    if bucket["expense_ratio_count"]
                    else None
                )
                bucket.pop("expense_ratio_sum", None)
                bucket.pop("expense_ratio_count", None)
                rows_out.append(bucket)
            rows_out.sort(key=lambda item: (abs(float(item.get("net_flow_usd") or 0.0)), float(item.get("total_aum_usd") or 0.0)), reverse=True)
            return rows_out

        funds_with_flow = [item for item in funds if item.get("has_flow")]
        funds_with_observation = [item for item in funds if item.get("captured_at")]
        flow_ready_funds = [item for item in funds if item.get("flow_ready")]
        nav_only_funds = [item for item in funds if item.get("nav_only")]
        inflow_total = sum(float(item.get("flow_usd") or 0.0) for item in funds_with_flow if float(item.get("flow_usd") or 0.0) > 0)
        outflow_total = sum(float(item.get("flow_usd") or 0.0) for item in funds_with_flow if float(item.get("flow_usd") or 0.0) < 0)
        total_aum = sum(float(item.get("aum_usd") or 0.0) for item in funds if item.get("aum_usd") is not None)
        latest_capture_at = max((str(item.get("captured_at")) for item in funds_with_observation if item.get("captured_at")), default=None)
        latest_flow_date = max((str(item.get("flow_as_of_date")) for item in funds_with_flow if item.get("flow_as_of_date")), default=None)

        by_issuer = aggregate(funds, "issuer")
        by_country = aggregate(funds_with_flow, "country_focus", include_diversified=False)
        by_development = aggregate(funds, "development")
        by_segment = aggregate(funds, "segment")
        by_type = aggregate(funds, "type_label")
        by_aum_bucket = aggregate(funds, "aum_bucket")

        top_inflows = sorted(
            [item for item in funds_with_flow if float(item.get("flow_usd") or 0.0) > 0],
            key=lambda item: float(item.get("flow_usd") or 0.0),
            reverse=True,
        )[:top_n]
        top_outflows = sorted(
            [item for item in funds_with_flow if float(item.get("flow_usd") or 0.0) < 0],
            key=lambda item: float(item.get("flow_usd") or 0.0),
        )[:top_n]

        heatmap_x = [row["label"] for row in sorted(by_segment, key=lambda item: float(item.get("total_aum_usd") or 0.0), reverse=True)[:8]]
        heatmap_y = [row["label"] for row in sorted(by_issuer, key=lambda item: float(item.get("total_aum_usd") or 0.0), reverse=True)]
        heatmap_matrix: list[list[float]] = []
        heatmap_cells: list[dict[str, Any]] = []
        for issuer in heatmap_y:
            row_values: list[float] = []
            for segment in heatmap_x:
                value = sum(
                    float(item.get("flow_usd") or 0.0)
                    for item in funds_with_flow
                    if item.get("issuer") == issuer and item.get("segment") == segment
                )
                row_values.append(value)
                heatmap_cells.append({
                    "issuer": issuer,
                    "segment": segment,
                    "value": value,
                })
            heatmap_matrix.append(row_values)

        flow_dates = sorted({str(row.get("as_of_date")) for row in flow_rows if row.get("as_of_date")})[-10:]
        trend_series = []
        for issuer in heatmap_y:
            points = []
            for flow_date in flow_dates:
                value = sum(
                    float(row.get("flow_usd") or 0.0)
                    for row in flow_rows
                    if _provider_label(str(row.get("provider") or "")) == issuer and str(row.get("as_of_date") or "") == flow_date
                )
                points.append({"date": flow_date, "value": value})
            trend_series.append({"issuer": issuer, "points": points})

        cards = [
            {"key": "active", "label": "Universo ativo", "value": len(funds), "detail": f"{len(funds_with_observation)} capturados"},
            {"key": "flow_ready", "label": "Flow-ready", "value": len(flow_ready_funds), "detail": f"{len(nav_only_funds)} nav-only"},
            {"key": "computed", "label": "Flows calculados", "value": len(funds_with_flow), "detail": latest_flow_date or "sem data"},
            {"key": "net", "label": "Net flow", "value": inflow_total + outflow_total, "detail": "latest por ETF"},
            {"key": "inflow", "label": "Entradas", "value": inflow_total, "detail": "soma positiva"},
            {"key": "outflow", "label": "Saidas", "value": outflow_total, "detail": "soma negativa"},
            {"key": "aum", "label": "AUM coberto", "value": total_aum, "detail": "US$ agregado"},
        ]

        return {
            "ok": True,
            "latest_capture_at": latest_capture_at,
            "latest_flow_date": latest_flow_date,
            "last_run": dict(last_run) if last_run else None,
            "cards": cards,
            "summary": {
                "active_funds": len(funds),
                "captured_funds": len(funds_with_observation),
                "flow_ready_funds": len(flow_ready_funds),
                "nav_only_funds": len(nav_only_funds),
                "flow_funds": len(funds_with_flow),
                "net_flow_usd": inflow_total + outflow_total,
                "inflow_usd": inflow_total,
                "outflow_usd": outflow_total,
                "total_aum_usd": total_aum,
            },
            "tables": {
                "by_issuer": by_issuer,
                "by_country": by_country[:top_n],
                "by_development": by_development,
                "by_segment": by_segment,
                "by_type": by_type,
                "by_aum_bucket": by_aum_bucket,
            },
            "top_inflows": top_inflows,
            "top_outflows": top_outflows,
            "heatmap": {
                "x": heatmap_x,
                "y": heatmap_y,
                "z": heatmap_matrix,
                "cells": heatmap_cells,
            },
            "trend": {
                "dates": flow_dates,
                "series": trend_series,
            },
        }

    def due_slot(self, now: datetime | None = None) -> str | None:
        now_local = (now or datetime.now(self.tz)).astimezone(self.tz)
        capture_times = self._capture_times()
        if not capture_times:
            return None
        candidates: list[datetime] = []
        for day_offset in (0, -1):
            base_date = now_local.date() + timedelta(days=day_offset)
            for capture_time in capture_times:
                candidates.append(datetime.combine(base_date, capture_time, tzinfo=self.tz))
        due = [candidate for candidate in candidates if candidate <= now_local]
        if not due:
            return None
        latest_due = max(due)
        slot = latest_due.strftime("%Y-%m-%dT%H:%M%z")
        with self._connect() as conn:
            last_slot = self._get_state(conn, "last_scheduler_slot")
        return None if last_slot == slot else slot

    def mark_slot_started(self, slot: str) -> None:
        with self._connect() as conn:
            self._set_state(conn, "last_scheduler_slot", slot)

    def next_run_at(self, now: datetime | None = None) -> str | None:
        now_local = (now or datetime.now(self.tz)).astimezone(self.tz)
        capture_times = self._capture_times()
        if not capture_times:
            return None
        candidates: list[datetime] = []
        for day_offset in (0, 1):
            base_date = now_local.date() + timedelta(days=day_offset)
            for capture_time in capture_times:
                candidate = datetime.combine(base_date, capture_time, tzinfo=self.tz)
                if candidate > now_local:
                    candidates.append(candidate)
        if not candidates:
            return None
        return min(candidates).isoformat()

    def _capture_times(self) -> list[dt_time]:
        output: list[dt_time] = []
        for item in str(Config.ETF_DAILY_FLOW_CAPTURE_TIMES or "").split(","):
            text = item.strip()
            if not text:
                continue
            try:
                hour, minute = text.split(":", 1)
                output.append(dt_time(hour=int(hour), minute=int(minute[:2])))
            except Exception:
                continue
        return sorted(output)


class EtfDailyFlowManager:
    def __init__(self, service: EtfDailyFlowService):
        self.service = service
        self.poll_interval_seconds = float(Config.ETF_DAILY_FLOW_SCHEDULER_POLL_SECONDS)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = threading.Event()
        self._last_error: str | None = None
        self._last_tick_at: str | None = None

    def start(self) -> dict[str, Any]:
        if self._thread and self._thread.is_alive():
            return {"ok": True, "running": True, "message": "already_running"}
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="etf-daily-flow-manager", daemon=True)
        self._thread.start()
        return {"ok": True, "running": True}

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        return {"ok": True, "running": self.running}

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "busy": self._running.is_set(),
            "poll_interval_seconds": self.poll_interval_seconds,
            "next_run_at": self.service.next_run_at(),
            "last_tick_at": self._last_tick_at,
            "last_error": self._last_error,
        }

    def _loop(self) -> None:
        logger.info("ETF daily flow scheduler started")
        while not self._stop.is_set():
            self._last_tick_at = _utc_now_iso()
            try:
                slot = self.service.due_slot()
                if slot and not self._running.is_set():
                    self._running.set()
                    self.service.mark_slot_started(slot)
                    try:
                        logger.info("ETF daily flow scheduled collection due: slot=%s", slot)
                        self.service.collect()
                    finally:
                        self._running.clear()
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("ETF daily flow scheduler failed")
            self._stop.wait(self.poll_interval_seconds)
        logger.info("ETF daily flow scheduler stopped")
