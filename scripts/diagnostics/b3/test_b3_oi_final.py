"""
Teste end-to-end do B3OIService:
  1. Coleta OI do dia 14/05/2026
  2. Verifica persistencia no store
  3. Testa lookup por simbolo
  4. Testa get_oi_map
  5. Testa checkpoint (nao re-coleta)
"""
import sys, os, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

from app.services.b3_oi_service import B3OIService
from app.services.options_store import OptionsStore

store = OptionsStore()
service = B3OIService(store=store)

TEST_DATE = "2026-05-14"

print("=" * 60)
print(f"  TESTE 1 — Coleta OI B3 para {TEST_DATE}")
print("=" * 60)

result = service.collect_daily_oi(trade_date=TEST_DATE, force=True)
print(f"  skipped    : {result.get('skipped')}")
print(f"  rows_saved : {result.get('rows_saved')}")
print(f"  error      : {result.get('error')}")

rows = result.get("rows") or []
if rows:
    print(f"\n  Primeiros 5 contratos:")
    for r in rows[:5]:
        print(f"    {r['symbol']:<15} strike={r['strike']:>10.0f}  OI_total={r['oi_total']:>8}  tipo={r['type']}")

    # Estatisticas
    calls = [r for r in rows if r["type"] == "CALL"]
    puts  = [r for r in rows if r["type"] == "PUT"]
    com_oi = [r for r in rows if r["oi_total"] > 0]
    print(f"\n  Total contratos: {len(rows)} ({len(calls)} CALL, {len(puts)} PUT)")
    print(f"  Com OI > 0: {len(com_oi)}")
    if com_oi:
        top5 = sorted(com_oi, key=lambda x: x["oi_total"], reverse=True)[:5]
        print(f"\n  Top 5 por OI:")
        for r in top5:
            print(f"    {r['symbol']:<15} OI={r['oi_total']:>10}  strike={r['strike']:>10.0f}  tipo={r['type']}")

print()
print("=" * 60)
print("  TESTE 2 — Verifica persistencia no store")
print("=" * 60)

loaded = store.load_b3_oi_rows(TEST_DATE)
print(f"  Registros carregados do disco: {len(loaded)}")
if loaded:
    print(f"  Primeiro: {loaded[0]}")

print()
print("=" * 60)
print("  TESTE 3 — Lookup por simbolo")
print("=" * 60)

# Pega um simbolo do resultado para testar
test_symbol = rows[0]["symbol"] if rows else "IBOVF178"
oi = service.get_oi(symbol=test_symbol, trade_date=TEST_DATE)
print(f"  OI para {test_symbol}: {json.dumps(oi, ensure_ascii=False)}")

print()
print("=" * 60)
print("  TESTE 4 — get_oi_map (para uso no Wyrm)")
print("=" * 60)

oi_map = service.get_oi_map(trade_date=TEST_DATE)
print(f"  Mapa retornou {len(oi_map)} entradas")
if oi_map:
    sample_key = list(oi_map.keys())[0]
    print(f"  Exemplo: {sample_key} -> {oi_map[sample_key]}")

print()
print("=" * 60)
print("  TESTE 5 — Checkpoint (nao deve re-coletar)")
print("=" * 60)

result2 = service.collect_daily_oi(trade_date=TEST_DATE, force=False)
print(f"  skipped: {result2.get('skipped')}  (esperado: True)")
print(f"  skip_reason: {result2.get('skip_reason')}")

print()
print("=" * 60)
print("  TESTE 6 — Datas coletadas")
print("=" * 60)

dates = service.list_collected_dates()
print(f"  Datas com OI salvo: {dates}")

print()
print("[OK] Todos os testes concluidos!")
