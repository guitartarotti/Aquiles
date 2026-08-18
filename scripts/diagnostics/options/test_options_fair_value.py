from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.options_fair_value_modeling import OptionsFairValueService


def main() -> None:
    service = OptionsFairValueService()
    payload = service.run_latest(
        underlying_security="IBOVE Index",
        refresh_options_model=False,
        refresh_global_overlay=False,
        persist=False,
    )
    summary = payload.get("summary") or {}
    print(json.dumps(
        {
            "run_id": payload.get("run_id"),
            "fair_value_final_future": summary.get("fair_value_final_future"),
            "mispricing_value": summary.get("mispricing_value"),
            "market_regime": summary.get("market_regime"),
            "dealer_pressure_state": summary.get("dealer_pressure_state"),
            "global_distortion_state": summary.get("global_distortion_state"),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
