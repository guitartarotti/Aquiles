"""
Testa prepare_universe completo via OptionsSnapshotService com OpLab.
Verifica structural, liquid, critical universes e snapshots.
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

from app.services.options_snapshot_service import OptionsSnapshotService

svc = OptionsSnapshotService()

print("=" * 65)
print("TESTE — prepare_universe('IBOVE Index')")
print("=" * 65)

universe = svc.prepare_universe("IBOVE Index")

summary = universe.get("summary", {})
print(f"  structural count  : {summary.get('structural_count')}")
print(f"  liquid count      : {summary.get('liquid_count')}")
print(f"  critical count    : {summary.get('critical_count')}")
print(f"  preview_status    : {universe.get('preview_status', {}).get('session_ok')}")
print()

critical = universe.get("critical", [])
print(f"Contratos criticos ({len(critical)}):")
for c in critical[:10]:
    f = {k: v for k, v in (c.get("fields") or c).items() if v is not None and k in (
        "bloomberg_ticker","put_call","strike","expiry_date","days_to_expiry_business",
        "OPT_STRIKE_PX","OPT_EXPIRE_DT","OPT_PUT_CALL","PX_LAST","OPT_DELTA","IVOL_MID"
    )}
    print(f"  {c.get('bloomberg_ticker', c.get('security','?')):<15} {json.dumps(f, ensure_ascii=False)[:150]}")

print()
print("=" * 65)
print("TESTE — collect_critical_snapshot('IBOVE Index')")
print("=" * 65)
snap_result = svc.collect_critical_snapshot("IBOVE Index")
batch = snap_result.get("batch") or {}
print(f"  session_date   : {batch.get('session_date')}")
print(f"  batch_key      : {batch.get('batch_key')}")
print(f"  rows_captured  : {batch.get('rows_captured')}")
print(f"  rows_ok        : {batch.get('rows_ok')}")
print(f"  rows_failed    : {batch.get('rows_failed')}")

rows = snap_result.get("rows") or []
print(f"\n  Primeiros 5 snapshots:")
for r in rows[:5]:
    f = r.get("fields") or {}
    print(
        f"  {r.get('security','?'):<15} ok={r.get('ok')}  "
        f"PX={f.get('PX_LAST')}  DELTA={f.get('OPT_DELTA')}  "
        f"IV={f.get('IVOL_MID')}  OI={f.get('OPT_OPEN_INTEREST')}"
    )

print()
print("[OK] Pipeline completo!")
