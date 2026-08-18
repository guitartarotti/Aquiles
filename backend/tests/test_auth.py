from __future__ import annotations

import json

import pytest
from flask import Flask, g, jsonify
from itsdangerous import SignatureExpired
from werkzeug.security import generate_password_hash

from app.auth import AUTH_EXTENSION_KEY, generate_user_record, register_auth, require_role


@pytest.fixture(scope="module")
def auth_users_json() -> str:
    return json.dumps(
        {
            "reader": {
                "password_hash": generate_password_hash("reader-password"),
                "roles": ["viewer"],
            },
            "operator": {
                "password_hash": generate_password_hash("operator-password"),
                "roles": ["operator"],
            },
            "admin": {
                "password_hash": generate_password_hash("admin-password"),
                "roles": ["admin"],
            },
            "inactive": {
                "password_hash": generate_password_hash("inactive-password"),
                "roles": ["viewer"],
                "active": False,
            },
        }
    )


@pytest.fixture()
def app(auth_users_json: str) -> Flask:
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        AUTH_ENABLED=True,
        AUTH_TOKEN_SECRET="test-token-secret-with-sufficient-entropy",
        AUTH_USERS_JSON=auth_users_json,
        AUTH_TOKEN_TTL_SECONDS=3600,
        AUTH_LOGIN_MAX_ATTEMPTS=2,
        AUTH_LOGIN_WINDOW_SECONDS=300,
    )
    register_auth(application, expose_login=True)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.get("/api/data")
    def read_data():
        return jsonify({"user": g.auth_principal.username})

    @application.post("/api/jobs")
    def run_job():
        return {"status": "started"}

    @application.post("/api/collector/start")
    @require_role("admin")
    def start_collector():
        return {"status": "started"}

    @application.delete("/api/data")
    def delete_data():
        return {"status": "deleted"}

    @application.post("/api/policy")
    @require_role("admin")
    def explicit_admin_policy():
        return {"status": "accepted"}

    return application


def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]["access_token"]


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_login_are_public_but_business_api_is_protected(app: Flask) -> None:
    client = app.test_client()

    assert client.get("/health").status_code == 200
    response = client.get("/api/data")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.get_json()["error"] == "Authentication required"


def test_login_returns_identity_and_signed_token(app: Flask) -> None:
    client = app.test_client()
    token = _login(client, "reader", "reader-password")

    response = client.get("/api/auth/me", headers=_authorization(token))

    assert response.status_code == 200
    assert response.get_json()["data"]["user"] == {
        "username": "reader",
        "roles": ["viewer"],
    }


def test_viewer_can_read_but_cannot_run_commands(app: Flask) -> None:
    client = app.test_client()
    token = _login(client, "reader", "reader-password")

    assert client.get("/api/data", headers=_authorization(token)).status_code == 200
    response = client.post("/api/jobs", headers=_authorization(token))

    assert response.status_code == 403
    assert response.get_json()["error"] == "Insufficient permissions"


def test_operator_can_run_jobs_but_not_admin_operations(app: Flask) -> None:
    client = app.test_client()
    token = _login(client, "operator", "operator-password")
    headers = _authorization(token)

    assert client.post("/api/jobs", headers=headers).status_code == 200
    assert client.post("/api/collector/start", headers=headers).status_code == 403
    assert client.delete("/api/data", headers=headers).status_code == 403
    assert client.post("/api/policy", headers=headers).status_code == 403


def test_admin_has_full_access(app: Flask) -> None:
    client = app.test_client()
    token = _login(client, "admin", "admin-password")
    headers = _authorization(token)

    assert client.get("/api/data", headers=headers).status_code == 200
    assert client.post("/api/jobs", headers=headers).status_code == 200
    assert client.post("/api/collector/start", headers=headers).status_code == 200
    assert client.delete("/api/data", headers=headers).status_code == 200
    assert client.post("/api/policy", headers=headers).status_code == 200


def test_invalid_credentials_are_rate_limited(app: Flask) -> None:
    client = app.test_client()

    first = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})
    second = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})
    blocked = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429


def test_inactive_user_cannot_log_in(app: Flask) -> None:
    response = app.test_client().post(
        "/api/auth/login",
        json={"username": "inactive", "password": "inactive-password"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Invalid username or password"


def test_tampered_and_escalated_tokens_are_rejected(app: Flask) -> None:
    client = app.test_client()
    reader_token = _login(client, "reader", "reader-password")
    manager = app.extensions[AUTH_EXTENSION_KEY]
    escalated_token = manager.serializer.dumps(
        {
            "version": 1,
            "subject": "reader",
            "roles": ["admin"],
            "token_id": "role-escalation-attempt",
        }
    )

    tampered = client.get("/api/data", headers=_authorization(f"{reader_token}tampered"))
    escalated = client.get("/api/data", headers=_authorization(escalated_token))

    assert tampered.status_code == 401
    assert tampered.get_json()["error"] == "Invalid access token"
    assert escalated.status_code == 401
    assert escalated.get_json()["error"] == "Invalid access token"


def test_expired_token_has_a_specific_public_error(app: Flask, monkeypatch) -> None:
    manager = app.extensions[AUTH_EXTENSION_KEY]

    def raise_expired(*_args, **_kwargs):
        raise SignatureExpired("expired")

    monkeypatch.setattr(manager.serializer, "loads", raise_expired)
    response = app.test_client().get(
        "/api/data",
        headers=_authorization("expired-token"),
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.get_json()["error"] == "Access token expired"


def test_invalid_role_policy_is_rejected_during_startup() -> None:
    with pytest.raises(ValueError, match="Unknown Aquiles role"):
        require_role("superuser")


def test_enabled_auth_without_users_fails_closed() -> None:
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        AUTH_ENABLED=True,
        AUTH_TOKEN_SECRET="configured-secret",
        AUTH_USERS_JSON="",
    )
    register_auth(application)

    @application.get("/api/data")
    def read_data():
        return {"sensitive": True}

    response = application.test_client().get("/api/data")

    assert response.status_code == 503
    assert response.get_json()["error"] == "Authentication service is not configured"


@pytest.mark.parametrize(
    "raw_users",
    [
        "not-json",
        "[]",
        json.dumps({"reader": "invalid-record"}),
        json.dumps({"reader": {"password_hash": "", "roles": ["viewer"]}}),
    ],
)
def test_invalid_user_configuration_fails_closed(raw_users: str) -> None:
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        AUTH_ENABLED=True,
        AUTH_TOKEN_SECRET="configured-secret",
        AUTH_USERS_JSON=raw_users,
    )
    register_auth(application)

    @application.get("/api/data")
    def read_data():
        return {"sensitive": True}

    response = application.test_client().get("/api/data")

    assert response.status_code == 503
    assert response.get_json()["error"] == "Authentication service is not configured"


def test_disabled_auth_allows_api_access_but_disables_login() -> None:
    application = Flask(__name__)
    application.config.update(TESTING=True, AUTH_ENABLED=False)
    register_auth(application, expose_login=True)

    @application.post("/api/jobs")
    def run_job():
        return {"user": g.auth_principal.username}

    client = application.test_client()
    api_response = client.post("/api/jobs")
    login_response = client.post("/api/auth/login", json={})

    assert api_response.status_code == 200
    assert api_response.get_json()["user"] == "auth-disabled"
    assert login_response.status_code == 409
    assert login_response.get_json()["error"] == "Authentication is disabled"


def test_options_and_non_api_routes_bypass_authentication(app: Flask) -> None:
    @app.get("/status")
    def status():
        return {"status": "ok"}

    client = app.test_client()

    assert client.open("/api/data", method="OPTIONS").status_code == 200
    assert client.get("/status").status_code == 200


def test_token_is_accepted_by_an_independent_service(app: Flask, auth_users_json: str) -> None:
    token = _login(app.test_client(), "reader", "reader-password")
    service = Flask("independent-service")
    service.config.update(
        TESTING=True,
        AUTH_ENABLED=True,
        AUTH_TOKEN_SECRET="test-token-secret-with-sufficient-entropy",
        AUTH_USERS_JSON=auth_users_json,
    )
    register_auth(service)

    @service.get("/api/status")
    def status():
        return {"status": "ok"}

    response = service.test_client().get("/api/status", headers=_authorization(token))

    assert response.status_code == 200


def test_generated_user_record_contains_a_hash_and_normalized_roles() -> None:
    record = generate_user_record("strong-password", ["ADMIN", "viewer", "unknown"])

    assert record["active"] is True
    assert record["roles"] == ["admin", "viewer"]
    assert record["password_hash"] != "strong-password"

    with pytest.raises(ValueError, match="password"):
        generate_user_record("", ["admin"])
