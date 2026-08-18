from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.options_bloomberg_service import OptionsBloombergService
from app.services.options_history_service import OptionsHistoryService
from app.services.options_query_service import OptionsQueryService
from app.services.options_snapshot_service import OptionsSnapshotService


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for the options Bloomberg module.")
    parser.add_argument("--underlying", default="IBOVE Index")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=15)
    parser.add_argument("--max-contracts", type=int)
    args = parser.parse_args()

    bloomberg = OptionsBloombergService()
    snapshot_service = OptionsSnapshotService(bloomberg=bloomberg)
    history_service = OptionsHistoryService(bloomberg=bloomberg, snapshot_service=snapshot_service)
    query_service = OptionsQueryService()

    output: dict[str, object] = {
        "status": bloomberg.status(),
        "underlying": args.underlying,
    }
    discovery = snapshot_service.discover_underlying(args.underlying)
    collect_once = snapshot_service.collect_underlying_snapshot(
        underlying_security=args.underlying,
        include_structural=True,
        include_liquid=True,
        include_critical=True,
        include_ticks=False,
    )
    output["discovery"] = {
        "underlying_security": discovery.get("underlying_security"),
        "chain_count": discovery.get("chain_count"),
        "valid_contract_count": discovery.get("valid_contract_count"),
        "invalid_contract_count": discovery.get("invalid_contract_count"),
        "sample_contracts": (discovery.get("contracts") or [])[:5],
    }
    output["collect_once"] = {
        "captured_at": collect_once.get("captured_at"),
        "universe": collect_once.get("universe"),
        "snapshot_keys": list((collect_once.get("snapshots") or {}).keys()),
        "snapshot_batches": {
            key: {
                "row_count": value.get("row_count"),
                "batch": value.get("batch"),
            }
            for key, value in (collect_once.get("snapshots") or {}).items()
        },
    }
    output["latest_critical"] = query_service.latest_snapshot("critical", underlying_security=args.underlying, limit=5)
    output["latest_oi_history"] = query_service.oi_history(underlying_security=args.underlying, limit=5)

    if args.backfill:
        output["backfill"] = history_service.backfill_open_interest_history(
            args.underlying,
            lookback_days=args.lookback_days,
            max_contracts=args.max_contracts,
        )
        output["latest_oi_history_after_backfill"] = query_service.oi_history(
            underlying_security=args.underlying,
            limit=5,
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
