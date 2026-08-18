from __future__ import annotations

import logging
import os

import requests as http_requests
from flask import jsonify, request

from ..http import error_response

LEGACY_SERVICE_NAME = "aquiles-legacy-heatmap-service"
logger = logging.getLogger(__name__)


def _legacy_heatmap_service_url() -> str:
    return str(os.environ.get("LEGACY_HEATMAP_SERVICE_URL") or "").strip().rstrip("/")


def legacy_heatmap_proxy_or_disabled(
    path: str,
    *,
    feature: str,
    timeout: float = 30.0,
):
    service_url = _legacy_heatmap_service_url()
    if not service_url:
        return jsonify({
            "success": False,
            "disabled": True,
            "legacy_service": LEGACY_SERVICE_NAME,
            "feature": feature,
            "error": (
                f"{feature} foi removido do backend principal e esta desativado. "
                "Suba o servico legado e configure LEGACY_HEATMAP_SERVICE_URL para consultar/reviver esta feature."
            ),
            "reactivation": {
                "pm2": "pm2 start ecosystem.config.js --only aquiles-legacy-heatmap-service",
                "env": "LEGACY_HEATMAP_SERVICE_URL=http://127.0.0.1:5022",
            },
        }), 410

    url = f"{service_url}{path}"
    try:
        response = http_requests.request(
            request.method,
            url,
            params=request.args if request.method == "GET" else None,
            json=request.get_json(silent=True) if request.method != "GET" else None,
            timeout=timeout,
        )
        try:
            payload = response.json()
        except ValueError:
            return response.text, response.status_code, {
                "Content-Type": response.headers.get("Content-Type", "text/plain"),
            }
        if isinstance(payload, dict):
            payload["delegated"] = True
            payload["legacy_service"] = LEGACY_SERVICE_NAME
        return jsonify(payload), response.status_code
    except Exception as exc:
        return error_response(logger, status_code=503, exception=exc, extra={'delegated': True, 'legacy_service': LEGACY_SERVICE_NAME, 'feature': feature})
