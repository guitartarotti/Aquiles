"""Route ownership for regulatory market data sources."""

from flask import Blueprint

cvm_cda_bp = Blueprint("cvm_cda", __name__)
nport_bp = Blueprint("nport", __name__)
