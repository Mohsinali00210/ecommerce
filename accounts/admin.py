from django.contrib import admin
from .models import ErrorLog

# admin.site.register(ErrorLog)
@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status_code", "method", "endpoint", "user")
    list_filter = ("status_code", "method")
    search_fields = ("endpoint", "error_message")
    readonly_fields = [f.name for f in ErrorLog._meta.fields]