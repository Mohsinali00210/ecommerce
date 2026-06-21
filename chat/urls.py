from django.urls import path, include
from .views import admin_messages,admin_threads,get_messages

urlpatterns = [
   
    path("admin/threads/", admin_threads, name="admin_threads"),
    path("admin/threads/<int:thread_id>/", get_messages, name="get_messages"),
    path("admin/messages/", admin_messages, name="admin_messages"),
]