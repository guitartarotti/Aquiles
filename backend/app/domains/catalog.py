"""Explicit catalog and HTTP composition root for Aquiles business domains."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Blueprint, Flask

from .funds_flow.api.routes import funds_flow_local_bp
from .graph.routes import graph_bp
from .macro.routes import macro_bp
from .market_data.routes import cvm_cda_bp, nport_bp
from .options.routes import options_bp
from .reports.routes import report_bp
from .simulations.routes import simulation_bp


@dataclass(frozen=True)
class DomainRoute:
    blueprint: Blueprint
    url_prefix: str


@dataclass(frozen=True)
class DomainSpec:
    name: str
    routes: tuple[DomainRoute, ...] = ()
    owned_api_modules: tuple[str, ...] = ()


DOMAIN_CATALOG = (
    DomainSpec(
        name="funds_flow",
        routes=(DomainRoute(funds_flow_local_bp, "/api/v1/funds-flow-local"),),
        owned_api_modules=("app.domains.funds_flow.api.routes",),
    ),
    DomainSpec(
        name="options",
        routes=(DomainRoute(options_bp, "/api/options"),),
        owned_api_modules=(
            "app.api.options_vol_index",
            "app.api.options_volume",
            "app.api.regime_price_making_api",
        ),
    ),
    DomainSpec(
        name="macro",
        routes=(DomainRoute(macro_bp, "/api/macro"),),
        owned_api_modules=("app.api.macro", "app.api.legacy_heatmap_proxy"),
    ),
    DomainSpec(
        name="market_data",
        routes=(
            DomainRoute(nport_bp, "/api/v1/nport"),
            DomainRoute(cvm_cda_bp, "/api/v1/cvm-cda"),
        ),
        owned_api_modules=("app.api.nport", "app.api.cvm_cda"),
    ),
    DomainSpec(
        name="graph",
        routes=(DomainRoute(graph_bp, "/api/graph"),),
        owned_api_modules=("app.api.graph",),
    ),
    DomainSpec(
        name="reports",
        routes=(DomainRoute(report_bp, "/api/report"),),
        owned_api_modules=("app.api.report",),
    ),
    DomainSpec(
        name="simulations",
        routes=(DomainRoute(simulation_bp, "/api/simulation"),),
    ),
    DomainSpec(name="auth", owned_api_modules=("app.auth",)),
)


def register_domain_blueprints(app: Flask) -> None:
    for domain in DOMAIN_CATALOG:
        for route in domain.routes:
            app.register_blueprint(route.blueprint, url_prefix=route.url_prefix)
