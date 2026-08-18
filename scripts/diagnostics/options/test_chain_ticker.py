"""
Teste de qual ticker Bloomberg retorna option chain.
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

from app.services.options_bloomberg_service import OptionsBloombergService

bloomberg = OptionsBloombergService()

# Candidatos para underlying de opcoes IBOV/WIN
CANDIDATES = [
    "IBOVE Index",   # como esta no .env agora
    "IBOV Index",
    "WINM26 Index",
    "WINQ26 Index",
    "WIN Index",
    "BVSP Index",
    "IBV Index",
]

print("\nTestando option chain para cada ticker candidato...\n")
print(f"{'TICKER':<30}  {'CHAIN'}  {'NOTA'}")
print("-" * 70)

for ticker in CANDIDATES:
    try:
        res = bloomberg.fetch_option_chain(ticker)
        chain = res.get("chain") or []
        sec_err = res.get("security_error")
        field_ex = res.get("field_exceptions") or []
        nota = ""
        if sec_err:
            nota = f"security_error: {sec_err.get('message', sec_err)}"
        elif field_ex:
            nota = f"field_exceptions: {[fe.get('field_id') for fe in field_ex[:2]]}"
        count = len(chain)
        icon = "[OK]  " if count > 0 else "[VAZIO]"
        sample = chain[0] if chain else ""
        print(f"{ticker:<30}  {icon}  {count:>4} contratos  {sample[:30]}  {nota}")
    except Exception as exc:
        print(f"{ticker:<30}  [ERRO]  {exc}")

print()
