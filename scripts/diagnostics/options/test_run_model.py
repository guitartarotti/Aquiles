"""
Simula o botao 'Run Model' da UI:
  POST /api/options/model/run
  → OptionsModelingService.run_from_snapshot_payload()

Verifica:
  - pipeline completo roda sem erro
  - gregas EFF_* chegam ao modeling
  - VEX e CEX usam vanna/charm do modelo proprietario
  - provider e OpLab (nao Bloomberg)
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
from app.services.options_modeling.service import OptionsModelingService
from app.services.options_data_provider import get_options_data_provider

UNDERLYING = "IBOVE Index"

# 1. Verifica provider
provider = get_options_data_provider()
print(f"Provider ativo: {type(provider).__name__}")

# 2. Coleta snapshot critico (fresh)
print(f"\nColetando snapshot critico para {UNDERLYING}...", flush=True)
snap_svc = OptionsSnapshotService()
snap_result = snap_svc.collect_critical_snapshot(UNDERLYING)
batch = snap_result.get("batch") or {}
print(f"  rows: {snap_result['row_count']}  batch_key: {batch.get('batch_key')}")

# 3. Le payload salvo
from app.services.options_store import OptionsStore
store = OptionsStore()
payload = store.read_snapshot_batch("critical", batch["session_date"], batch["batch_key"])
rows = payload.get("rows") or []

# Verifica que EFF_* estao presentes
with_eff_delta = sum(1 for r in rows if r.get("EFF_DELTA") is not None)
with_eff_vanna = sum(1 for r in rows if r.get("EFF_VANNA") is not None)
with_eff_gamma = sum(1 for r in rows if r.get("EFF_GAMMA_PT") is not None)
print(f"\n  EFF_DELTA  presente: {with_eff_delta}/{len(rows)}")
print(f"  EFF_GAMMA_PT       : {with_eff_gamma}/{len(rows)}")
print(f"  EFF_VANNA          : {with_eff_vanna}/{len(rows)}")

# 4. Roda o modelo proprietario
print(f"\nRodando OptionsModelingService...", flush=True)
modeling_svc = OptionsModelingService()
print(f"  modeling provider: {type(modeling_svc.bloomberg).__name__}")

try:
    result = modeling_svc.run_from_snapshot_payload(payload, persist=True)
except Exception as e:
    print(f"\n[ERRO] {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 5. Resultados
prepared = result.get("prepared_options") or []
exposures = result.get("option_exposures") or []
aggregates = result.get("aggregates") or {}
totals = aggregates.get("totals") or {}
summary = result.get("summary") or {}
market_ctx = result.get("market_context") or {}

print(f"\n=== Resultado do modelo ===")
print(f"  run_id          : {result.get('run_id','?')[:12]}...")
print(f"  prepared_options: {len(prepared)}")
print(f"  option_exposures: {len(exposures)}")
print(f"  spot_price      : {market_ctx.get('spot_price')}")
print(f"  forward_price   : {market_ctx.get('forward_price')}")
print(f"  spot_source     : {(market_ctx.get('sources') or {}).get('spot', {}).get('source')}")

print(f"\nAgregados (totais):")
for key in ("dex","gex","vex","cex","dex_notional","gex_notional","vex_notional","cex_notional"):
    val = totals.get(key)
    print(f"  {key:<18}: {round(val,4) if val is not None else None}")

# 6. Verifica fonte de vanna/charm nas exposures
src_vanna_obs  = sum(1 for e in exposures if (e.get("selected_greeks") or {}).get("source_vanna") == "observed")
src_vanna_model = sum(1 for e in exposures if (e.get("selected_greeks") or {}).get("source_vanna") == "model")
src_delta_obs   = sum(1 for e in exposures if (e.get("selected_greeks") or {}).get("source_delta") == "observed")
src_delta_model = sum(1 for e in exposures if (e.get("selected_greeks") or {}).get("source_delta") == "model")

print(f"\nFonte das gregas nas exposures ({len(exposures)} contratos):")
print(f"  delta  — observed (EFF_*): {src_delta_obs}  |  model (BSM interno): {src_delta_model}")
print(f"  vanna  — observed (EFF_*): {src_vanna_obs}  |  model (BSM interno): {src_vanna_model}")

# 7. Primeiras 5 exposures
print(f"\nPrimeiros 5 contratos:")
for e in exposures[:5]:
    opt = e.get("option") or {}
    sg  = e.get("selected_greeks") or {}
    print(
        f"  {opt.get('bloomberg_ticker','?'):<15} "
        f"delta={round(sg.get('delta',0),4):<7} "
        f"gamma={round(sg.get('gamma',0),6):<10} "
        f"vanna={round(sg.get('vanna',0),5):<9} "
        f"[src_delta={sg.get('source_delta')} src_vanna={sg.get('source_vanna')}]"
    )

print(f"\n[OK] Run Model completo sem erros!")
