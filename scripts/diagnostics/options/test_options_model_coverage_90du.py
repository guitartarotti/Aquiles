"""
Auditoria end-to-end do modelo de opções IBOV usando:
  - chain completa da OpLab
  - OI da B3 do último dia útil publicado
  - snapshot full <= 90 DU
  - run completo do modelo

Mede:
  - quantas opções a OpLab retorna
  - quantas ficam dentro de 90 DU
  - quantas batem com OI > 0 da B3
  - quantas conseguem gregas calculadas no snapshot
  - quantas entram no modelo com OI > 0
  - quantos vencimentos e strikes por vencimento ficam utilizáveis
"""
import io
import os
import sys
import time
import types
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"), override=True)

_svc = types.ModuleType("app.services")
_svc.__path__ = [os.path.join(BACKEND, "app", "services")]
_svc.__package__ = "app.services"
sys.modules["app.services"] = _svc

from app.config import Config  # noqa: E402
from app.services.b3_oi_service import B3OIService  # noqa: E402
from app.services.oplab_options_service import OpLabOptionsService, _business_days_to_expiry  # noqa: E402
from app.services.options_modeling.service import OptionsModelingService  # noqa: E402
from app.services.options_snapshot_service import OptionsSnapshotService  # noqa: E402
from app.services.options_store import OptionsStore  # noqa: E402

UNDERLYING = "IBOVE Index"
UNDERLYING_SYMBOL = "IBOV"
TARGET_DU = int(getattr(Config, "OPTIONS_MAX_BUSINESS_DAYS", 90))
POLL_INTERVAL_SECONDS = 0.5
MAX_POLLS = 6
STABLE_ROUNDS = 2


def get_dtm(row: dict) -> int | None:
    dtm = row.get("days_to_maturity")
    if dtm is not None:
        try:
            return int(dtm)
        except Exception:
            pass
    return _business_days_to_expiry(row.get("due_date"))


def poll_stable_chain(provider: OpLabOptionsService) -> tuple[list[dict], list[dict]]:
    last_symbols: set[str] | None = None
    stable_rounds = 0
    attempts: list[dict] = []
    chosen_rows: list[dict] = []

    for attempt in range(1, MAX_POLLS + 1):
        data = provider._make_request("GET", f"/market/options/{UNDERLYING_SYMBOL}")
        rows = data if isinstance(data, list) else []
        symbols = {str(row.get("symbol") or "") for row in rows if row.get("symbol")}
        diff_vs_prev = None if last_symbols is None else len(symbols.symmetric_difference(last_symbols))
        attempts.append({
            "attempt": attempt,
            "count": len(rows),
            "unique": len(symbols),
            "diff_vs_prev": diff_vs_prev,
        })
        if last_symbols is not None and symbols == last_symbols:
            stable_rounds += 1
        else:
            stable_rounds = 0
        last_symbols = symbols
        chosen_rows = rows
        if stable_rounds >= STABLE_ROUNDS:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    return chosen_rows, attempts


def print_expiry_breakdown(title: str, rows: list[dict]) -> None:
    grouped: dict[str, set[float]] = defaultdict(set)
    for row in rows:
        expiry = str(row.get("expiry_date") or row.get("OPT_EXPIRE_DT") or row.get("due_date") or "")[:10]
        strike = row.get("strike") or row.get("OPT_STRIKE_PX")
        if not expiry or strike in (None, ""):
            continue
        grouped[expiry].add(float(strike))
    print(f"\n{title}")
    for expiry in sorted(grouped):
        print(f"  {expiry}: {len(grouped[expiry])} strikes")


def main() -> int:
    provider = OpLabOptionsService()
    b3_service = B3OIService()
    snapshot_service = OptionsSnapshotService()
    model_service = OptionsModelingService()
    store = OptionsStore()

    print(f"Underlying: {UNDERLYING}")
    print(f"Target DU : {TARGET_DU}")

    raw_rows, attempts = poll_stable_chain(provider)
    rows_90: list[dict] = []
    for row in raw_rows:
        dtm = get_dtm(row)
        if (dtm if dtm is not None else 9999) <= TARGET_DU:
            rows_90.append(row)
    chain_symbols_90 = {str(row.get("symbol") or "") for row in rows_90 if row.get("symbol")}

    print("\n=== OpLab chain stability ===")
    for item in attempts:
        print(
            f"  attempt={item['attempt']} total={item['count']} "
            f"unique={item['unique']} diff_vs_prev={item['diff_vs_prev']}"
        )

    print("\n=== OpLab chain coverage ===")
    print(f"  total raw chain            : {len(raw_rows)}")
    print(f"  total <= {TARGET_DU} DU           : {len(rows_90)}")

    last_b3_trade_date = b3_service.last_published_trade_date()
    oi_ready = b3_service.ensure_recent_oi(trade_date=last_b3_trade_date)
    oi_payload = b3_service.get_recent_oi_map(trade_date=last_b3_trade_date, lookback_business_days=5, ensure=False)
    oi_trade_date = oi_payload.get("trade_date")
    oi_map = oi_payload.get("map") or {}
    oi_positive_symbols = {
        str(symbol).upper()
        for symbol, row in oi_map.items()
        if symbol and float(row.get("oi_total") or 0) > 0
    }
    matched_oi_symbols = {
        symbol for symbol in chain_symbols_90
        if symbol.upper() in oi_positive_symbols
    }

    print("\n=== B3 OI coverage ===")
    print(f"  requested trade date       : {last_b3_trade_date}")
    print(f"  resolved trade date        : {oi_trade_date}")
    print(f"  ensure_recent_oi error     : {oi_ready.get('error')}")
    print(f"  B3 symbols with OI > 0     : {len(oi_positive_symbols)}")
    print(f"  OpLab <= {TARGET_DU} DU with OI>0 : {len(matched_oi_symbols)}")

    print("\nColetando snapshot full...", flush=True)
    snapshot_result = snapshot_service.collect_full_snapshot(UNDERLYING)
    batch = snapshot_result.get("batch") or {}
    payload = store.read_snapshot_batch("full", str(batch.get("session_date") or ""), str(batch.get("batch_key") or ""))
    snapshot_rows = payload.get("rows") or []

    snapshot_with_oi = [
        row for row in snapshot_rows
        if float(row.get("OPEN_INT") or row.get("OPT_OPEN_INTEREST") or 0) > 0
    ]
    snapshot_with_greeks = [
        row for row in snapshot_rows
        if row.get("EFF_DELTA") is not None and row.get("EFF_GAMMA_PT") is not None
    ]
    snapshot_with_oi_and_greeks = [
        row for row in snapshot_rows
        if float(row.get("OPEN_INT") or row.get("OPT_OPEN_INTEREST") or 0) > 0
        and row.get("EFF_DELTA") is not None
        and row.get("EFF_GAMMA_PT") is not None
    ]

    print("\n=== Snapshot full ===")
    print(f"  rows captured              : {len(snapshot_rows)}")
    print(f"  rows with OI > 0           : {len(snapshot_with_oi)}")
    print(f"  rows with greek coverage   : {len(snapshot_with_greeks)}")
    print(f"  rows with OI + greeks      : {len(snapshot_with_oi_and_greeks)}")

    print("\nRodando modelo full...", flush=True)
    result = model_service.run_from_snapshot_payload(payload, persist=True)
    prepared = result.get("prepared_options") or []
    exposures = result.get("option_exposures") or []

    prepared_with_oi = [row for row in prepared if float(row.get("open_int") or 0) > 0]
    exposure_with_signal = [
        item for item in exposures
        if float(((item.get("option") or {}).get("open_int") or 0)) > 0
    ]
    exposure_nonzero_gex = [item for item in exposure_with_signal if abs(float(item.get("gex") or 0)) > 0]
    exposure_nonzero_dex = [item for item in exposure_with_signal if abs(float(item.get("dex") or 0)) > 0]

    print("\n=== Model run ===")
    print(f"  run_id                     : {str(result.get('run_id') or '')[:12]}...")
    print(f"  diagnostics.prepared_count : {(result.get('diagnostics') or {}).get('prepared_count')}")
    print(f"  diagnostics.model_fallback : {(result.get('diagnostics') or {}).get('model_greek_fallback_count')}")
    print(f"  diagnostics.b3_oi_trade_dt : {(result.get('diagnostics') or {}).get('b3_oi_trade_date')}")
    print(f"  prepared total             : {len(prepared)}")
    print(f"  prepared with OI > 0       : {len(prepared_with_oi)}")
    print(f"  exposures with OI > 0      : {len(exposure_with_signal)}")
    print(f"  exposures with nonzero GEX : {len(exposure_nonzero_gex)}")
    print(f"  exposures with nonzero DEX : {len(exposure_nonzero_dex)}")

    print_expiry_breakdown("=== Expiry/strike breakdown: snapshot rows with OI + greeks ===", snapshot_with_oi_and_greeks)
    print_expiry_breakdown("=== Expiry/strike breakdown: prepared options with OI > 0 ===", prepared_with_oi)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
