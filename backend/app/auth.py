"""Authentication and role-based access control for Aquiles HTTP services."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Iterable, Mapping, TypeVar

from flask import Flask, Response, current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

AUTH_EXTENSION_KEY = "aquiles_auth"
AUTH_TOKEN_SALT = "aquiles-access-token-v1"
VALID_ROLES = frozenset({"viewer", "operator", "admin"})
ROLE_LEVEL = {"viewer": 10, "operator": 20, "admin": 30}
PUBLIC_PATHS = frozenset({"/health", "/api/auth/login"})
ADMIN_PATH_SUFFIXES = (
    "/start",
    "/stop",
    "/reset",
    "/backfill",
    "/rebuild",
    "/hard-refresh",
    "/close-env",
)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class AuthPrincipal:
    """Authenticated identity made available through ``flask.g``."""

    username: str
    roles: frozenset[str]

    def has_role(self, required_role: str) -> bool:
        highest_level = max((ROLE_LEVEL.get(role, 0) for role in self.roles), default=0)
        return highest_level >= ROLE_LEVEL[required_role]

    def as_dict(self) -> dict[str, Any]:
        return {"username": self.username, "roles": sorted(self.roles)}


@dataclass(frozen=True)
class AuthUser:
    username: str
    password_hash: str
    roles: frozenset[str]
    active: bool = True


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    token_secret: str
    token_ttl_seconds: int
    login_max_attempts: int
    login_window_seconds: int
    users: Mapping[str, AuthUser]


class LoginRateLimiter:
    """Small per-process limiter for the interactive login endpoint."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max(max_attempts, 1)
        self.window_seconds = max(window_seconds, 1)
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = self._recent_attempts(key, now)
            return len(attempts) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            attempts = self._recent_attempts(key, now)
            attempts.append(now)
            self._attempts[key] = attempts

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def _recent_attempts(self, key: str, now: float) -> list[float]:
        threshold = now - self.window_seconds
        attempts = [attempt for attempt in self._attempts.get(key, []) if attempt >= threshold]
        if attempts:
            self._attempts[key] = attempts
        else:
            self._attempts.pop(key, None)
        return attempts


class AuthManager:
    """Issue and validate signed access tokens shared by Aquiles services."""

    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings
        self.serializer = URLSafeTimedSerializer(
            settings.token_secret,
            salt=AUTH_TOKEN_SALT,
        )
        self.rate_limiter = LoginRateLimiter(
            settings.login_max_attempts,
            settings.login_window_seconds,
        )

    @property
    def ready(self) -> bool:
        return not self.settings.enabled or bool(
            self.settings.token_secret and self.settings.users
        )

    def authenticate_credentials(self, username: str, password: str) -> AuthPrincipal | None:
        user = self.settings.users.get(username.casefold())
        password_hash = user.password_hash if user else _dummy_password_hash()
        password_matches = check_password_hash(password_hash, password)
        if not user or not user.active or not password_matches:
            return None
        return AuthPrincipal(username=user.username, roles=user.roles)

    def issue_token(self, principal: AuthPrincipal) -> str:
        return self.serializer.dumps(
            {
                "version": 1,
                "subject": principal.username,
                "roles": sorted(principal.roles),
                "token_id": uuid.uuid4().hex,
            }
        )

    def validate_token(self, token: str) -> AuthPrincipal:
        payload = self.serializer.loads(
            token,
            max_age=self.settings.token_ttl_seconds,
        )
        if payload.get("version") != 1:
            raise BadSignature("Unsupported token version")

        username = str(payload.get("subject") or "").strip()
        roles = _normalize_roles(payload.get("roles") or [])
        user = self.settings.users.get(username.casefold())
        if not username or not roles or not user or not user.active:
            raise BadSignature("Invalid token subject")
        if not roles.issubset(user.roles):
            raise BadSignature("Token roles are no longer valid")
        return AuthPrincipal(username=user.username, roles=roles)


_dummy_hash: str | None = None
_dummy_hash_lock = threading.Lock()


def _dummy_password_hash() -> str:
    global _dummy_hash
    with _dummy_hash_lock:
        if _dummy_hash is None:
            _dummy_hash = generate_password_hash(uuid.uuid4().hex)
        return _dummy_hash


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_roles(raw_roles: Iterable[str]) -> frozenset[str]:
    roles = frozenset(str(role).strip().lower() for role in raw_roles)
    return roles.intersection(VALID_ROLES)


def _load_users(raw_users: str) -> Mapping[str, AuthUser]:
    if not raw_users.strip():
        return {}
    try:
        payload = json.loads(raw_users)
    except json.JSONDecodeError as exc:
        raise ValueError("AQUILES_AUTH_USERS_JSON must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("AQUILES_AUTH_USERS_JSON must be a JSON object")

    users: dict[str, AuthUser] = {}
    for username, record in payload.items():
        normalized_username = str(username).strip()
        if not normalized_username or not isinstance(record, dict):
            raise ValueError("Each authentication user must be a named JSON object")
        password_hash = str(record.get("password_hash") or "").strip()
        roles = _normalize_roles(record.get("roles") or [])
        if not password_hash or not roles:
            raise ValueError(f"Authentication user {normalized_username!r} is incomplete")
        user = AuthUser(
            username=normalized_username,
            password_hash=password_hash,
            roles=roles,
            active=bool(record.get("active", True)),
        )
        users[normalized_username.casefold()] = user
    return users


def _settings_from_app(app: Flask) -> AuthSettings:
    enabled = bool(app.config.get("AUTH_ENABLED", _env_bool("AQUILES_AUTH_ENABLED", True)))
    token_secret_source = (
        app.config["AUTH_TOKEN_SECRET"]
        if "AUTH_TOKEN_SECRET" in app.config
        else os.environ.get("AQUILES_AUTH_TOKEN_SECRET", "")
    )
    users_source = (
        app.config["AUTH_USERS_JSON"]
        if "AUTH_USERS_JSON" in app.config
        else os.environ.get("AQUILES_AUTH_USERS_JSON", "")
    )
    token_secret = str(token_secret_source or "").strip()
    raw_users = str(users_source or "")
    return AuthSettings(
        enabled=enabled,
        token_secret=token_secret,
        token_ttl_seconds=max(
            int(app.config.get("AUTH_TOKEN_TTL_SECONDS", os.environ.get("AQUILES_AUTH_TOKEN_TTL_SECONDS", 28800))),
            60,
        ),
        login_max_attempts=max(
            int(app.config.get("AUTH_LOGIN_MAX_ATTEMPTS", os.environ.get("AQUILES_AUTH_LOGIN_MAX_ATTEMPTS", 5))),
            1,
        ),
        login_window_seconds=max(
            int(app.config.get("AUTH_LOGIN_WINDOW_SECONDS", os.environ.get("AQUILES_AUTH_LOGIN_WINDOW_SECONDS", 300))),
            1,
        ),
        users=_load_users(raw_users),
    )


def _json_error(message: str, status_code: int) -> tuple[Response, int]:
    payload: dict[str, Any] = {"success": False, "error": message}
    request_id = getattr(g, "request_id", None)
    if request_id:
        payload["request_id"] = request_id
    response = jsonify(payload)
    if status_code == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response, status_code


def _extract_bearer_token() -> str | None:
    scheme, _, credentials = request.headers.get("Authorization", "").partition(" ")
    if scheme.casefold() != "bearer" or not credentials.strip():
        return None
    return credentials.strip()


def is_admin_operation(method: str, path: str) -> bool:
    """Return whether an HTTP operation changes privileged runtime state."""
    normalized_path = str(path or "").rstrip("/")
    return str(method or "").upper() == "DELETE" or normalized_path.endswith(
        ADMIN_PATH_SUFFIXES
    )


def _required_role() -> str:
    view = current_app.view_functions.get(request.endpoint or "")
    explicit_role = getattr(view, "_aquiles_required_role", None)
    if explicit_role:
        return explicit_role
    if is_admin_operation(request.method, request.path):
        return "admin"
    if request.method in {"POST", "PUT", "PATCH"}:
        return "operator"
    return "viewer"


def require_role(role: str) -> Callable[[F], F]:
    """Override the default method-based role for a route."""

    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        raise ValueError(f"Unknown Aquiles role: {role}")

    def decorator(view: F) -> F:
        setattr(view, "_aquiles_required_role", normalized_role)

        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            return view(*args, **kwargs)

        setattr(wrapped, "_aquiles_required_role", normalized_role)
        return wrapped  # type: ignore[return-value]

    return decorator


def register_auth(app: Flask, *, expose_login: bool = False) -> AuthManager:
    """Install fail-closed authentication and RBAC on a Flask application."""

    logger = logging.getLogger("aquiles.auth")
    if "AUTH_ENABLED" not in app.config:
        # Standalone services do not use the main app factory, so load the same
        # environment-backed authentication settings explicitly.
        from .config import Config

        for setting_name in (
            "AUTH_ENABLED",
            "AUTH_TOKEN_SECRET",
            "AUTH_USERS_JSON",
            "AUTH_TOKEN_TTL_SECONDS",
            "AUTH_LOGIN_MAX_ATTEMPTS",
            "AUTH_LOGIN_WINDOW_SECONDS",
        ):
            app.config.setdefault(setting_name, getattr(Config, setting_name))
    try:
        settings = _settings_from_app(app)
    except (TypeError, ValueError) as exc:
        logger.error("Invalid authentication configuration: %s", exc)
        settings = AuthSettings(True, "", 28800, 5, 300, {})
    manager = AuthManager(settings)
    app.extensions[AUTH_EXTENSION_KEY] = manager

    @app.before_request
    def authenticate_request():
        if request.method == "OPTIONS" or request.path in PUBLIC_PATHS:
            return None
        if not request.path.startswith("/api/"):
            return None
        if not manager.settings.enabled:
            g.auth_principal = AuthPrincipal("auth-disabled", frozenset({"admin"}))
            return None
        if not manager.ready:
            logger.error("Authentication is enabled but has no secret or configured users")
            return _json_error("Authentication service is not configured", 503)

        token = _extract_bearer_token()
        if not token:
            return _json_error("Authentication required", 401)
        try:
            principal = manager.validate_token(token)
        except SignatureExpired:
            return _json_error("Access token expired", 401)
        except BadSignature:
            return _json_error("Invalid access token", 401)

        required_role = _required_role()
        if not principal.has_role(required_role):
            logger.warning(
                "access denied user=%s role=%s method=%s path=%s",
                principal.username,
                required_role,
                request.method,
                request.path,
            )
            return _json_error("Insufficient permissions", 403)
        g.auth_principal = principal
        return None

    if expose_login:
        _register_auth_routes(app, manager, logger)
    return manager


def _register_auth_routes(app: Flask, manager: AuthManager, logger: logging.Logger) -> None:
    @app.post("/api/auth/login")
    def auth_login():
        if not manager.settings.enabled:
            return _json_error("Authentication is disabled", 409)
        if not manager.ready:
            return _json_error("Authentication service is not configured", 503)

        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username") or "").strip()[:128]
        password = str(payload.get("password") or "")[:1024]
        rate_key = f"{request.remote_addr or 'unknown'}:{username.casefold()}"
        if manager.rate_limiter.is_blocked(rate_key):
            logger.warning("login rate limited username=%s address=%s", username, request.remote_addr)
            return _json_error("Too many login attempts", 429)

        principal = manager.authenticate_credentials(username, password)
        if principal is None:
            manager.rate_limiter.record_failure(rate_key)
            logger.warning("login failed username=%s address=%s", username, request.remote_addr)
            return _json_error("Invalid username or password", 401)

        manager.rate_limiter.clear(rate_key)
        logger.info("login succeeded username=%s address=%s", principal.username, request.remote_addr)
        return jsonify(
            {
                "success": True,
                "data": {
                    "access_token": manager.issue_token(principal),
                    "token_type": "Bearer",
                    "expires_in": manager.settings.token_ttl_seconds,
                    "user": principal.as_dict(),
                },
            }
        )

    @app.get("/api/auth/me")
    @require_role("viewer")
    def auth_me():
        principal: AuthPrincipal = g.auth_principal
        return jsonify({"success": True, "data": {"user": principal.as_dict()}})


def generate_user_record(password: str, roles: Iterable[str]) -> dict[str, Any]:
    """Build the JSON-safe record expected by ``AQUILES_AUTH_USERS_JSON``."""

    normalized_roles = _normalize_roles(roles)
    if not password or not normalized_roles:
        raise ValueError("A password and at least one valid role are required")
    return {
        "password_hash": generate_password_hash(password),
        "roles": sorted(normalized_roles),
        "active": True,
    }
