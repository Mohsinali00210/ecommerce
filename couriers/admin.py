from django.contrib import admin

from .models import (CourierCity, CourierCredential, CourierProvider, Shipment, ShipmentEvent,
                     ShipperProfile, StatusMapping, WebhookLog)


class CredentialInline(admin.StackedInline):
    model = CourierCredential
    extra = 0
    readonly_fields = ("webhook_token", "last_verified_at", "last_error")


@admin.register(CourierProvider)
class CourierProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "adapter", "environment", "is_active", "is_default",
                    "auto_book_enabled")
    inlines = [CredentialInline]


@admin.register(CourierCity)
class CourierCityAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "external_id", "allow_origin", "allow_destination", "is_active")
    list_filter = ("provider", "is_active")
    search_fields = ("name", "aliases", "external_id")


@admin.register(StatusMapping)
class StatusMappingAdmin(admin.ModelAdmin):
    list_display = ("courier_status", "provider", "match_type", "shipment_status", "order_status",
                    "notify_customer", "priority")
    list_filter = ("provider", "shipment_status")
    list_editable = ("priority",)


class EventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    readonly_fields = ("status", "raw_status", "description", "location", "event_time", "source")


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("tracking_number", "order", "provider", "status", "raw_status", "cod_amount",
                    "booked_at")
    list_filter = ("provider", "status", "unmapped_status")
    search_fields = ("tracking_number", "order__order_number", "consignee_name", "consignee_phone")
    readonly_fields = ("request_payload", "response_payload")
    inlines = [EventInline]


admin.site.register(ShipperProfile)


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ("received_at", "provider", "remote_ip", "authenticated", "success",
                    "updates_applied")
    list_filter = ("provider", "authenticated", "success")
