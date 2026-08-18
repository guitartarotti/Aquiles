from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any


def _atomic_replace(temp_path: str, target_path: str, retries: int = 12, retry_sleep: float = 0.1) -> None:
    last_error: Exception | None = None
    for _ in range(max(int(retries), 1)):
        try:
            os.replace(temp_path, target_path)
            last_error = None
            break
        except PermissionError as exc:
            last_error = exc
            time.sleep(max(float(retry_sleep), 0.0))
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception:
        pass
    if last_error is not None:
        raise last_error


def _mkstemp_near(target_path: str) -> tuple[int, str]:
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    prefix = f"{os.path.basename(target_path)}."
    return tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=os.path.dirname(target_path))


def atomic_json_dump(
    target_path: str,
    payload: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = 2,
    retries: int = 12,
    retry_sleep: float = 0.1,
) -> None:
    fd, temp_path = _mkstemp_near(target_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=ensure_ascii, indent=indent)
            handle.flush()
            os.fsync(handle.fileno())
        _atomic_replace(temp_path, target_path, retries=retries, retry_sleep=retry_sleep)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        raise


def atomic_text_write(
    target_path: str,
    content: str,
    *,
    retries: int = 12,
    retry_sleep: float = 0.1,
) -> None:
    fd, temp_path = _mkstemp_near(target_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _atomic_replace(temp_path, target_path, retries=retries, retry_sleep=retry_sleep)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        raise
