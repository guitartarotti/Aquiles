"""Shared HTTP error handling for Aquiles services."""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, current_app, g, has_request_context, jsonify, request
from flask.typing import ResponseReturnValue
from werkzeug.exceptions import HTTPException

FORBIDDEN_PUBLIC_ERROR_KEYS = frozenset(
    {
        "exception",
        "service_url",
        "stack",
        "stack_trace",
        "stacktrace",
        "traceback",
    }
)
REDACTED_PUBLIC_ERROR_KEYS = frozenset({"internal_error", "last_error"})


def _sanitize_public_payload(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize_public_payload(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized_keys = {str(key).strip().lower() for key in value}
    is_internal_error_record = bool(
        normalized_keys.intersection(FORBIDDEN_PUBLIC_ERROR_KEYS)
        or {"error_type", "stage"}.issubset(normalized_keys)
    )
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key).strip().lower()
        if normalized_key in FORBIDDEN_PUBLIC_ERROR_KEYS:
            continue
        if normalized_key in REDACTED_PUBLIC_ERROR_KEYS and item:
            sanitized[key] = "Service unavailable"
            continue
        if normalized_key == "error" and item and is_internal_error_record:
            sanitized[key] = "Operation failed"
            continue
        sanitized[key] = _sanitize_public_payload(item)
    return sanitized


def error_response(
    logger: Any,
    *,
    status_code: int = 500,
    message: str | None = None,
    exception: Exception | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    """Log the internal exception and return a stable, non-sensitive API error."""
    request_id = getattr(g, "request_id", None) if has_request_context() else None
    if exception is not None:
        logger.exception(
            "request failed status=%s request_id=%s",
            status_code,
            request_id,
            exc_info=exception,
        )

    payload = {
        "success": False,
        "error": message or ("Internal server error" if status_code >= 500 else "Request failed"),
    }
    if request_id:
        payload["request_id"] = request_id
    if extra:
        payload.update(extra)
    response = jsonify(payload)
    setattr(response, "_aquiles_safe_error", True)
    return response, status_code


def register_error_handlers(app: Flask) -> None:
    """Install JSON handlers for API errors without leaking stack traces."""
    logger = app.logger

    @app.after_request
    def sanitize_server_error(response: Response) -> Response:
        """Enforce the public 5xx contract even for legacy route handlers."""
        if request.path != "/health" and not request.path.startswith("/api/"):
            return response

        payload = response.get_json(silent=True)
        if isinstance(payload, (dict, list)):
            sanitized_payload = _sanitize_public_payload(payload)
            if sanitized_payload != payload:
                response.set_data(current_app.json.dumps(sanitized_payload))
                response.content_type = "application/json"
            payload = sanitized_payload

        if response.status_code < 500:
            return response
        if not isinstance(payload, dict):
            payload = {}

        public_payload = {
            key: payload[key]
            for key in (
                "ok",
                "request_id",
                "task_id",
                "status",
                "delegated",
                "legacy_service",
                "feature",
                "source_id",
            )
            if key in payload
        }
        public_payload["success"] = False
        public_payload["error"] = (
            payload.get("error", "Internal server error")
            if getattr(response, "_aquiles_safe_error", False)
            else "Internal server error"
        )
        request_id = getattr(g, "request_id", None)
        if request_id:
            public_payload["request_id"] = request_id

        response.set_data(current_app.json.dumps(public_payload))
        response.content_type = "application/json"
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException) -> ResponseReturnValue | HTTPException:
        if not request.path.startswith("/api/"):
            return exc
        return error_response(
            logger,
            status_code=exc.code or 500,
            message=exc.description,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception) -> ResponseReturnValue:
        if not request.path.startswith("/api/"):
            raise exc
        return error_response(logger, exception=exc)
