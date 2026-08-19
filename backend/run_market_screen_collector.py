"""
Standalone market screen capture/OCR worker.

This process owns W32 Basica capture, OCR, latest-file writes, and SQLite history
appends so the main Flask backend can stay focused on API requests.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time


if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.market_screen_capture_service import MarketScreenCaptureCollectorManager
from app.utils.logger import get_logger


logger = get_logger("aquiles.market_screen_worker")


def main() -> None:
    os.environ.pop("AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR", None)
    stop_event = threading.Event()
    manager = MarketScreenCaptureCollectorManager.get_instance()

    def request_stop(signum=None, frame=None) -> None:
        logger.info("Stopping market screen worker signal=%s", signum)
        stop_event.set()
        try:
            manager.stop()
        except Exception:
            logger.exception("Failed to stop market screen collector cleanly")

    for signame in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signame):
            signal.signal(getattr(signal, signame), request_stop)

    logger.info("Starting standalone market screen capture/OCR worker")
    manager.start()

    while not stop_event.wait(5.0):
        try:
            status = manager.status()
            if not status.get("running"):
                logger.warning(
                    "Market screen collector loop is not running; restarting. last_error=%s",
                    status.get("last_error"),
                )
                manager.start()
        except Exception:
            logger.exception("Market screen worker watchdog failed")
            time.sleep(2.0)

    logger.info("Standalone market screen capture/OCR worker stopped")


if __name__ == "__main__":
    main()
