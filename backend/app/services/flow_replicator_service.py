from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from typing import Any

from ..utils.logger import get_logger
from .flow_replicator_store import FlowReplicatorStore

logger = get_logger("aquiles.flow_replicator")

MONTH_CODES = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}


class WinContractResolver:
    def __init__(self) -> None:
        self.override = str(os.environ.get("FLOW_REPLICATOR_TICKER") or "").strip()
        self.roll_days_before_expiry = max(
            int(os.environ.get("FLOW_REPLICATOR_ROLL_DAYS_BEFORE_EXPIRY", "0") or 0),
            0,
        )
        self.roll_hour_utc = min(
            max(int(os.environ.get("FLOW_REPLICATOR_ROLL_HOUR_UTC", "21") or 21), 0),
            23,
        )

    def current_ticker(self, now: datetime | None = None) -> str:
        return self.candidate_tickers(now=now, count=1)[0]

    def candidate_tickers(self, now: datetime | None = None, count: int = 4) -> list[str]:
        if self.override:
            return [self.override]

        current = now or datetime.now(timezone.utc)
        year = current.year
        month = current.month
        if self._should_roll_contract(current, year, month):
            year, month = self._next_month(year, month)

        tickers = []
        for offset in range(max(int(count or 4), 1)):
            ticker_year, ticker_month = self._add_months(year, month, offset)
            tickers.append(self._ticker_for(ticker_year, ticker_month))
        return tickers

    def describe(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        candidates = self.candidate_tickers(now=current, count=6)
        month = current.month
        year = current.year
        expiry = self._expiration_date(year, month)
        return {
            "override": self.override or None,
            "current": candidates[0],
            "candidates": candidates,
            "base_expiration_date": expiry.isoformat(),
            "roll_days_before_expiry": self.roll_days_before_expiry,
            "roll_hour_utc": self.roll_hour_utc,
        }

    def _should_roll_contract(self, current: datetime, year: int, month: int) -> bool:
        expiry = self._expiration_date(year, month)
        roll_date = expiry - timedelta(days=self.roll_days_before_expiry)
        roll_at = datetime.combine(
            roll_date,
            datetime_time(hour=self.roll_hour_utc),
            tzinfo=timezone.utc,
        )
        return current >= roll_at

    @staticmethod
    def _expiration_date(year: int, month: int) -> date:
        # WIN follows the monthly B3 index-futures code. In practice the
        # expiration is the Wednesday closest to the 15th; holiday adjustment
        # can be layered in later from an official B3 calendar.
        candidates = [date(year, month, day) for day in range(12, 19)]
        wednesdays = [item for item in candidates if item.weekday() == 2]
        if not wednesdays:
            return date(year, month, 15)
        return min(wednesdays, key=lambda item: abs(item.day - 15))

    @staticmethod
    def _next_month(year: int, month: int) -> tuple[int, int]:
        return WinContractResolver._add_months(year, month, 1)

    @staticmethod
    def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
        zero_based = (year * 12) + (month - 1) + offset
        return zero_based // 12, (zero_based % 12) + 1

    @staticmethod
    def _ticker_for(year: int, month: int) -> str:
        month_code = MONTH_CODES.get(month, "M")
        year_code = str(year)[-2:]
        return f"WIN{month_code}{year_code}"


class FlowReplicatorService:
    def __init__(self, store: FlowReplicatorStore | None = None) -> None:
        self.store = store or FlowReplicatorStore()
        self.resolver = WinContractResolver()
        self.ws_url = os.environ.get("FLOW_REPLICATOR_WS_URL", "wss://replicador2.aquantx.com.br/v1/ws")
        self.auth_header = (
            os.environ.get("FLOW_REPLICATOR_WS_AUTH")
            or os.environ.get("AQUANTX_WS_AUTH")
            or ""
        ).strip()
        self.reconnect_delay_seconds = float(os.environ.get("FLOW_REPLICATOR_RECONNECT_DELAY_SECONDS", "2"))
        self.contract_check_seconds = float(os.environ.get("FLOW_REPLICATOR_CONTRACT_CHECK_SECONDS", "60"))
        self.subscription_grace_seconds = float(os.environ.get("FLOW_REPLICATOR_SUBSCRIPTION_GRACE_SECONDS", "20"))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state_lock = threading.RLock()
        self._state: dict[str, Any] = {
            "running": False,
            "connected": False,
            "ticker": None,
            "last_message_at": None,
            "last_persist_at": None,
            "last_error": None,
            "message_count": 0,
            "snapshot_count": 0,
            "delta_count": 0,
            "contract_resolver": self.resolver.describe(),
            "contract_candidates": self.resolver.candidate_tickers(count=6),
            "started_at": None,
            "stopped_at": None,
            "missing_auth": not bool(self.auth_header),
        }

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            state = dict(self._state)
        latest = self.store.latest_snapshot(state.get("ticker"))
        state["latest_snapshot"] = latest
        state["db_path"] = self.store.db_path
        state["contract_resolver"] = self.resolver.describe()
        return state

    def start(self) -> dict[str, Any]:
        if not self.auth_header:
            with self._state_lock:
                self._state["last_error"] = "Missing FLOW_REPLICATOR_WS_AUTH/AQUANTX_WS_AUTH"
                self._state["missing_auth"] = True
            return self.status()
        if self._thread and self._thread.is_alive():
            return self.status()
        self._stop_event.clear()
        with self._state_lock:
            self._state.update({
                "running": True,
                "connected": False,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "stopped_at": None,
                "last_error": None,
                "missing_auth": False,
            })
        self._thread = threading.Thread(target=self._run_thread, name="flow-replicator", daemon=True)
        self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        with self._state_lock:
            self._state["running"] = False
            self._state["stopped_at"] = datetime.now(timezone.utc).isoformat()
        return self.status()

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run_loop())
        except Exception as exc:
            logger.exception("Flow replicator loop crashed")
            with self._state_lock:
                self._state["running"] = False
                self._state["connected"] = False
                self._state["last_error"] = str(exc)

    async def _connect(self, ticker: str) -> Any:
        del ticker
        import websockets

        headers = {"Authorization": self.auth_header}
        try:
            return await websockets.connect(self.ws_url, extra_headers=headers, ping_interval=20, ping_timeout=20)
        except TypeError:
            return await websockets.connect(self.ws_url, additional_headers=headers, ping_interval=20, ping_timeout=20)

    async def _subscribe(self, ws: Any, ticker: str) -> None:
        await ws.send(json.dumps({
            "kind": "market.summary.subscribe",
            "data": {"ticker": ticker},
        }, separators=(",", ":")))

    async def _run_loop(self) -> None:
        last_contract_check = 0.0
        candidate_index = 0
        candidates = self.resolver.candidate_tickers()
        ticker = candidates[candidate_index]
        with self._state_lock:
            self._state["ticker"] = ticker
            self._state["contract_candidates"] = candidates

        while not self._stop_event.is_set():
            now = time.time()
            if now - last_contract_check >= self.contract_check_seconds:
                next_candidates = self.resolver.candidate_tickers()
                next_ticker = next_candidates[0]
                last_contract_check = now
                if next_ticker != ticker or next_candidates != candidates:
                    candidates = next_candidates
                    candidate_index = 0
                    ticker = next_ticker
                    with self._state_lock:
                        self._state["ticker"] = ticker
                        self._state["contract_candidates"] = candidates
                    logger.info("Flow replicator rolled ticker to %s", ticker)

            try:
                async with await self._connect(ticker) as ws:
                    await self._subscribe(ws, ticker)
                    connected_at = time.time()
                    messages_for_connection = 0
                    with self._state_lock:
                        self._state["connected"] = True
                        self._state["ticker"] = ticker
                        self._state["contract_candidates"] = candidates
                        self._state["last_error"] = None
                    logger.info("Flow replicator connected to %s", ticker)

                    while not self._stop_event.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        except asyncio.TimeoutError:
                            next_candidates = self.resolver.candidate_tickers()
                            next_ticker = next_candidates[0]
                            if next_ticker != ticker or next_candidates != candidates:
                                candidates = next_candidates
                                candidate_index = 0
                                ticker = next_ticker
                                break
                            if (
                                messages_for_connection <= 0
                                and len(candidates) > candidate_index + 1
                                and time.time() - connected_at >= self.subscription_grace_seconds
                            ):
                                candidate_index += 1
                                ticker = candidates[candidate_index]
                                logger.warning("No flow messages received; trying fallback ticker %s", ticker)
                                with self._state_lock:
                                    self._state["ticker"] = ticker
                                    self._state["last_error"] = "No messages received before subscription grace period"
                                break
                            continue
                        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                        received_at = datetime.now(timezone.utc).isoformat()
                        persisted = await self._handle_message(ticker=ticker, received_at=received_at, text=text)
                        if persisted:
                            messages_for_connection += 1
            except Exception as exc:
                logger.warning("Flow replicator connection error for %s: %s", ticker, exc)
                with self._state_lock:
                    self._state["connected"] = False
                    self._state["last_error"] = str(exc)
                if len(candidates) > candidate_index + 1:
                    candidate_index += 1
                    ticker = candidates[candidate_index]
                    with self._state_lock:
                        self._state["ticker"] = ticker
                    logger.warning("Trying fallback ticker %s after connection error", ticker)
                await asyncio.sleep(self.reconnect_delay_seconds)
            finally:
                with self._state_lock:
                    self._state["connected"] = False

        with self._state_lock:
            self._state["running"] = False
            self._state["connected"] = False
            self._state["stopped_at"] = datetime.now(timezone.utc).isoformat()

    async def _handle_message(self, *, ticker: str, received_at: str, text: str) -> bool:
        try:
            payload = json.loads(text)
        except Exception:
            with self._state_lock:
                self._state["last_error"] = "Invalid JSON payload"
            return False

        if str(payload.get("kind") or "") != "market.summary.updated":
            return False
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        message_ticker = str(data.get("ticker") or ticker).strip() or ticker
        result = self.store.persist_summary_message(
            ticker=message_ticker,
            contract=message_ticker,
            received_at=received_at,
            payload=payload,
            raw_payload=text,
        )
        with self._state_lock:
            self._state["last_message_at"] = received_at
            self._state["last_persist_at"] = received_at
            self._state["message_count"] = int(self._state.get("message_count") or 0) + 1
            self._state["snapshot_count"] = int(self._state.get("snapshot_count") or 0) + 1
            self._state["delta_count"] = int(self._state.get("delta_count") or 0) + int(result.get("delta_count") or 0)
        return True
