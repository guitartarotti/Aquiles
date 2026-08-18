"""Background-service bootstrap for the main Aquiles API process."""

from __future__ import annotations

import importlib
import os
import threading
from dataclasses import dataclass
from typing import Any

from flask import Flask


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CollectorSpec:
    label: str
    module: str
    manager_class: str
    disabled_by: str | None = None
    owner_when_disabled: str = "an external worker"


COLLECTORS = (
    CollectorSpec("CVM CDA collector", ".services.cvm_cda_manager", "CvmCdaManager"),
    CollectorSpec(
        "funds-flow collector",
        ".services.funds_flow_local_manager",
        "FundsFlowLocalManager",
    ),
    CollectorSpec(
        "report-source collector",
        ".services.report_source_discovery_service",
        "ReportSourceDiscoveryManager",
    ),
    CollectorSpec("macro collector", ".services.macro_live_service", "MacroCollectorManager"),
    CollectorSpec(
        "options collector",
        ".services.options_collector_manager",
        "OptionsCollectorManager",
        "AQUILES_DISABLE_OPTIONS_COLLECTOR",
    ),
    CollectorSpec(
        "market-screen collector",
        ".services.market_screen_capture_service",
        "MarketScreenCaptureCollectorManager",
        "AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR",
        "the dedicated OCR worker",
    ),
    CollectorSpec(
        "options-volume tracker",
        ".services.options_volume_tracker",
        "OptionsVolumeTracker",
        "AQUILES_DISABLE_OPTIONS_VOLUME_TRACKER",
        "the dedicated volume worker",
    ),
)


def _resume_collector(spec: CollectorSpec, logger: Any, verbose: bool) -> None:
    if spec.disabled_by and _env_truthy(spec.disabled_by):
        if verbose:
            logger.info("%s disabled; %s owns this workload", spec.label, spec.owner_when_disabled)
        return

    try:
        module = importlib.import_module(spec.module, package=__package__)
        manager_type = getattr(module, spec.manager_class)
        status = manager_type.get_instance().resume_if_needed()
        if verbose:
            logger.info("%s resumed status=%s", spec.label, status)
    except Exception:
        logger.exception("Failed to resume %s", spec.label)


def _resume_all_collectors(logger: Any, verbose: bool) -> None:
    for spec in COLLECTORS:
        _resume_collector(spec, logger, verbose)


def start_background_services(app: Flask, logger: Any, verbose: bool) -> threading.Thread | None:
    """Start collector recovery outside the request-serving thread."""
    if not app.config.get("START_BACKGROUND_SERVICES", True):
        if verbose:
            logger.info("Background services disabled for this application instance")
        return None

    thread = threading.Thread(
        target=_resume_all_collectors,
        args=(logger, verbose),
        daemon=True,
        name="aquiles-startup-collectors",
    )
    thread.start()
    return thread
