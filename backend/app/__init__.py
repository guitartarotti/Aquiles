"""Aquiles Flask application factory."""

from __future__ import annotations

import os
import time
import uuid
import warnings
from typing import Any

from flask import Flask, g, request
from flask_cors import CORS

# Some optional ML dependencies create noisy resource-tracker warnings on shutdown.
warnings.filterwarnings("ignore", message=".*resource_tracker.*")


def _register_blueprints(app: Flask) -> None:
    from .api import (
        cvm_cda_bp,
        funds_flow_local_bp,
        graph_bp,
        macro_bp,
        nport_bp,
        options_bp,
        report_bp,
        simulation_bp,
    )

    blueprints = (
        (graph_bp, "/api/graph"),
        (simulation_bp, "/api/simulation"),
        (report_bp, "/api/report"),
        (macro_bp, "/api/macro"),
        (options_bp, "/api/options"),
        (funds_flow_local_bp, "/api/v1/funds-flow-local"),
        (nport_bp, "/api/v1/nport"),
        (cvm_cda_bp, "/api/v1/cvm-cda"),
    )
    for blueprint, prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=prefix)


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


def create_app(config_class: type | None = None) -> Flask:
    """Create and configure an Aquiles backend application instance."""
    from .auth import register_auth
    from .config import Config
    from .http import register_error_handlers
    from .services.simulation_runner import SimulationRunner
    from .startup import start_background_services
    from .utils.logger import setup_logger

    app = Flask(__name__)
    app.config.from_object(config_class or Config)
    app.json.ensure_ascii = False

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
    register_auth(app, expose_login=True)
    register_error_handlers(app)

    SimulationRunner.register_cleanup()
    start_background_services(app, logger, should_log_startup)

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
