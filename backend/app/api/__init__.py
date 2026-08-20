"""HTTP route composition for Aquiles business domains."""

from ..domains.funds_flow.api.routes import funds_flow_local_bp
from ..domains.graph.routes import graph_bp
from ..domains.macro.routes import macro_bp
from ..domains.market_data.routes import cvm_cda_bp, nport_bp
from ..domains.options.routes import options_bp
from ..domains.reports.routes import report_bp
from ..domains.simulations.routes import simulation_bp

__all__ = [
    "cvm_cda_bp",
    "funds_flow_local_bp",
    "graph_bp",
    "macro_bp",
    "nport_bp",
    "options_bp",
    "report_bp",
    "simulation_bp",
]

from . import (
    cvm_cda,
    graph,
    macro,
    nport,
    options_routes,
    options_vol_index,
    options_volume,
    report,
    simulation_routes,
)

_ROUTE_MODULES = (
    cvm_cda,
    graph,
    macro,
    nport,
    options_routes,
    options_vol_index,
    options_volume,
    report,
    simulation_routes,
)
