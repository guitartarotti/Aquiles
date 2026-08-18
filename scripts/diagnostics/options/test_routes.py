import sys, types, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

class _S(types.ModuleType):
    class _A:
        def __init__(self,*a,**kw): pass
        def __call__(self,*a,**kw): return type(self)()
        def __getattr__(self,n): return type(self)()
        def __iter__(self): return iter([])
    def __getattr__(self,n): return self._A()
    def __iter__(self): return iter([])
for m in ["neo4j","graphiti_core","openai","anthropic","zep_cloud","blpapi",
          "zep_cloud.client","graphiti_core.nodes","graphiti_core.edges"]:
    if m not in sys.modules: sys.modules[m]=_S(m)
class _C:
    def __init__(self,*a,**kw): pass
sys.modules["openai"].OpenAI = _C
sys.modules["anthropic"].Anthropic = _C
_svc = types.ModuleType("app.services")
_svc.__path__ = [os.path.join(BACKEND,"app","services")]
_svc.__package__ = "app.services"
sys.modules["app.services"] = _svc

# Import only options blueprint to avoid graph/other deps
from flask import Blueprint, Flask
options_bp = Blueprint('options', __name__)
sys.modules["app.api"] = types.ModuleType("app.api")
sys.modules["app.api"].options_bp = options_bp

# Patch the import in options.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "app.api.options",
    os.path.join(BACKEND, "app", "api", "options.py")
)
mod = importlib.util.module_from_spec(spec)
sys.modules["app.api.options"] = mod
try:
    spec.loader.exec_module(mod)
    print("options.py loaded OK")
except Exception as e:
    print(f"ERROR loading options.py: {e}")
    import traceback; traceback.print_exc()

app = Flask('test')
app.register_blueprint(options_bp, url_prefix='/api/options')

volume_routes = sorted([str(r.rule) for r in app.url_map.iter_rules() if 'volume' in r.rule])
print(f"\nVolume routes ({len(volume_routes)}):")
for r in volume_routes:
    print(f"  {r}")
