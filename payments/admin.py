from django.contrib import admin

from .models import Payment, PaymentEvent, PaymentGateway


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "amount", "status", "reference", "created_at", "paid_at")
    list_filter = ("method", "status")
    search_fields = ("order__order_number", "reference", "tracker")
    readonly_fields = ("raw",)


@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "environment", "is_active")
    exclude = ("api_key", "secret_key", "webhook_secret")  # edit them in the admin panel (encrypted)


admin.site.register(PaymentEvent)
