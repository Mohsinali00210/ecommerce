from django.urls import path, include
from .views import question_mark_read,question_reply,question_list,mark_thread_read,admin_unread_total,TicketDetail,AdminTicketList,admin_messages,admin_threads,get_messages

urlpatterns = [
   
    path("admin/threads/", admin_threads, name="admin_threads"),
    path("admin/threads/<int:thread_id>/", get_messages, name="get_messages"),
    path("admin/messages/", admin_messages, name="admin_messages"),
    path("admin-tickets/", AdminTicketList, name="AdminTicketList"),
        path("contact/ticket/<int:ticket_id>/", TicketDetail, name="AdminTicketDetail"),
    path("admin/threads/<int:thread_id>/read/", mark_thread_read, name="mark_thread_read"),
    path("admin/unread-total/", admin_unread_total, name="admin_unread_total"),
    path("questions/", question_list, name="StaffQuestionList"),
    path("questions/<int:question_id>/reply/", question_reply, name="StaffQuestionReply"),
    path("questions/<int:question_id>/mark-read/", question_mark_read, name="StaffQuestionMarkRead"),
]