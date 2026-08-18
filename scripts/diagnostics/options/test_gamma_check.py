"""Verifica EFF_GAMMA_PT e EFF_GAMMA_1PCT nos rows salvos."""
import sys, os, io, types, logging, glob, json
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

# Pega o batch de snapshot mais recente
pattern = os.path.join(ROOT, "data", "snapshots", "critical", "**", "*.json")
files = sorted(glob.glob(pattern, recursive=True))
if not files:
    print("Nenhum batch encontrado — rodando coleta...")
    from app.services.options_snapshot_service import OptionsSnapshotService
    from app.services.options_store import OptionsStore
    svc = OptionsSnapshotService()
    store = OptionsStore()
    snap = svc.collect_critical_snapshot("IBOVE Index")
    b = snap["batch"]
    payload = store.read_snapshot_batch("critical", b["session_date"], b["batch_key"])
    rows = payload.get("rows") or []
else:
    with open(files[-1], encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload.get("rows") or []

prop = [r for r in rows if r.get("MODEL_SOURCE") == "proprietary"]

print(f"Contratos com modelo proprietario: {len(prop)}/{len(rows)}")
print()
fmt = f"{'Ticker':<15} {'pc':4} {'K':>8}  {'EFF_GAMMA_PT':>13}  {'EFF_GAMMA_1PCT':>14}  {'MODEL_GAMMA_PT':>14}  {'OPT_GAMMA':>10}"
print(fmt)
print("-" * 85)
for r in prop[:12]:
    gpt  = r.get("EFF_GAMMA_PT")
    g1   = r.get("EFF_GAMMA_1PCT")
    mpt  = r.get("MODEL_GAMMA_POINT")
    olab = r.get("OPT_GAMMA")
    print(
        f"{r.get('bloomberg_ticker','?'):<15} "
        f"{str(r.get('put_call','?')):4} "
        f"{str(r.get('strike','?')):>8}  "
        f"{str(round(gpt, 8) if gpt is not None else None):>13}  "
        f"{str(round(g1, 6) if g1 is not None else None):>14}  "
        f"{str(round(mpt, 8) if mpt is not None else None):>14}  "
        f"{str(olab):>10}"
    )

with_gpt  = sum(1 for r in rows if r.get("EFF_GAMMA_PT") is not None)
with_g1   = sum(1 for r in rows if r.get("EFF_GAMMA_1PCT") is not None)
with_mgpt = sum(1 for r in rows if r.get("MODEL_GAMMA_POINT") is not None)
with_oplab_g = sum(1 for r in rows if r.get("OPT_GAMMA") is not None)

print()
print("Cobertura de gamma:")
print(f"  MODEL_GAMMA_POINT  : {with_mgpt}/{len(rows)}")
print(f"  EFF_GAMMA_PT       : {with_gpt}/{len(rows)}")
print(f"  EFF_GAMMA_1PCT     : {with_g1}/{len(rows)}")
print(f"  OPT_GAMMA (OpLab)  : {with_oplab_g}/{len(rows)}")
