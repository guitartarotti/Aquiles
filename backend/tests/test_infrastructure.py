from __future__ import annotations

import ast
import logging
from pathlib import Path

from flask import Flask

from app import create_app
from app.http import error_response, register_error_handlers
from app.services import market_screen_capture_service


class _TestConfig:
    TESTING = True
    START_BACKGROUND_SERVICES = False
    AUTH_ENABLED = False
    CORS_ORIGINS = ["http://localhost:3000"]
    APP_VERSION = "test"


def test_error_response_does_not_expose_internal_exception() -> None:
    app = Flask(__name__)
    with app.test_request_context("/api/example"):
        response, status = error_response(
            logging.getLogger("test"),
            exception=RuntimeError("database-password-should-not-leak"),
        )

    assert status == 500
    assert response.get_json() == {"success": False, "error": "Internal server error"}


def test_market_screen_capture_degrades_without_windows_bindings(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(market_screen_capture_service, "win32api", None)
    monkeypatch.setattr(market_screen_capture_service, "win32gui", None)
    service = market_screen_capture_service.MarketScreenCaptureService(root_dir=str(tmp_path))

    target = service._find_window_bbox("W 32: Basica")

    assert target == {
        "ok": False,
        "error": "windows_capture_unavailable",
        "title_query": "W 32: Basica",
    }
    assert service._monitor_rect(1) is None
    assert service.status()["windows_capture_available"] is False


def test_health_contract_preserves_request_id() -> None:
    app = create_app(_TestConfig)
    response = app.test_client().get(
        "/health",
        headers={"X-Request-ID": "contract-test"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "service": "aquiles-backend",
        "status": "ok",
        "version": "test",
    }
    assert response.headers["X-Request-ID"] == "contract-test"


def test_unexpected_api_error_uses_public_contract() -> None:
    app = create_app(_TestConfig)

    @app.get("/api/_test/failure")
    def fail_with_sensitive_message() -> None:
        raise RuntimeError("provider-token-should-not-leak")

    response = app.test_client().get("/api/_test/failure")
    payload = response.get_json()

    assert response.status_code == 500
    assert payload["success"] is False
    assert payload["error"] == "Internal server error"
    assert payload["request_id"]
    assert "provider-token" not in response.get_data(as_text=True)


def test_caught_legacy_error_is_sanitized_before_response() -> None:
    app = create_app(_TestConfig)

    @app.get("/api/_test/legacy-failure")
    def legacy_failure():
        return {
            "success": False,
            "error": "database-password-should-not-leak",
            "traceback": "Traceback: private implementation details",
            "details": {"provider_token": "secret-token"},
        }, 500

    response = app.test_client().get("/api/_test/legacy-failure")
    payload = response.get_json()
    response_text = response.get_data(as_text=True)

    assert response.status_code == 500
    assert payload["success"] is False
    assert payload["error"] == "Internal server error"
    assert payload["request_id"]
    assert "traceback" not in payload
    assert "password" not in response_text
    assert "secret-token" not in response_text


def test_plain_text_server_error_is_converted_to_safe_json() -> None:
    app = create_app(_TestConfig)

    @app.get("/api/_test/plain-failure")
    def plain_failure():
        return "provider-secret-should-not-leak", 502

    response = app.test_client().get("/api/_test/plain-failure")

    assert response.status_code == 502
    assert response.is_json
    assert response.get_json()["error"] == "Internal server error"
    assert "provider-secret" not in response.get_data(as_text=True)


def test_explicit_public_error_message_from_helper_is_preserved() -> None:
    app = create_app(_TestConfig)

    @app.get("/api/_test/safe-unavailable")
    def safe_unavailable():
        return error_response(
            logging.getLogger("test"),
            status_code=503,
            message="Market data temporarily unavailable",
        )

    response = app.test_client().get("/api/_test/safe-unavailable")

    assert response.status_code == 503
    assert response.get_json()["error"] == "Market data temporarily unavailable"


def test_successful_diagnostics_cannot_expose_internal_error_fields() -> None:
    app = create_app(_TestConfig)

    @app.get("/api/_test/diagnostics")
    def diagnostics():
        return {
            "success": True,
            "data": {
                "status": "degraded",
                "last_error": "connection refused at private-host:5432",
                "service_url": "http://private-host:5012",
                "failures": [
                    {
                        "provider": "example",
                        "error": "database connection refused",
                        "traceback": "private stack trace",
                    }
                ],
            },
        }

    response = app.test_client().get("/api/_test/diagnostics")
    payload = response.get_json()
    response_text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert payload["data"]["last_error"] == "Service unavailable"
    assert "service_url" not in payload["data"]
    assert "traceback" not in payload["data"]["failures"][0]
    assert payload["data"]["failures"][0]["error"] == "Operation failed"
    assert "private-host" not in response_text
    assert "private stack" not in response_text


def test_public_health_payload_is_sanitized() -> None:
    app = Flask(__name__)
    register_error_handlers(app)

    @app.get("/health")
    def detailed_health():
        return {
            "status": "degraded",
            "last_error": "private database address",
            "traceback": "private stack trace",
        }

    response = app.test_client().get("/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload == {"status": "degraded", "last_error": "Service unavailable"}


def test_manual_diagnostics_stay_out_of_runtime_roots() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    backend_root = repository_root / "backend"
    diagnostic_root = repository_root / "scripts" / "diagnostics"

    root_manual_scripts = sorted(
        path.name
        for pattern in ("test_*.py", "debug_*.py", "probe_*.py", "diagnose_*.py")
        for path in repository_root.glob(pattern)
    )
    backend_manual_scripts = sorted(
        path.name
        for path in backend_root.glob("*.py")
        if path.name != "run.py" and not path.name.startswith("run_")
    )
    legacy_manual_tests = sorted(path.name for path in (backend_root / "scripts").glob("test_*.py"))

    assert root_manual_scripts == []
    assert backend_manual_scripts == []
    assert legacy_manual_tests == []
    assert (diagnostic_root / "README.md").is_file()
    assert len(list(diagnostic_root.glob("**/*.py"))) >= 30


def test_manual_diagnostics_do_not_embed_credentials() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    diagnostic_root = repository_root / "scripts" / "diagnostics"
    credential_assignments: list[str] = []

    for script_path in diagnostic_root.glob("**/*.py"):
        tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target_names = [target.id for target in targets if isinstance(target, ast.Name)]
            if len(value.value) >= 16 and any(
                marker in target_name.upper()
                for target_name in target_names
                for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")
            ):
                credential_assignments.append(f"{script_path}:{node.lineno}")

    assert credential_assignments == []
