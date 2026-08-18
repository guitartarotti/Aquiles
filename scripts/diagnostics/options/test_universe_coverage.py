"""
Diagnóstico de cobertura do universo IBOV até 80 DU:
  - Quantas opções a OpLab retorna na chain (com e sem DTM)
  - Quantas têm dados de preço (close/bid/ask)
  - Quantas têm gregas no histórico (delta/IV)
  - Quantas têm Open Interest na B3
"""
import sys, os, io, types, logging
from datetime import datetime, timedelta, timezone
from collections import Counter

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

from app.services.oplab_options_service import OpLabOptionsService, _business_days_to_expiry

svc = OpLabOptionsService()

# ── 1. Chain completa do IBOV (sem filtro de DTM) ─────────────────────────────
print("Buscando chain completa IBOV...", flush=True)
raw = svc._make_request("GET", "/market/options/IBOV")
all_rows = raw if isinstance(raw, list) else []

print(f"Total de contratos na chain (sem filtro): {len(all_rows)}")

# Clasifica por DTM
def get_dtm(row):
    dtm = row.get("days_to_maturity")
    if dtm is not None:
        try: return int(dtm)
        except: pass
    due = row.get("due_date")
    return _business_days_to_expiry(due)

dtm_present  = [r for r in all_rows if r.get("days_to_maturity") is not None]
dtm_computed = [r for r in all_rows if r.get("days_to_maturity") is None and r.get("due_date")]

rows_80 = [r for r in all_rows if (get_dtm(r) or 9999) <= 80]
rows_over = [r for r in all_rows if (get_dtm(r) or 0) > 80]

print(f"  com days_to_maturity na chain   : {len(dtm_present)}")
print(f"  DTM calculado via due_date      : {len(dtm_computed)}")
print(f"  até 80 DU                       : {len(rows_80)}")
print(f"  acima de 80 DU                  : {len(rows_over)}")
print()

# ── 2. Cobertura de preços na chain (até 80 DU) ───────────────────────────────
has_close = sum(1 for r in rows_80 if r.get("close") and float(r["close"]) > 0)
has_bid   = sum(1 for r in rows_80 if r.get("bid")   and float(r["bid"])   > 0)
has_ask   = sum(1 for r in rows_80 if r.get("ask")   and float(r["ask"])   > 0)
has_bid_ask = sum(1 for r in rows_80
                  if r.get("bid") and r.get("ask")
                  and float(r["bid"]) > 0 and float(r["ask"]) > 0)
has_any_price = sum(1 for r in rows_80
                    if (r.get("close") and float(r["close"]) > 0)
                    or (r.get("bid")   and float(r["bid"])   > 0)
                    or (r.get("ask")   and float(r["ask"])   > 0))

print(f"=== Cobertura de PREÇOS na chain OpLab (≤80 DU) ===")
print(f"  Total contratos ≤80 DU  : {len(rows_80)}")
print(f"  com close > 0           : {has_close} ({has_close/len(rows_80)*100:.1f}%)")
print(f"  com bid > 0             : {has_bid}   ({has_bid/len(rows_80)*100:.1f}%)")
print(f"  com ask > 0             : {has_ask}   ({has_ask/len(rows_80)*100:.1f}%)")
print(f"  com bid E ask > 0       : {has_bid_ask} ({has_bid_ask/len(rows_80)*100:.1f}%)")
print(f"  com qualquer preço      : {has_any_price} ({has_any_price/len(rows_80)*100:.1f}%)")
print()

# ── 3. Cobertura de gregas no histórico ───────────────────────────────────────
print("Buscando gregas históricas OpLab (hoje e D-1)...", flush=True)
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

greeks_today = svc._get_greeks_cache("IBOV", today)
greeks_yday  = svc._get_greeks_cache("IBOV", yesterday)

greeks_list = greeks_today if greeks_today else greeks_yday
greeks_date = today if greeks_today else yesterday
greeks_by_sym = {g.get("symbol"): g for g in greeks_list if g.get("symbol")}

syms_80 = {r.get("symbol") for r in rows_80}

with_delta  = sum(1 for s in syms_80 if greeks_by_sym.get(s, {}).get("delta") is not None)
with_iv     = sum(1 for s in syms_80 if greeks_by_sym.get(s, {}).get("volatility") is not None)
with_gamma  = sum(1 for s in syms_80 if greeks_by_sym.get(s, {}).get("gamma") is not None)
with_theta  = sum(1 for s in syms_80 if greeks_by_sym.get(s, {}).get("theta") is not None)

print(f"=== Cobertura de GREGAS OpLab histórico ({greeks_date}) ===")
print(f"  Total símbolos ≤80 DU   : {len(syms_80)}")
print(f"  Total no histórico      : {len(greeks_list)}")
print(f"  com delta               : {with_delta} ({with_delta/len(syms_80)*100:.1f}%)")
print(f"  com IV (volatility)     : {with_iv}    ({with_iv/len(syms_80)*100:.1f}%)")
print(f"  com gamma               : {with_gamma}  ({with_gamma/len(syms_80)*100:.1f}%)")
print(f"  com theta               : {with_theta}  ({with_theta/len(syms_80)*100:.1f}%)")
print()

# ── 4. Open Interest B3 ───────────────────────────────────────────────────────
print("Verificando Open Interest B3 (amostra de até 200 contratos)...", flush=True)
try:
    from app.services.b3_oi_service import B3OIService
    b3 = B3OIService()

    syms_sample = list(syms_80)[:200]
    oi_today_count = 0
    oi_yday_count  = 0
    oi_any_count   = 0

    yday_bd = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    # pula final de semana
    d = datetime.now(timezone.utc).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    last_bd = d.isoformat()

    for sym in syms_sample:
        rec_t = b3.get_oi(sym, trade_date=today)
        rec_y = b3.get_oi(sym, trade_date=last_bd) if rec_t is None else None
        if rec_t and (rec_t.get("oi_total") or 0) > 0:
            oi_today_count += 1
            oi_any_count   += 1
        elif rec_y and (rec_y.get("oi_total") or 0) > 0:
            oi_yday_count += 1
            oi_any_count  += 1

    print(f"=== Cobertura de OPEN INTEREST B3 (amostra {len(syms_sample)} contratos) ===")
    print(f"  com OI hoje ({today})  : {oi_today_count}")
    print(f"  com OI D-1  ({last_bd}) : {oi_yday_count}")
    print(f"  com OI (hoje ou D-1)    : {oi_any_count} ({oi_any_count/len(syms_sample)*100:.1f}%)")
    print(f"  sem OI nenhum           : {len(syms_sample)-oi_any_count} ({(len(syms_sample)-oi_any_count)/len(syms_sample)*100:.1f}%)")

    # Extrapolação para universo completo
    frac = oi_any_count / len(syms_sample) if syms_sample else 0
    print(f"\n  Estimativa para os {len(syms_80)} contratos ≤80 DU: ~{int(frac*len(syms_80))} com OI")

except Exception as e:
    print(f"B3OIService não disponível: {e}")

# ── 5. Breakdown por vencimento ───────────────────────────────────────────────
print()
print("=== Breakdown por vencimento (contratos ≤80 DU) ===")
from collections import defaultdict
by_due = defaultdict(list)
for r in rows_80:
    due = (r.get("due_date") or "?")[:10]
    by_due[due].append(r)

for due in sorted(by_due.keys()):
    bucket = by_due[due]
    dtm_val = get_dtm(bucket[0]) if bucket else "?"
    calls = sum(1 for r in bucket if str(r.get("type","")).upper() == "CALL")
    puts  = sum(1 for r in bucket if str(r.get("type","")).upper() == "PUT")
    priced = sum(1 for r in bucket if (r.get("close") and float(r["close"]) > 0))
    print(f"  {due} (DU≈{dtm_val:>3})  total={len(bucket):>4}  calls={calls:>3}  puts={puts:>3}  com_preço={priced:>4}")
