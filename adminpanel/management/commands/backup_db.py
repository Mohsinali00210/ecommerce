from django.core.management.base import BaseCommand, CommandError

from adminpanel.backups import BackupError, create_backup


class Command(BaseCommand):
    help = "Create a full backup zip in BACKUP_DIR (same format as the admin panel)."

    def add_arguments(self, parser):
        parser.add_argument("--no-media", action="store_true", help="Database only, no uploaded files")
        parser.add_argument("--note", default="Created from the command line")

    def handle(self, *args, **o):
        try:
            b = create_backup(kind="manual", include_media=not o["no_media"], note=o["note"])
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"{b.path}  ({b.record_count} records, {b.size_bytes} bytes)"))
