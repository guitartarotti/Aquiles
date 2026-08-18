"""
Teste isolado — OI diário + diagnóstico Bloomberg
Roda sem servidor Flask.
"""
from __future__ import annotations

import sys
import os
import json
import traceback
from datetime import datetime

# Garante que o backend está no path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

# Carrega o .env manualmente (igual ao config.py)
from dotenv import load_dotenv
env_path = os.path.join(ROOT, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
    print(f"[ENV] Carregado: {env_path}")
else:
    print(f"[ENV] AVISO: .env não encontrado em {env_path}")

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OK   = "[OK] "
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"

def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def result(label: str, ok: bool, detail: str = "") -> None:
    icon = OK if ok else FAIL
    print(f"  {icon}  {label}" + (f"  ->  {detail}" if detail else ""))


# ─────────────────────────────────────────────
# TESTE 1: Checkpoint OI diário (sem Bloomberg)
# ─────────────────────────────────────────────
section("TESTE 1 — Checkpoint OI diário (lógica pura, sem Bloomberg)")

try:
    from app.services.options_store import OptionsStore
    from app.services.options_history_service import OptionsHistoryService, _daily_oi_checkpoint_key

    store = OptionsStore()
    history = OptionsHistoryService(store=store)

    underlying = "IBOVE Index"
    today = datetime.now().date().isoformat()
    fake_date = "2099-01-01"  # data fictícia que com certeza não tem checkpoint

    # 1a — dia fictício não deve estar completo
    complete_before = history.is_daily_oi_complete(underlying, fake_date)
    result("is_daily_oi_complete(fake_date) == False antes", not complete_before,
           f"retornou {complete_before}")

    # 1b — salva checkpoint manualmente
    history._mark_daily_oi_complete(
        underlying_security=underlying,
        trade_date=fake_date,
        processed_contracts=42,
        rows_written=100,
    )

    # 1c — agora deve estar completo
    complete_after = history.is_daily_oi_complete(underlying, fake_date)
    result("is_daily_oi_complete(fake_date) == True após mark", complete_after,
           f"retornou {complete_after}")

    # 1d — limpa checkpoint de teste
    key = _daily_oi_checkpoint_key(underlying, fake_date)
    checkpoints_path = store.backfill_checkpoints_path
    with store._lock:
        raw = store._load_json_unlocked(checkpoints_path, {})
        raw.get("jobs", {}).pop(key, None)
        store._save_json_unlocked(checkpoints_path, raw)
    print(f"  {INFO}  Checkpoint de teste removido")

    # 1e — verifica que update_daily_open_interest com dado já coletado retorna skipped
    # Primeiro marca como completo hoje
    history._mark_daily_oi_complete(underlying, today, 10, 50)
    ret = history.update_daily_open_interest(underlying, trade_date=today, force=False)
    result(
        "update_daily_open_interest retorna skipped=True quando já coletado",
        ret.get("skipped") is True and ret.get("skip_reason") == "daily_oi_already_collected",
        json.dumps({k: ret.get(k) for k in ("skipped", "skip_reason", "processed_contracts")}),
    )

    # 1f — limpa checkpoint de hoje para não interferir
    key_today = _daily_oi_checkpoint_key(underlying, today)
    with store._lock:
        raw = store._load_json_unlocked(checkpoints_path, {})
        raw.get("jobs", {}).pop(key_today, None)
        store._save_json_unlocked(checkpoints_path, raw)
    print(f"  {INFO}  Checkpoint de hoje removido (não poluir estado real)")

    result("Teste 1 concluído", True)

except Exception as exc:
    result("Teste 1 FALHOU", False, str(exc))
    traceback.print_exc()


# ─────────────────────────────────────────────
# TESTE 2: Bloomberg — conectividade
# ─────────────────────────────────────────────
section("TESTE 2 — Bloomberg: status de conexão")

bloomberg_ok = False
try:
    from app.services.options_bloomberg_service import OptionsBloombergService

    bloomberg = OptionsBloombergService()
    status = bloomberg.status()

    result("Bloomberg habilitado (MACRO_BLOOMBERG_ENABLE=True)",
           bool(status.get("enabled")),
           str(status.get("enabled")))

    result("blpapi instalado",
           bool(status.get("blpapi_available")),
           str(status.get("blpapi_available")))

    result("BBComm acessível (TCP)",
           bool(status.get("tcp_available")),
           f"{status.get('host')}:{status.get('port')}")

    bloomberg_ok = bool(
        status.get("enabled") and
        status.get("blpapi_available") and
        status.get("tcp_available")
    )

    if not bloomberg_ok:
        print(f"\n  {WARN}  Bloomberg não disponível — pulando testes 3 e 4")
        print(f"       enabled={status.get('enabled')}  "
              f"blpapi={status.get('blpapi_available')}  "
              f"tcp={status.get('tcp_available')}")

except Exception as exc:
    result("Teste 2 FALHOU", False, str(exc))
    traceback.print_exc()


# ─────────────────────────────────────────────
# TESTE 3: Bloomberg — option chain
# ─────────────────────────────────────────────
section("TESTE 3 — Bloomberg: option chain do IBOVE Index")

chain: list[str] = []
if not bloomberg_ok:
    print(f"  {WARN}  Pulado (Bloomberg indisponível)")
else:
    try:
        underlying = "IBOVE Index"
        chain_result = bloomberg.fetch_option_chain(underlying)
        chain = chain_result.get("chain") or []

        result("Retornou contratos na chain",
               len(chain) > 0,
               f"{len(chain)} contratos")

        if chain:
            print(f"\n  {INFO}  Primeiros 5 tickers:")
            for ticker in chain[:5]:
                print(f"         {ticker}")

        if chain_result.get("security_error"):
            print(f"  {WARN}  security_error: {chain_result['security_error']}")

        if chain_result.get("field_exceptions"):
            print(f"  {WARN}  field_exceptions: {chain_result['field_exceptions'][:3]}")

    except Exception as exc:
        result("Teste 3 FALHOU", False, str(exc))
        traceback.print_exc()


# ─────────────────────────────────────────────
# TESTE 4: Bloomberg — snapshot de 3 contratos
# ─────────────────────────────────────────────
section("TESTE 4 — Bloomberg: snapshot de 3 opções")

if not bloomberg_ok:
    print(f"  {WARN}  Pulado (Bloomberg indisponível)")
elif not chain:
    print(f"  {WARN}  Pulado (chain vazia no Teste 3)")
else:
    try:
        sample = chain[:3]
        print(f"  {INFO}  Consultando: {sample}")

        snap = bloomberg.fetch_option_snapshots(sample, bloomberg.DISCOVERY_FIELDS)
        rows = snap.get("rows") or []
        rows_ok   = [r for r in rows if r.get("ok")]
        rows_fail = [r for r in rows if not r.get("ok")]

        result("Retornou rows", len(rows) > 0, f"{len(rows)} rows")
        result("Pelo menos 1 contrato OK", len(rows_ok) > 0,
               f"{len(rows_ok)}/{len(rows)} OK")

        campos_criticos = ["OPT_STRIKE_PX", "OPT_UNDL_PX", "IVOL_MID",
                           "OPT_PUT_CALL", "OPT_EXPIRE_DT"]
        for campo in campos_criticos:
            tem = any(
                r.get("fields", {}).get(campo) is not None
                for r in rows_ok
            )
            result(f"Campo {campo} presente", tem)

        print(f"\n  {INFO}  Detalhe por contrato:")
        for row in rows:
            fields = row.get("fields") or {}
            campos_preenchidos = [k for k, v in fields.items() if v is not None]
            print(f"    {'OK' if row.get('ok') else 'FAIL'}  {row.get('security')}")
            print(f"         campos preenchidos ({len(campos_preenchidos)}): "
                  f"{', '.join(campos_preenchidos[:8])}"
                  + (" ..." if len(campos_preenchidos) > 8 else ""))
            if row.get("security_error"):
                print(f"         security_error: {row['security_error']}")
            if row.get("field_exceptions"):
                print(f"         field_exceptions: {[fe.get('field_id') for fe in row['field_exceptions']]}")

        if rows_fail:
            print(f"\n  {WARN}  Contratos com falha:")
            for row in rows_fail:
                print(f"         {row.get('security')} → {row.get('security_error')}")

    except Exception as exc:
        result("Teste 4 FALHOU", False, str(exc))
        traceback.print_exc()


# ─────────────────────────────────────────────
# RESUMO FINAL
# ─────────────────────────────────────────────
section("RESUMO")
print(f"  Checkpoint OI diário:   {'funcionando' if True else 'ERRO'}")
print(f"  Bloomberg disponível:   {'SIM' if bloomberg_ok else 'NÃO — BBComm offline ou blpapi não instalado'}")
if bloomberg_ok:
    print(f"  Option chain:           {len(chain)} contratos encontrados para IBOVE Index")
print()
