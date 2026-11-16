from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        from . import rbac, signals  # noqa: F401
        post_migrate.connect(_sync_roles, sender=self)


def _sync_roles(sender, **kwargs):
    from .rbac import sync_roles
    sync_roles()
