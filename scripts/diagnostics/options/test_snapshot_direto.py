"""
Testa snapshot Bloomberg com tickers de opcoes conhecidos da B3,
e verifica o que ja existe salvo no store local.
"""
import sys, os, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

from app.services.options_bloomberg_service import OptionsBloombergService
from app.services.options_store import OptionsStore

bloomberg = OptionsBloombergService()
store = OptionsStore()

# ─── 1. O que ja existe no store local? ────────────────────────────────
print("\n" + "="*60)
print("  PARTE 1 — Snapshots e universo salvos localmente")
print("="*60)

batches = store.list_snapshot_batches(limit=10)
print(f"\n  Ultimos {len(batches)} snapshot batches no store:")
if batches:
    for b in batches[:5]:
        print(f"    tier={b.get('universe_tier'):<12}  "
              f"underlying={b.get('underlying_security'):<15}  "
              f"date={b.get('session_date')}  "
              f"rows={b.get('row_count', '?')}")
else:
    print("    (nenhum snapshot salvo)")

# Verifica universe state salvo
uploads_dir = os.path.join(ROOT, "backend", "uploads", "options")
universe_files = []
for root, dirs, files in os.walk(uploads_dir):
    for f in files:
        if "universe" in f.lower():
            universe_files.append(os.path.join(root, f))

print(f"\n  Arquivos de universo encontrados: {len(universe_files)}")
for uf in universe_files[:5]:
    try:
        with open(uf, encoding="utf-8") as fh:
            data = json.load(fh)
        critical = data.get("critical") or []
        structural = data.get("structural") or []
        print(f"    {os.path.basename(uf)}: structural={len(structural)} critical={len(critical)}")
        if critical:
            print(f"      Amostra critical: {[r.get('bloomberg_ticker') for r in critical[:3]]}")
        if structural:
            print(f"      Amostra structural: {[r.get('bloomberg_ticker') for r in structural[:3]]}")
    except Exception as e:
        print(f"    {os.path.basename(uf)}: erro ao ler - {e}")

# ─── 2. Tickers de opcoes B3 conhecidos para teste direto ─────────────
print("\n" + "="*60)
print("  PARTE 2 — Snapshot direto com tickers de opcoes B3 conhecidos")
print("="*60)

# Exemplos de tickers de opcoes IBOV/WIN na B3 via Bloomberg
# Formato tipico: WINM26C177000 Index ou IBOV opcoes
OPCOES_TESTE = [
    "WINM26C177000 Index",
    "WINM26P177000 Index",
    "WINM26C180000 Index",
    "WINM26P175000 Index",
    "IBOVESPA C Index",
]

fields_teste = ["PX_LAST", "BID", "ASK", "OPT_STRIKE_PX", "OPT_UNDL_PX",
                "OPT_PUT_CALL", "OPT_EXPIRE_DT", "IVOL_MID", "OPT_OPEN_INTEREST"]

print(f"\n  Testando snapshot com {len(OPCOES_TESTE)} tickers...")
try:
    snap = bloomberg.fetch_option_snapshots(OPCOES_TESTE, fields_teste)
    rows = snap.get("rows") or []
    print(f"  status: {snap.get('status', {})}")
    print(f"  Retornados: {len(rows)} rows")
    for row in rows:
        fields = row.get("fields") or {}
        preenchidos = {k: v for k, v in fields.items() if v is not None}
        print(f"\n    {'OK' if row.get('ok') else 'FAIL'}  {row.get('security')}")
        if preenchidos:
            for k, v in preenchidos.items():
                print(f"           {k}: {v}")
        if row.get("security_error"):
            print(f"           security_error: {row['security_error']}")
        if row.get("field_exceptions"):
            print(f"           field_exceptions: {[fe.get('field_id') for fe in row['field_exceptions']]}")
except Exception as e:
    print(f"  ERRO: {e}")
    import traceback; traceback.print_exc()

# ─── 3. Referencia simples — spot do IBOV ─────────────────────────────
print("\n" + "="*60)
print("  PARTE 3 — Referencia simples: spot IBOV e WIN futuro")
print("="*60)

REF_TICKERS = ["IBOV Index", "IBOVE Index", "XB1 Index", "BVMF:WINM26"]
ref_fields = ["PX_LAST", "BID", "ASK", "CHG_PCT_1D"]

print(f"\n  Testando reference data (fetch_reference_securities)...")
from app.config import Config
# habilita temporariamente
_orig = Config.BLOOMBERG_REALTIME_REFERENCE_ENABLE
Config.BLOOMBERG_REALTIME_REFERENCE_ENABLE = True
try:
    ref = bloomberg.fetch_reference_securities(REF_TICKERS, ref_fields)
    for row in (ref.get("rows") or []):
        fields = row.get("fields") or {}
        print(f"    {'OK' if row.get('ok') else 'FAIL'}  {row.get('security'):<25}  "
              f"PX_LAST={fields.get('PX_LAST')}  CHG={fields.get('CHG_PCT_1D')}  "
              f"err={row.get('security_error', {}).get('message') if row.get('security_error') else ''}")
except Exception as e:
    print(f"  ERRO: {e}")
    import traceback; traceback.print_exc()
finally:
    Config.BLOOMBERG_REALTIME_REFERENCE_ENABLE = _orig

print()
