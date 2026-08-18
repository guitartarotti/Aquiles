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
    parser = argparse.ArgumentParser(description="Ingest SEC N-PORT quarterly TSV package into the local N-PORT SQLite database.")
    parser.add_argument("--source-dir", default=r"C:\Users\Windows\Downloads\2026q1_nport")
    parser.add_argument("--quarter", default=None, help="Quarter id such as 2026q1. Inferred from source path when omitted.")
    parser.add_argument("--force", action="store_true", help="Replace an existing quarter import.")
    args = parser.parse_args()

    service = NportService()
    result = service.ingest_local_directory(args.source_dir, quarter=args.quarter, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
