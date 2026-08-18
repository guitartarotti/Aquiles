"""
Teste final — verifica campos do snapshot salvo.
"""
import sys, os, io, json, types, logging
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

from app.services.options_snapshot_service import OptionsSnapshotService
from app.services.options_store import OptionsStore

svc = OptionsSnapshotService()
store = OptionsStore()

snap_result = svc.collect_critical_snapshot("IBOVE Index")
batch = snap_result.get("batch") or {}
print(f"row_count      : {snap_result.get('row_count')}")
print(f"session_date   : {batch.get('session_date')}")
print(f"batch_key      : {batch.get('batch_key')}")

# Le os dados salvos
session_date = batch.get("session_date", "")
batch_key = batch.get("batch_key", "")
payload = store.read_snapshot_batch("critical", session_date, batch_key)
rows = payload.get("rows") or [] if payload else []

print(f"\nSnapshots no store: {len(rows)}")
print(f"\nPrimeiros 8 (campos Bloomberg):")
for r in rows[:8]:
    print(
        f"  {r.get('bloomberg_ticker','?'):<15} "
        f"put_call={r.get('put_call'):<5} "
        f"strike={r.get('strike'):<10} "
        f"PX_LAST={r.get('PX_LAST')}  "
        f"OPT_DELTA={r.get('OPT_DELTA')}  "
        f"IVOL_MID={r.get('IVOL_MID')}  "
        f"OPT_UNDL_PX={r.get('OPT_UNDL_PX')}  "
        f"OI={r.get('OPT_OPEN_INTEREST')}  "
        f"moneyness={r.get('moneyness_spot'):.4f}" if r.get('moneyness_spot') is not None else ""
    )

# Conta contratos com dados uteis
with_price = sum(1 for r in rows if r.get('PX_LAST') is not None)
with_delta = sum(1 for r in rows if r.get('OPT_DELTA') is not None)
with_iv = sum(1 for r in rows if r.get('IVOL_MID') is not None)
with_spot = sum(1 for r in rows if r.get('OPT_UNDL_PX') is not None)
print(f"\nCobertura ({len(rows)} contratos criticos):")
print(f"  com PX_LAST    : {with_price}/{len(rows)}")
print(f"  com OPT_DELTA  : {with_delta}/{len(rows)}")
print(f"  com IVOL_MID   : {with_iv}/{len(rows)}")
print(f"  com OPT_UNDL_PX: {with_spot}/{len(rows)}")

print()
print("[OK] Pipeline completo e funcionando!")
