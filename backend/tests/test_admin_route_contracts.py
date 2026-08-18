from __future__ import annotations

import importlib
from pathlib import Path

from app import create_app
from app.auth import is_admin_operation
from app.config import Config


class RouteAuditConfig(Config):
    TESTING = True
    START_BACKGROUND_SERVICES = False
    AUTH_ENABLED = False


def _http_service_apps():
    backend_root = Path(__file__).resolve().parents[1]
    yield "aquiles-backend", create_app(RouteAuditConfig)
    for runner_path in sorted(backend_root.glob("run*_service.py")):
        module = importlib.import_module(runner_path.stem)
        yield runner_path.stem, module.app


def test_admin_operation_policy_covers_destructive_and_runtime_actions() -> None:
    assert is_admin_operation("DELETE", "/api/report/report-1")
    assert is_admin_operation("POST", "/api/simulation/start")
    assert is_admin_operation("POST", "/api/simulation/stop/")
    assert is_admin_operation("POST", "/api/graph/project/project-1/reset")
    assert is_admin_operation("POST", "/api/options/history/backfill")
    assert is_admin_operation("POST", "/api/v1/nport/analytics/rebuild")
    assert is_admin_operation("POST", "/api/options/hard-refresh")
    assert not is_admin_operation("GET", "/api/options/model/latest")
    assert not is_admin_operation("POST", "/api/options/model/run")


def test_every_admin_operation_declares_admin_role_explicitly() -> None:
    audited_routes: list[str] = []
    missing_declarations: list[str] = []

    for app_name, application in _http_service_apps():
        for rule in application.url_map.iter_rules():
            view = application.view_functions[rule.endpoint]
            for method in sorted(set(rule.methods or ()) - {"HEAD", "OPTIONS"}):
                if not is_admin_operation(method, rule.rule):
                    continue
                route_label = f"{app_name}: {method} {rule.rule}"
                audited_routes.append(route_label)
                if getattr(view, "_aquiles_required_role", None) != "admin":
                    missing_declarations.append(route_label)

    assert len(audited_routes) >= 40
    assert missing_declarations == []
