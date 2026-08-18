"""
Debug por que o modelo proprietario nao roda para a maioria dos contratos.
"""
import sys, os, io, types, logging
logging.disable(logging.WARNING)
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

from app.services.oplab_options_service import OpLabOptionsService, _business_days_to_expiry, _safe_float
from app.services.options_greeks_model import compute_greeks_from_snapshot

svc = OpLabOptionsService()

# 1. Busca chain bruta do IBOV
print("=== Chain bruta (primeiras 10 entradas) ===")
data = svc._make_request("GET", "/market/options/IBOV")
rows = data if isinstance(data, list) else []

sample_syms = ["IBOVQ178A3", "IBOVE179A3", "IBOVQ180A3", "IBOVQ173B3"]
for sym in sample_syms:
    entry = next((r for r in rows if r.get("symbol") == sym), None)
    if entry:
        print(f"\n{sym}:")
        for key in ("symbol", "type", "strike", "spot_price", "days_to_maturity",
                    "due_date", "close", "bid", "ask"):
            print(f"  {key:20} = {entry.get(key)}")
    else:
        print(f"\n{sym}: NAO ENCONTRADO na chain")

# 2. Testa compute_greeks_from_snapshot diretamente para IBOVQ178A3
print("\n\n=== Teste direto de compute_greeks_from_snapshot ===")
# Use valores do primeiro teste
S = 178365.86
K = 178000.0
price_mid = 2080.0
r = svc._get_cdi_rate()
print(f"CDI rate: {r:.4f}")

for t_du in [5, 10, 15, 20]:
    res = compute_greeks_from_snapshot(S=S, K=K, T_du=t_du, price_mid=price_mid, r_cont=r, opt="P")
    if res:
        print(f"T_du={t_du:3d}  IV={res['iv']*100:.2f}%  delta={res['delta']:.4f}  vanna={res['vanna']:.4f}")
    else:
        print(f"T_du={t_du:3d}  → None (dados insuficientes)")

# 3. Verifica business_days_to_expiry para due_dates tipicas
print("\n\n=== _business_days_to_expiry ===")
for due in ["2026-05-20", "2026-06-15", "2026-07-20", None]:
    print(f"  due={due!r:20} -> {_business_days_to_expiry(due)}")
