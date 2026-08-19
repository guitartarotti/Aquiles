from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.fair_value_legs_chart_service import (
    BENCHMARK_SYMBOL,
    FairValueLegsChartService,
)


def _market_frame(service: FairValueLegsChartService) -> pd.DataFrame:
    legs = service._normalize_leg_config(None)
    symbols = {BENCHMARK_SYMBOL}
    for leg in legs:
        symbols.update(leg.get("available_assets") or [])

    start = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    rows = []
    for point in range(48):
        captured_at = start + timedelta(minutes=5 * point)
        for symbol_index, symbol in enumerate(sorted(symbols)):
            base = 135_000.0 if symbol == BENCHMARK_SYMBOL else 50.0 + symbol_index * 7.5
            sign = -1.0 if symbol_index % 3 == 0 else 1.0
            wave = ((point % 7) - 3) * 0.0007
            change_decimal = sign * point * 0.00035 + wave
            price = base * (1.0 + change_decimal)
            rows.append(
                {
                    "capture_id": f"{point}-{symbol_index}",
                    "captured_at": pd.Timestamp(captured_at),
                    "local_dt": pd.Timestamp(captured_at).tz_convert("America/Sao_Paulo"),
                    "symbol": symbol,
                    "price": price,
                    "daily_change_pct": change_decimal * 100.0,
                    "session_date": "2026-08-18",
                    "bucket": pd.Timestamp(captured_at).floor("5min"),
                }
            )
    return service._attach_intraday_returns(pd.DataFrame(rows))


def test_fair_value_legs_pipeline_builds_chart_rpc_and_cache(monkeypatch) -> None:
    service = FairValueLegsChartService()
    frame = _market_frame(service)
    monkeypatch.setattr(service, "_candidate_row_files", lambda _sessions: [])
    monkeypatch.setattr(service, "_read_rows_from_store", lambda **_kwargs: frame.copy())
    monkeypatch.setattr(service, "_store_payload_snapshot", lambda _payload: None)
    monkeypatch.setattr(
        service.history_store,
        "replace_fair_value_asset_stats",
        lambda *_args, **_kwargs: None,
    )

    payload = service.build_payload(
        sessions=1,
        bar_minutes=5,
        rolling_window_points=12,
        vol_context={
            "implied_vol": 0.22,
            "vol_of_vol_daily_pct": 1.5,
        },
    )
    cached = service.build_payload(
        sessions=1,
        bar_minutes=5,
        rolling_window_points=12,
        vol_context={
            "implied_vol": 0.22,
            "vol_of_vol_daily_pct": 1.5,
        },
    )

    assert payload["ok"] is True
    assert payload["sessions"][0]["date"] == "2026-08-18"
    assert len(payload["chart_rows"]) == 48
    assert payload["latest"]["close"] is not None
    assert payload["latest"]["rpc_pressure_score"] is not None
    assert payload["risk_pressure_composite"]["active_version"] == "v2"
    assert any(item["assets"] for item in payload["legs"])
    assert cached["chart_rows"] == payload["chart_rows"]
    assert service.payload_last_timestamp_ms(payload) == payload["latest"]["timestamp_ms"]
