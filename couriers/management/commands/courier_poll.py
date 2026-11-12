from django.core.management.base import BaseCommand

from couriers.tasks import poll_active_shipments


class Command(BaseCommand):
    help = "Track all active shipments now (same job Celery beat runs on a schedule)."

    def handle(self, *args, **opts):
        self.stdout.write(str(poll_active_shipments()))
