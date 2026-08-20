from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from app.config import Config
from app.services.macro_options_heatmap_context_service import (
    LOCAL_TZ,
    MacroOptionsHeatmapContextService,
    _clamp,
    _curve_conditions_delta_magnitude,
    _deep_copy_json,
    _finite_float,
    _has_meaningful_curve_snapshot,
    _is_degraded_curve_snapshot,
    _is_live_excel_price_source,
    _median,
    _median_abs_deviation,
    _parse_iso,
    _session_date_from_timestamp,
)


def _service(tmp_path) -> MacroOptionsHeatmapContextService:
    service = MacroOptionsHeatmapContextService.__new__(MacroOptionsHeatmapContextService)
    service.root_dir = str(tmp_path)
    service.state_path = str(tmp_path / "state.json")
    service.fair_value_history_path = str(tmp_path / "fair-value.json")
    service.live_capture_archive_dir = str(tmp_path / "live")
    (tmp_path / "live").mkdir()
    service._lock = threading.RLock()
    service._capture_lock = threading.Lock()
    service._async_lock = threading.RLock()
    service._latest_model_run_cache = {}
    service._latest_model_run_cache_at = {}
    service._latest_fair_value_run_cache = {}
    service._latest_fair_value_run_cache_at = {}
    return service


def test_context_numeric_time_and_curve_helpers_are_defensive() -> None:
    source = {"at": datetime(2026, 8, 19, 12, tzinfo=timezone.utc)}
    cloned = _deep_copy_json(source)
    assert cloned["at"].startswith("2026-08-19")
    assert _parse_iso("2026-08-19T12:00:00Z") == datetime(
        2026, 8, 19, 12, tzinfo=timezone.utc
    )
    assert _parse_iso("bad") is None
    assert _finite_float("1.25") == 1.25
    assert _finite_float(float("inf"), 7) == 7
    assert _clamp(12, 0, 10) == 10
    assert _median([3, 1, 2]) == 2
    assert _median([4, 2]) == 3
    assert _median([]) is None
    assert _median_abs_deviation([1, 2, 3]) == 1
    assert _is_live_excel_price_source("live_reference:excel_fair_value_basket:XB1")
    assert _session_date_from_timestamp("2026-08-19T02:00:00Z") == "2026-08-18"

    meaningful = {"state": "steep", "slope_change": 0.5}
    degraded = {"state": "mixed_curve", "summary": "curva mista", "slope_change": 0}
    assert _curve_conditions_delta_magnitude(meaningful) == 0.5
    assert _has_meaningful_curve_snapshot(meaningful)
    assert not _is_degraded_curve_snapshot(meaningful)
    assert _is_degraded_curve_snapshot(degraded)
    assert not _has_meaningful_curve_snapshot({})


def test_context_state_compaction_round_trips_and_archives(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Config, "MACRO_OPTIONS_LIVE_CAPTURE_STATE_LIMIT", 2)
    service = _service(tmp_path)
    workbook_values = {
        "XB1 Index": {
            "raw_value": 138_500,
            "daily_change_pct": 0.012,
            "timestamp": "2026-08-19T13:00:00Z",
            "row_number": 4,
        },
        "IBOV Index": [136_900, 0.008],
        "": [1, 2],
    }
    factor_values = {
        "usdbrl": {"raw_value": 5.42, "daily_change_pct": 0.004, "is_live": True},
        "di": [14.9, -0.002],
    }
    snapshot = {
        "captured_at": "2026-08-19T13:00:00Z",
        "session_date": "2026-08-19",
        "underlying_security": "IBOVE Index",
        "current_future_price": 138_500,
        "current_spot_price": 136_900,
        "workbook_values": workbook_values,
        "factor_values": factor_values,
    }

    compact = service._compact_live_snapshot_for_disk(snapshot)
    assert compact["workbook_values"]["XB1 Index"] == [138_500, 0.012]
    expanded = service._expand_live_snapshot_from_disk(compact)
    assert expanded["workbook_values"]["XB1 Index"]["raw_value"] == 138_500
    assert expanded["factor_values"]["usdbrl"]["raw_value"] == 5.42
    assert service._workbook_pair_from_disk(compact["workbook_values"], "xb1 index") == (
        138_500,
        0.012,
    )
    assert service._workbook_pair_from_disk({}, "") == (None, None)

    state = service._default_state()
    state["live_capture_history"].update(
        {
            "current_session_date": "2026-08-19",
            "latest_snapshot": snapshot,
            "snapshots": [snapshot, snapshot | {"captured_at": "2026-08-19T13:01:00Z"}],
        }
    )
    state["fair_value_history"].update(
        {
            "current_session_date": "2026-08-19",
            "latest_sample": {"captured_at": "2026-08-19T13:00:00Z", "fair_value_final_future": 138_000},
            "samples": [{"captured_at": "a"}, {"captured_at": "b"}],
        }
    )
    service._save_state_unlocked(state, persist_fair_value_history=True)
    loaded = service._load_state_unlocked()
    assert loaded["live_capture_history"]["latest_snapshot"]["workbook_value_count"] == 2
    assert loaded["fair_value_history"]["samples_total"] == 2

    service._append_live_capture_archive_unlocked(snapshot)
    archive = service._load_live_capture_archive_unlocked(
        session_date="2026-08-19", underlying_security="IBOVE Index"
    )
    assert len(archive) == 1
    assert service._list_live_capture_archive_session_dates_unlocked(
        underlying_security="IBOVE Index"
    ) == ["2026-08-19"]
    series = service.read_live_capture_workbook_series(
        session_date="2026-08-19",
        underlying_security="IBOVE Index",
        security="XB1 Index",
        include_recent_state=True,
    )
    assert series[-1]["raw_value"] == 138_500
    latest = service.read_live_capture_latest_workbook_value(
        underlying_security="IBOVE Index", security="XB1 Index"
    )
    assert latest and latest["session_date"] == "2026-08-19"
    assert service.read_live_capture_snapshots(session_date="2026-08-19")

    archive_path = service._live_capture_archive_path(
        session_date="2026-08-19", underlying_security="IBOVE Index"
    )
    with open(archive_path, "a", encoding="utf-8") as handle:
        handle.write("not-json\n")
        handle.write(json.dumps([]) + "\n")
    assert len(
        service._load_live_capture_archive_unlocked(
            session_date="2026-08-19", underlying_security="IBOVE Index"
        )
    ) == 1


def test_context_samples_projection_and_stabilization(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)
    payload = {
        "captured_at": "2026-08-19T13:00:00Z",
        "session_date": "2026-08-19",
        "summary": {
            "current_future_price": 138_500,
            "current_spot_price": 136_900,
            "fair_value_final_future": 138_000,
            "fair_value_band_low": 137_800,
            "fair_value_band_high": 138_200,
            "quality_adjusted_fair_value_xb1": 137_950,
            "core_fair_value_xb1": 138_050,
            "quality_ribbon": {"upper": 138_250, "lower": 137_750, "width": 500},
            "core_legs": {"rates": {"contribution_points": 100}},
            "shadow_legs": {"credit": {"quality_impact": -40}},
            "block_contributions": {"macro_structural": {"rates": 100, "fx": -50}},
            "live_factor_rows": [
                {"factor": "di", "label": "DI", "block": "rates", "feature_zscore": 1.5},
                {"factor": "usdbrl", "label": "USD/BRL", "block": "fx", "feature_zscore": -2},
            ],
            "us_rates_context": {"summary_state": "hawkish"},
        },
    }
    sample = service._sample_from_fair_value_payload(payload)
    assert sample["mispricing_value"] == 500
    assert sample["fair_value_model_version"] == "fair_value_ois_v2"
    assert [row["tone"] for row in sample["block_tones"]] == ["buy", "sell"]

    reprojected = service._reproject_leg_buckets(sample)
    assert reprojected["core_legs"]["rates"]["implied_fair_value_xb1"] == 138_600
    shifted = service._shift_projected_fair_value_fields(reprojected, 50)
    assert shifted["fair_value_final_future"] == 138_050
    assert shifted["quality_ribbon"]["upper"] == 138_300

    previous = shifted | {
        "current_future_price": 138_600,
        "current_spot_price": 137_000,
        "current_price_source": "live_reference:excel_fair_value_basket:XB1 Index",
        "curve_conditions": {"state": "steep", "slope_change": 0.4},
    }
    stale = shifted | {
        "current_future_price": 138_000,
        "current_price_source": "stored_snapshot",
        "curve_conditions": {"state": "mixed_curve", "slope_change": 0},
    }
    stabilized = service._stabilize_sample_with_previous_live_quote(previous, stale)
    stabilized = service._stabilize_curve_conditions_with_previous_sample(previous, stabilized)
    assert stabilized["current_future_price"] == 138_600
    assert stabilized["curve_conditions"]["slope_change"] == 0.4
    assert service._find_latest_trusted_live_sample([stale, previous]) == previous

    monkeypatch.setattr(Config, "MACRO_OPTIONS_FAIR_VALUE_SAMPLE_LIMIT", 120)
    state = service._default_state()
    state = service._append_fair_value_sample(state, sample)
    assert state["fair_value_history"]["latest_sample"] == sample
    snapshot = {
        "ok": True,
        "captured_at": "2026-08-19T13:00:00Z",
        "session_date": "2026-08-19",
        "underlying_security": "IBOVE Index",
        "current_future_price": 138_500,
        "workbook_values": {"XB1 Index": [138_500, 0.01]},
    }
    assert service._is_valid_live_snapshot(snapshot)
    state = service._append_live_capture_snapshot(state, snapshot)
    assert state["live_capture_history"]["latest_snapshot"] == snapshot


def test_context_gamma_regions_async_merge_and_capture_schedule(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)
    model = {
        "run_id": "run-1",
        "captured_at": "2026-08-19T12:00:00Z",
        "summary": {"forward_price": 138_500, "spot_price": 136_900},
        "strike_profiles": [
            {
                "strike": 137_000,
                "gex_notional_future_net": 2_000_000,
                "open_interest_total": 100,
                "open_interest_call": 70,
                "open_interest_put": 30,
                "open_interest_imbalance": 40,
            },
            {
                "strike": 139_000,
                "gex_notional_future_net": -3_000_000,
                "open_interest_total": 120,
                "open_interest_call": 40,
                "open_interest_put": 80,
                "open_interest_imbalance": -40,
            },
        ],
        "pressure": {
            "zero_pressure": {"spot": 137_500},
            "max_acceleration": {"spot": 138_000},
            "pinning_band": {"low": 137_000, "high": 137_400},
            "acceleration_band": {"low": 138_200, "high": 138_600},
        },
    }
    gamma = service._build_gamma_context(
        "IBOVE Index",
        model,
        {"summary": {"fair_value_final_future": 138_100}},
        {"current_future_price": 138_500, "current_spot_price": 136_900},
    )
    assert gamma["summary"]["region_count"] == 2
    assert {row["gamma_sign"] for row in gamma["regions"]} == {"positive", "negative"}
    assert gamma["summary"]["special_region_count"] == 4
    assert service._estimate_gamma_step([137_000, 137_500, 138_000], 138_000) == 500
    assert service._build_price_band(100, 10) == (92, 108)

    merged = service._merge_async_collector_fields(
        {"last_projection_completed_at": "2026-08-19T10:00:00Z"},
        {
            "last_projection_completed_at": "2026-08-19T11:00:00Z",
            "last_projection_error": None,
            "intraday_correlation_live": {"last_refreshed_at": "2026-08-19T11:05:00Z"},
        },
    )
    assert merged["last_projection_completed_at"].endswith("11:00:00Z")
    assert merged["intraday_correlation_live"]["last_refreshed_at"].endswith("11:05:00Z")

    now = datetime(2026, 8, 19, 12, tzinfo=LOCAL_TZ)
    old = (now.astimezone(timezone.utc) - timedelta(hours=1)).isoformat()
    recent = now.astimezone(timezone.utc).isoformat()
    assert service._should_capture_live_snapshot({}, now)
    assert service._should_capture_live_snapshot(
        {"live_capture_history": {"latest_snapshot": {"captured_at": old}}}, now
    )
    assert not service._should_capture_live_snapshot(
        {"live_capture_history": {"latest_snapshot": {"captured_at": recent}}}, now
    )
    assert service._should_capture_fair_value_sample({}, now, force=True)

    monkeypatch.setattr(Config, "OPTIONS_WYRM_AUTORUN_ENABLE", False)
    assert not service._should_run_wyrm({}, now)
    assert service._should_run_wyrm({}, now, force=True)
