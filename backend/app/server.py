"""Consistent WSGI server entry point for Aquiles HTTP services."""

from __future__ import annotations

import os
from typing import Any


def serve(app: Any, *, host: str, port: int, debug: bool = False) -> None:
    """Run Flask's debugger locally or Waitress for normal service execution."""
    if debug:
        app.run(host=host, port=port, debug=True, threaded=True, use_reloader=False)
        return

    from waitress import serve as waitress_serve

    threads = max(4, int(os.environ.get("AQUILES_HTTP_THREADS", "8")))
    waitress_serve(
        app,
        host=host,
        port=port,
        threads=threads,
        channel_timeout=120,
        clear_untrusted_proxy_headers=True,
    )
