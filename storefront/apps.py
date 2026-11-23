from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "storefront"
    verbose_name = "Storefront & SEO"

    def ready(self):
        from . import signals  # noqa: F401
