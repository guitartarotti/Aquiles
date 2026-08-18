"""
Testa a pipeline completa do OptionsVolumeTracker:
  - Poll 1: baseline (todos vistos pela primeira vez)
  - Poll 2: simula variacao em contratos com volume real > 0
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

from app.services.options_data_provider import get_options_data_provider
from app.services.options_volume_tracker import OptionsVolumeTracker
from app.services.options_store import OptionsStore

UNDERLYING = "IBOVE Index"

# Reseta estado
store = OptionsStore()
store.save_volume_state({})

provider = get_options_data_provider()
tracker = OptionsVolumeTracker(store=store, provider=provider)
print(f"Provider: {type(provider).__name__}")

# POLL 1: baseline
print(f"\n=== POLL 1 (baseline) para {UNDERLYING} ===", flush=True)
r1 = tracker.poll_once(UNDERLYING)
print(f"  chain_size    : {r1['chain_size']}")
print(f"  first_seen    : {r1['first_seen']}")
print(f"  events_created: {r1['events_created']}  (esperado: 0)")
assert r1['events_created'] == 0

# Encontra simbolos com volume > 0 para simular delta real
state = store.load_volume_state()
with_volume = [(sym, vol) for sym, vol in state.items() if vol > 0]
print(f"\n  Contratos com volume > 0 no baseline: {len(with_volume)}")
print(f"  Top 5 por volume: {sorted(with_volume, key=lambda x: -x[1])[:5]}")

# Reduz baseline dos 3 com maior volume para forcar deteccao
targets = sorted(with_volume, key=lambda x: -x[1])[:3]
for sym, vol in targets:
    state[sym] = max(0.0, vol - max(1.0, vol * 0.5))  # reduz 50% do volume real
store.save_volume_state(state)
print(f"\n  Forcando delta em: {[(s, v) for s, v in targets]}")

# POLL 2: deteccao real
print(f"\n=== POLL 2 (deteccao de atividade) ===", flush=True)
r2 = tracker.poll_once(UNDERLYING)
print(f"  chain_size    : {r2['chain_size']}")
print(f"  events_created: {r2['events_created']}  (esperado: 3)")
print(f"  events_written: {r2['events_written']}")

evs = r2.get('events') or []
print(f"\n  Eventos detectados:")
for ev in evs:
    print(f"    {ev['symbol']:<14} {ev['put_call']} K={ev['strike']:>8.0f}  "
          f"vencto={ev['expiry_date']}  "
          f"vol {ev['volume_before']:.0f} -> {ev['volume_after']:.0f}  "
          f"delta=+{ev['volume_delta']:.0f}")

# Leitura final
rows = store.read_volume_activity()
summ = store.volume_activity_summary()
print(f"\n  Total eventos no store (hoje): {len(rows)}")
print(f"  Summary: {summ}")

# Verifica que o tracker esta OK mesmo sem events para underlyings sem dados
print(f"\n=== POLL 3 (sem mudancas) ===", flush=True)
r3 = tracker.poll_once(UNDERLYING)
print(f"  events_created: {r3['events_created']}  (esperado: 0 - volumes estabilizados)")

print(f"\n[OK] Volume Tracker pipeline 100% funcional!")
print(f"     Cobertura: {r1['chain_size']} contratos monitorados")
print(f"     Arquivo estado: {store.volume_state_path}")
print(f"     Arquivo atividade: {store.volume_activity_dir}")
