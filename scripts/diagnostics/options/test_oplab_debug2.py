"""
Debug 2: verifica IBOVA na chain e OPLAB_MAX_DTM
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

# Check OPLAB_MAX_DTM
print(f"OPLAB_MAX_DTM = {Config.OPLAB_MAX_DTM}")
print()

# Pega a chain raw e encontra entradas IBOVA
chain_data = session.get(f"{BASE}/market/options/IBOV", timeout=30).json()
sample = chain_data if isinstance(chain_data, list) else []

ibova_entries = [r for r in sample if r.get("symbol","").startswith("IBOVA")]
print(f"Entradas IBOVA na chain: {len(ibova_entries)}")
for r in ibova_entries[:5]:
    print(f"  symbol={r.get('symbol'):<15} dtm={r.get('days_to_maturity')}  due_date={r.get('due_date')}  close={r.get('close')}")

print()

# Entradas filtradas por dtm <= 180
filtered = [r for r in sample if (r.get("days_to_maturity") or 0) <= 180]
print(f"Total na chain raw: {len(sample)}")
print(f"Com dtm <= 180: {len(filtered)}")
print(f"Com dtm > 180: {len(sample) - len(filtered)}")

print()

# Distribui por dtm
from collections import Counter
dtm_dist = Counter()
for r in sample:
    dtm = r.get("days_to_maturity")
    if dtm is None: dtm_dist["None"] += 1
    elif dtm <= 7: dtm_dist["0-7d"] += 1
    elif dtm <= 30: dtm_dist["8-30d"] += 1
    elif dtm <= 60: dtm_dist["31-60d"] += 1
    elif dtm <= 90: dtm_dist["61-90d"] += 1
    elif dtm <= 180: dtm_dist["91-180d"] += 1
    else: dtm_dist[">180d"] += 1

print("Distribuicao por DTM:")
for k, v in sorted(dtm_dist.items()):
    print(f"  {k}: {v}")
