"""Store settings, backups (OTP-protected) and the order-requests inbox."""
from django import forms
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from accounts.error_logging import security_event

from . import otp, unseen
from .backups import BackupError, delete_backup, inspect, store_upload
from .models import Backup, StoreSettings

# Access (accounts/rbac.py): Settings -> manage_settings, Backups -> manage_backups
# (super admins only), Requests -> view_orders / manage_orders.


# ---------------------------------------------------------------------------
# Store settings
# ---------------------------------------------------------------------------
class StoreSettingsForm(forms.ModelForm):
    email_statuses = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple(
        attrs={"class": "form-check-input me-1"}))

    class Meta:
        model = StoreSettings
        fields = ["online_payments_enabled", "cod_enabled", "cod_max_amount", "bank_transfer_enabled",
                  "bank_transfer_details", "online_payment_timeout_minutes",
                  "email_order_confirmation", "email_status_changes", "email_statuses", "email_admin_new_order",
                  "backup_schedule_enabled", "backup_hour", "backup_keep", "backup_include_media"]
        widgets = {"bank_transfer_details": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        from Web.models import Order
        self.fields["email_statuses"].choices = [c for c in Order.ORDER_STATUS if c[0] not in ("pending",)]
        for name, f in self.fields.items():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
                w.attrs["role"] = "switch"
            elif not isinstance(w, forms.CheckboxSelectMultiple):
                w.attrs["class"] = "form-control"

    def clean_backup_hour(self):
        h = self.cleaned_data["backup_hour"]
        if h > 23:
            raise forms.ValidationError("Use an hour from 0 to 23.")
        return h

    def clean(self):
        data = super().clean()
        if not (data.get("cod_enabled") or data.get("bank_transfer_enabled") or data.get("online_payments_enabled")):
            raise forms.ValidationError("Keep at least one payment method on, or customers can't check out.")
        if data.get("online_payments_enabled"):
            from payments.models import PaymentGateway
            if not PaymentGateway.online():
                self.add_error("online_payments_enabled",
                               "Set up and activate Safepay first (Payments → Safepay settings).")
        return data


def store_settings(request):
    obj = StoreSettings.get()
    obj = StoreSettings.objects.get(pk=obj.pk)  # fresh row, not the cached copy
    before = {f: getattr(obj, f) for f in ("online_payments_enabled", "cod_enabled", "bank_transfer_enabled")}
    form = StoreSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        s.updated_by = request.user
        s.save()
        after = {f: getattr(s, f) for f in before}
        if after != before:
            security_event("payment_settings_changed", request, severity="WARNING", before=before, after=after)
        messages.success(request, "Settings saved.")
        return redirect("admin_store_settings")
    from payments.models import PaymentGateway
    return render(request, "adminpanel/store_settings.html",
                  {"form": form, "gateway": PaymentGateway.objects.filter(code="safepay").first()})


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
def backups_page(request):
    return render(request, "adminpanel/backups.html", {
        "backups": Backup.objects.select_related("created_by")[:100],
        "settings": StoreSettings.get(),
        "download_left": otp.seconds_left(request, "download"),
        "restore_left": otp.seconds_left(request, "restore"),
        "running": Backup.objects.filter(status__in=["running", "restoring"]).exists(),
    })


@require_POST
@ratelimit(key="user", rate="6/h", block=True)
def backup_create(request):
    from .tasks import create_backup_task
    include_media = request.POST.get("include_media") == "1"
    security_event("backup_requested", request, severity="WARNING", include_media=include_media)
    create_backup_task.delay(request.user.pk, include_media, (request.POST.get("note") or "")[:200])
    messages.success(request, "Backup started. It appears below when ready.")
    return redirect("admin_backups")


@require_POST
@ratelimit(key="user", rate="5/15m", block=True)
def otp_request(request, purpose):
    if purpose not in otp.PURPOSES:
        raise Http404
    from accounts.error_logging import log_error
    from .emailcheck import config_problem, explain
    problem = config_problem()
    if problem:
        log_error(request, status_code=502, message=f"OTP email not sent: {problem}")
        return JsonResponse({"detail": f"We couldn't send the code. {problem}"}, status=502)
    try:
        otp.issue(request, purpose)
    except Exception as exc:
        reason = explain(exc)
        log_error(request, exc, 502, message=f"OTP email not sent: {reason}")
        # Only super admins reach this page, so the (secret-free) reason is shown to help fix it.
        return JsonResponse({"detail": f"We couldn't send the code. {reason}"}, status=502)
    return JsonResponse({"ok": True, "message": f"We emailed a 6-digit code to {request.user.email}."})


@require_POST
@ratelimit(key="user", rate="5/10m", block=True)
def email_test(request):
    from .emailcheck import send_test
    ok, msg = send_test(request.user.email)
    if not ok:
        from accounts.error_logging import log_error
        log_error(request, status_code=502, message=f"Test email failed: {msg}", severity="WARNING")
    return JsonResponse({"ok": ok, "detail": msg, "message": msg}, status=200 if ok else 502)


@require_POST
@ratelimit(key="user", rate="15/15m", block=True)
def otp_verify(request, purpose):
    if purpose not in otp.PURPOSES:
        raise Http404
    ok, msg = otp.verify(request, purpose, request.POST.get("code", ""))
    return JsonResponse({"ok": ok, "message": msg, "seconds": otp.seconds_left(request, purpose)},
                        status=200 if ok else 400)


@require_GET
def backup_download(request, pk):
    b = get_object_or_404(Backup, pk=pk, status__in=["ready", "restored"])
    if not otp.granted(request, "download"):
        messages.error(request, "Enter the code we email you before downloading.")
        return redirect("admin_backups")
    if not b.path or not b.path.exists():
        messages.error(request, "The backup file is missing on the server.")
        return redirect("admin_backups")
    security_event("backup_downloaded", request, severity="WARNING", backup=b.filename, size=b.size_bytes)
    resp = FileResponse(open(b.path, "rb"), as_attachment=True, filename=b.filename)
    resp["Cache-Control"] = "private, no-store"
    return resp


@require_POST
def backup_upload(request):
    f = request.FILES.get("file")
    if not f or not f.name.lower().endswith(".zip"):
        messages.error(request, "Choose a .zip backup file.")
        return redirect("admin_backups")
    try:
        b = store_upload(f, request.user)
    except BackupError as exc:
        messages.error(request, str(exc))
        return redirect("admin_backups")
    security_event("backup_uploaded", request, severity="WARNING", backup=b.filename, size=b.size_bytes)
    messages.success(request, f"Backup uploaded and checked ({b.record_count} records). You can restore it below.")
    return redirect("admin_backups")


@require_POST
def backup_restore(request, pk):
    b = get_object_or_404(Backup, pk=pk, status__in=["ready", "restored"])
    if (request.POST.get("confirm") or "").strip().upper() != "RESTORE":
        messages.error(request, 'Type RESTORE to confirm.')
        return redirect("admin_backups")
    if not otp.granted(request, "restore", consume=True):
        messages.error(request, "Enter the code we email you before restoring.")
        return redirect("admin_backups")
    _, problems = inspect(b.path)
    if problems:
        messages.error(request, "This backup can't be restored: " + " ".join(problems))
        return redirect("admin_backups")
    security_event("backup_restore_started", request, severity="CRITICAL", backup=b.filename)
    from .tasks import restore_backup_task
    result = restore_backup_task.delay(b.pk, request.user.pk, request.POST.get("restore_media") == "1")
    # Runs in the worker; in development (no Redis) it ran inline and the session is now gone.
    if isinstance(getattr(result, "result", None), dict):
        # The restore emptied the sessions table, including this one: start a
        # fresh anonymous session instead of trying to save the deleted one.
        request.session.flush()
        return render(request, "adminpanel/restore_done.html", {"result": result.result})
    messages.success(request, "Restore started. You'll be signed out when it finishes - sign in again.")
    return redirect("admin_backups")


@require_POST
def backup_delete(request, pk):
    b = get_object_or_404(Backup, pk=pk)
    if b.status in ("running", "restoring"):
        messages.error(request, "Wait until it finishes.")
        return redirect("admin_backups")
    security_event("backup_deleted", request, severity="WARNING", backup=b.filename)
    delete_backup(b)
    messages.success(request, "Backup deleted.")
    return redirect("admin_backups")


# ---------------------------------------------------------------------------
# Order requests inbox
# ---------------------------------------------------------------------------
def order_requests(request):
    from django.core.paginator import Paginator
    from Web.models import OrderRequest
    status = request.GET.get("status", "pending")
    qs = (OrderRequest.objects.filter(is_deleted=False).select_related("order", "user")
          .prefetch_related("items__product").order_by("-created_at"))
    if status != "all":
        qs = qs.filter(status=status)
    return render(request, "adminpanel/order_requests.html", {
        "page": Paginator(qs, 25).get_page(request.GET.get("page")), "f_status": status,
    })


@require_GET
def unseen_counts(request):
    return JsonResponse(unseen.counts(request.user))
