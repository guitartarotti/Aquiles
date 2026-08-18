"""
Teste end-to-end do OpLabOptionsService via provider factory.
"""
import sys, os, io, json, types, importlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

# ── Stub de qualquer modulo ausente (chamado automaticamente) ─────────────────
class _AutoStub(types.ModuleType):
    """Modulo stub que aceita qualquer atributo/chamada sem erro."""
    class _Any:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return type(self)()
        def __getattr__(self, n): return type(self)()
        def __iter__(self): return iter([])
        def __class_getitem__(cls, item): return cls
    def __getattr__(self, name):
        return self._Any()

def _stub_if_missing(*names):
    for n in names:
        if n not in sys.modules:
            sys.modules[n] = _AutoStub(n)

_stub_if_missing(
    "neo4j", "neo4j.graph", "neo4j.exceptions",
    "graphiti_core", "graphiti_core.nodes", "graphiti_core.edges",
    "graphiti_core.search", "graphiti_core.search.search",
    "graphiti_core.llm_client", "graphiti_core.llm_client.config",
    "openai", "openai.types", "openai.types.chat",
    "anthropic",
    "zep_cloud",
    "blpapi",
)

# Precisamos que openai.OpenAI seja uma classe real para import direto
class _FakeCls:
    def __init__(self, *a, **kw): pass
for _attr in ("OpenAI", "AsyncOpenAI"):
    setattr(sys.modules["openai"], _attr, _FakeCls)
for _attr in ("Anthropic", "AsyncAnthropic"):
    setattr(sys.modules["anthropic"], _attr, _FakeCls)

# ── Injeta stub de app.services ANTES do import real ─────────────────────────
# Isso impede que o __init__.py pesado seja executado
_svc_stub = _AutoStub("app.services")
_svc_stub.__path__ = [os.path.join(BACKEND, "app", "services")]
_svc_stub.__package__ = "app.services"
sys.modules["app.services"] = _svc_stub

# ── Imports reais ─────────────────────────────────────────────────────────────
from app.config import Config  # noqa

# Importa as dependencias do options_data_provider diretamente
import importlib.util

def _load_module(dotted_name: str, file_path: str, package: str = "app.services"):
    """Carrega um modulo de arquivo sem depender do __init__.py."""
    spec = importlib.util.spec_from_file_location(
        dotted_name, file_path, submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = package
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod

_svc_dir = os.path.join(BACKEND, "app", "services")

# Carrega options_data_provider (depende de oplab_options_service e config)
_load_module("app.services.options_data_provider",
             os.path.join(_svc_dir, "options_data_provider.py"))

from app.services.options_data_provider import get_options_data_provider  # noqa

provider = get_options_data_provider()

print("=" * 65)
print(f"  Provider: {type(provider).__name__}")
print("=" * 65)

# ─── TESTE 1 — status ────────────────────────────────────────────────────────
print()
print("TESTE 1 — status()")
print("-" * 40)
st = provider.status()
print(f"  provider     : {st.get('provider')}")
print(f"  enabled      : {st.get('enabled')}")
print(f"  session_ok   : {st.get('session_ok')}")
print(f"  market_status: {st.get('market_status')}")
print(f"  error        : {st.get('error')}")

# ─── TESTE 2 — fetch_option_chain ────────────────────────────────────────────
print()
print("TESTE 2 — fetch_option_chain('IBOVE Index')")
print("-" * 40)
chain_result = provider.fetch_option_chain("IBOVE Index")
chain = chain_result.get("chain", [])
print(f"  count        : {chain_result.get('count')}")
print(f"  primeiros 10 : {chain[:10]}")
print(f"  status.error : {chain_result.get('status', {}).get('error')}")

if not chain:
    print("  AVISO: chain vazia — verifique OPLAB_UNDERLYING_MAP e token")
    sys.exit(1)

# ─── TESTE 3 — fetch_option_snapshots ────────────────────────────────────────
print()
print("TESTE 3 — fetch_option_snapshots(chain[:5])")
print("-" * 40)
snap = provider.fetch_option_snapshots(chain[:5], None)
rows = snap.get("rows", [])
print(f"  rows total   : {len(rows)}")
print(f"  captured     : {snap.get('status', {}).get('captured_count')}")
print(f"  failed       : {snap.get('status', {}).get('failed_count')}")
for r in rows:
    f = r.get("fields", {})
    print(
        f"  {r['security']:<15} ok={r['ok']}  "
        f"PX_LAST={f.get('PX_LAST')}  "
        f"DELTA={f.get('OPT_DELTA')}  "
        f"IVOL={f.get('IVOL_MID')}  "
        f"OI={f.get('OPT_OPEN_INTEREST')}  "
        f"STRIKE={f.get('OPT_STRIKE_PX')}  "
        f"EXP={f.get('OPT_EXPIRE_DT')}  "
        f"TYPE={f.get('OPT_PUT_CALL')}"
    )

# ─── TESTE 4 — fetch_option_history ──────────────────────────────────────────
print()
print(f"TESTE 4 — fetch_option_history({chain[0]!r}, '2026-05-12', '2026-05-15')")
print("-" * 40)
hist = provider.fetch_option_history(chain[0], "2026-05-12", "2026-05-15", None)
hist_rows = hist.get("rows", [])
print(f"  linhas       : {len(hist_rows)}")
for r in hist_rows:
    f = r.get("fields", {})
    print(
        f"  {r.get('trade_date')}  PX_LAST={f.get('PX_LAST')}  "
        f"IVOL={f.get('IVOL_MID')}  DELTA={f.get('OPT_DELTA')}  "
        f"OI={f.get('OPT_OPEN_INTEREST')}"
    )
if not hist_rows:
    print("  (sem historico para esse ticker no intervalo — normal se mercado fechado)")

# ─── TESTE 5 — provider correto ──────────────────────────────────────────────
print()
print("TESTE 5 — verifica que Bloomberg NAO esta sendo usado")
print("-" * 40)
print(f"  OPLAB_ENABLE            : {Config.OPLAB_ENABLE}")
print(f"  OPTIONS_BLOOMBERG_ENABLE: {getattr(Config, 'OPTIONS_BLOOMBERG_ENABLE', 'N/A')}")
print(f"  Provider class          : {type(provider).__name__}")
assert type(provider).__name__ == "OpLabOptionsService", "ERRO: provider nao e OpLab!"
print("  [OK] OpLabOptionsService confirmado")

print()
print("[OK] Todos os testes concluidos!")
