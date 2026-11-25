"""Payment gateway adapters. Add a gateway = one adapter module + a PaymentGateway row."""
_REGISTRY = {}


def register(code):
    def deco(cls):
        cls.code = code
        _REGISTRY[code] = cls
        return cls
    return deco


def get_adapter(code):
    try:
        return _REGISTRY[code]
    except KeyError:
        raise LookupError(f"No payment gateway adapter '{code}'")


def choices():
    return [(c, cls.display_name) for c, cls in sorted(_REGISTRY.items())]


from . import easypaisa, jazzcash, safepay, stripe, testgateway  # noqa: E402,F401
