from __future__ import annotations

from flask import Flask

from app.api import options_bp
from app.api import options_volume as volume_api


def _app() -> Flask:
    application = Flask(__name__)
    application.config.update(TESTING=True)
    application.register_blueprint(options_bp, url_prefix="/api/options")
    return application


def test_volume_routes_remain_registered() -> None:
    rules = {rule.rule: rule.methods for rule in _app().url_map.iter_rules()}

    expected = {
        "/api/options/volume/activity",
        "/api/options/volume/summary",
        "/api/options/volume/iv-history",
        "/api/options/volume/state",
        "/api/options/volume/poll",
        "/api/options/volume/poll/all",
        "/api/options/volume/tracker/status",
        "/api/options/volume/tracker/start",
        "/api/options/volume/tracker/stop",
        "/api/options/volume/tracker/backfill",
        "/api/options/hedge/delta",
    }

    assert expected.issubset(rules)


def test_empty_hedge_request_preserves_response_contract() -> None:
    response = _app().test_client().post("/api/options/hedge/delta", json={})

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "sabr_params": {},
        "events": [],
        "summary": {"n_events": 0, "cumul_n_win": 0.0, "cumul_n_ind": 0.0},
    }


def test_native_float_handles_scalar_adapters_and_non_finite_values() -> None:
    class Scalar:
        def item(self):
            return 1.23456

    assert volume_api._native_float(Scalar(), 3) == 1.235
    assert volume_api._native_float(float("inf"), 2) == 0.0
    assert volume_api._native_float("invalid", 2) == 0.0
