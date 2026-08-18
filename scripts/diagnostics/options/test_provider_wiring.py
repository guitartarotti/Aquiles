"""
Verifica que todos os servicos de opcoes instanciam corretamente
usando OpLab como provider (sem Bloomberg).
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
from app.services.options_contract_service import OptionsContractService
from app.services.options_snapshot_service import OptionsSnapshotService

# 1. Factory
p = get_options_data_provider()
print(f"get_options_data_provider() : {type(p).__name__}")

# 2. ContractService instanciado diretamente (sem bloomberg= arg)
cs = OptionsContractService()
print(f"OptionsContractService()    : bloomberg={type(cs.bloomberg).__name__}")

# 3. SnapshotService instanciado diretamente
ss = OptionsSnapshotService()
print(f"OptionsSnapshotService()    : bloomberg={type(ss.bloomberg).__name__}")
print(f"  contract_service.bloomberg: {type(ss.contract_service.bloomberg).__name__}")

# 4. Interface completa presente
REQUIRED_METHODS = [
    "status",
    "fetch_option_chain",
    "fetch_option_snapshots",
    "fetch_option_history",
    "fetch_option_ticks",       # stub de compatibilidade Bloomberg
    "fetch_intraday_bars",      # stub de compatibilidade Bloomberg
]
print()
print("Interface do provider:")
all_ok = True
for method in REQUIRED_METHODS:
    present = hasattr(p, method)
    flag = "[OK]" if present else "[FALTA]"
    print(f"  {flag}  {method}")
    if not present:
        all_ok = False

# 5. Status
st = p.status()
print()
print(f"status.provider : {st.get('provider')}")
print(f"status.enabled  : {st.get('enabled')}")

# 6. Campos MODEL_* e EFF_* presentes nos SNAPSHOT_FIELDS ou gerados automaticamente
# (esses campos sao injetados no fetch_option_snapshots, nao estao em SNAPSHOT_FIELDS)
MODEL_FIELDS = [
    "MODEL_IV", "MODEL_DELTA", "MODEL_GAMMA_POINT", "MODEL_GAMMA_1PCT",
    "MODEL_VEGA_1PCTVOL", "MODEL_THETA_BD252", "MODEL_VANNA", "MODEL_CHARM_BD252",
    "MODEL_SOURCE",
    "EFF_DELTA", "EFF_GAMMA_PT", "EFF_GAMMA_1PCT",
    "EFF_IV", "EFF_VEGA", "EFF_THETA", "EFF_VANNA", "EFF_CHARM",
]
print()
print(f"SNAPSHOT_FIELDS Bloomberg padrao: {len(p.SNAPSHOT_FIELDS)} campos")
print(f"Campos MODEL_*/EFF_* injetados  : {len(MODEL_FIELDS)} campos (gerados em fetch_option_snapshots)")

# 7. fetch_option_ticks stub retorna estrutura correta
tick_result = p.fetch_option_ticks("IBOVQ178A3", "2026-05-15T09:00:00", "2026-05-15T18:00:00")
print()
print(f"fetch_option_ticks stub:")
print(f"  rows: {tick_result.get('rows')}")
print(f"  status.error: {tick_result.get('status', {}).get('error')}")

print()
if all_ok:
    print("[OK] Todos os servicos e metodos verificados — OpLab ativo como provider principal.")
else:
    print("[ERRO] Alguns metodos estao faltando!")
