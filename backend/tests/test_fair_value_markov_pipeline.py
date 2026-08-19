from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.services.fair_value_markov_regime_service import FairValueMarkovRegimeService

LEG_KEYS = [
    "di",
    "equity_local",
    "fx",
    "credit",
    "risk",
    "equity_foreign",
    "funding",
    "commodities",
    "sentiment",
]


def _legs_payload() -> dict:
    start = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    previous_close = 135_000.0
    rows = []
    for index in range(120):
        timestamp = start + timedelta(minutes=5 * index)
        session_date = timestamp.date().isoformat()
        cycle = math.sin(index / 7.0)
        slower_cycle = math.cos(index / 19.0)
        trend = (index - 60) * 0.00004
        close = previous_close * (1.0 + trend + cycle * 0.002 + slower_cycle * 0.001)
        row = {
            "timestamp": timestamp.isoformat(),
            "timestamp_ms": int(timestamp.timestamp() * 1000),
            "session_date": session_date,
            "open": close - 25,
            "high": close + 70,
            "low": close - 65,
            "close": close,
            "previous_close": previous_close,
            "rpc_pressure_score": cycle * 75,
            "rpc_slope": math.cos(index / 7.0) * 35,
            "rpc_acceleration": -cycle * 20,
            "rpc_v2_vixbr_score": -cycle * 45,
            "fair_value_core": close + cycle * 180,
            "fair_value_shadow": close - slower_cycle * 120,
            "fair_value_range_points": 450 + abs(cycle) * 200,
            "edge_bias_score": slower_cycle * 65,
            "sentiment_components": {"gap_z": cycle * 2.5},
        }
        for leg_index, key in enumerate(LEG_KEYS):
            sign = -1.0 if leg_index % 3 == 0 else 1.0
            row[f"leg_{key}_impact_decimal"] = sign * (
                cycle * (0.0005 + leg_index * 0.00003)
                + slower_cycle * 0.0002
            )
        rows.append(row)
    return {
        "ok": True,
        "generated_at": "2026-08-18T13:00:00+00:00",
        "benchmark_symbol": "XB1",
        "sessions": [
            {"date": "2026-08-17", "previous_close": previous_close},
            {"date": "2026-08-18", "previous_close": previous_close},
        ],
        "legs": [{"key": key, "enabled": True} for key in LEG_KEYS],
        "chart_rows": rows,
    }


class _LegsService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def build_payload(self, **_kwargs) -> dict:
        return self.payload


class _CurveService:
    pass


def test_markov_pipeline_fits_states_transitions_and_risk_layers(monkeypatch) -> None:
    legs_payload = _legs_payload()
    service = FairValueMarkovRegimeService(
        legs_chart_service=_LegsService(legs_payload),
        curve_discovery_service=_CurveService(),
    )
    curve_points = [
        {
            "timestamp_ms": row["timestamp_ms"],
            "slope_change": math.sin(index / 11.0) * 0.03,
            "level_change": math.cos(index / 13.0) * 0.025,
        }
        for index, row in enumerate(legs_payload["chart_rows"])
    ]
    monkeypatch.setattr(service, "_latest_source_probe", lambda **_kwargs: {})
    monkeypatch.setattr(service, "_di_curve_history_for_session", lambda _session: curve_points)
    monkeypatch.setattr(service, "_build_flow_activity_meta", lambda _session: None)
    monkeypatch.setattr(
        service,
        "_apply_regime_persistence",
        lambda payload, **_kwargs: payload,
    )
    monkeypatch.setattr(service, "_store_snapshot", lambda _payload: None)

    params = {
        "config": {},
        "sessions": 2,
        "bar_minutes": 5,
        "session_start": "09:00",
        "session_end": "18:30",
        "rolling_window_points": 24,
        "vol_context": {"implied_vol": 0.22},
        "regime_mode": "smart",
        "target_session_date": None,
    }
    payload = service._build_fresh_payload_locked(
        params=params,
        cache_key="synthetic-markov-contract",
        use_memory_cache=False,
    )

    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert len(payload["rows"]) >= 100
    assert len(payload["states"]) >= 4
    assert len(payload["transition_matrix"]) == len(payload["states"])
    assert payload["correlation_regime"]["states"]
    assert payload["tape_regime"]["states"]
    assert payload["risk_thermometer"]["latest"]
    assert payload["latest"]["dominant_state_key"]
    assert payload["model_spec"]["feature_keys"]
