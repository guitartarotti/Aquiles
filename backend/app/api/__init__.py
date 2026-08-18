"""
API路由模块
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
macro_bp = Blueprint('macro', __name__)
options_bp = Blueprint('options', __name__)
funds_flow_local_bp = Blueprint('funds_flow_local', __name__)
nport_bp = Blueprint('nport', __name__)
cvm_cda_bp = Blueprint('cvm_cda', __name__)

from . import (
    cvm_cda,  # noqa: E402, F401
    funds_flow_local,  # noqa: E402, F401
    graph,  # noqa: E402, F401
    macro,  # noqa: E402, F401
    nport,  # noqa: E402, F401
    options,  # noqa: E402, F401
    options_vol_index,  # noqa: E402, F401
    options_volume,  # noqa: E402, F401
    report,  # noqa: E402, F401
    simulation,  # noqa: E402, F401
)
