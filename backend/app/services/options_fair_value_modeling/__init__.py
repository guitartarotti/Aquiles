__all__ = ["OptionsFairValueService"]

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "OptionsFairValueService":
        from .service import OptionsFairValueService

        return OptionsFairValueService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
