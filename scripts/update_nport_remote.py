from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.nport_service import NportService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SEC N-PORT quarterly data sets and download/import a new quarter.")
    parser.add_argument("--quarter", default=None, help="Specific quarter like 2026q1. Defaults to latest remote quarter.")
    parser.add_argument("--force", action="store_true", help="Download and import even if the quarter is already local.")
    parser.add_argument("--check-only", action="store_true", help="Only list remote/local quarter status.")
    args = parser.parse_args()

    service = NportService()
    remote = service.discover_remote_quarters()
    if args.check_only:
        print(json.dumps(remote, ensure_ascii=False, indent=2))
        return 0

    quarter = (args.quarter or remote.get("latest_remote_quarter") or "").lower()
    if not quarter:
        raise RuntimeError("No remote N-PORT quarter found.")

    local_status = next(
        (item.get("local_status") for item in remote.get("quarters", []) if item.get("quarter") == quarter),
        "missing",
    )
    if local_status == "ready" and not args.force:
        print(json.dumps({"ok": True, "quarter": quarter, "status": "already_ready"}, ensure_ascii=False, indent=2))
        return 0

    result = service.download_quarter(quarter=quarter, force=args.force, ingest=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
