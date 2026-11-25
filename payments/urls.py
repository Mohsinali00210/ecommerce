from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("pay/<str:token>/", views.pay, name="pay"),
    path("<int:pk>/return/", views.payment_return, name="return"),
    path("<int:pk>/cancel/", views.payment_cancel, name="cancel"),
    path("<int:pk>/proof/", views.upload_proof, name="upload_proof"),
    path("<int:pk>/proof/view/", views.view_proof, name="view_proof"),
    path("webhook/<slug:code>/", views.webhook, name="webhook"),
    path("test-gateway/<str:token>/", views.test_gateway, name="test_gateway"),
]


from . import admin_views  # noqa: E402

admin_urlpatterns = [
    path("", admin_views.payments_list, name="admin_payments"),
    path("<int:pk>/", admin_views.payment_detail, name="admin_payment_detail"),
    path("<int:pk>/action/", admin_views.payment_action, name="admin_payment_action"),
    path("gateway/", admin_views.gateway_settings, name="admin_payment_gateway"),
    path("gateway/<slug:code>/", admin_views.gateway_edit, name="admin_payment_gateway_edit"),
    path("gateway/<slug:code>/test/", admin_views.gateway_test, name="admin_payment_gateway_test"),
    path("logs/", admin_views.payment_logs, name="admin_payment_logs"),
    path("transactions/", admin_views.transactions, name="admin_transactions"),
    path("payouts/", admin_views.payout_settings, name="admin_payout_settings"),
    path("payouts/logs/", admin_views.payout_logs, name="admin_payout_logs"),
    path("payouts/<slug:code>/", admin_views.payout_method_edit, name="admin_payout_method_edit"),
]
