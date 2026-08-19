from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from ..config import Config
from ..utils.logger import get_logger
from .options_contract_service import OptionsContractService
from .options_data_provider import get_options_data_provider
from .options_store import OptionsStore
from .options_universe_service import OptionsUniverseService

if TYPE_CHECKING:
    # Importado apenas para IDEs/type checkers — nao afeta execucao
    pass


logger = get_logger("aquiles.options_snapshot")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


class OptionsSnapshotService:
    UNIVERSE_VERSION = "options-universe-v1"
    SNAPSHOT_VERSION = "options-snapshot-v1"
    REF_DATA_CHUNK_SIZE = 100

    def __init__(
        self,
        store: OptionsStore | None = None,
        bloomberg: Any | None = None,
        contract_service: OptionsContractService | None = None,
        universe_service: OptionsUniverseService | None = None,
    ):
        self.store = store or OptionsStore()
        self.bloomberg = bloomberg or get_options_data_provider()
        self.contract_service = contract_service or OptionsContractService(store=self.store, bloomberg=self.bloomberg)
        self.universe_service = universe_service or OptionsUniverseService()

    def discover_underlying(self, underlying_security: str) -> dict[str, Any]:
        return self.contract_service.discover_underlying_contracts(underlying_security)

    def prepare_universe(self, underlying_security: str) -> dict[str, Any]:
        discovery = self.contract_service.discover_underlying_contracts(underlying_security)
        active_contracts = [
            row for row in discovery.get("contracts", [])
            if row.get("status") == "active" and row.get("mvp_eligible")
        ]
        preview = self._fetch_reference_rows(
            [row.get("bloomberg_ticker") for row in active_contracts],
            self.bloomberg.DISCOVERY_FIELDS,
        )

        structural_rows = self.universe_service.build_structural_universe(active_contracts, preview["rows"])
        liquid_rows = self.universe_service.build_liquid_universe(structural_rows)
        critical_rows = self.universe_service.build_critical_universe(liquid_rows)

        captured_at = _utc_now().isoformat()
        session_date = datetime.now(LOCAL_TZ).date().isoformat()
        payload = {
            "underlying_security": underlying_security,
            "underlying_trade_symbol": Config.OPTIONS_UNDERLYING_TRADE_MAP.get(underlying_security),
            "captured_at": captured_at,
            "session_date": session_date,
            "universe_version": self.UNIVERSE_VERSION,
            "summary": self.universe_service.summarize_universe(
                underlying_security,
                active_contracts,
                structural_rows,
                liquid_rows,
                critical_rows,
            ),
            "full": active_contracts,
            "structural": structural_rows,
            "liquid": liquid_rows,
            "critical": critical_rows,
            "discovery": {
                "chain_count": discovery.get("chain_count"),
                "valid_contract_count": discovery.get("valid_contract_count"),
                "invalid_contract_count": discovery.get("invalid_contract_count"),
            },
            "preview_status": preview.get("status", {}),
        }
        self.store.save_universe_state(underlying_security, payload)
        return payload

    def collect_full_snapshot(self, underlying_security: str) -> dict[str, Any]:
        universe_payload = self.prepare_universe(underlying_security)
        return self._capture_universe_batch(
            underlying_security=underlying_security,
            universe_tier="full",
            selected_rows=universe_payload.get("full", []),
            interval_seconds=Config.OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS,
        )

    def collect_structural_snapshot(self, underlying_security: str) -> dict[str, Any]:
        universe_payload = self.prepare_universe(underlying_security)
        structural_rows = [row for row in universe_payload.get("structural", []) if row.get("structural_eligible")]
        return self._capture_universe_batch(
            underlying_security=underlying_security,
            universe_tier="structural",
            selected_rows=structural_rows,
            interval_seconds=Config.OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS,
        )

    def collect_liquid_snapshot(self, underlying_security: str) -> dict[str, Any]:
        universe_payload = self.prepare_universe(underlying_security)
        return self._capture_universe_batch(
            underlying_security=underlying_security,
            universe_tier="liquid",
            selected_rows=universe_payload.get("liquid", []),
            interval_seconds=Config.OPTIONS_LIQUID_SNAPSHOT_INTERVAL_SECONDS,
        )

    def collect_critical_snapshot(self, underlying_security: str) -> dict[str, Any]:
        universe_payload = self.prepare_universe(underlying_security)
        return self._capture_universe_batch(
            underlying_security=underlying_security,
            universe_tier="critical",
            selected_rows=universe_payload.get("critical", []),
            interval_seconds=Config.OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS,
        )

    def collect_underlying_snapshot(
        self,
        underlying_security: str,
        include_structural: bool = True,
        include_liquid: bool = True,
        include_critical: bool = True,
        include_ticks: bool | None = None,
    ) -> dict[str, Any]:
        universe_payload = self.prepare_universe(underlying_security)
        result = {
            "underlying_security": underlying_security,
            "captured_at": _utc_now().isoformat(),
            "universe": {
                "summary": universe_payload.get("summary", {}),
                "captured_at": universe_payload.get("captured_at"),
                "session_date": universe_payload.get("session_date"),
            },
            "snapshots": {},
            "ticks": {},
        }

        if include_structural:
            structural_rows = [row for row in universe_payload.get("structural", []) if row.get("structural_eligible")]
            result["snapshots"]["structural"] = self._capture_universe_batch(
                underlying_security=underlying_security,
                universe_tier="structural",
                selected_rows=structural_rows,
                interval_seconds=Config.OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS,
            )
        if include_liquid:
            result["snapshots"]["liquid"] = self._capture_universe_batch(
                underlying_security=underlying_security,
                universe_tier="liquid",
                selected_rows=universe_payload.get("liquid", []),
                interval_seconds=Config.OPTIONS_LIQUID_SNAPSHOT_INTERVAL_SECONDS,
            )
        if include_critical:
            critical_rows = universe_payload.get("critical", [])
            result["snapshots"]["critical"] = self._capture_universe_batch(
                underlying_security=underlying_security,
                universe_tier="critical",
                selected_rows=critical_rows,
                interval_seconds=Config.OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS,
            )
            if include_ticks if include_ticks is not None else Config.OPTIONS_TICK_CAPTURE_ENABLE:
                result["ticks"]["critical"] = self.capture_recent_ticks(underlying_security, critical_rows)

        return result

    def capture_recent_ticks(self, underlying_security: str, critical_rows: list[dict[str, Any]]) -> dict[str, Any]:
        end_dt = _utc_now()
        start_dt = end_dt - timedelta(seconds=Config.OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS)
        rows_written = 0
        per_contract: list[dict[str, Any]] = []
        for row in critical_rows[: Config.OPTIONS_TICK_CAPTURE_MAX_CONTRACTS]:
            security = row.get("bloomberg_ticker")
            option_id = row.get("option_id")
            if not security or not option_id:
                continue
            tick_result = self.bloomberg.fetch_option_ticks(security, start_dt, end_dt)
            tick_rows = []
            for item in tick_result.get("rows", []):
                tick_rows.append({
                    "option_id": option_id,
                    "security": security,
                    "event_time": item.get("event_time"),
                    "event_type": item.get("event_type"),
                    "price": item.get("price"),
                    "size": item.get("size"),
                    "condition_code": item.get("condition_code"),
                    "captured_at": end_dt.isoformat(),
                })
            write_result = self.store.write_tick_rows(option_id, end_dt.date().isoformat(), tick_rows)
            rows_written += int(write_result.get("rows_written", 0))
            per_contract.append({
                "option_id": option_id,
                "security": security,
                "captured_count": len(tick_rows),
            })
        return {
            "underlying_security": underlying_security,
            "captured_at": end_dt.isoformat(),
            "rows_written": rows_written,
            "contracts": per_contract,
        }

    def _fetch_reference_rows(self, securities: list[str], fields: list[str]) -> dict[str, Any]:
        all_rows: list[dict[str, Any]] = []
        statuses: list[dict[str, Any]] = []
        clean_securities = [security for security in securities if security]
        for index in range(0, len(clean_securities), self.REF_DATA_CHUNK_SIZE):
            chunk = clean_securities[index:index + self.REF_DATA_CHUNK_SIZE]
            if not chunk:
                continue
            result = self.bloomberg.fetch_option_snapshots(chunk, fields)
            all_rows.extend(result.get("rows", []))
            statuses.append(result.get("status", {}))
        return {
            "rows": all_rows,
            "status": statuses[-1] if statuses else {},
            "chunks": len(statuses),
        }

    def _capture_universe_batch(
        self,
        underlying_security: str,
        universe_tier: str,
        selected_rows: list[dict[str, Any]],
        interval_seconds: int,
    ) -> dict[str, Any]:
        captured_at = _utc_now()
        session_date = datetime.now(LOCAL_TZ).date().isoformat()
        batch_key = self._build_batch_key(underlying_security, universe_tier, captured_at, interval_seconds)
        batch_id = hashlib.sha1(f"{underlying_security}|{universe_tier}|{batch_key}".encode("utf-8")).hexdigest()
        securities = [row.get("bloomberg_ticker") for row in selected_rows if row.get("bloomberg_ticker")]
        contract_map = {str(row.get("bloomberg_ticker")): row for row in selected_rows if row.get("bloomberg_ticker")}

        response = self._fetch_reference_rows(securities, self.bloomberg.SNAPSHOT_FIELDS)
        quality_flags: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []
        for raw_row in response.get("rows", []):
            security = str(raw_row.get("security") or "")
            contract = contract_map.get(security)
            if not contract:
                continue
            enriched = self.enrich_snapshot_row(raw_row, contract, batch_id=batch_id, batch_key=batch_key, universe_tier=universe_tier, captured_at=captured_at)
            snapshot_rows.append(enriched)
            quality_flags.extend(self._build_quality_flags(enriched))

        batch_info = self.store.write_snapshot_batch(
            universe_tier=universe_tier,
            session_date=session_date,
            batch_key=batch_key,
            rows=snapshot_rows,
            metadata={
                "batch_id": batch_id,
                "captured_at": captured_at.isoformat(),
                "underlying_security": underlying_security,
                "underlying_trade_symbol": Config.OPTIONS_UNDERLYING_TRADE_MAP.get(underlying_security),
            },
        )
        self.store.append_quality_flags(quality_flags)
        return {
            "batch": batch_info,
            "row_count": len(snapshot_rows),
            "quality_flag_count": len(quality_flags),
        }

    def enrich_snapshot_row(
        self,
        row: dict[str, Any],
        contract: dict[str, Any],
        batch_id: str,
        batch_key: str,
        universe_tier: str,
        captured_at: datetime,
    ) -> dict[str, Any]:
        fields = row.get("fields") or {}
        bid = _safe_float(fields.get("BID"))
        ask = _safe_float(fields.get("ASK"))
        px_last = _safe_float(fields.get("PX_LAST"))
        underlying_px = _safe_float(fields.get("OPT_UNDL_PX"))
        strike = _safe_float(fields.get("OPT_STRIKE_PX")) or _safe_float(contract.get("strike"))
        mid = None
        if bid is not None and ask is not None and ask >= bid:
            mid = (bid + ask) / 2.0
        spread_abs = (ask - bid) if bid is not None and ask is not None and ask >= bid else None
        spread_pct = None
        if spread_abs is not None and mid and mid > 0:
            spread_pct = spread_abs / mid
        moneyness_spot = None
        distance_to_atm = None
        if underlying_px and underlying_px > 0 and strike is not None:
            moneyness_spot = (strike / underlying_px) - 1.0
            distance_to_atm = abs(moneyness_spot)

        open_int = _safe_float(fields.get("OPT_OPEN_INTEREST"))
        if open_int is None:
            open_int = _safe_float(fields.get("OPEN_INT"))
        px_volume = _safe_float(fields.get("PX_VOLUME"))
        if px_volume is None:
            px_volume = _safe_float(fields.get("VOLUME"))

        liquidity_score = self._initial_liquidity_score(
            open_int=open_int,
            px_volume=px_volume,
            spread_pct=spread_pct,
            distance_to_atm=distance_to_atm,
        )
        stale_flag = px_last is None and bid is None and ask is None
        snapshot_id = hashlib.sha1(
            f"{contract.get('option_id')}|{batch_id}|{universe_tier}".encode("utf-8")
        ).hexdigest()

        return {
            "snapshot_id": snapshot_id,
            "batch_id": batch_id,
            "batch_key": batch_key,
            "capture_version": self.SNAPSHOT_VERSION,
            "captured_at": captured_at.isoformat(),
            "source_timestamp": None,
            "universe_tier": universe_tier,
            "option_id": contract.get("option_id"),
            "bloomberg_ticker": contract.get("bloomberg_ticker"),
            "root_symbol": contract.get("root_symbol"),
            "underlying_security": contract.get("underlying_security"),
            "underlying_trade_symbol": contract.get("underlying_trade_symbol"),
            "put_call": contract.get("put_call"),
            "strike": strike,
            "expiry_date": contract.get("expiry_date"),
            "days_to_expiry_calendar": contract.get("days_to_expiry_calendar"),
            "days_to_expiry_business": contract.get("days_to_expiry_business"),
            "contract_status": contract.get("status"),
            "PX_LAST": px_last,
            "BID": bid,
            "ASK": ask,
            "MID": mid,
            "bid_ask_mid": mid,
            "spread_abs": spread_abs,
            "spread_pct": spread_pct,
            "bid_ask_spread": spread_abs,
            "bid_ask_spread_pct": spread_pct,
            "PX_VOLUME": _safe_float(fields.get("PX_VOLUME")),
            "VOLUME": _safe_float(fields.get("VOLUME")),
            "OPEN_INT": _safe_float(fields.get("OPEN_INT")),
            "OPT_OPEN_INTEREST": _safe_float(fields.get("OPT_OPEN_INTEREST")),
            "IVOL_BID": _safe_float(fields.get("IVOL_BID")),
            "IVOL_ASK": _safe_float(fields.get("IVOL_ASK")),
            "IVOL_MID": _safe_float(fields.get("IVOL_MID")),
            "IVOL_LAST": _safe_float(fields.get("IVOL_LAST")),
            "OPT_DELTA": _safe_float(fields.get("OPT_DELTA")),
            "OPT_GAMMA": _safe_float(fields.get("OPT_GAMMA")),
            "OPT_VEGA": _safe_float(fields.get("OPT_VEGA")),
            "OPT_THETA": _safe_float(fields.get("OPT_THETA")),
            "OPT_DELTA_BID": _safe_float(fields.get("OPT_DELTA_BID")),
            "OPT_DELTA_ASK": _safe_float(fields.get("OPT_DELTA_ASK")),
            "OPT_DELTA_MID": _safe_float(fields.get("OPT_DELTA_MID")),
            "OPT_DELTA_LAST": _safe_float(fields.get("OPT_DELTA_LAST")),
            "OPT_GAMMA_BID": _safe_float(fields.get("OPT_GAMMA_BID")),
            "OPT_GAMMA_ASK": _safe_float(fields.get("OPT_GAMMA_ASK")),
            "OPT_GAMMA_MID": _safe_float(fields.get("OPT_GAMMA_MID")),
            "OPT_GAMMA_LAST": _safe_float(fields.get("OPT_GAMMA_LAST")),
            "OPT_VEGA_BID": _safe_float(fields.get("OPT_VEGA_BID")),
            "OPT_VEGA_ASK": _safe_float(fields.get("OPT_VEGA_ASK")),
            "OPT_VEGA_MID": _safe_float(fields.get("OPT_VEGA_MID")),
            "OPT_VEGA_LAST": _safe_float(fields.get("OPT_VEGA_LAST")),
            "OPT_THETA_BID": _safe_float(fields.get("OPT_THETA_BID")),
            "OPT_THETA_ASK": _safe_float(fields.get("OPT_THETA_ASK")),
            "OPT_THETA_MID": _safe_float(fields.get("OPT_THETA_MID")),
            "OPT_THETA_LAST": _safe_float(fields.get("OPT_THETA_LAST")),
            "OPT_UNDL_PX": underlying_px,
            "OPT_STRIKE_PX": strike,
            "OPT_EXPIRE_DT": fields.get("OPT_EXPIRE_DT") or contract.get("expiry_date"),
            "OPT_PUT_CALL": fields.get("OPT_PUT_CALL") or contract.get("put_call"),
            "moneyness_spot": moneyness_spot,
            "moneyness_forward_placeholder": moneyness_spot,
            "distance_to_atm": distance_to_atm,
            "liquidity_score_initial": liquidity_score,
            "stale_flag_initial": stale_flag,
            "liquidity_score": liquidity_score,
            "stale_flag": stale_flag,
            "market_ok": bool(row.get("ok")),
            "field_exceptions": row.get("field_exceptions") or [],
            "security_error": row.get("security_error"),
            "relevance_score": contract.get("relevance_score"),
            "relevance_components": contract.get("relevance_components"),
            # ── Modelo proprietário de Greeks ──────────────────────────────
            "MODEL_IV":           _safe_float(fields.get("MODEL_IV")),
            "MODEL_DELTA":        _safe_float(fields.get("MODEL_DELTA")),
            "MODEL_GAMMA_POINT":  _safe_float(fields.get("MODEL_GAMMA_POINT")),
            "MODEL_GAMMA_1PCT":   _safe_float(fields.get("MODEL_GAMMA_1PCT")),
            "MODEL_VEGA_1PCTVOL": _safe_float(fields.get("MODEL_VEGA_1PCTVOL")),
            "MODEL_THETA_BD252":  _safe_float(fields.get("MODEL_THETA_BD252")),
            "MODEL_VANNA":        _safe_float(fields.get("MODEL_VANNA")),
            "MODEL_CHARM_BD252":  _safe_float(fields.get("MODEL_CHARM_BD252")),
            "MODEL_SOURCE":       fields.get("MODEL_SOURCE"),
            # ── Greeks efetivos (prioridade: proprietário > OpLab > None) ─
            "EFF_DELTA":          _safe_float(fields.get("EFF_DELTA")),
            "EFF_GAMMA_PT":       _safe_float(fields.get("EFF_GAMMA_PT")),
            "EFF_GAMMA_1PCT":     _safe_float(fields.get("EFF_GAMMA_1PCT")),
            "EFF_IV":             _safe_float(fields.get("EFF_IV")),
            "EFF_VEGA":           _safe_float(fields.get("EFF_VEGA")),
            "EFF_THETA":          _safe_float(fields.get("EFF_THETA")),
            "EFF_VANNA":          _safe_float(fields.get("EFF_VANNA")),
            "EFF_CHARM":          _safe_float(fields.get("EFF_CHARM")),
        }

    def _build_quality_flags(self, snapshot_row: dict[str, Any]) -> list[dict[str, Any]]:
        flags: list[dict[str, Any]] = []
        option_id = snapshot_row.get("option_id")
        snapshot_id = snapshot_row.get("snapshot_id")
        trade_date = str(snapshot_row.get("captured_at") or "")[:10]

        def add_flag(flag_type: str, severity: str, message: str) -> None:
            flags.append({
                "flag_id": hashlib.sha1(f"{snapshot_id}|{flag_type}|{message}".encode("utf-8")).hexdigest(),
                "option_id": option_id,
                "snapshot_id": snapshot_id,
                "trade_date": trade_date,
                "flag_type": flag_type,
                "severity": severity,
                "message": message,
                "created_at": _utc_now().isoformat(),
            })

        if not snapshot_row.get("strike"):
            add_flag("missing_strike", "high", "Contract snapshot missing strike.")
        if not snapshot_row.get("expiry_date"):
            add_flag("missing_expiry", "high", "Contract snapshot missing expiry date.")
        if snapshot_row.get("OPT_PUT_CALL") not in {"Call", "Put"} and snapshot_row.get("put_call") not in {"Call", "Put"}:
            add_flag("missing_put_call", "high", "Contract snapshot missing put/call side.")
        bid = snapshot_row.get("BID")
        ask = snapshot_row.get("ASK")
        if bid is not None and ask is not None and ask < bid:
            add_flag("invalid_bid_ask", "medium", "Ask price is below bid price.")
        if snapshot_row.get("stale_flag"):
            add_flag("stale_quote", "low", "Snapshot has no last/bid/ask values.")
        if not snapshot_row.get("market_ok"):
            add_flag("partial_capture_failure", "medium", "Bloomberg returned a partial or failed quote for this option.")
        return flags

    def _initial_liquidity_score(
        self,
        open_int: float | None,
        px_volume: float | None,
        spread_pct: float | None,
        distance_to_atm: float | None,
    ) -> float:
        oi_component = min((open_int or 0.0) / 1_000_000.0, 1.0)
        volume_component = min((px_volume or 0.0) / 100_000.0, 1.0)
        spread_component = 0.0
        if spread_pct is not None:
            spread_component = max(0.0, 1.0 - min(spread_pct / 0.10, 1.0))
        atm_component = 0.0
        if distance_to_atm is not None:
            atm_component = max(0.0, 1.0 - min(distance_to_atm / max(Config.OPTIONS_MONEYNESS_BAND_PCT, 1e-6), 1.0))
        return round((0.35 * oi_component + 0.25 * volume_component + 0.20 * spread_component + 0.20 * atm_component) * 100, 4)

    def _build_batch_key(
        self,
        underlying_security: str,
        universe_tier: str,
        captured_at: datetime,
        interval_seconds: int,
    ) -> str:
        interval_seconds = max(1, int(interval_seconds))
        bucket_epoch = int(captured_at.timestamp()) // interval_seconds
        bucket_start = datetime.fromtimestamp(bucket_epoch * interval_seconds, tz=timezone.utc)
        slug = underlying_security.replace(" ", "_").replace("/", "_")
        return f"{slug}_{universe_tier}_{bucket_start.strftime('%Y%m%dT%H%M%SZ')}"
