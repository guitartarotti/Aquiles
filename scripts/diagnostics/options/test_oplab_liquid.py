"""
Testa snapshots com contratos liquidos (que estao no historico de ontem).
"""
import sys, os, io, json, types
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
    def __getattr__(self,n): return self._A()
for m in ["neo4j","graphiti_core","openai","anthropic","zep_cloud","blpapi"]:
    if m not in sys.modules: sys.modules[m]=_S(m)
class _C:
    def __init__(self,*a,**kw): pass
sys.modules["openai"].OpenAI = _C
sys.modules["anthropic"].Anthropic = _C
_svc = types.ModuleType("app.services")
_svc.__path__ = [os.path.join(BACKEND,"app","services")]
_svc.__package__ = "app.services"
sys.modules["app.services"] = _svc

from app.config import Config
import requests

session = requests.Session()
session.headers["access-token"] = Config.OPLAB_ACCESS_TOKEN
BASE = Config.OPLAB_BASE_URL.rstrip("/")

# Pega contratos do historico de ontem (2026-05-14) que tem gregas
hist = session.get(f"{BASE}/market/historical/options/IBOV/2026-05-14/2026-05-14", timeout=30).json()
hist_list = hist if isinstance(hist, list) else hist.get("data", [])

# Filtra: tem volume > 0 ou delta > 0
liquid = [r for r in hist_list if (r.get("delta") or 0) > 0.05]
liquid.sort(key=lambda r: abs(r.get("delta",0)-0.5))  # mais proximos de ATM
test_symbols = [r["symbol"] for r in liquid[:8]]

print(f"Contratos liquidos de ontem para testar: {test_symbols}")
print()

# Agora testa com o provider
import importlib.util, os as _os

def _load_mod(name, path, pkg="app.services"):
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_svc_dir = _os.path.join(BACKEND, "app", "services")
_load_mod("app.services.options_data_provider", _os.path.join(_svc_dir, "options_data_provider.py"))

from app.services.options_data_provider import get_options_data_provider
provider = get_options_data_provider()

print("=== Snapshots para contratos ATM de ontem ===")
snap = provider.fetch_option_snapshots(test_symbols, None)
for r in snap.get("rows", []):
    f = r.get("fields", {})
    print(
        f"  {r['security']:<15} ok={r['ok']}  "
        f"PX_LAST={f.get('PX_LAST')}  "
        f"DELTA={f.get('OPT_DELTA')}  "
        f"GAMMA={f.get('OPT_GAMMA')}  "
        f"IVOL={f.get('IVOL_MID')}  "
        f"OI={f.get('OPT_OPEN_INTEREST')}  "
        f"STRIKE={f.get('OPT_STRIKE_PX')}  "
        f"TYPE={f.get('OPT_PUT_CALL')}"
    )

print()
print("=== Historico do primeiro contrato ===")
if test_symbols:
    hist2 = provider.fetch_option_history(test_symbols[0], "2026-05-12", "2026-05-15", None)
    for r in hist2.get("rows", []):
        f = r.get("fields", {})
        print(
            f"  {r.get('trade_date')}  PX_LAST={f.get('PX_LAST')}  "
            f"IVOL={f.get('IVOL_MID')}  DELTA={f.get('OPT_DELTA')}  "
            f"OI={f.get('OPT_OPEN_INTEREST')}"
        )
