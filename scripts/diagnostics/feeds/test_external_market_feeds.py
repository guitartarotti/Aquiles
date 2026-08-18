"""
Smoke-test external macro/news and market-data feeds used for scenario building.

Usage:
    set BLEU_WS_AUTH=your_token
    uv run --project backend --no-sync python scripts/diagnostics/feeds/test_external_market_feeds.py
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
import websockets


BLEU_WS_URL = "wss://news-ws.bleu.com.br/ws?topics=breaking,important,relevant"
AQUANT_SECURITY_SYMBOLS = ["VALE3", "PETR4", "ITUB4", "BPAC11", "BBDC4"]
AQUANT_PARTICIPANTS_BASE_URL = "https://sdk.aquant.com.br/trade/participants/net"
AQUANT_PARTICIPANTS_TICKERS = [
    "BVMF:WINJ26",
    "BVMF:WDOK26",
    "BVMF:DI1F27",
    "BVMF:DI1F28",
    "BVMF:DI1F29",
    "BVMF:DI1F30",
    "BVMF:DI1F31",
    "BVMF:DI1F35",
]
AQUANT_WIN_OHLCV_URL = (
    "https://sdk.aquant.com.br/trade/BVMF:WINJ26/ohlcv"
    "?start=2026-04-10T16:00:00Z&end=2026-04-10T17:00:00Z&interval=1+min"
)
AQUANT_WDO_OHLCV_URL = (
    "https://sdk.aquant.com.br/trade/BVMF:WDOK26/ohlcv"
    "?start=2026-04-10T16:00:00Z&end=2026-04-10T17:00:00Z&interval=1+min"
)
AQUANT_BOOK_URLS = {
    "BVMF:WINJ26": "https://book.financial.aquant.com.br/book/BVMF:WINJ26",
    "BVMF:WDOK26": "https://book.financial.aquant.com.br/book/BVMF:WDOK26",
    "BVMF:DI1F27": "https://book.financial.aquant.com.br/book/BVMF:DI1F27",
    "BVMF:DI1F28": "https://book.financial.aquant.com.br/book/BVMF:DI1F28",
    "BVMF:DI1F29": "https://book.financial.aquant.com.br/book/BVMF:DI1F29",
    "BVMF:DI1F30": "https://book.financial.aquant.com.br/book/BVMF:DI1F30",
    "BVMF:DI1F31": "https://book.financial.aquant.com.br/book/BVMF:DI1F31",
    "BVMF:DI1F35": "https://book.financial.aquant.com.br/book/BVMF:DI1F35",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_decimal_string(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, dict) and "mantissa" in value:
        mantissa = Decimal(str(value["mantissa"]))
        exponent = int(value.get("exponent", 0))
        return format(mantissa * (Decimal(10) ** exponent), "f")

    return str(value)


@dataclass
class HttpResult:
    url: str
    ok: bool
    status_code: int | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class WsResult:
    url: str
    ok: bool
    connected: bool = False
    messages_received: int = 0
    timeout_windows: int = 0
    sample_messages: list[Any] = field(default_factory=list)
    error: str | None = None


def fetch_json(url: str, timeout: int = 20) -> tuple[requests.Response | None, Any | None, str | None]:
    try:
        response = requests.get(url, timeout=timeout)
        try:
            payload = response.json() if response.text else None
        except Exception:
            payload = response.text
        return response, payload, None
    except Exception as exc:
        return None, None, str(exc)


def summarize_security_header() -> HttpResult:
    summary: dict[str, Any] = {}
    last_url = ""
    ok = True
    last_status_code: int | None = None
    errors: list[str] = []

    for symbol in AQUANT_SECURITY_SYMBOLS:
        url = f"https://bff-portal.aquant.com.br/security/{symbol}/header"
        last_url = url
        response, payload, error = fetch_json(url)
        if error or response is None:
            ok = False
            summary[symbol] = {"ok": False, "error": error}
            errors.append(f"{symbol}: {error}")
            continue

        last_status_code = response.status_code
        security = payload.get("security", {}) if isinstance(payload, dict) else {}
        summary[symbol] = {
            "ok": response.ok,
            "ticker": security.get("ticker", symbol),
            "name": security.get("name"),
            "price": security.get("price"),
            "change_percent": security.get("changePercent"),
            "updated_at": security.get("updatedAt"),
        }
        ok = ok and response.ok

    return HttpResult(
        url=last_url,
        ok=ok,
        status_code=last_status_code,
        summary=summary,
        error="; ".join(errors) if errors else None,
    )


def summarize_participants() -> HttpResult:
    summary: dict[str, Any] = {}
    last_status_code: int | None = None
    had_success = False
    had_failure = False

    for ticker in AQUANT_PARTICIPANTS_TICKERS:
        url = f"{AQUANT_PARTICIPANTS_BASE_URL}?tickers={ticker}"
        response, payload, error = fetch_json(url, timeout=60)

        if error or response is None:
            had_failure = True
            summary[ticker] = {"ok": False, "error": error, "rows": 0, "top_3": []}
            continue

        last_status_code = response.status_code
        rows = payload.get(ticker, []) if isinstance(payload, dict) else []
        ticker_ok = response.ok
        had_success = had_success or ticker_ok
        had_failure = had_failure or (not ticker_ok)
        summary[ticker] = {
            "ok": ticker_ok,
            "rows": len(rows),
            "top_3": rows[:3],
            "bottom_3": rows[-3:] if len(rows) >= 3 else rows,
        }

    return HttpResult(
        url=AQUANT_PARTICIPANTS_BASE_URL,
        ok=had_success and not had_failure,
        status_code=last_status_code,
        summary=summary,
        error=None if had_success else "All participant requests failed",
    )


def summarize_ohlcv(url: str, label: str) -> HttpResult:
    response, payload, error = fetch_json(url)
    if error or response is None:
        return HttpResult(url=url, ok=False, error=error)

    candles = payload.get("candles", []) if isinstance(payload, dict) else []
    summary = {
        "label": label,
        "candles": len(candles),
        "first": candles[0] if candles else None,
        "last": candles[-1] if candles else None,
    }
    return HttpResult(url=url, ok=response.ok, status_code=response.status_code, summary=summary)


def summarize_book(ticker: str, url: str) -> HttpResult:
    response, payload, error = fetch_json(url)
    if error or response is None:
        return HttpResult(url=url, ok=False, error=error)

    if not response.ok:
        return HttpResult(url=url, ok=False, status_code=response.status_code, error=str(payload))

    bid = payload.get("bid", []) if isinstance(payload, dict) else []
    ask = payload.get("ask", []) if isinstance(payload, dict) else []
    best_bid = bid[0] if bid else None
    best_ask = ask[0] if ask else None
    summary = {
        "ticker": ticker,
        "bid_levels": len(bid),
        "ask_levels": len(ask),
        "best_bid": {
            "broker_id": best_bid.get("brokerId") if best_bid else None,
            "price": to_decimal_string(best_bid.get("price")) if best_bid else None,
            "amount": best_bid.get("amount") if best_bid else None,
        },
        "best_ask": {
            "broker_id": best_ask.get("brokerId") if best_ask else None,
            "price": to_decimal_string(best_ask.get("price")) if best_ask else None,
            "amount": best_ask.get("amount") if best_ask else None,
        },
    }
    return HttpResult(url=url, ok=True, status_code=response.status_code, summary=summary)


async def summarize_bleu_ws(
    auth_token: str | None,
    wait_seconds: int = 10,
    read_windows: int = 3,
) -> WsResult:
    if not auth_token:
        return WsResult(url=BLEU_WS_URL, ok=False, error="BLEU_WS_AUTH is not set")

    sample_messages: list[Any] = []
    timeout_windows = 0
    try:
        async with websockets.connect(
            BLEU_WS_URL,
            additional_headers={"Authorization": auth_token},
            ping_interval=None,
        ) as ws:
            await ws.send(json.dumps({"action": "subscribe", "topics": ["breaking", "important"]}))

            for _ in range(read_windows):
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=wait_seconds)
                    try:
                        sample_messages.append(json.loads(message))
                    except Exception:
                        sample_messages.append(message)
                except TimeoutError:
                    timeout_windows += 1

        return WsResult(
            url=BLEU_WS_URL,
            ok=True,
            connected=True,
            messages_received=len(sample_messages),
            timeout_windows=timeout_windows,
            sample_messages=sample_messages,
        )
    except Exception as exc:
        return WsResult(url=BLEU_WS_URL, ok=False, error=str(exc))


def write_report(report: dict[str, Any]) -> Path:
    output_dir = Path(__file__).resolve().parents[1] / "uploads" / "feed_tests"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"feed_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = output_dir / filename
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


async def main() -> None:
    bleu_result = await summarize_bleu_ws(os.environ.get("BLEU_WS_AUTH"))
    report = {
        "generated_at": now_iso(),
        "bleu_ws": asdict(bleu_result),
        "aquant_security_header": asdict(summarize_security_header()),
        "aquant_participants_net": asdict(summarize_participants()),
        "aquant_ohlcv": [
            asdict(summarize_ohlcv(AQUANT_WIN_OHLCV_URL, "WINJ26 intraday sample")),
            asdict(summarize_ohlcv(AQUANT_WDO_OHLCV_URL, "WDOK26 intraday sample")),
        ],
        "aquant_books": [asdict(summarize_book(ticker, url)) for ticker, url in AQUANT_BOOK_URLS.items()],
    }

    output_path = write_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved report to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
