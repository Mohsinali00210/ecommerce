from django.apps import AppConfig


class CouriersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "couriers"
    verbose_name = "Couriers & Shipping"

    def ready(self):
        # Register adapters and order signals.
        from . import adapters  # noqa: F401
        from . import signals  # noqa: F401
