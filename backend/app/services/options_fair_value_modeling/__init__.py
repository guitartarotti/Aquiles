__all__ = ["OptionsFairValueService"]


def __getattr__(name: str):
    if name == "OptionsFairValueService":
        from .service import OptionsFairValueService

        return OptionsFairValueService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
