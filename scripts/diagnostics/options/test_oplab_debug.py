"""
Debug: examina a resposta raw da API OpLab para entender campos e formato.
"""
import sys, os, io, json, types, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

# Stubs minimos
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

# Cria sessao direta
import requests
session = requests.Session()
session.headers["access-token"] = Config.OPLAB_ACCESS_TOKEN
BASE = Config.OPLAB_BASE_URL.rstrip("/")

def get(path, **params):
    r = session.get(f"{BASE}{path}", params=params or None, timeout=30)
    r.raise_for_status()
    return r.json()

# ── 1. Inspeciona campos da chain ─────────────────────────────────────────────
print("=== Chain IBOV — primeiros 3 contratos (campos completos) ===")
chain_data = get("/market/options/IBOV")
sample = chain_data if isinstance(chain_data, list) else chain_data.get("options", chain_data.get("data", []))
print(f"Total contratos: {len(sample)}")
for row in sample[:3]:
    print(json.dumps(row, ensure_ascii=False, indent=2))

# ── 2. Inspeciona historico de ontem ─────────────────────────────────────────
print()
print("=== Historico IBOV 2026-05-14 — primeiros 3 registros ===")
hist = get("/market/historical/options/IBOV/2026-05-14/2026-05-14")
hist_list = hist if isinstance(hist, list) else hist.get("data", hist.get("options", []))
print(f"Total registros: {len(hist_list)}")
for row in hist_list[:3]:
    print(json.dumps(row, ensure_ascii=False, indent=2))

# ── 3. Verifica opcoes com maior volume / OI no historico ────────────────────
print()
print("=== Top 5 por volume ontem ===")
if hist_list:
    top = sorted(hist_list, key=lambda x: x.get("volume") or 0, reverse=True)[:5]
    for r in top:
        print(f"  {r.get('symbol'):<15} volume={r.get('volume')}  premium={r.get('premium')}  "
              f"delta={r.get('delta')}  iv={r.get('volatility')}  dtm={r.get('days_to_maturity')}")

# ── 4. Verifica o campo dias_ate_vencimento na chain ─────────────────────────
print()
print("=== Campos de vencimento nos primeiros 10 contratos da chain ===")
for row in sample[:10]:
    keys_with_maturity = {k: v for k, v in row.items() if "mat" in k.lower() or "day" in k.lower() or "due" in k.lower() or "exp" in k.lower() or "vcto" in k.lower()}
    print(f"  {row.get('symbol'):<15} {keys_with_maturity}")
