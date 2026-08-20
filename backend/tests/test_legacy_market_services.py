from __future__ import annotations

from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from app.config import Config
from app.services.flow_activity_radar_service import (
    DetectionThresholds,
    FlowActivityRadarService,
)
from app.services.market_screen_capture_service import (
    MarketScreenCaptureService,
    _contextual_ocr_symbol_fix,
    _contextual_ocr_token_fix,
    _display_symbol_from_security,
    _json_clone,
    _normalize_match_text,
    _normalize_security,
    _normalize_symbol_token,
    _ocr_symbol_variant,
    _parse_iso_utc,
    _safe_float,
    _security_match_variants,
    _slugify,
    _split_security_candidates,
    _strip_accents,
)

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _token(text: str, x: float, y: float, width: float = 80) -> dict[str, object]:
    return {
        "text": text,
        "confidence": 0.99,
        "bbox": [[x, y], [x + width, y], [x + width, y + 20], [x, y + 20]],
        "left": x,
        "top": y,
        "right": x + width,
        "bottom": y + 20,
        "center_x": x + width / 2,
        "center_y": y + 10,
    }


def test_market_screen_normalizers_cover_ocr_and_market_number_variants() -> None:
    assert _strip_accents("Último preço") == "Ultimo preco"
    assert _normalize_match_text("  Último\n preço ") == "ULTIMO PRECO"
    assert _normalize_security("  ibov   index ") == "IBOV INDEX"
    assert _slugify("W 32: Básica") == "w-32-basica"
    assert _json_clone({"rows": [1]}) == {"rows": [1]}
    assert _json_clone(None) is None
    assert _parse_iso_utc("2026-08-19T12:00:00Z").tzinfo is not None
    assert _parse_iso_utc("2026-08-19T12:00:00").tzinfo is not None
    assert _parse_iso_utc("bad") is None
    assert _safe_float("↑ 138.500,25") == 138500.25
    assert _safe_float("1,234.50%") == 1234.5
    assert _safe_float("1.234.567") == 1234.567
    assert _safe_float("-") is None
    assert _split_security_candidates("IBOV Index|DOL Curncy;DI1F29") == [
        "IBOV Index",
        "DOL Curncy",
        "DI1F29",
    ]
    assert _normalize_symbol_token("IBOV Index D") == "IBOV"
    assert _display_symbol_from_security("DOL Curncy") == "DOL"
    assert _contextual_ocr_token_fix("0DF29") == "ODF29"
    assert _contextual_ocr_token_fix("C0P0M") == "COPOM"
    assert _contextual_ocr_symbol_fix(".0DF29 D") == ".ODF29"
    assert _ocr_symbol_variant("0D15") == "ODIS"
    variants = _security_match_variants("ODF29 Index")
    assert "ODF29" in variants
    assert "ODF29" in _security_match_variants("0DF29")
    assert _security_match_variants("") == set()


def test_market_screen_parses_rows_with_and_without_headers(tmp_path: Path) -> None:
    service = MarketScreenCaptureService(root_dir=str(tmp_path))
    tokens = [
        _token("Ticker", 10, 10),
        _token("Últ Preço", 330, 10),
        _token("%1D", 520, 10),
        _token("IBOV Index", 10, 60, 120),
        _token("↑138.500,25", 330, 60, 100),
        _token("+1,25%", 520, 60),
        _token("DOL Curncy", 10, 95, 120),
        _token("↓5,4321", 330, 95, 100),
        _token("-0,40%", 520, 95),
    ]
    parsed = service._parse_rows(tokens=tokens, image_width=700, image_height=300)
    assert [row["symbol"] for row in parsed["rows"]] == ["IBOV INDEX", "DOL CURNCY"]
    assert parsed["rows"][0]["direction"] == "up"
    assert parsed["rows"][1]["direction"] == "down"

    inferred = service._parse_rows(
        tokens=[
            _token("WINQ26", 10, 70, 100),
            _token("138500", 330, 70, 90),
            _token("+0.5%", 530, 70),
        ],
        image_width=700,
        image_height=300,
    )
    assert inferred["rows"][0]["price"] == 138500
    assert service._window_matches("Bloomberg - W 32: Básica", "w 32: basica")
    assert service._token_from_ocr([[[0, 0], [10, 0], [10, 10], [0, 10]], "WIN", 0.9])
    assert service._token_from_ocr("invalid") is None
    assert service._token_from_ocr([[], "", 0.1]) is None


def test_market_screen_capture_pipeline_persists_and_projects_excel_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MarketScreenCaptureService(root_dir=str(tmp_path))
    monkeypatch.setattr(Config, "MARKET_SCREEN_W32_OCR_SCALE", 1.0)
    monkeypatch.setattr(Config, "MARKET_SCREEN_W32_HISTORY_DB_ENABLE", False)
    monkeypatch.setattr(Config, "MARKET_SCREEN_W32_HISTORY_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", True)
    monkeypatch.setattr(
        service,
        "_resolve_capture_target",
        lambda **_kwargs: {
            "ok": True,
            "strategy": "fixture",
            "window_title": "W 32: Basica",
            "title_query": "W 32",
            "bbox": [0, 0, 700, 300],
        },
    )
    monkeypatch.setattr(service, "_capture_image", lambda _target: Image.new("RGB", (700, 300), "white"))
    monkeypatch.setattr(
        service,
        "_run_ocr",
        lambda _image: [
            _token("Últ Preço", 330, 10),
            _token("%1D", 520, 10),
            _token("IBOV Index", 10, 60, 120),
            _token("138500", 330, 60, 100),
            _token("+1.25%", 520, 60),
            _token("0DF29 D", 10, 95, 120),
            _token("12.50", 330, 95, 100),
            _token("-0.10%", 520, 95),
        ],
    )

    payload = service.capture_w32_basica(persist=True, save_image=False)
    assert payload["ok"] is True
    assert payload["row_count"] == 2
    assert payload["rows"][1]["symbol"] == "ODF29"
    assert Path(service.latest_path).exists()
    assert Path(service.latest_csv_path).exists()
    assert service.read_latest_capture()["capture_id"] == payload["capture_id"]

    excel = service.build_excel_compatible_payload(payload)
    assert excel["ok"] is True
    assert excel["source"] == "market_screen_w32_ocr"
    assert excel["row_count"] == 2
    assert excel["security_map"]["IBOV Index"]["fields"]["PX_LAST"] == 138500
    assert service.status()["latest_row_count"] == 2
    assert service.build_excel_compatible_payload({"ok": False, "error": "fixture"}) == {
        "ok": False,
        "source": "excel_live_workbook",
        "error": "fixture",
    }

    Path(service.latest_path).write_text("[]", encoding="utf-8")
    assert service.read_latest_capture() is None
    Path(service.latest_path).write_text("not-json", encoding="utf-8")
    assert service.read_latest_capture() is None


def test_market_screen_capture_failure_paths_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MarketScreenCaptureService(root_dir=str(tmp_path))
    monkeypatch.setattr(service, "_resolve_capture_target", lambda **_kwargs: {"ok": False, "error": "missing"})
    assert service.capture_w32_basica()["error"] == "missing"

    monkeypatch.setattr(
        service,
        "_resolve_capture_target",
        lambda **_kwargs: {"ok": True, "strategy": "fixture", "bbox": [0, 0, 10, 10]},
    )
    monkeypatch.setattr(service, "_capture_image", lambda _target: (_ for _ in ()).throw(RuntimeError("capture")))
    assert service.capture_w32_basica()["error"] == "image_capture_failed:capture"

    monkeypatch.setattr(service, "_capture_image", lambda _target: Image.new("RGB", (10, 10), "white"))
    monkeypatch.setattr(service, "_run_ocr", lambda _image: (_ for _ in ()).throw(RuntimeError("ocr")))
    assert service.capture_w32_basica(save_image=False)["error"] == "ocr_failed:ocr"
    assert service._image_is_probably_blank(Image.new("RGB", (5, 5), "white"))
    assert not service._image_is_probably_blank(Image.linear_gradient("L"))


class _FlowStore:
    def latest_snapshot(self, ticker: str | None = None) -> dict[str, object]:
        return {
            "ticker": ticker or "WINQ26",
            "received_at": "2026-08-19T13:30:00-03:00",
            "vwap": 138500,
            "rlp_vwap": 138510,
            "agent_count": 2,
        }

    def resolve_broker_name(self, agent_code: str, broker_name: object) -> str:
        return str(broker_name or f"Broker {agent_code}")


def _flow_rows(session_start_epoch: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for minute in range(8, 35):
        for code, name, side in (("101", "Alpha", 1), ("202", "Beta", -1)):
            delta = side * (160 + minute * 4)
            rows.append(
                {
                    "bucket_epoch": session_start_epoch + minute * 60,
                    "agent_code": code,
                    "broker_name": name,
                    "delta_qty": delta,
                    "delta_buy_quantity": max(delta, 0),
                    "delta_sell_quantity": abs(min(delta, 0)),
                    "delta_agression_balance": delta * 0.7,
                    "delta_maker_balance": delta * 0.2,
                    "delta_rlp_balance": delta * 0.1,
                    "sample_count": 1,
                    "first_epoch": session_start_epoch + minute * 60,
                    "last_epoch": session_start_epoch + minute * 60 + 30,
                }
            )
    return rows


def test_flow_activity_radar_builds_detected_runs_and_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FlowActivityRadarService(store=_FlowStore())
    meta = service._build_session_meta(session_date=date(2026, 8, 19), bucket_minutes=1)
    rows = _flow_rows(meta["start_epoch"])
    monkeypatch.setattr(service, "_load_minute_buckets", lambda **_kwargs: rows)

    dashboard = service.build_dashboard(ticker="WINQ26", session_date="2026-08-19", top_runs=10)
    assert dashboard["ok"] is True
    assert dashboard["ticker"] == "WINQ26"
    assert dashboard["detections"]
    assert {item["side"] for item in dashboard["detections"]} == {"buy", "sell"}
    assert dashboard["summary"]["buy_runs"] + dashboard["summary"]["sell_runs"] >= 2
    assert dashboard["reader"]["headline"]
    assert dashboard["session_flow"]


def test_flow_activity_radar_empty_states_thresholds_and_math(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FlowActivityRadarService(store=_FlowStore())
    monkeypatch.setattr(service, "_load_minute_buckets", lambda **_kwargs: [])
    empty = service.build_dashboard(ticker="WINQ26", session_date="invalid")
    assert empty["ok"] is False
    assert empty["summary"]["active_runs"] == 0

    no_ticker = FlowActivityRadarService(store=_FlowStore())
    monkeypatch.setattr(no_ticker.store, "latest_snapshot", lambda _ticker=None: {})
    assert no_ticker.build_dashboard()["ticker"] is None

    defaults = service._derive_thresholds(values=[], bucket_minutes=2)
    dynamic = service._derive_thresholds(values=[10, 20, 50, 100, 200, 400], bucket_minutes=1)
    assert defaults.start_threshold > defaults.noise_floor
    assert dynamic.reversal_threshold > dynamic.noise_floor
    assert service._linear_fit([1, 2, 3])[0] == 1
    assert service._linear_fit([1])[1] == 0
    assert service._percentile([1, 2, 3, 4], 0.5) == 3
    assert service._percentile([], 0.5) == 0
    assert service._ewma([1, 2, 3], 0.5) == [0.5, 1.25, 2.125]
    assert service._directional_consistency(values=[2, 1, -1], side=1, noise_floor=0.5) == pytest.approx(2 / 3)
    assert service._sign(-1) == -1
    assert service._sign(0) == 0
    assert service._clamp(12, 0, 10) == 10
    assert service._regularity_score([10, 10, 10]) == 1
    assert service._cadence_score([1, 2, 3, 4]) == 1
    assert service._pulse_ratio(recent=[10, 20], baseline=[5, 5]) == 3
    assert service._blended_linearity(fit_r2=0.8, recent_r2=0.6, active_minutes=10) > 0.6
    assert service._status_rank("active") < service._status_rank("inactive")
    assert service._status_weight("active") > service._status_weight("inactive")
    assert service._status_label("cooling")
    assert service._run_scope_label("detected_run")
    assert service._side_label("buy") == "comprando"
    assert service._bias_word("sell") == "vendedor"
    assert service._signed_contracts(-120) == "-120"
    assert service._signed_number(1.234, 2) == "+1,23"

    thresholds = DetectionThresholds(10, 20, 30, 25, 80, 3)
    meta = service._build_session_meta(session_date=date(2026, 8, 19), bucket_minutes=1)
    meta["latest_bucket_index"] = 5
    agent = {"agent_code": "1", "broker_name": "Noise", "points": {}}
    assert service._detect_agent_runs(agent=agent, session_meta=meta, thresholds=thresholds) == []
