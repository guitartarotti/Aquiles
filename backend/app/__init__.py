"""Aquiles Flask application factory."""

from __future__ import annotations

import os
import time
import uuid
import warnings
from typing import TYPE_CHECKING, Any

from flask import Flask, g, request
from flask_cors import CORS

if TYPE_CHECKING:
    from .container import AquilesContainer

# Some optional ML dependencies create noisy resource-tracker warnings on shutdown.
warnings.filterwarnings("ignore", message=".*resource_tracker.*")


def _register_blueprints(app: Flask) -> None:
    from . import api as _route_implementations  # noqa: F401
    from .domains.catalog import register_domain_blueprints

    register_domain_blueprints(app)


def _configure_request_observability(app: Flask) -> None:
    from .utils.logger import get_logger

    request_logger = get_logger("aquiles.request")

    @app.before_request
    def begin_request() -> None:
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.request_started_at = time.perf_counter()
        request_logger.debug(
            "request started method=%s path=%s request_id=%s content_length=%s",
            request.method,
            request.path,
            g.request_id,
            request.content_length,
        )

    @app.after_request
    def finish_request(response: Any) -> Any:
        elapsed_ms = (time.perf_counter() - g.request_started_at) * 1000
        response.headers["X-Request-ID"] = g.request_id
        request_logger.debug(
            "request completed method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
            g.request_id,
        )
        return response


def create_app(
    config_class: type | None = None,
    *,
    dependencies: AquilesContainer | None = None,
) -> Flask:
    """Create and configure an Aquiles backend application instance."""
    from .config import Config
    from .container import AquilesContainer, attach_container
    from .domains.auth import register_auth_routes
    from .http import register_error_handlers
    from .services.simulation_runner import SimulationRunner
    from .utils.logger import setup_logger

    app = Flask(__name__)
    app.config.from_object(config_class or Config)
    app.json.ensure_ascii = False
    attach_container(app, dependencies or AquilesContainer())

    logger = setup_logger("aquiles")
    should_log_startup = not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if should_log_startup:
        logger.info("Aquiles backend starting")

    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
    )
    _configure_request_observability(app)
    _register_blueprints(app)
    register_auth_routes(app, expose_login=True)
    register_error_handlers(app)

    SimulationRunner.register_cleanup()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "aquiles-backend",
            "version": app.config.get("APP_VERSION", "0.1.0"),
        }

    if should_log_startup:
        logger.info("Aquiles backend ready")
    return app
