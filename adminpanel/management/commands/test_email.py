from django.conf import settings
from django.core.management.base import BaseCommand

from adminpanel.emailcheck import send_test


class Command(BaseCommand):
    help = "Send a test email and explain any failure. Usage: manage.py test_email you@example.com"

    def add_arguments(self, parser):
        parser.add_argument("to", nargs="?", default=None)

    def handle(self, to=None, **o):
        to = to or settings.ADMIN_EMAIL
        self.stdout.write(f"Host {settings.EMAIL_HOST}:{settings.EMAIL_PORT}  SSL={settings.EMAIL_USE_SSL} "
                          f"TLS={settings.EMAIL_USE_TLS}  user={settings.EMAIL_HOST_USER or '(empty)'}  "
                          f"from={settings.DEFAULT_FROM_EMAIL}  password={'set' if settings.EMAIL_HOST_PASSWORD else 'MISSING'}")
        ok, msg = send_test(to)
        self.stdout.write(self.style.SUCCESS(msg) if ok else self.style.ERROR(msg))
