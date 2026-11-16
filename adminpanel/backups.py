"""
Full backup & restore.

A backup is one .zip:
    manifest.json   format, date, Django version, DB vendor, migration state, checksums
    data.json       every row of every app (Django dumpdata, natural keys, soft-deleted rows included)
    media/...       uploaded files (product images, avatars...)      - optional
    private/...     private uploads (bank receipts)                   - optional

Restore = validate -> automatic safety backup -> flush + load inside ONE
transaction (any error rolls everything back) -> copy files back.
Works on PostgreSQL and SQLite, no pg_dump needed.
"""
import hashlib
import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import django
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

log = logging.getLogger("app")

FORMAT = 1
EXCLUDE = ["contenttypes", "auth.permission", "sessions", "admin.logentry", "accounts.adminaccess",
           "adminpanel.backup", "adminpanel.adminseen"]


class BackupError(Exception):
    pass


def backup_dir():
    d = Path(settings.BACKUP_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _migration_state():
    state = {}
    for app, name in MigrationRecorder(connection).migration_qs.values_list("app", "name"):
        if name > state.get(app, ""):
            state[app] = name
    return state


def _add_tree(zf, root, prefix):
    root = Path(root)
    if not root.exists():
        return 0
    n = 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            full = Path(dirpath) / fn
            zf.write(full, f"{prefix}/{full.relative_to(root).as_posix()}")
            n += 1
    return n


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def create_backup(kind="manual", user=None, include_media=True, note=""):
    from .models import Backup
    b = Backup.objects.create(kind=kind, created_by=user, includes_media=include_media, note=note[:255])
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    final = backup_dir() / f"shanzee-backup-{stamp}-{kind}-{b.pk}.zip"
    tmp_zip = final.with_suffix(".part")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "data.json"
            call_command("dumpdata", natural_foreign=True, natural_primary=True, use_base_manager=True,
                         exclude=EXCLUDE, output=str(data_path), verbosity=0)
            with open(data_path, "rb") as f:
                records = len(json.load(f))
            manifest = {
                "app": "shanzee", "format": FORMAT, "created_at": timezone.now().isoformat(),
                "django": django.get_version(), "db_vendor": connection.vendor,
                "migrations": _migration_state(), "records": records, "includes_media": include_media,
                "data_sha256": _sha256_file(data_path), "kind": kind,
            }
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
                zf.write(data_path, "data.json")
                if include_media:
                    manifest["media_files"] = _add_tree(zf, settings.MEDIA_ROOT, "media")
                    manifest["private_files"] = _add_tree(zf, settings.PRIVATE_MEDIA_ROOT, "private")
        os.replace(tmp_zip, final)
        b.filename, b.status = final.name, "ready"
        b.size_bytes, b.sha256, b.record_count = final.stat().st_size, _sha256_file(final), records
        b.save()
        log.info("Backup %s created (%s records, %s bytes)", final.name, records, b.size_bytes)
        return b
    except Exception as exc:
        tmp_zip.unlink(missing_ok=True)
        b.status, b.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        b.save(update_fields=["status", "error"])
        log.exception("Backup failed")
        raise BackupError("The backup could not be created. Details are in the error log.") from exc


def prune_scheduled(keep):
    from .models import Backup
    old = Backup.objects.filter(kind="scheduled", status="ready").order_by("-created_at")[keep:]
    for b in old:
        if b.path and b.path.exists():
            b.path.unlink()
        b.delete()


def delete_backup(b):
    if b.path and b.path.exists():
        b.path.unlink()
    b.delete()


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------
def inspect(path):
    """Return (manifest, problems). problems empty = safe to restore."""
    problems = []
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return None, ["This isn't a valid backup file (not a zip archive)."]
    with zf:
        names = set(zf.namelist())
        if "manifest.json" not in names or "data.json" not in names:
            return None, ["This zip isn't a Shan Zee backup (manifest or data missing)."]
        for n in names:
            if n.startswith("/") or ".." in Path(n).parts:
                return None, ["The backup contains unsafe file paths."]
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except ValueError:
            return None, ["The backup manifest is damaged."]
        if manifest.get("app") != "shanzee" or manifest.get("format") != FORMAT:
            problems.append("Unsupported backup format.")
        h = hashlib.sha256()
        with zf.open("data.json") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest() != manifest.get("data_sha256"):
            problems.append("The data file is corrupted (checksum mismatch).")
    current = _migration_state()
    newer = [f"{app} ({name})" for app, name in (manifest.get("migrations") or {}).items()
             if app in current and name > current[app]]
    if newer:
        problems.append("The backup comes from a newer version of the site: update the code first ("
                        + ", ".join(newer[:5]) + ").")
    return manifest, problems


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
def _safe_extract(zf, prefix, target):
    target = Path(target).resolve()
    n = 0
    for info in zf.infolist():
        if not info.filename.startswith(prefix + "/") or info.is_dir():
            continue
        rel = info.filename[len(prefix) + 1:]
        dest = (target / rel).resolve()
        if target not in dest.parents:
            continue  # path traversal attempt - skip
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        n += 1
    return n


def restore_backup(backup, user=None, restore_media=True):
    from .models import Backup
    manifest, problems = inspect(backup.path)
    if problems:
        raise BackupError(" ".join(problems))

    safety = create_backup(kind="safety", user=user, include_media=False,
                           note=f"Automatic copy before restoring {backup.filename}")

    # Backup rows aren't part of the data; keep the list across the flush.
    keep = list(Backup.objects.values())
    backup.status = "restoring"
    backup.save(update_fields=["status"])
    try:
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(backup.path) as zf:
            data_path = Path(tmp) / "data.json"
            with zf.open("data.json") as src, open(data_path, "wb") as out:
                shutil.copyfileobj(src, out)
            with transaction.atomic():
                call_command("flush", interactive=False, verbosity=0)
                call_command("loaddata", str(data_path), verbosity=0)
                Backup.objects.all().delete()
                for row in keep:
                    Backup.objects.create(**row)
            files = 0
            if restore_media and manifest.get("includes_media"):
                files += _safe_extract(zf, "media", settings.MEDIA_ROOT)
                files += _safe_extract(zf, "private", settings.PRIVATE_MEDIA_ROOT)
    except Exception as exc:
        Backup.objects.filter(pk=backup.pk).update(status="ready")
        log.exception("Restore failed - database rolled back")
        raise BackupError("The restore failed and nothing was changed. Details are in the error log.") from exc

    Backup.objects.filter(pk=backup.pk).update(status="restored", restored_at=timezone.now())
    from accounts.error_logging import security_event
    security_event("backup_restored", None, user=None, severity="CRITICAL",
                   username=getattr(user, "email", ""), backup=backup.filename,
                   safety_backup=safety.filename, records=manifest.get("records"), files=files)
    return {"records": manifest.get("records"), "files": files, "safety": safety.filename}


def store_upload(uploaded, user):
    """Save an uploaded backup zip after validating it."""
    from .models import Backup
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir() / f"shanzee-backup-{stamp}-uploaded.zip"
    with open(dest, "wb") as out:
        for chunk in uploaded.chunks():
            out.write(chunk)
    manifest, problems = inspect(dest)
    if manifest is None:
        dest.unlink(missing_ok=True)
        raise BackupError(problems[0])
    return Backup.objects.create(
        kind="uploaded", created_by=user, status="ready", filename=dest.name, size_bytes=dest.stat().st_size,
        sha256=_sha256_file(dest), record_count=manifest.get("records") or 0,
        includes_media=bool(manifest.get("includes_media")),
        note=("; ".join(problems) if problems else f"Uploaded, made {manifest.get('created_at', '')[:16]}")[:255])
