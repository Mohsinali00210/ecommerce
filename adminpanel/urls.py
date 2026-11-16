from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_page, name="admin_dashboard"),
    path("Dashboard/", views.dashboard_page, name="admin_dashboard_page"),
    path("Dashboard/data/", views.dashboard_data, name="admin_dashboard_data"),
    path("Session/status/", views.session_status, name="admin_session_status"),
    path("Session/extend/", views.session_extend, name="admin_session_extend"),
    path("Session/token/", views.session_token, name="admin_session_token"),
    path("Logs/", views.logs_page, name="admin_logs"),
    path("Logs/<str:kind>/<int:pk>/", views.log_detail, name="admin_log_detail"),
    path("Team/", views.team_page, name="admin_team"),
    path("Team/add/", views.team_add, name="admin_team_add"),
    path("Team/<int:user_id>/", views.team_update, name="admin_team_update"),
]

from . import views_system  # noqa: E402

urlpatterns += [
    path("Settings/", views_system.store_settings, name="admin_store_settings"),
    path("Settings/test-email/", views_system.email_test, name="admin_email_test"),
    path("Backups/", views_system.backups_page, name="admin_backups"),
    path("Backups/create/", views_system.backup_create, name="admin_backup_create"),
    path("Backups/upload/", views_system.backup_upload, name="admin_backup_upload"),
    path("Backups/otp/<str:purpose>/request/", views_system.otp_request, name="admin_otp_request"),
    path("Backups/otp/<str:purpose>/verify/", views_system.otp_verify, name="admin_otp_verify"),
    path("Backups/<int:pk>/download/", views_system.backup_download, name="admin_backup_download"),
    path("Backups/<int:pk>/restore/", views_system.backup_restore, name="admin_backup_restore"),
    path("Backups/<int:pk>/delete/", views_system.backup_delete, name="admin_backup_delete"),
    path("Requests/", views_system.order_requests, name="admin_order_requests"),
    path("Session/unseen/", views_system.unseen_counts, name="admin_unseen_counts"),
]
