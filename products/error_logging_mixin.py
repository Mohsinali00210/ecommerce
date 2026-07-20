import re
import traceback as tb_module

from django.db import IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError

# Update this import to wherever you put the model from error_logging_models.py
from accounts.models import ErrorLog


def _snapshot(request):
    """Trims the request payload down to something safe/small to store —
    drops file uploads and anything over ~2KB so ErrorLog rows stay light."""
    try:
        data = {}
        for key in request.data.keys():
            values = request.data.getlist(key) if hasattr(request.data, 'getlist') else [request.data[key]]
            data[key] = values if len(values) > 1 else values[0]
        snapshot = {k: v for k, v in data.items() if k not in getattr(request, 'FILES', {})}
        text = str(snapshot)
        return snapshot if len(text) < 2000 else {"_truncated": text[:2000]}
    except Exception:
        return None


def extract_field_from_integrity_error(exc, model_name=""):
    """
    Postgres/MySQL/SQLite IntegrityError messages usually name the column
    that violated a constraint, e.g.:
      - 'duplicate key value violates unique constraint "product_sku_key"'
      - 'UNIQUE constraint failed: product.sku'
      - "Column 'price' cannot be null"
    This pulls that column name out so the API response — and therefore
    the frontend's highlightServerErrors() — can point at the exact input.
    """
    msg = str(exc)

    match = re.search(r'constraint failed:\s*\w+\.(\w+)', msg)              # SQLite UNIQUE
    if not match:
        match = re.search(r'violates unique constraint "(\w+?)_(\w+)_key"', msg)  # Postgres unique
    if not match:
        match = re.search(r"Column '(\w+)' cannot be null", msg)            # MySQL NOT NULL
    if not match:
        match = re.search(r'null value in column "(\w+)"', msg)             # Postgres NOT NULL

    if match:
        return match.group(match.lastindex)
    return None


class ErrorLoggingMixin:
    """
    Mixin for DRF ViewSets. Provides:
      - log_validation_error(request, errors): logs a 400 to the DB
      - log_exception(request, exc, status_code, table_name=None): logs a
        500/other exception, trying to pin it to a specific field/table
      - safe_call(fn, table_name): wraps a create/update call, converts
        IntegrityError into a field-tagged 400 instead of a raw 500
    """

    def log_validation_error(self, request, errors):
        ErrorLog.objects.create(
            level='validation',
            field_name=', '.join(errors.keys()) if hasattr(errors, 'keys') else None,
            table_name=self.queryset.model.__name__ if getattr(self, 'queryset', None) is not None else self.get_queryset().model.__name__,
            view_name=f"{self.__class__.__name__}.{request.method}",
            message=str(errors),
            request_snapshot=_snapshot(request),
            user=request.user if request.user and request.user.is_authenticated else None,
        )

    def log_exception(self, request, exc, status_code, table_name=None, field_name=None):
        if field_name is None and isinstance(exc, IntegrityError):
            field_name = extract_field_from_integrity_error(exc)

        ErrorLog.objects.create(
            level='server',
            field_name=field_name,
            table_name=table_name or (self.get_queryset().model.__name__ if hasattr(self, 'get_queryset') else None),
            view_name=f"{self.__class__.__name__}",
            message=str(exc),
            traceback=tb_module.format_exc(),
            request_snapshot=_snapshot(request),
            user=request.user if request.user and request.user.is_authenticated else None,
        )
        return field_name

    def handle_db_exception(self, request, exc, table_name=None):
        """
        Call this from a try/except around perform_create/perform_update.
        Logs the error and returns a Response the view can return directly,
        with the offending field + table named so the frontend can
        highlight the exact input (see highlightServerErrors in the JS).
        """
        field_name = self.log_exception(request, exc, status.HTTP_500_INTERNAL_SERVER_ERROR, table_name=table_name)

        detail = "This value already exists or violates a database constraint." \
            if isinstance(exc, IntegrityError) else "Something went wrong while saving. This has been logged."

        return Response(
            {"field": field_name, "table": table_name, "detail": detail},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
