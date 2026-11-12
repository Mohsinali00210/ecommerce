"""Adapter registry. Each courier API is one adapter class."""
_REGISTRY = {}


def register(code):
    def deco(cls):
        cls.code = code
        _REGISTRY[code] = cls
        return cls
    return deco


def get_adapter_class(code):
    try:
        return _REGISTRY[code]
    except KeyError:
        raise LookupError(f"No courier adapter named '{code}'. Available: {', '.join(sorted(_REGISTRY))}")


def adapter_choices():
    return [(code, cls.display_name or code) for code, cls in sorted(_REGISTRY.items())]


# Import adapters so they register themselves. Add new couriers here.
from . import manual  # noqa: E402,F401
from . import leopards  # noqa: E402,F401
