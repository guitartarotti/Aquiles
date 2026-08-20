from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.options_store import (
    OptionsStore,
    _deep_copy_json,
    _normalize_trade_date,
    _parse_iso,
)


def test_options_store_contracts_snapshots_and_oi_history(tmp_path) -> None:
    store = OptionsStore(str(tmp_path))
    assert store.read_state()["collector"]["running"] is False
    assert store.update_collector_status(running=True, run_count=1)["running"] is True
    assert _normalize_trade_date("20260819") == "2026-08-19"
    assert _normalize_trade_date(datetime(2026, 8, 18, tzinfo=timezone.utc)) == "2026-08-18"
    assert _parse_iso("bad") is None
    source = {"nested": {"value": 1}}
    copied = _deep_copy_json(source)
    copied["nested"]["value"] = 2
    assert source["nested"]["value"] == 1

    contracts = [
        {
            "option_id": "PETR4-C-30",
            "underlying_security": "PETR4",
            "expiry_date": "2026-09-18",
            "strike": 30,
            "put_call": "CALL",
            "status": "active",
        },
        {
            "option_id": "PETR4-P-28",
            "underlying_security": "PETR4",
            "expiry_date": "2026-09-18",
            "strike": 28,
            "put_call": "PUT",
            "status": "inactive",
        },
        {},
    ]
    assert store.upsert_contracts(contracts) == {"inserted": 2, "updated": 0, "total": 2}
    assert store.upsert_contracts([contracts[0]])["updated"] == 1
    assert len(store.list_contracts("PETR4")) == 2
    assert [row["option_id"] for row in store.list_contracts(only_active=True)] == [
        "PETR4-C-30"
    ]

    universe = {
        "captured_at": "2026-08-19T12:00:00Z",
        "session_date": "2026-08-19",
        "universe_version": "v1",
        "summary": {"count": 2},
    }
    assert store.save_universe_state("PETR4", universe)["universe_version"] == "v1"
    assert store.load_universe_state("PETR4")["summary"]["count"] == 2
    assert "PETR4" in store.load_universe_state()["underlyings"]

    batch = store.write_snapshot_batch(
        "critical",
        "2026-08-19",
        "batch-1",
        [{"option_id": "PETR4-C-30", "price": 2.5}, {"option_id": "PETR4-P-28", "price": 1.2}],
        {
            "captured_at": "2026-08-19T13:00:00Z",
            "underlying_security": "PETR4",
        },
    )
    assert batch["row_count"] == 2
    assert store.read_latest_snapshot("critical", "PETR4", limit=1)["rows"][0]["price"] == 2.5
    assert store.read_snapshot_batch("critical", "2026-08-19", "batch-1")["batch"][
        "batch_id"
    ] == "batch-1"
    assert store.read_snapshot_batch("critical", "2026-08-19", "missing") == {}
    assert len(store.list_snapshot_batches(session_date="2026-08-19")) == 1

    rows = [
        {
            "trade_date": "20260818",
            "option_id": "PETR4-C-30",
            "underlying_security": "PETR4",
            "expiry_date": "2026-09-18",
            "strike": 30,
            "put_call": "CALL",
            "opt_open_interest": 100,
        },
        {
            "trade_date": "2026-08-19",
            "option_id": "PETR4-C-30",
            "underlying_security": "PETR4",
            "expiry_date": "2026-09-18",
            "strike": 30,
            "put_call": "CALL",
            "opt_open_interest": 130,
        },
    ]
    assert store.upsert_oi_daily_rows(rows)["dates_written"] == 2
    assert store.get_latest_trade_date_for_option("PETR4-C-30") == "2026-08-19"
    assert store.get_latest_oi_row_before("PETR4-C-30", "2026-08-19")[
        "opt_open_interest"
    ] == 100
    assert store.recompute_oi_changes(["PETR4-C-30"])["updated_rows"] == 2
    history = store.list_oi_history(option_id="PETR4-C-30")
    assert history[0]["oi_change_abs"] == 30
    assert store.load_oi_rows_for_trade_date("2026-08-19")[0]["oi_change_pct"] == 0.3
    assert store.load_latest_oi_map(["PETR4-C-30"])["PETR4-C-30"][
        "opt_open_interest"
    ] == 130


def test_options_store_jobs_b3_ticks_and_scheduler_leases(tmp_path) -> None:
    store = OptionsStore(str(tmp_path))
    job = store.record_job_state(
        {"job_id": "job-1", "kind": "snapshot", "status": "running", "details": {"n": 1}}
    )
    assert job["job_id"] == "job-1"
    assert store.get_job("job-1")["status"] == "running"
    assert store.get_job("missing") is None

    acquired = store.try_acquire_scheduled_checkpoint(
        "model:2026-08-19:13:00",
        {
            "job_kind": "model",
            "trade_date": "2026-08-19",
            "slot": "13:00",
            "underlying_security": "IBOVE Index",
        },
        owner="worker-a",
        lease_seconds=60,
    )
    assert acquired["acquired"] is True
    denied = store.try_acquire_scheduled_checkpoint(
        "model:2026-08-19:13:00",
        {"job_kind": "model", "trade_date": "2026-08-19", "slot": "13:00"},
        owner="worker-b",
        lease_seconds=60,
    )
    assert denied["acquired"] is False
    saved = store.save_scheduled_checkpoint(
        "model:2026-08-19:13:00",
        {"status": "completed", "complete": True, "owner": "worker-a", "details": {"run": 1}},
    )
    assert saved["complete"] is True
    assert store.load_scheduled_checkpoint("model:2026-08-19:13:00")["status"] == "completed"

    store.save_backfill_checkpoint("oi:PETR4", {"last_date": "2026-08-19", "complete": False})
    assert store.load_backfill_checkpoint("oi:PETR4")["last_date"] == "2026-08-19"
    b3_rows = [
        {"symbol": "PETR4C30", "open_interest": 500},
        {"symbol": "PETR4P28", "open_interest": 300},
    ]
    assert store.save_b3_oi_rows("20260819", b3_rows)["rows_written"] == 2
    assert store.load_b3_oi_rows("2026-08-19")[0]["symbol"] == "PETR4C30"
    assert store.get_b3_oi_for_symbol("PETR4P28", "2026-08-19")["open_interest"] == 300
    assert store.list_b3_oi_dates() == ["2026-08-19"]
    assert store.append_quality_flags([{"kind": "missing_iv"}, {"kind": "stale"}]) == 2
    ticks = store.write_tick_rows(
        "PETR4-C-30",
        "2026-08-19",
        [{"captured_at": "2026-08-19T13:00:00Z", "price": 2.5}],
    )
    assert ticks["rows_written"] == 1


def test_options_store_analytics_manifests_and_user_context(tmp_path) -> None:
    store = OptionsStore(str(tmp_path))
    common = {
        "session_date": "2026-08-19",
        "captured_at": "2026-08-19T13:00:00Z",
        "underlying_security": "IBOVE Index",
        "summary": {"status": "ok"},
    }
    model = common | {"run_id": "model-1", "universe_tier": "critical"}
    assert store.write_model_run(model)["run_id"] == "model-1"
    assert store.read_model_run("model-1")["summary"]["status"] == "ok"
    assert store.read_latest_model_run("IBOVE Index")["run_id"] == "model-1"

    global_run = common | {"run_id": "global-1"}
    assert store.write_global_run(global_run)["run_id"] == "global-1"
    assert store.read_global_run("global-1")["run_id"] == "global-1"
    assert store.read_latest_global_run("IBOVE Index")["run_id"] == "global-1"

    fair = common | {"run_id": "fair-1"}
    assert store.write_fair_value_run(fair)["run_id"] == "fair-1"
    assert store.read_fair_value_run("fair-1")["run_id"] == "fair-1"
    assert store.read_latest_fair_value_run("IBOVE Index")["run_id"] == "fair-1"
    assert store.list_recent_fair_value_runs("IBOVE Index")[0]["run_id"] == "fair-1"

    correlation = common | {
        "run_id": "corr-1",
        "lookback_days": 5,
        "horizon_minutes": 15,
        "factors_signature": "usdbrl,di",
        "modes_signature": "pure",
        "status": "ok",
        "selected_sessions": ["2026-08-19"],
        "row_count": 2,
        "selected_factors": ["usdbrl", "di"],
    }
    assert store.write_intraday_correlation_run(correlation)["run_id"] == "corr-1"
    latest_correlation = store.read_latest_intraday_correlation_run(
        "IBOVE Index", 5, 15, "usdbrl,di", "pure"
    )
    assert latest_correlation and latest_correlation["run_id"] == "corr-1"

    regime = common | {"run_id": "regime-1"}
    assert store.write_regime_price_making_run(regime)["run_id"] == "regime-1"
    assert store.read_regime_price_making_run("regime-1")["run_id"] == "regime-1"
    assert store.read_latest_regime_price_making_run("IBOVE Index")["run_id"] == "regime-1"
    counts = store.append_regime_price_making_snapshots(
        session_date="20260819",
        asset_rows=[{"asset": "WIN"}],
        leg_rows=[{"leg": "rates"}],
        market_state_row={"state": "risk_off"},
        regime_row={"regime": "stress"},
    )
    assert all(value == 1 for value in counts.values())

    insight = {"summary": "Mercado defensivo"}
    thread = {"messages": [{"role": "user", "content": "Explique"}]}
    assert store.write_daily_insight("IBOVE Index", "20260819", "dealer", insight) == insight
    assert store.read_daily_insight("IBOVE Index", "2026-08-19", "dealer") == insight
    assert store.write_chat_thread("IBOVE Index", "20260819", "dealer", thread) == thread
    assert store.read_chat_thread("IBOVE Index", "2026-08-19", "dealer") == thread
    with pytest.raises(ValueError, match="run_id"):
        store.write_model_run({})
    with pytest.raises(ValueError, match="trade_date"):
        store.write_daily_insight("IBOVE Index", "", "dealer", {})


def test_options_store_volume_activity_and_iv_history(tmp_path) -> None:
    store = OptionsStore(str(tmp_path))
    store.save_volume_state({"PETR4C30": 100, "PETR4P28": 80})
    assert store.load_volume_state()["PETR4C30"] == 100
    events = [
        {
            "session_date": "2026-08-19",
            "captured_at": "2026-08-19T13:00:00Z",
            "symbol": "PETR4C30",
            "underlying_security": "PETR4",
            "volume_delta": 25,
        },
        {
            "session_date": "2026-08-19",
            "captured_at": "2026-08-19T13:01:00Z",
            "symbol": "PETR4P28",
            "underlying_security": "PETR4",
            "volume_delta": 15,
        },
    ]
    assert store.append_volume_activity(events) == 2
    assert store.append_volume_activity([]) == 0
    assert store.read_volume_activity(session_date="2026-08-19", symbol="PETR4C30")[0][
        "volume_delta"
    ] == 25
    summary = store.volume_activity_summary("2026-08-19", "PETR4")
    assert summary["event_count"] == 2
    assert summary["active_contracts"] == 2
    assert summary["total_volume_delta"] == 40

    snapshot = {
        "session_date": "2026-08-19",
        "captured_at": "2026-08-19T13:02:00Z",
        "underlying_security": "PETR4",
        "atm_iv": 0.32,
    }
    assert store.append_volume_iv_snapshot(snapshot) == 1
    assert store.append_volume_iv_snapshot({}) == 0
    history = store.read_volume_iv_history(
        session_date="2026-08-19", underlying_security="PETR4"
    )
    assert history[0]["atm_iv"] == 0.32
    assert store.read_latest_volume_iv_snapshot("PETR4")["atm_iv"] == 0.32
