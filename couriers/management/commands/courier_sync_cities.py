from django.core.management.base import BaseCommand, CommandError

from couriers.models import CourierProvider
from couriers.services import sync_cities


class Command(BaseCommand):
    help = "Download a courier's city list (needed to map customer cities to courier city ids)."

    def add_arguments(self, parser):
        parser.add_argument("provider_code", nargs="?", default="leopards")

    def handle(self, provider_code, **opts):
        p = CourierProvider.objects.filter(code=provider_code).first()
        if not p:
            raise CommandError(f"No courier with code '{provider_code}'")
        self.stdout.write(self.style.SUCCESS(f"{sync_cities(p)} cities synced for {p.name}"))
