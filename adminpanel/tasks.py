import logging

from celery import shared_task
from django.utils import timezone

log = logging.getLogger("app")


@shared_task
def create_backup_task(user_id=None, include_media=True, note="", kind="manual"):
    from django.contrib.auth import get_user_model
    from .backups import BackupError, create_backup
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    try:
        return create_backup(kind=kind, user=user, include_media=include_media, note=note).pk
    except BackupError as exc:
        return f"failed: {exc}"


@shared_task
def restore_backup_task(backup_id, user_id=None, restore_media=True):
    from django.contrib.auth import get_user_model
    from .backups import BackupError, restore_backup
    from .models import Backup
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    try:
        return restore_backup(Backup.objects.get(pk=backup_id), user=user, restore_media=restore_media)
    except BackupError as exc:
        Backup.objects.filter(pk=backup_id).update(error=str(exc)[:2000])
        return f"failed: {exc}"


@shared_task
def scheduled_backup():
    """Runs hourly; makes the daily backup at the hour chosen in Store settings."""
    from .backups import BackupError, create_backup, prune_scheduled
    from .models import Backup, StoreSettings
    s = StoreSettings.get()
    if not s.backup_schedule_enabled:
        return "disabled"
    now = timezone.localtime()
    if now.hour != s.backup_hour:
        return "not now"
    if Backup.objects.filter(kind="scheduled", created_at__gte=timezone.now() - timezone.timedelta(hours=20)).exists():
        return "already done"
    try:
        b = create_backup(kind="scheduled", include_media=s.backup_include_media, note="Daily automatic backup")
    except BackupError as exc:
        from accounts.error_logging import security_event
        security_event("scheduled_backup_failed", None, severity="ERROR", error=str(exc))
        return f"failed: {exc}"
    prune_scheduled(max(1, s.backup_keep))
    return b.filename
