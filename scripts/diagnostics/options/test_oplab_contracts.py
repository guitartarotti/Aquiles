"""
Testa o ciclo completo de discovery de contratos via OpLab:
  1. fetch_option_chain → chain_rows com metadados
  2. normalize_contract via chain_row (sem regex Bloomberg)
  3. Contratos validos e mvp_eligible
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

import importlib.util, os as _os
def _load(name, path, pkg="app.services"):
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_d = _os.path.join(BACKEND, "app", "services")
_load("app.services.options_data_provider", _os.path.join(_d, "options_data_provider.py"))

from app.services.options_data_provider import get_options_data_provider
from app.services.options_store import OptionsStore
from app.services.options_contract_service import OptionsContractService

provider = get_options_data_provider()
store = OptionsStore()
contract_service = OptionsContractService(store=store, bloomberg=provider)

print("=" * 65)
print("TESTE 1 — fetch_option_chain retorna chain_rows")
print("=" * 65)
chain_result = provider.fetch_option_chain("IBOVE Index")
print(f"  chain count    : {chain_result.get('count')}")
print(f"  chain_rows len : {len(chain_result.get('chain_rows', []))}")
sample_row = chain_result.get("chain_rows", [{}])[0] if chain_result.get("chain_rows") else {}
print(f"  sample row     : {json.dumps(sample_row, ensure_ascii=False)[:200]}")

print()
print("=" * 65)
print("TESTE 2 — normalize_contract via chain_row")
print("=" * 65)
chain_rows = chain_result.get("chain_rows", [])
# Testa com um contrato especifico
test_row = next((r for r in chain_rows if r.get("type") == "CALL" and (r.get("days_to_maturity") or 0) >= 5), None)
if test_row:
    symbol = test_row["symbol"]
    contract = contract_service.normalize_contract(symbol, "IBOVE Index", chain_row=test_row)
    print(f"  symbol         : {symbol}")
    print(f"  option_id      : {contract.get('option_id')}")
    print(f"  put_call       : {contract.get('put_call')}")
    print(f"  strike         : {contract.get('strike')}")
    print(f"  expiry_date    : {contract.get('expiry_date')}")
    print(f"  dtm_business   : {contract.get('days_to_expiry_business')}")
    print(f"  status         : {contract.get('status')}")
    print(f"  mvp_eligible   : {contract.get('mvp_eligible')}")
    print(f"  source         : {contract.get('source')}")
    valid, errors = contract_service.validate_contract(contract)
    print(f"  valid          : {valid}  errors={errors}")
else:
    print("  AVISO: nenhum contrato CALL com dtm>=5 encontrado")

print()
print("=" * 65)
print("TESTE 3 — discover_underlying_contracts completo")
print("=" * 65)
discovery = contract_service.discover_underlying_contracts("IBOVE Index")
print(f"  chain_count    : {discovery.get('chain_count')}")
print(f"  valid_count    : {discovery.get('valid_contract_count')}")
print(f"  invalid_count  : {discovery.get('invalid_contract_count')}")

contracts = discovery.get("contracts", [])
active = [c for c in contracts if c.get("status") == "active"]
mvp = [c for c in contracts if c.get("mvp_eligible")]
print(f"  active         : {len(active)}")
print(f"  mvp_eligible   : {len(mvp)}")

# Mostra primeiros 5 contratos MVP
print(f"\n  Primeiros 5 MVP:")
for c in sorted(mvp, key=lambda x: x.get("days_to_expiry_business", 999))[:5]:
    print(
        f"    {c['bloomberg_ticker']:<15} "
        f"put_call={c['put_call']:<5} "
        f"strike={c.get('strike'):<10} "
        f"exp={c.get('expiry_date')}  "
        f"dtm={c.get('days_to_expiry_business')}"
    )

# Invalidos
if discovery.get("invalid_contracts"):
    print(f"\n  Sample invalidos (primeiros 3):")
    for inv in discovery.get("invalid_contracts", [])[:3]:
        print(f"    {inv.get('security')}: {inv.get('errors')}")

print()
print("[OK] Testes concluidos!")
