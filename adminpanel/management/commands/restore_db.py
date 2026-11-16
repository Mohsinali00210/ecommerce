from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from adminpanel.backups import BackupError, inspect, restore_backup, store_upload


class Command(BaseCommand):
    help = "Restore a backup zip. Makes a safety backup first. Replaces ALL current data."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--no-media", action="store_true")
        parser.add_argument("--yes", action="store_true", help="Don't ask for confirmation")

    def handle(self, file, **o):
        path = Path(file)
        if not path.exists():
            raise CommandError(f"{path} not found")
        manifest, problems = inspect(path)
        if problems:
            raise CommandError("Can't restore: " + " ".join(problems))
        self.stdout.write(f"Backup from {manifest.get('created_at')} with {manifest.get('records')} records.")
        if not o["yes"] and input("Type RESTORE to replace all current data: ").strip() != "RESTORE":
            raise CommandError("Cancelled.")
        with open(path, "rb") as fh:
            b = store_upload(File(fh, name=path.name), None)
        try:
            res = restore_backup(b, restore_media=not o["no_media"])
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"Restored {res['records']} records, {res['files']} files. Safety copy: {res['safety']}"))
