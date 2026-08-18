"""
Verifica os campos MODEL_* e EFF_* no snapshot salvo.
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

from app.services.options_snapshot_service import OptionsSnapshotService
from app.services.options_store import OptionsStore

svc = OptionsSnapshotService()
store = OptionsStore()

snap_result = svc.collect_critical_snapshot("IBOVE Index")
batch = snap_result.get("batch") or {}
session_date = batch.get("session_date", "")
batch_key    = batch.get("batch_key", "")
payload = store.read_snapshot_batch("critical", session_date, batch_key)
rows = payload.get("rows") or [] if payload else []

with_model   = [r for r in rows if r.get("MODEL_SOURCE") == "proprietary"]
with_oplab   = [r for r in rows if r.get("MODEL_SOURCE") == "oplab"]
insufficient = [r for r in rows if r.get("MODEL_SOURCE") == "insufficient_data"]

print(f"Total contratos criticos        : {len(rows)}")
print(f"  MODEL_SOURCE=proprietary      : {len(with_model)}")
print(f"  MODEL_SOURCE=oplab            : {len(with_oplab)}")
print(f"  MODEL_SOURCE=insufficient_data: {len(insufficient)}")
print()

print("--- Contratos com modelo proprietario (primeiros 5) ---")
for r in with_model[:5]:
    iv_pct = round(r["MODEL_IV"] * 100, 2) if r.get("MODEL_IV") is not None else None
    print(
        f"  {r.get('bloomberg_ticker','?'):<15} "
        f"pc={r.get('put_call','?'):4} "
        f"K={r.get('strike'):<10} "
        f"MODEL_IV={iv_pct}%  "
        f"EFF_DELTA={r.get('EFF_DELTA') and round(r['EFF_DELTA'],4)}  "
        f"EFF_VANNA={r.get('EFF_VANNA') and round(r['EFF_VANNA'],6)}  "
        f"EFF_CHARM={r.get('EFF_CHARM') and round(r['EFF_CHARM'],6)}"
    )

print()
print("--- Contratos apenas com gregas OpLab (primeiros 5) ---")
for r in with_oplab[:5]:
    print(
        f"  {r.get('bloomberg_ticker','?'):<15} "
        f"EFF_DELTA={r.get('EFF_DELTA')}  "
        f"EFF_VANNA={r.get('EFF_VANNA')}  "
        f"MODEL_IV={r.get('MODEL_IV')}"
    )

with_eff_delta = sum(1 for r in rows if r.get("EFF_DELTA") is not None)
with_eff_vanna = sum(1 for r in rows if r.get("EFF_VANNA") is not None)
with_eff_charm = sum(1 for r in rows if r.get("EFF_CHARM") is not None)
with_model_iv  = sum(1 for r in rows if r.get("MODEL_IV") is not None)

print()
print("Cobertura de campos efetivos:")
print(f"  MODEL_IV   : {with_model_iv}/{len(rows)}")
print(f"  EFF_DELTA  : {with_eff_delta}/{len(rows)}")
print(f"  EFF_VANNA  : {with_eff_vanna}/{len(rows)}")
print(f"  EFF_CHARM  : {with_eff_charm}/{len(rows)}")
print()
print("[OK] Campos MODEL_* e EFF_* verificados!")
