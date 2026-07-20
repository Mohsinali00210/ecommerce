# Add this model to your models.py (same app as Product, or a shared
# "core"/"logs" app — either works, just update the import path below
# wherever it's used).

from django.conf import settings
from django.db import models


class ErrorLog(models.Model):
    """
    Persists every failed insert/update so support/devs can see exactly
    which field or table broke, without needing to reproduce the bug.
    """
    LEVEL_CHOICES = [
        ('validation', 'Validation Error'),
        ('server', 'Server Error'),
    ]

    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='server')

    # The exact input name / serializer field that caused the failure,
    # e.g. "sku", "variants[2].price". Nullable because some errors
    # (e.g. a totally malformed request) can't be pinned to one field.
    field_name = models.CharField(max_length=255, blank=True, null=True)

    # Which model/table the failing insert or update targeted,
    # e.g. "Product", "ProductVariant", "Promotion".
    table_name = models.CharField(max_length=100, blank=True, null=True)

    # Which endpoint/action this happened on, e.g. "ProductViewSet.create"
    view_name = models.CharField(max_length=255, blank=True, null=True)

    message = models.TextField()
    traceback = models.TextField(blank=True, null=True)

    # A trimmed snapshot of what was submitted, useful for reproducing
    # the bug later. Never store file contents here — just field values.
    request_snapshot = models.JSONField(blank=True, null=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='error_logs',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['table_name', 'field_name']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"[{self.level}] {self.table_name}.{self.field_name}: {self.message[:80]}"
