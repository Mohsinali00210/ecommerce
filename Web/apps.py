from django.apps import AppConfig


class WebConfig(AppConfig):
    name = 'Web'

    def ready(self):
        from . import signals  # noqa: F401  (order status emails)
