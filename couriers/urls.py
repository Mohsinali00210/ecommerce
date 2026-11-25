from django.urls import path

from . import views

app_name = "couriers"

urlpatterns = [
    # Admin panel (staff only)
    path("", views.dashboard, name="dashboard"),
    path("orders/<int:order_id>/book/", views.book_order, name="book"),
    path("orders/<int:order_id>/info/", views.order_shipment_info, name="order_info"),
    path("bulk-book/", views.bulk_book, name="bulk_book"),
    path("shipments/<int:pk>/", views.shipment_detail, name="shipment"),
    path("shipments/<int:pk>/refresh/", views.shipment_refresh, name="shipment_refresh"),
    path("shipments/<int:pk>/cancel/", views.shipment_cancel, name="shipment_cancel"),
    path("shipments/<int:pk>/status/", views.shipment_set_status, name="shipment_status"),

    path("settings/", views.settings_page, name="settings"),
    path("settings/couriers/add/", views.provider_edit, name="provider_add"),
    path("settings/couriers/<int:pk>/", views.provider_edit, name="provider_edit"),
    path("settings/couriers/<int:pk>/test/", views.provider_test, name="provider_test"),
    path("settings/couriers/<int:pk>/sync-cities/", views.provider_sync_cities, name="provider_sync_cities"),
    path("settings/couriers/<int:provider_id>/credentials/add/", views.credential_edit, name="credential_add"),
    path("settings/couriers/<int:provider_id>/credentials/<int:pk>/", views.credential_edit,
         name="credential_edit"),
    path("settings/credentials/<int:pk>/rotate-webhook/", views.credential_rotate_token,
         name="credential_rotate"),
    path("settings/shipper/add/", views.shipper_edit, name="shipper_add"),
    path("settings/shipper/<int:pk>/", views.shipper_edit, name="shipper_edit"),
    path("settings/status-mappings/add/", views.mapping_edit, name="mapping_add"),
    path("settings/status-mappings/<int:pk>/", views.mapping_edit, name="mapping_edit"),
    path("settings/status-mappings/<int:pk>/delete/", views.mapping_delete, name="mapping_delete"),
    path("settings/webhook-logs/<int:pk>/", views.webhook_log_detail, name="webhook_log"),
    path("settings/rates/", views.tariff_list, name="tariffs"),
    path("settings/rates/add/", views.tariff_edit, name="tariff_add"),
    path("settings/rates/<int:pk>/", views.tariff_edit, name="tariff_edit"),
    path("settings/rates/<int:pk>/action/", views.tariff_action, name="tariff_action"),
]

# Mounted at /couriers/ (outside the admin panel prefix)
public_urlpatterns = [
    path("webhook/<slug:provider_code>/<str:token>/", views.webhook, name="webhook"),
    path("api/cities/", views.city_list, name="city_list"),
    path("api/track/<str:order_number>/", views.customer_tracking, name="customer_tracking"),
]
public_urls = (public_urlpatterns, "couriers_public")
