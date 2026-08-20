from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.options_global_modeling import OptionsGlobalTriangulationService


def _local_model_run(underlying: str = "IBOVE Index") -> dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat()
    return {
        "run_id": f"model-{underlying}",
        "captured_at": captured_at,
        "session_date": captured_at[:10],
        "underlying_security": underlying,
        "summary": {
            "spot_price": 100,
            "forward_price": 101,
            "future_basis_points": 1,
            "gex_total": 2_500_000,
            "vex_total": -350_000,
            "cex_total": 180_000,
        },
        "pressure": {
            "pinning_band": {"low": 99, "high": 101},
            "max_acceleration": {"spot": 104},
            "zero_pressure": {"spot": 100.5},
        },
        "dealer_inference": {
            "comparison": {
                "reference_dealer_inference_value": 100.2,
                "reference_dealer_inference_future_value": 101.2,
                "reference_confidence": 0.88,
            },
            "rows": [
                {"strike": 98, "iv_skew_score": -0.25},
                {"strike": 102, "iv_skew_score": -0.18},
            ],
        },
        "strike_profiles": [
            {"strike": 96, "gex": 900_000, "open_interest": 2000},
            {"strike": 100, "gex": 1_200_000, "open_interest": 3500},
            {"strike": 104, "gex": -700_000, "open_interest": 1800},
        ],
        "range_projection": {
            "enabled": True,
            "bands": [
                {
                    "label": "1 sigma",
                    "adjusted_upper_spot": 104,
                    "adjusted_lower_spot": 96,
                    "adjusted_upper_future": 105,
                    "adjusted_lower_future": 97,
                },
                {
                    "label": "2 sigma",
                    "adjusted_upper_spot": 108,
                    "adjusted_lower_spot": 92,
                    "adjusted_upper_future": 109,
                    "adjusted_lower_future": 93,
                },
            ],
        },
    }


class _GlobalStore:
    def read_latest_model_run(self, underlying: str) -> dict[str, Any]:
        return _local_model_run(underlying)

    def write_global_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"run_id": payload["run_id"], "stored": True}

    def read_latest_global_run(self, underlying: str) -> dict[str, Any]:
        return {"underlying_security": underlying, "run_id": "latest-global"}

    def read_global_run(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id}


class _Bloomberg:
    def fetch_reference_securities(self, securities: list[str]) -> dict[str, Any]:
        rows = []
        for index, security in enumerate(securities):
            rows.append(
                {
                    "ok": True,
                    "security": security,
                    "price": 100 + index * 5,
                    "fields": {
                        "PX_LAST": 100 + index * 5,
                        "IVOL_MID": 0.18 + index * 0.005,
                    },
                }
            )
        return {"rows": rows, "status": {"session_ok": True}}

    def fetch_intraday_bars(self, security: str, **_kwargs: Any) -> dict[str, Any]:
        seed = sum(ord(char) for char in security) % 7
        start = datetime.now(timezone.utc) - timedelta(minutes=150)
        rows = []
        for index in range(31):
            trend = (index * (0.08 + seed * 0.01)) + ((index % 3) - 1) * 0.03
            rows.append(
                {
                    "event_time": (start + timedelta(minutes=index * 5)).isoformat(),
                    "close": 100 + seed * 3 + trend,
                }
            )
        return {"rows": rows, "status": {"session_ok": True}}


class _LocalModeling:
    def run_latest(self, underlying_security: str, **_kwargs: Any) -> dict[str, Any]:
        return _local_model_run(underlying_security)


def test_global_options_triangulation_runs_all_financial_layers() -> None:
    store = _GlobalStore()
    service = OptionsGlobalTriangulationService(
        store=store,
        bloomberg=_Bloomberg(),
        local_modeling=_LocalModeling(),
    )
    payload = service.run_latest(
        underlying_security="IBOVE Index",
        refresh_local_model=False,
        persist=True,
    )

    assert payload["underlying_security"] == "IBOVE Index"
    assert payload["prepared_inputs"]["asset_count"] >= 4
    assert payload["dynamic_beta_model"]["relationships"]
    assert payload["distortion_band"]["distortion_regime"]
    assert payload["structural_scores"]["per_asset_scores"]
    assert payload["regime"]["global_regime"]
    assert payload["summary"]["asset_states"]
    assert payload["summary"]["desk_summary"]
    assert payload["cross_asset_level_map"]["enabled"] is True
    assert payload["persisted"]["stored"] is True
    assert service.read_latest_run("IBOVE Index")["run_id"] == "latest-global"
    assert service.read_run("run-1")["run_id"] == "run-1"


def test_global_options_refreshes_stale_local_model() -> None:
    class _StaleStore(_GlobalStore):
        def read_latest_model_run(self, underlying: str) -> dict[str, Any]:
            payload = _local_model_run(underlying)
            payload["captured_at"] = "2020-01-01T00:00:00Z"
            return payload

    service = OptionsGlobalTriangulationService(
        store=_StaleStore(),
        bloomberg=_Bloomberg(),
        local_modeling=_LocalModeling(),
    )
    payload = service.run_latest("IBOVE Index", refresh_local_model=False, persist=False)
    assert payload["source"]["local_model_run_id"] == "model-IBOVE Index"
