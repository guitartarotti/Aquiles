"""
Macro live feed collection, storage, and project sync helpers.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests
import websockets

from ..config import Config
from ..utils.logger import get_logger
from .bloomberg_desktop_service import BloombergDesktopService
from .macro_live_projection import MacroProjectionService
from .macro_live_rules import (
    CORPORATE_DEAL_TERMS,
    GENERIC_EQUITY_TERMS,
    HARD_MACRO_ANCHOR_TERMS,
    HIGH_CONFIDENCE_MACRO_TERMS,
    HIGH_CONVICTION_CENTRAL_BANK_TERMS,
    IDIOSYNCRATIC_NEWS_TERMS,
    LOW_SIGNAL_MACRO_TERMS,
    MACRO_NEWS_KEYWORDS,
    MACRO_THEME_RULES,
    MARKET_RELEVANCE_TERMS,
    NEWS_RELEVANCE_WEIGHTS,
    REGIME_SHIFT_SCENARIO_TERMS,
    SECONDARY_ECHO_SCENARIO_TERMS,
    SESSION_RISK_THEMES,
    TECHNICAL_BALANCE_SHEET_RULES,
    TECHNICAL_LIQUIDITY_RULES,
    _build_market_groups,
    _keyword_in_text,
    _match_all_keyword_groups,
    _match_any_keyword_rule,
    _resolve_market_bucket,
)
from .macro_live_state_store import MacroStateStore
from .macro_live_utils import (
    EVENT_CLASSIFICATION_VERSION,
    _bucket_start,
    _deep_copy_json,
    _iso_from_timestamp,
    _now_iso,
    _parse_iso_datetime,
    _safe_float,
    _sha1_text,
    _to_price_string,
    _utc_now,
)

logger = get_logger("aquiles.macro_live")

__all__ = [
    "MacroCollectorManager",
    "MacroIngestionService",
    "MacroProjectionService",
    "MacroStateStore",
]


class MacroIngestionService:
    def __init__(
        self,
        config_class: type[Config] = Config,
        store: Optional[MacroStateStore] = None,
    ) -> None:
        self.config = config_class
        self.store = store or MacroStateStore()
        self.bloomberg = BloombergDesktopService(config_class=config_class)

    def _macro_transmission_score(
        self,
        *,
        buckets: list[str],
        contracts: list[str],
        securities: list[str],
        themes: list[str],
        high_conviction_macro_terms: list[str],
        idiosyncratic_terms: list[str],
        corporate_deal_terms: list[str],
        generic_equity_terms: list[str],
        technical_operation: bool,
    ) -> float:
        score = 0.0
        score += min(len(set(buckets)), 3) * 2.2
        score += min(len(set(themes)), 2) * 2.6
        score += min(len(set(contracts)), 3) * 1.4
        score += min(len(set(high_conviction_macro_terms)), 3) * 1.8
        score += min(len(set(securities)), 2) * 0.4
        if technical_operation:
            score -= 4.5
        if idiosyncratic_terms:
            score -= min(len(set(idiosyncratic_terms)), 3) * 1.5
        if corporate_deal_terms:
            score -= min(len(set(corporate_deal_terms)), 4) * 1.8
        if generic_equity_terms and not (buckets or themes or high_conviction_macro_terms):
            score -= 2.2
        return round(score, 2)

    def _fetch_json(
        self,
        url: str,
        timeout: Optional[int] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> tuple[requests.Response | None, Any | None, str | None]:
        timeout = timeout or self.config.MACRO_AQUANT_TIMEOUT_SECONDS

        try:
            response = requests.get(url, params=params, timeout=timeout)
            try:
                payload = response.json() if response.text else None
            except Exception:
                payload = response.text
            return response, payload, None
        except Exception as exc:
            return None, None, str(exc)

    def _event_has_frozen_classification(self, event: dict[str, Any]) -> bool:
        if not isinstance(event, dict):
            return False
        required_fields = (
            "impact_score",
            "scenario_classification",
            "signal_strength",
            "macro_scope",
            "linked_contracts",
            "linked_buckets",
            "linked_securities",
            "themes",
        )
        return event.get("classification_version") == EVENT_CLASSIFICATION_VERSION and all(
            field in event for field in required_fields
        )

    def freeze_news_events(
        self,
        news_events: list[dict[str, Any]],
        market_snapshot: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not news_events:
            return []

        frozen_events: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for event in news_events:
            if self._event_has_frozen_classification(event):
                frozen_events.append(_deep_copy_json(event))
            else:
                pending.append(event)

        if pending:
            enriched_pending, _, _ = self._build_news_market_links(pending, market_snapshot or {})
            frozen_events.extend(enriched_pending)

        order_map = {
            (
                item.get("event_id") or _sha1_text(item.get("headline"), item.get("event_time"))
            ): index
            for index, item in enumerate(news_events)
        }
        frozen_events.sort(
            key=lambda item: order_map.get(
                item.get("event_id") or _sha1_text(item.get("headline"), item.get("event_time")),
                10**9,
            )
        )
        return frozen_events

    async def _read_bleu_messages(self) -> dict[str, Any]:
        auth_token = self.config.MACRO_BLEU_WS_AUTH
        if not auth_token:
            return {
                "ok": False,
                "connected": False,
                "messages": [],
                "timeout_windows": 0,
                "error": "MACRO_BLEU_WS_AUTH is not set",
            }

        messages: list[Any] = []
        timeout_windows = 0
        try:
            async with websockets.connect(
                self.config.MACRO_BLEU_WS_URL,
                additional_headers={"Authorization": auth_token},
                ping_interval=None,
            ) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "action": "subscribe",
                            "topics": self.config.MACRO_BLEU_TOPICS,
                        }
                    )
                )

                for _ in range(self.config.MACRO_BLEU_READ_WINDOWS):
                    try:
                        message = await asyncio.wait_for(
                            ws.recv(),
                            timeout=self.config.MACRO_BLEU_WAIT_SECONDS,
                        )
                        try:
                            messages.append(json.loads(message))
                        except Exception:
                            messages.append({"raw_text": message})
                    except TimeoutError:
                        timeout_windows += 1

            return {
                "ok": True,
                "connected": True,
                "messages": messages,
                "timeout_windows": timeout_windows,
                "error": None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "connected": False,
                "messages": [],
                "timeout_windows": timeout_windows,
                "error": str(exc),
            }

    def _build_bleu_event(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return None

        headline = message.get("headline")
        if not headline:
            return None

        return {
            "event_id": _sha1_text(
                "bleu",
                headline,
                message.get("timestamp"),
                message.get("postedBy"),
            ),
            "source": "bleu_news",
            "event_type": "macro_news",
            "headline": headline,
            "posted_by": message.get("postedBy"),
            "relevance": message.get("relevancy"),
            "event_time": _iso_from_timestamp(message.get("timestamp")) or _now_iso(),
            "raw_timestamp": message.get("timestamp"),
            "raw": message,
        }

    def collect_bleu_news(self) -> dict[str, Any]:
        raw = asyncio.run(self._read_bleu_messages())
        events: list[dict[str, Any]] = []

        for message in raw.get("messages", []):
            event = self._build_bleu_event(message)
            if event:
                events.append(event)

        return {
            "source_status": {
                "ok": raw.get("ok", False),
                "connected": raw.get("connected", False),
                "messages_received": len(raw.get("messages", [])),
                "timeout_windows": raw.get("timeout_windows", 0),
                "error": raw.get("error"),
            },
            "events": events,
        }

    async def _stream_bleu_messages(self, stop_event: threading.Event) -> None:
        auth_token = self.config.MACRO_BLEU_WS_AUTH
        if not auth_token:
            self.store.update_collector_status(
                last_news_error="MACRO_BLEU_WS_AUTH is not set",
                news_listener_running=False,
            )
            return

        idle_timeout = max(1, int(self.config.MACRO_BLEU_IDLE_TIMEOUT_SECONDS))
        reconnect_delay = max(1, int(self.config.MACRO_BLEU_RECONNECT_DELAY_SECONDS))
        topics = list(self.config.MACRO_BLEU_TOPICS)
        total_messages = 0
        total_events = 0
        reconnect_count = 0
        timeout_windows = 0

        while not stop_event.is_set():
            try:
                async with websockets.connect(
                    self.config.MACRO_BLEU_WS_URL,
                    additional_headers={"Authorization": auth_token},
                    ping_interval=None,
                ) as ws:
                    await ws.send(
                        json.dumps(
                            {
                                "action": "subscribe",
                                "topics": topics,
                            }
                        )
                    )
                    reconnect_count += 1
                    timeout_windows = 0
                    connected_at = _now_iso()
                    self.store.update_collector_status(
                        news_listener_running=True,
                        last_news_connected_at=connected_at,
                        last_news_error=None,
                        news_reconnect_count=reconnect_count,
                    )

                    while not stop_event.is_set():
                        try:
                            message = await asyncio.wait_for(
                                ws.recv(),
                                timeout=idle_timeout,
                            )
                        except TimeoutError:
                            timeout_windows += 1
                            self.store.update_collector_status(
                                last_news_batch_at=_now_iso(),
                            )
                            continue

                        timeout_windows = 0
                        total_messages += 1

                        try:
                            payload = json.loads(message)
                        except Exception:
                            payload = {"raw_text": message}

                        event = self._build_bleu_event(payload if isinstance(payload, dict) else {})
                        status = {
                            "ok": True,
                            "connected": True,
                            "mode": "continuous_ws",
                            "messages_received": total_messages,
                            "events_persisted": total_events,
                            "timeout_windows": timeout_windows,
                            "topics": topics,
                            "last_message_at": _now_iso(),
                            "error": None,
                        }

                        if not event:
                            self.store.update_collector_status(
                                news_messages_received=total_messages,
                                last_news_batch_at=status["last_message_at"],
                                last_news_error=None,
                            )
                            continue

                        current_state = self.store.read_state()
                        current_market = ((current_state.get("snapshot") or {}).get("market")) or {}
                        event = self.freeze_news_events([event], market_snapshot=current_market)[0]
                        total_events += 1
                        status["events_persisted"] = total_events
                        self.store.record_news_events([event], source_status=status)
                        self.store.update_collector_status(
                            news_messages_received=total_messages,
                            news_events_persisted=total_events,
                            last_news_event_at=event.get("event_time"),
                            last_news_batch_at=status["last_message_at"],
                            last_news_error=None,
                        )
            except Exception as exc:
                self.store.update_collector_status(
                    last_news_error=str(exc),
                    news_listener_running=False,
                    news_reconnect_count=reconnect_count,
                )
                if stop_event.wait(reconnect_delay):
                    break

    def stream_bleu_news(self, stop_event: threading.Event) -> None:
        asyncio.run(self._stream_bleu_messages(stop_event))

    def collect_security_headers(self) -> tuple[dict[str, Any], dict[str, Any]]:
        securities: dict[str, Any] = {}
        source_status: dict[str, Any] = {}

        for symbol in self.config.MACRO_AQUANT_SECURITY_SYMBOLS:
            url = f"https://bff-portal.aquant.com.br/security/{symbol}/header"
            response, payload, error = self._fetch_json(url)

            if error or response is None:
                securities[symbol] = {"ok": False, "error": error}
                continue

            security = payload.get("security", {}) if isinstance(payload, dict) else {}
            securities[symbol] = {
                "ok": response.ok,
                "ticker": security.get("ticker", symbol),
                "name": security.get("name"),
                "price": security.get("price"),
                "change_percent": security.get("changePercent"),
                "updated_at": security.get("updatedAt"),
            }
            source_status[symbol] = {
                "ok": response.ok,
                "status_code": response.status_code,
            }

        return securities, source_status

    def _normalize_participant_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            quantity = _safe_float(row.get("quantity")) or 0.0
            normalized.append(
                {
                    "broker_id": row.get("broker_id"),
                    "broker_name": row.get("broker_name"),
                    "average_price": row.get("average_price"),
                    "quantity": row.get("quantity"),
                    "quantity_float": quantity,
                    "percentage": row.get("percentage"),
                    "percentage_float": _safe_float(row.get("percentage")),
                    "relative_percentage": row.get("relative_percentage"),
                    "relative_percentage_float": _safe_float(row.get("relative_percentage")),
                }
            )
        return normalized

    def _build_participant_summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {
                "participant_count": 0,
                "total_quantity": 0.0,
                "top_share_percentage": 0.0,
                "top_5_share_percentage": 0.0,
                "leaders": [],
            }

        sorted_rows = sorted(rows, key=lambda row: row.get("quantity_float", 0.0), reverse=True)
        total_quantity = sum(row.get("quantity_float", 0.0) for row in sorted_rows)
        top_share = sorted_rows[0].get("percentage_float") or 0.0
        top_5_share = sum((row.get("percentage_float") or 0.0) for row in sorted_rows[:5])

        return {
            "participant_count": len(sorted_rows),
            "total_quantity": total_quantity,
            "top_share_percentage": round(top_share, 2),
            "top_5_share_percentage": round(top_5_share, 2),
            "leaders": [
                {
                    "broker_name": row.get("broker_name"),
                    "broker_id": row.get("broker_id"),
                    "quantity": row.get("quantity"),
                    "percentage": row.get("percentage"),
                }
                for row in sorted_rows[:5]
            ],
        }

    def _build_ohlcv_windows(self, candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        window_minutes = max(1, int(self.config.MACRO_ANALYSIS_WINDOW_MINUTES))
        buckets: dict[str, dict[str, Any]] = {}

        for candle in candles:
            candle_dt = _parse_iso_datetime(candle.get("time"))
            if not candle_dt:
                continue

            bucket_dt = _bucket_start(candle_dt, window_minutes)
            bucket_key = bucket_dt.isoformat()
            bucket = buckets.setdefault(
                bucket_key,
                {
                    "window_start": bucket_dt.isoformat(),
                    "window_end": None,
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                    "volume": 0.0,
                    "candle_count": 0,
                },
            )

            open_price = _safe_float(candle.get("open"))
            high_price = _safe_float(candle.get("high"))
            low_price = _safe_float(candle.get("low"))
            close_price = _safe_float(candle.get("close"))
            volume = _safe_float(candle.get("volume")) or 0.0

            if bucket["open"] is None:
                bucket["open"] = open_price
            bucket["close"] = close_price
            bucket["window_end"] = candle.get("time")
            bucket["high"] = (
                high_price
                if bucket["high"] is None
                else max(bucket["high"], high_price or bucket["high"])
            )
            bucket["low"] = (
                low_price
                if bucket["low"] is None
                else min(bucket["low"], low_price or bucket["low"])
            )
            bucket["volume"] += volume
            bucket["candle_count"] += 1

        windows = sorted(buckets.values(), key=lambda item: item["window_start"])
        for window in windows:
            open_price = window.get("open")
            close_price = window.get("close")
            net_change = None
            net_change_pct = None
            if open_price is not None and close_price is not None:
                net_change = close_price - open_price
                if open_price:
                    net_change_pct = (net_change / open_price) * 100.0

            window["direction"] = (
                "up" if (net_change or 0.0) > 0 else "down" if (net_change or 0.0) < 0 else "flat"
            )
            window["net_change"] = net_change
            window["net_change_pct"] = net_change_pct
            window["range"] = (
                (window.get("high") or 0.0) - (window.get("low") or 0.0)
                if window.get("high") is not None and window.get("low") is not None
                else None
            )
        return windows

    def _build_book_summary(
        self, bid: list[dict[str, Any]], ask: list[dict[str, Any]]
    ) -> dict[str, Any]:
        top_bid_levels = bid[:20]
        top_ask_levels = ask[:20]
        best_bid = top_bid_levels[0] if top_bid_levels else None
        best_ask = top_ask_levels[0] if top_ask_levels else None

        best_bid_price = _safe_float(_to_price_string(best_bid.get("price")) if best_bid else None)
        best_ask_price = _safe_float(_to_price_string(best_ask.get("price")) if best_ask else None)
        best_bid_amount = _safe_float(best_bid.get("amount")) or 0.0 if best_bid else 0.0
        best_ask_amount = _safe_float(best_ask.get("amount")) or 0.0 if best_ask else 0.0
        top_bid_size = sum((_safe_float(level.get("amount")) or 0.0) for level in top_bid_levels)
        top_ask_size = sum((_safe_float(level.get("amount")) or 0.0) for level in top_ask_levels)

        spread = None
        if best_bid_price is not None and best_ask_price is not None:
            spread = best_ask_price - best_bid_price

        imbalance = None
        total_top_size = top_bid_size + top_ask_size
        if total_top_size:
            imbalance = (top_bid_size - top_ask_size) / total_top_size

        return {
            "best_bid_price": best_bid_price,
            "best_ask_price": best_ask_price,
            "best_bid_amount": best_bid_amount,
            "best_ask_amount": best_ask_amount,
            "spread": spread,
            "top_bid_size": top_bid_size,
            "top_ask_size": top_ask_size,
            "imbalance": imbalance,
        }

    def _collect_contract_snapshot(self, ticker: str) -> dict[str, Any]:
        end = _utc_now()
        start = end - timedelta(minutes=self.config.MACRO_AQUANT_OHLCV_WINDOW_MINUTES)

        participants_response, participants_payload, participants_error = self._fetch_json(
            "https://sdk.aquant.com.br/trade/participants/net",
            timeout=max(60, self.config.MACRO_AQUANT_TIMEOUT_SECONDS),
            params={"tickers": ticker},
        )
        participants_rows: list[dict[str, Any]] = []
        if isinstance(participants_payload, dict):
            participants_rows = [
                row
                for row in (participants_payload.get(ticker, []) or [])
                if isinstance(row, dict)
            ]
        normalized_participants = self._normalize_participant_rows(participants_rows)
        participant_summary = self._build_participant_summary(normalized_participants)

        ohlcv_response, ohlcv_payload, ohlcv_error = self._fetch_json(
            f"https://sdk.aquant.com.br/trade/{ticker}/ohlcv",
            params={
                "start": start.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "end": end.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "interval": self.config.MACRO_AQUANT_OHLCV_INTERVAL,
            },
        )
        candles: list[dict[str, Any]] = []
        if isinstance(ohlcv_payload, dict):
            candles = [
                candle
                for candle in (ohlcv_payload.get("candles", []) or [])
                if isinstance(candle, dict)
            ]
        windows_5m = self._build_ohlcv_windows(candles)
        latest_window = windows_5m[-1] if windows_5m else None
        previous_window = windows_5m[-2] if len(windows_5m) > 1 else None

        book_response, book_payload, book_error = self._fetch_json(
            f"https://book.financial.aquant.com.br/book/{ticker}"
        )
        bid = book_payload.get("bid", []) if isinstance(book_payload, dict) else []
        ask = book_payload.get("ask", []) if isinstance(book_payload, dict) else []
        best_bid = bid[0] if bid else None
        best_ask = ask[0] if ask else None
        book_summary = self._build_book_summary(bid, ask)

        return {
            "ticker": ticker,
            "bucket": _resolve_market_bucket(ticker),
            "collected_at": _now_iso(),
            "participants": {
                "ok": bool(participants_response and participants_response.ok),
                "status_code": participants_response.status_code if participants_response else None,
                "rows": len(participants_rows),
                "all_rows": normalized_participants,
                "top_3": normalized_participants[:3],
                "summary": participant_summary,
                "error": participants_error,
            },
            "ohlcv": {
                "ok": bool(ohlcv_response and ohlcv_response.ok),
                "status_code": ohlcv_response.status_code if ohlcv_response else None,
                "interval": self.config.MACRO_AQUANT_OHLCV_INTERVAL,
                "candle_count": len(candles),
                "candles_1m": candles[-120:],
                "first": candles[0] if candles else None,
                "last": candles[-1] if candles else None,
                "windows_5m": windows_5m,
                "latest_window": latest_window,
                "previous_window": previous_window,
                "error": ohlcv_error,
            },
            "book": {
                "ok": bool(book_response and book_response.ok),
                "status_code": book_response.status_code if book_response else None,
                "bid_levels": len(bid),
                "ask_levels": len(ask),
                "best_bid": {
                    "broker_id": best_bid.get("brokerId") if best_bid else None,
                    "price": _to_price_string(best_bid.get("price")) if best_bid else None,
                    "amount": best_bid.get("amount") if best_bid else None,
                },
                "best_ask": {
                    "broker_id": best_ask.get("brokerId") if best_ask else None,
                    "price": _to_price_string(best_ask.get("price")) if best_ask else None,
                    "amount": best_ask.get("amount") if best_ask else None,
                },
                "summary": book_summary,
                "error": None
                if (book_response and book_response.ok)
                else book_error or str(book_payload),
            },
        }

    def collect_market_snapshot(self) -> dict[str, Any]:
        contracts: dict[str, Any] = {}
        contract_status: dict[str, Any] = {}
        groups = _build_market_groups()

        for ticker in self.config.MACRO_AQUANT_TICKERS:
            snapshot = self._collect_contract_snapshot(ticker)
            contracts[ticker] = snapshot
            contract_status[ticker] = {
                "participants_ok": snapshot["participants"]["ok"],
                "ohlcv_ok": snapshot["ohlcv"]["ok"],
                "book_ok": snapshot["book"]["ok"],
            }

        securities, security_status = self.collect_security_headers()
        reference_assets, bloomberg_status = self.bloomberg.capture_reference_assets()
        reference_groups: dict[str, list[str]] = {}
        for security, item in reference_assets.items():
            bucket = str(item.get("bucket") or "reference")
            reference_groups.setdefault(bucket, []).append(security)

        return {
            "contracts": contracts,
            "securities": securities,
            "groups": groups,
            "reference_assets": reference_assets,
            "reference_groups": reference_groups,
            "source_status": {
                "contracts": contract_status,
                "securities": security_status,
                "bloomberg": bloomberg_status,
            },
        }

    def _build_contract_signal(self, ticker: str, contract: dict[str, Any]) -> dict[str, Any]:
        latest_window = (contract.get("ohlcv") or {}).get("latest_window") or {}
        participant_summary = (contract.get("participants") or {}).get("summary") or {}
        book_summary = (contract.get("book") or {}).get("summary") or {}

        return {
            "ticker": ticker,
            "bucket": contract.get("bucket", "other"),
            "direction_5m": latest_window.get("direction", "flat"),
            "net_change_5m": latest_window.get("net_change"),
            "net_change_pct_5m": latest_window.get("net_change_pct"),
            "volume_5m": latest_window.get("volume"),
            "range_5m": latest_window.get("range"),
            "top_participants": participant_summary.get("leaders", [])[:5],
            "top_5_share_percentage": participant_summary.get("top_5_share_percentage"),
            "book_imbalance": book_summary.get("imbalance"),
            "spread": book_summary.get("spread"),
        }

    def reclassify_news_events(
        self,
        news_events: list[dict[str, Any]],
        market_snapshot: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.freeze_news_events(news_events, market_snapshot=market_snapshot or {})

    def _detect_news_targets(
        self,
        event: dict[str, Any],
        contract_signals: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        text = " ".join(
            [
                str(event.get("headline") or ""),
                str(event.get("posted_by") or ""),
            ]
        ).lower()

        buckets: list[str] = []
        securities: list[str] = []
        themes: list[str] = []
        contracts: list[str] = []
        reasons: list[str] = []
        market_terms = [term for term in MARKET_RELEVANCE_TERMS if _keyword_in_text(text, term)]
        macro_terms = [term for term in HIGH_CONFIDENCE_MACRO_TERMS if _keyword_in_text(text, term)]
        high_conviction_macro_terms = [
            term for term in macro_terms if term not in LOW_SIGNAL_MACRO_TERMS
        ]
        idiosyncratic_terms = [
            term for term in IDIOSYNCRATIC_NEWS_TERMS if _keyword_in_text(text, term)
        ]
        corporate_deal_terms = [
            term for term in CORPORATE_DEAL_TERMS if _keyword_in_text(text, term)
        ]
        generic_equity_terms = [
            term for term in GENERIC_EQUITY_TERMS if _keyword_in_text(text, term)
        ]
        corporate_style_headline = bool(corporate_deal_terms or idiosyncratic_terms)
        macro_anchor_terms = [
            term for term in HARD_MACRO_ANCHOR_TERMS if _keyword_in_text(text, term)
        ]
        if corporate_style_headline and not macro_anchor_terms:
            market_terms = [term for term in market_terms if term in HARD_MACRO_ANCHOR_TERMS]
            macro_terms = [term for term in macro_terms if term in HARD_MACRO_ANCHOR_TERMS]
            high_conviction_macro_terms = [
                term for term in high_conviction_macro_terms if term in HARD_MACRO_ANCHOR_TERMS
            ]
        technical_liquidity_operation = _match_any_keyword_rule(text, TECHNICAL_LIQUIDITY_RULES)
        technical_balance_sheet_disclosure = _match_any_keyword_rule(
            text, TECHNICAL_BALANCE_SHEET_RULES
        )
        if not technical_balance_sheet_disclosure:
            technical_balance_sheet_disclosure = any(
                token in text
                for token in (
                    "fed de nova york",
                    "new york fed",
                    "ny fed",
                    "federal reserve bank of new york",
                )
            ) and any(
                token in text
                for token in (
                    "unrealized loss",
                    "unrealized losses",
                    "prejuizo nao realizado",
                    "prejuÃ­zo nÃ£o realizado",
                    "preju",
                    "nao realizado",
                    "nÃ£o realizado",
                    "realizado",
                    "loss",
                    "annual report",
                    "relatorio anual",
                    "relatÃ³rio anual",
                    "balance sheet",
                    "balanco",
                    "balanÃ§o",
                    "mark-to-market",
                    "mark to market",
                    "soma",
                )
            )
        if technical_liquidity_operation and any(
            _keyword_in_text(text, term) for term in HIGH_CONVICTION_CENTRAL_BANK_TERMS
        ):
            technical_liquidity_operation = False
        if technical_balance_sheet_disclosure and any(
            _keyword_in_text(text, term) for term in HIGH_CONVICTION_CENTRAL_BANK_TERMS
        ):
            technical_balance_sheet_disclosure = False
        technical_operation = technical_liquidity_operation or technical_balance_sheet_disclosure

        for key, keywords in MACRO_NEWS_KEYWORDS.items():
            if any(_keyword_in_text(text, keyword) for keyword in keywords):
                reasons.append(key)
                if key in {"curve_short", "curve_long", "index", "dollar"}:
                    buckets.append(key)
                    contracts.extend(_build_market_groups().get(key, []))
                    themes.append(key)
                else:
                    securities.append(key)

        if (
            "index" in reasons
            and not any(
                _keyword_in_text(text, term)
                for term in (
                    "ibov",
                    "ibovespa",
                    "indice",
                    "s&p",
                    "nasdaq",
                    "dow",
                    "russell",
                    "futuros de indice",
                    "index futures",
                )
            )
            and generic_equity_terms
        ):
            buckets = [bucket for bucket in buckets if bucket != "index"]
            contracts = [
                ticker for ticker in contracts if _resolve_market_bucket(ticker) != "index"
            ]
            themes = [theme for theme in themes if theme != "index"]
            reasons = [reason for reason in reasons if reason != "index"]

        for theme, rule in MACRO_THEME_RULES.items():
            if (
                theme in SESSION_RISK_THEMES
                and corporate_style_headline
                and not high_conviction_macro_terms
            ):
                continue
            if not _match_all_keyword_groups(text, rule.get("keyword_groups") or []):
                continue

            themes.append(theme)
            reasons.append(theme)

            for bucket in rule.get("buckets") or []:
                buckets.append(bucket)
                contracts.extend(_build_market_groups().get(bucket, []))

            securities.extend(rule.get("securities") or [])
            contracts.extend(rule.get("contracts") or [])

        explicit_contracts = [
            ticker for ticker in contract_signals if _keyword_in_text(text, ticker.lower())
        ]
        contracts.extend(explicit_contracts)

        if technical_liquidity_operation:
            reasons.append("technical_liquidity_operation")
        if technical_balance_sheet_disclosure:
            reasons.append("technical_balance_sheet_disclosure")

        transmission_score = self._macro_transmission_score(
            buckets=buckets,
            contracts=contracts,
            securities=securities,
            themes=themes,
            high_conviction_macro_terms=high_conviction_macro_terms,
            idiosyncratic_terms=idiosyncratic_terms,
            corporate_deal_terms=corporate_deal_terms,
            generic_equity_terms=generic_equity_terms,
            technical_operation=technical_operation,
        )
        strong_macro_signal = bool(
            high_conviction_macro_terms
            or buckets
            or explicit_contracts
            or themes
            or transmission_score >= 5.5
        )
        if (
            corporate_style_headline
            and not macro_anchor_terms
            and not (buckets or themes or explicit_contracts or securities)
        ):
            strong_macro_signal = False
        tracked_security_only = (
            bool(securities) and transmission_score < 4.5 and not strong_macro_signal
        )
        idiosyncratic_only = (
            bool(idiosyncratic_terms or corporate_deal_terms)
            and transmission_score < 4.5
            and not strong_macro_signal
            and not securities
        )
        market_relevant = bool(
            transmission_score >= 4.5
            or strong_macro_signal
            or technical_operation
            or (securities and macro_terms)
        )
        event_relevance = (event.get("relevance") or "").lower()

        if (
            not contracts
            and strong_macro_signal
            and event_relevance in {"breaking", "important"}
            and not idiosyncratic_only
            and not technical_operation
        ):
            top_movers = sorted(
                contract_signals.values(),
                key=lambda item: abs(item.get("net_change_pct_5m") or 0.0),
                reverse=True,
            )
            fallback_contracts = [
                str(item["ticker"]) for item in top_movers[:2] if item.get("ticker")
            ]
            if fallback_contracts:
                contracts.extend(fallback_contracts)
                reasons.append("fallback_top_movers")

        signal_strength = "low"
        if idiosyncratic_only:
            signal_strength = "idiosyncratic"
        elif technical_operation:
            signal_strength = "technical_low"
        elif transmission_score >= 7.0 and (
            themes
            or explicit_contracts
            or len(buckets) >= 2
            or len(high_conviction_macro_terms) >= 2
        ):
            signal_strength = "high"
        elif market_relevant or tracked_security_only:
            signal_strength = "medium"
        scenario_profile = self._build_scenario_profile(
            text=text,
            relevance=event_relevance,
            contracts=contracts,
            securities=securities,
            buckets=buckets,
            themes=themes,
            reasons=reasons,
            high_conviction_macro_terms=high_conviction_macro_terms,
            transmission_score=transmission_score,
            market_relevant=market_relevant,
            tracked_security_only=tracked_security_only,
            idiosyncratic_only=idiosyncratic_only,
            technical_operation=technical_operation,
        )

        return {
            "contracts": list(dict.fromkeys(contract for contract in contracts if contract)),
            "securities": list(dict.fromkeys(symbol for symbol in securities if symbol)),
            "buckets": list(dict.fromkeys(bucket for bucket in buckets if bucket)),
            "themes": list(dict.fromkeys(theme for theme in themes if theme)),
            "reasons": list(dict.fromkeys(reasons)),
            "market_relevance_terms": list(dict.fromkeys(market_terms)),
            "high_conviction_macro_terms": list(dict.fromkeys(high_conviction_macro_terms)),
            "macro_terms": list(dict.fromkeys(macro_terms)),
            "idiosyncratic_terms": list(dict.fromkeys(idiosyncratic_terms)),
            "corporate_deal_terms": list(dict.fromkeys(corporate_deal_terms)),
            "generic_equity_terms": list(dict.fromkeys(generic_equity_terms)),
            "macro_transmission_score": transmission_score,
            "market_relevant": market_relevant,
            "tracked_security_only": tracked_security_only,
            "idiosyncratic_only": idiosyncratic_only,
            "technical_operation": technical_operation,
            "signal_strength": signal_strength,
            "macro_scope": "macro"
            if market_relevant
            else "tracked_security"
            if tracked_security_only
            else "idiosyncratic"
            if idiosyncratic_only
            else "none",
            "scenario_classification": scenario_profile["classification"],
            "scenario_reason": scenario_profile["reason"],
        }

    def _build_scenario_profile(
        self,
        text: str,
        relevance: str,
        contracts: list[str],
        securities: list[str],
        buckets: list[str],
        themes: list[str],
        reasons: list[str],
        high_conviction_macro_terms: list[str],
        transmission_score: float,
        market_relevant: bool,
        tracked_security_only: bool,
        idiosyncratic_only: bool,
        technical_operation: bool,
    ) -> dict[str, str]:
        if technical_operation:
            return {
                "classification": "technical_noise",
                "reason": "Operational, accounting or liquidity-plumbing headline with little standalone power to change the macro regime.",
            }
        if idiosyncratic_only:
            return {
                "classification": "technical_noise",
                "reason": "Single-name or idiosyncratic headline with no broad macro transmission.",
            }
        if tracked_security_only:
            return {
                "classification": "secondary_echo",
                "reason": f"Tracked security move is relevant for context, but transmission is still narrow (score {transmission_score}) and not broad macro yet.",
            }

        regime_shift_terms = [
            term for term in REGIME_SHIFT_SCENARIO_TERMS if _keyword_in_text(text, term)
        ]
        secondary_terms = [
            term for term in SECONDARY_ECHO_SCENARIO_TERMS if _keyword_in_text(text, term)
        ]
        multi_bucket = len(set(buckets)) >= 2
        explicit_transmission = bool(contracts or securities or buckets or themes)
        risk_theme_hit = bool(set(themes) & SESSION_RISK_THEMES)

        if market_relevant and (
            (
                relevance in {"breaking", "important"}
                and transmission_score >= 7.0
                and (multi_bucket or len(high_conviction_macro_terms) >= 2)
            )
            or regime_shift_terms
            or (
                risk_theme_hit
                and transmission_score >= 6.0
                and (explicit_transmission or len(high_conviction_macro_terms) >= 1)
            )
        ):
            return {
                "classification": "regime_shift",
                "reason": f"Headline carries regime-sensitive language and broad transmission potential across multiple macro buckets (score {transmission_score}).",
            }
        if (
            market_relevant
            and transmission_score >= 4.5
            and explicit_transmission
            and (themes or buckets or high_conviction_macro_terms)
        ):
            return {
                "classification": "tradable_catalyst",
                "reason": f"Headline is macro-relevant and links to assets or buckets that can move the intraday scenario in a tradable way (score {transmission_score}).",
            }
        if market_relevant or transmission_score >= 2.5 or reasons or secondary_terms:
            return {
                "classification": "secondary_echo",
                "reason": f"Headline belongs on the tape, but looks more like context reinforcement than a fresh regime-defining catalyst (score {transmission_score}).",
            }
        return {
            "classification": "technical_noise",
            "reason": f"Headline lacks broad transmission channels and should stay close to noise unless the market starts confirming it (score {transmission_score}).",
        }

    def _score_news_impact(
        self,
        event: dict[str, Any],
        detected: dict[str, Any],
    ) -> int:
        relevance = (event.get("relevance") or "").lower()
        score = NEWS_RELEVANCE_WEIGHTS.get(relevance, 0)
        scope = str(detected.get("macro_scope") or "none")
        transmission_score = float(detected.get("macro_transmission_score") or 0.0)
        score += len(detected.get("contracts", [])) * 2
        score += len(detected.get("buckets", [])) * 2
        score += len(detected.get("securities", []))
        score += min(len(detected.get("themes", [])), 2)
        score += min(len(detected.get("high_conviction_macro_terms", [])), 2)
        if detected.get("market_relevant"):
            score += 1
        score += min(max(int(transmission_score // 2), 0), 4)
        risk_theme_hit = bool(set(detected.get("themes", [])) & SESSION_RISK_THEMES)
        broad_macro_context = bool(
            risk_theme_hit
            or detected.get("buckets")
            or len(detected.get("contracts", [])) >= 2
            or len(detected.get("high_conviction_macro_terms", [])) >= 2
        )
        scenario_classification = str(detected.get("scenario_classification") or "")
        if scenario_classification == "technical_noise":
            score = min(score, 1)
        elif scenario_classification == "regime_shift":
            score = max(score + 3, 6 if broad_macro_context else 4)
        elif scenario_classification == "tradable_catalyst":
            score = max(score + 2, 5 if broad_macro_context else 3)
        elif scenario_classification == "secondary_echo":
            if broad_macro_context:
                score = min(max(score + 1, 4), 6)
            else:
                score = min(score, 3)
        if scope == "macro" and not (
            detected.get("contracts")
            or detected.get("buckets")
            or detected.get("themes")
            or detected.get("securities")
        ):
            score = min(score, 2)
        if "fallback_top_movers" in (detected.get("reasons") or []):
            score = max(score - 1, 1)
        if detected.get("technical_operation"):
            score = min(score, 1)
        elif detected.get("signal_strength") == "low":
            score = min(score, 4 if broad_macro_context else 2)
        if detected.get("idiosyncratic_only") or detected.get("corporate_deal_terms"):
            score = min(score, 1 if transmission_score < 4.5 else 3)
        if scope == "tracked_security":
            score = min(score, 4)
        elif scope != "macro":
            score = min(score, 1)
        return score

    def _build_news_market_links(
        self,
        news_events: list[dict[str, Any]],
        market_snapshot: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        contracts = market_snapshot.get("contracts", {}) or {}
        contract_signals = {
            ticker: self._build_contract_signal(ticker, contract)
            for ticker, contract in contracts.items()
        }
        security_headers = market_snapshot.get("securities", {}) or {}

        enriched_events: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        for event in news_events:
            detected = self._detect_news_targets(event, contract_signals)
            impact_score = self._score_news_impact(event, detected)
            enriched_event = {
                **event,
                "linked_contracts": detected["contracts"],
                "linked_securities": detected["securities"],
                "linked_buckets": detected["buckets"],
                "themes": detected["themes"],
                "link_reasons": detected["reasons"],
                "market_relevance": detected["market_relevant"],
                "market_relevance_terms": detected["market_relevance_terms"],
                "high_conviction_macro_terms": detected["high_conviction_macro_terms"],
                "macro_terms": detected["macro_terms"],
                "idiosyncratic_terms": detected["idiosyncratic_terms"],
                "corporate_deal_terms": detected["corporate_deal_terms"],
                "macro_transmission_score": detected["macro_transmission_score"],
                "macro_scope": detected["macro_scope"],
                "tracked_security_only": detected["tracked_security_only"],
                "idiosyncratic_only": detected["idiosyncratic_only"],
                "technical_operation": detected["technical_operation"],
                "signal_strength": detected["signal_strength"],
                "scenario_classification": detected["scenario_classification"],
                "scenario_reason": detected["scenario_reason"],
                "impact_score": impact_score,
                "classification_version": EVENT_CLASSIFICATION_VERSION,
                "classification_frozen": True,
                "classification_frozen_at": _now_iso(),
            }
            enriched_events.append(enriched_event)

            for ticker in detected["contracts"]:
                signal = contract_signals.get(ticker, {})
                links.append(
                    {
                        "event_id": event.get("event_id"),
                        "headline": event.get("headline"),
                        "relevance": event.get("relevance"),
                        "event_time": event.get("event_time"),
                        "ticker": ticker,
                        "bucket": signal.get("bucket"),
                        "direction_5m": signal.get("direction_5m"),
                        "net_change_pct_5m": signal.get("net_change_pct_5m"),
                        "volume_5m": signal.get("volume_5m"),
                        "book_imbalance": signal.get("book_imbalance"),
                        "top_participants": signal.get("top_participants", [])[:3],
                        "linked_securities": detected["securities"],
                        "themes": detected["themes"],
                        "link_reasons": detected["reasons"],
                        "impact_score": impact_score,
                    }
                )

        enriched_events.sort(
            key=lambda item: (
                int(item.get("impact_score") or 0),
                (
                    _parse_iso_datetime(item.get("event_time"))
                    or datetime.min.replace(tzinfo=timezone.utc)
                ).timestamp(),
            ),
            reverse=True,
        )
        links.sort(
            key=lambda item: (
                int(item.get("impact_score") or 0),
                abs(item.get("net_change_pct_5m") or 0.0),
            ),
            reverse=True,
        )

        overview = {
            "top_movers_5m": sorted(
                contract_signals.values(),
                key=lambda item: abs(item.get("net_change_pct_5m") or 0.0),
                reverse=True,
            )[:5],
            "market_relevant_news_count": sum(
                1 for item in enriched_events if item.get("market_relevance")
            ),
            "impactful_news_count": sum(
                1 for item in enriched_events if int(item.get("impact_score") or 0) >= 4
            ),
            "impactful_news": [
                {
                    "headline": item.get("headline"),
                    "relevance": item.get("relevance"),
                    "impact_score": item.get("impact_score"),
                    "linked_contracts": item.get("linked_contracts", []),
                    "themes": item.get("themes", []),
                }
                for item in enriched_events
                if int(item.get("impact_score") or 0) >= 4
            ][:5],
            "security_moves": [
                {
                    "ticker": ticker,
                    "price": security.get("price"),
                    "change_percent": security.get("change_percent"),
                }
                for ticker, security in security_headers.items()
            ],
        }

        return enriched_events, links, overview

    def collect_all_once(
        self,
        include_news: bool = True,
        include_market: bool = True,
        persist: bool = True,
    ) -> dict[str, Any]:
        started_at = _now_iso()
        news_events: list[dict[str, Any]] = []
        news_status: dict[str, Any] = {}
        market_snapshot: dict[str, Any] = {
            "contracts": {},
            "securities": {},
            "reference_assets": {},
            "reference_groups": {},
        }
        market_status: dict[str, Any] = {}

        if include_news:
            news_result = self.collect_bleu_news()
            news_events = news_result.get("events", [])
            news_status = news_result.get("source_status", {})

        if include_market:
            market_result = self.collect_market_snapshot()
            market_snapshot = {
                "contracts": market_result.get("contracts", {}),
                "securities": market_result.get("securities", {}),
                "groups": market_result.get("groups", {}),
                "reference_assets": market_result.get("reference_assets", {}),
                "reference_groups": market_result.get("reference_groups", {}),
            }
            market_status = market_result.get("source_status", {})

        recent_pool: list[dict[str, Any]] = []
        if include_news or include_market:
            state = self.store.read_state()
            recent_cutoff = _utc_now() - timedelta(
                minutes=self.config.MACRO_NEWS_LINK_LOOKBACK_MINUTES
            )
            recent_pool = [
                event
                for event in state.get("recent_events", [])
                if (_parse_iso_datetime(event.get("event_time")) or _utc_now()) >= recent_cutoff
            ]

        candidate_news = []
        seen_event_ids = set()
        for event in news_events + recent_pool:
            event_id = event.get("event_id") or _sha1_text(
                event.get("headline"), event.get("event_time")
            )
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            candidate_news.append(event)

        enriched_news = candidate_news
        market_links: list[dict[str, Any]] = []
        market_overview: dict[str, Any] = {}
        if include_market:
            enriched_news, market_links, market_overview = self._build_news_market_links(
                candidate_news,
                market_snapshot,
            )

        snapshot = {
            "generated_at": _now_iso(),
            "news": {
                "count": len(enriched_news),
                "new_count": len(news_events),
                "items": enriched_news[:20],
                "linked_items": sum(
                    1
                    for item in enriched_news
                    if item.get("linked_contracts")
                    or item.get("linked_securities")
                    or item.get("linked_buckets")
                ),
                "market_relevant_items": sum(
                    1 for item in enriched_news if item.get("market_relevance")
                ),
                "impactful_items": sum(
                    1 for item in enriched_news if int(item.get("impact_score") or 0) >= 4
                ),
                "timeout_windows": news_status.get("timeout_windows", 0),
            },
            "market": {
                **market_snapshot,
                "overview": market_overview,
                "news_links": market_links[:80],
            },
            "sources": {
                "bleu_ws": news_status,
                "aquant": market_status,
            },
        }

        current_event_ids = {
            event.get("event_id") for event in news_events if event.get("event_id")
        }
        persisted_news_events = [
            event for event in enriched_news if event.get("event_id") in current_event_ids
        ] or news_events

        result = {
            "started_at": started_at,
            "completed_at": _now_iso(),
            "snapshot": snapshot,
            "news_events": persisted_news_events,
        }

        if persist:
            self.store.record_collection(result)
            try:
                from .macro_driver_service import MacroDriverService

                MacroDriverService(store=self.store, ingestion=self).refresh_drivers()
            except Exception:
                logger.exception("Failed to refresh macro drivers after collection")

        return result

    def get_snapshot(self, limit_events: int = 20) -> dict[str, Any]:
        state = self.store.read_state()
        state["recent_events"] = state.get("recent_events", [])[:limit_events]
        return state

class MacroCollectorManager:
    _instance: Optional["MacroCollectorManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.store = MacroStateStore()
        self.service = MacroIngestionService(store=self.store)
        self._market_thread: Optional[threading.Thread] = None
        self._news_thread: Optional[threading.Thread] = None
        self._market_stop_event = threading.Event()
        self._news_stop_event = threading.Event()
        self._runtime_lock = threading.RLock()
        self._supervisor_thread: Optional[threading.Thread] = None
        self._supervisor_stop_event = threading.Event()
        self._manual_stop_requested = False
        self._ensure_supervisor_running()

    @classmethod
    def get_instance(cls) -> "MacroCollectorManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _increment_run_count(self) -> int:
        state = self.store.read_state()
        current = int((state.get("collector") or {}).get("run_count", 0))
        return current + 1

    def _increment_restart_count(self) -> int:
        state = self.store.read_state()
        current = int((state.get("collector") or {}).get("restart_count", 0))
        return current + 1

    def _ensure_supervisor_running(self) -> None:
        with self._runtime_lock:
            if self._supervisor_thread and self._supervisor_thread.is_alive():
                return

            self._supervisor_stop_event = threading.Event()
            self._supervisor_thread = threading.Thread(
                target=self._supervisor_loop,
                daemon=True,
                name="macro-collector-supervisor",
            )
            self._supervisor_thread.start()
            self.store.update_collector_status(supervisor_running=True)

    def _supervisor_loop(self) -> None:
        interval = max(5, int(Config.MACRO_INGEST_SUPERVISOR_INTERVAL_SECONDS))

        while not self._supervisor_stop_event.wait(interval):
            try:
                self.recover_if_needed()
            except Exception:
                logger.exception("Macro collector supervisor iteration failed")

        self.store.update_collector_status(supervisor_running=False)

    def _spawn_market_thread(self, interval_seconds: int) -> None:
        self._market_stop_event = threading.Event()
        self._market_thread = threading.Thread(
            target=self._run_market_loop,
            args=(interval_seconds,),
            daemon=True,
            name="macro-market-poller",
        )
        self._market_thread.start()

    def _spawn_news_thread(self) -> None:
        self._news_stop_event = threading.Event()
        self._news_thread = threading.Thread(
            target=self._run_news_loop,
            daemon=True,
            name="macro-news-listener",
        )
        self._news_thread.start()

    def _market_thread_alive(self) -> bool:
        return bool(self._market_thread and self._market_thread.is_alive())

    def _news_thread_alive(self) -> bool:
        return bool(self._news_thread and self._news_thread.is_alive())

    def _collector_threads_alive(self) -> bool:
        return self._market_thread_alive() or self._news_thread_alive()

    def _run_market_loop(self, interval_seconds: int) -> None:
        while not self._market_stop_event.is_set():
            try:
                result = self.service.collect_all_once(
                    include_news=False,
                    include_market=True,
                    persist=True,
                )
                self.store.update_collector_status(
                    running=self._collector_threads_alive(),
                    market_poller_running=True,
                    last_completed_at=result.get("completed_at"),
                    last_market_completed_at=result.get("completed_at"),
                    last_error=None,
                    run_count=self._increment_run_count(),
                )
            except Exception as exc:
                logger.exception("Macro market poller iteration failed")
                self.store.update_collector_status(
                    last_completed_at=_now_iso(),
                    last_market_completed_at=_now_iso(),
                    last_error=str(exc),
                    run_count=self._increment_run_count(),
                )

            if self._market_stop_event.wait(interval_seconds):
                break

        with self._runtime_lock:
            current_thread = threading.current_thread()
            if self._market_thread is current_thread:
                self._market_thread = None

        stopped_reason = "manual_stop" if self._manual_stop_requested else "market_poller_stopped"
        self.store.update_collector_status(
            running=self._news_thread_alive(),
            market_poller_running=False,
            stopped_reason=stopped_reason,
        )

    def _run_news_loop(self) -> None:
        self.store.update_collector_status(
            running=True,
            news_listener_running=True,
            last_news_error=None,
        )
        try:
            self.service.stream_bleu_news(self._news_stop_event)
        except Exception as exc:
            logger.exception("Macro news listener failed")
            self.store.update_collector_status(last_news_error=str(exc))
        finally:
            with self._runtime_lock:
                current_thread = threading.current_thread()
                if self._news_thread is current_thread:
                    self._news_thread = None

            stopped_reason = (
                "manual_stop" if self._manual_stop_requested else "news_listener_stopped"
            )
            self.store.update_collector_status(
                running=self._market_thread_alive(),
                news_listener_running=False,
                stopped_reason=stopped_reason,
            )

    def start(self, interval_seconds: int | None = None) -> dict[str, Any]:
        interval_seconds = interval_seconds or Config.MACRO_INGEST_INTERVAL_SECONDS

        with self._runtime_lock:
            self._ensure_supervisor_running()

            self._manual_stop_requested = False
            self.store.update_collector_status(
                running=True,
                desired_running=True,
                auto_restart_enabled=Config.MACRO_INGEST_AUTO_RESTART,
                interval_seconds=interval_seconds,
                last_started_at=_now_iso(),
                last_error=None,
                last_news_error=None,
                stopped_reason=None,
            )

            if not self._market_thread_alive():
                self._spawn_market_thread(interval_seconds)

            if not self._news_thread_alive():
                self._spawn_news_thread()

            collector = self.store.read_state().get("collector", {})
            return dict(collector) if isinstance(collector, dict) else {}

    def stop(self) -> dict[str, Any]:
        with self._runtime_lock:
            self._manual_stop_requested = True
            if self._market_thread_alive():
                self._market_stop_event.set()
                market_thread = self._market_thread
                if market_thread is not None:
                    market_thread.join(timeout=3)
                if not self._market_thread_alive():
                    self._market_thread = None

            if self._news_thread_alive():
                self._news_stop_event.set()
                news_thread = self._news_thread
                if news_thread is not None:
                    news_thread.join(timeout=3)
                if not self._news_thread_alive():
                    self._news_thread = None

            self.store.update_collector_status(
                running=False,
                desired_running=False,
                market_poller_running=False,
                news_listener_running=False,
                stopped_reason="manual_stop",
            )
            collector = self.store.read_state().get("collector", {})
            return dict(collector) if isinstance(collector, dict) else {}

    def status(self) -> dict[str, Any]:
        self._ensure_supervisor_running()
        self.recover_if_needed()
        raw_status = self.store.read_state().get("collector", {})
        status = dict(raw_status) if isinstance(raw_status, dict) else {}
        status["running"] = self._collector_threads_alive()
        status["market_poller_running"] = self._market_thread_alive()
        status["news_listener_running"] = self._news_thread_alive()
        status["supervisor_running"] = bool(
            self._supervisor_thread and self._supervisor_thread.is_alive()
        )
        return status

    def recover_if_needed(self) -> dict[str, Any]:
        with self._runtime_lock:
            state = self.store.read_state()
            collector = state.get("collector", {})
            desired_running = bool(collector.get("desired_running"))
            auto_restart_enabled = bool(
                collector.get("auto_restart_enabled", Config.MACRO_INGEST_AUTO_RESTART)
            )

            if not desired_running or not auto_restart_enabled:
                status = dict(collector)
                status["running"] = self._collector_threads_alive()
                status["market_poller_running"] = self._market_thread_alive()
                status["news_listener_running"] = self._news_thread_alive()
                status["supervisor_running"] = bool(
                    self._supervisor_thread and self._supervisor_thread.is_alive()
                )
                return status

            interval_seconds = int(
                collector.get("interval_seconds") or Config.MACRO_INGEST_INTERVAL_SECONDS
            )
            restarted_any = False

            if not self._market_thread_alive():
                restarted_any = True
                self._manual_stop_requested = False
                self._spawn_market_thread(interval_seconds)

            if not self._news_thread_alive():
                restarted_any = True
                self._manual_stop_requested = False
                self._spawn_news_thread()

            if restarted_any:
                self.store.update_collector_status(
                    running=True,
                    market_poller_running=self._market_thread_alive(),
                    news_listener_running=self._news_thread_alive(),
                    interval_seconds=interval_seconds,
                    last_started_at=_now_iso(),
                    last_restart_at=_now_iso(),
                    restart_count=self._increment_restart_count(),
                    stopped_reason="auto_restart",
                    last_error=None,
                    last_news_error=None,
                )
                logger.warning(
                    "Macro collector worker was down and has been restarted automatically"
                )

            raw_status = self.store.read_state().get("collector", {})
            status = dict(raw_status) if isinstance(raw_status, dict) else {}
            status["running"] = self._collector_threads_alive()
            status["market_poller_running"] = self._market_thread_alive()
            status["news_listener_running"] = self._news_thread_alive()
            status["supervisor_running"] = bool(
                self._supervisor_thread and self._supervisor_thread.is_alive()
            )
            return status

    def resume_if_needed(self) -> dict[str, Any]:
        self._ensure_supervisor_running()
        collector = self.store.read_state().get("collector", {})
        legacy_running = bool(collector.get("running"))
        should_resume = (
            bool(collector.get("desired_running")) or legacy_running or Config.MACRO_INGEST_ENABLE
        )

        if not should_resume:
            status = dict(collector)
            status["running"] = self._collector_threads_alive()
            status["market_poller_running"] = self._market_thread_alive()
            status["news_listener_running"] = self._news_thread_alive()
            status["supervisor_running"] = bool(
                self._supervisor_thread and self._supervisor_thread.is_alive()
            )
            return status

        if (Config.MACRO_INGEST_ENABLE or legacy_running) and not collector.get("desired_running"):
            self.store.update_collector_status(
                desired_running=True,
                auto_restart_enabled=Config.MACRO_INGEST_AUTO_RESTART,
            )

        return self.recover_if_needed()

    def collect_once(
        self, include_news: bool = True, include_market: bool = True
    ) -> dict[str, Any]:
        self.store.update_collector_status(last_started_at=_now_iso(), last_error=None)
        try:
            result = self.service.collect_all_once(
                include_news=include_news,
                include_market=include_market,
                persist=True,
            )
            self.store.update_collector_status(
                last_completed_at=result.get("completed_at"),
                last_market_completed_at=result.get("completed_at") if include_market else None,
                last_error=None,
                run_count=self._increment_run_count(),
            )
            return result
        except Exception as exc:
            self.store.update_collector_status(
                last_completed_at=_now_iso(),
                last_error=str(exc),
                run_count=self._increment_run_count(),
            )
            raise
