from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

from dotenv import load_dotenv


if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.config import Config  # noqa: E402
from app.services.market_screen_capture_service import MarketScreenCaptureService  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture the W 32 Basica panel, OCR quotes, and persist rows.",
    )
    parser.add_argument(
        "--loop-seconds",
        type=float,
        default=0.0,
        help="Repeat capture every N seconds. Use 0 to capture once.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Optional max iterations when looping. 0 means run forever.",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write JSON/JSONL/CSV artifacts.",
    )
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Do not save the PNG capture to disk.",
    )
    parser.add_argument(
        "--window-title",
        default=None,
        help="Override the window title query.",
    )
    parser.add_argument(
        "--fallback-monitor-index",
        type=int,
        default=None,
        help="Override the fallback monitor index if title detection fails.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full capture payload as JSON.",
    )
    return parser


def _print_summary(payload: dict) -> None:
    artifacts = payload.get("artifacts") or {}
    image = payload.get("image") or {}
    print(
        json.dumps(
            {
                "ok": payload.get("ok"),
                "captured_at": payload.get("captured_at"),
                "row_count": payload.get("row_count"),
                "window_title": payload.get("window_title"),
                "image_path": image.get("path"),
                "snapshot_path": artifacts.get("snapshot_path"),
                "rows_path": artifacts.get("rows_path"),
                "csv_path": artifacts.get("csv_path"),
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    args = _build_parser().parse_args()
    service = MarketScreenCaptureService()
    loop_seconds = float(args.loop_seconds or 0.0)
    if loop_seconds <= 0:
        loop_seconds = 0.0
    elif loop_seconds < 0.5:
        loop_seconds = max(float(Config.MARKET_SCREEN_W32_POLL_INTERVAL_SECONDS), 0.5)

    iteration = 0
    try:
        while True:
            iteration += 1
            payload = service.capture_w32_basica(
                persist=not args.no_persist,
                save_image=not args.no_image,
                title_query=args.window_title,
                fallback_monitor_index=args.fallback_monitor_index,
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_summary(payload)

            if loop_seconds <= 0.0:
                return 0 if payload.get("ok") else 1
            if args.iterations and iteration >= int(args.iterations):
                return 0
            time.sleep(loop_seconds)
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
