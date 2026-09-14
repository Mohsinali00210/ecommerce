from django.shortcuts import render,get_object_or_404

# Create your views here.

from django.contrib.auth.models import User
from django.http import JsonResponse
from Web.models import ChatThread,ChatThreadRead
from products.models import Product,ProductQuestion
from django.contrib.auth.decorators import login_required


from django.utils import timezone
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404


def _get_unread_count(thread, user):
    read = ChatThreadRead.objects.filter(thread=thread, user=user).first()
    since = read.last_read_at if read else thread.created_at

    # An admin cares about unread USER messages; a customer cares about unread ADMIN messages.
    opposite_sender = "user" if user.is_staff else "admin"

    return thread.messages.filter(
        sender_type=opposite_sender,
        created_at__gt=since
    ).count()


from django.urls import reverse


@login_required
def admin_threads(request):
    threads = ChatThread.objects.all().order_by("-created_at")

    data = []
    for t in threads:
        product_name = None
        product_url = None

        if t.product_id:
            product = Product.objects.filter(id=t.product_id).first()
            if product:
                product_name = product.name
                product_url = reverse("home:Product_Details", kwargs={"slug": product.slug})

        data.append({
            "id": t.id,
            "user": t.user.full_name,
            "product_id": t.product_id,
            "product_name": product_name,
            "product_url": product_url,
            "unread_count": _get_unread_count(t, request.user),
        })

    return JsonResponse(data, safe=False)


@login_required
@require_POST
def mark_thread_read(request, thread_id):
    thread = get_object_or_404(ChatThread, id=thread_id)

    ChatThreadRead.objects.update_or_create(
        thread=thread,
        user=request.user,
        defaults={"last_read_at": timezone.now()}
    )

    return JsonResponse({"success": True})


@login_required
def admin_unread_total(request):
    threads = ChatThread.objects.all()
    total = sum(_get_unread_count(t, request.user) for t in threads)
    return JsonResponse({"unread_total": total})
def get_messages(request, thread_id):
    thread = ChatThread.objects.get(id=thread_id)

    messages = thread.messages.all().order_by("created_at")

    data = [
        {
            "sender": m.sender_type,
            "message": m.message,
        }
        for m in messages
    ]

    return JsonResponse({"messages": data})

@login_required
def admin_messages(request):
    return render(request, "chat/messages.html")

from Web.models import SupportTicket
@login_required
def AdminTicketList(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff only.")

    tickets = SupportTicket.objects.all().select_related("user")
    return render(request, "chat/AdminTicketList.html", {"tickets": tickets})


@login_required
def TicketDetail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id)

    if ticket.user_id != request.user.id and not request.user.is_staff:
        return HttpResponseForbidden("You don't have permission to view this ticket.")

    if request.method == "POST":
        reply_message = (request.POST.get("message") or "").strip()

        if reply_message:
            SupportTicketReply.objects.create(
                ticket=ticket,
                sender=request.user,
                is_staff_reply=request.user.is_staff,
                message=reply_message,
            )

            if request.user.is_staff:
                new_status = request.POST.get("status")
                if new_status in dict(SupportTicket.STATUS_CHOICES):
                    ticket.status = new_status
                    ticket.save(update_fields=["status"])

            messages.success(request, "Reply sent.")

        return redirect("AdminTicketDetail", ticket_id=ticket.id)

    return render(request, "chat/TicketDetail.html", {
        "ticket": ticket,
        "replies": ticket.replies.select_related("sender"),
    })

# admin_views.py (or wherever your staff-only views live)
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.db.models import Q
import json


@staff_member_required
def question_list(request):
    """
    Staff Q&A inbox. Filter via ?status=unread|answered|unanswered (default: all).
    "Unread" is scoped to the logged-in staff member's own read_by state.
    """
    status = request.GET.get("status", "all")

    questions = ProductQuestion.objects.filter(is_deleted=False).select_related(
        "product", "user", "answered_by"
    ).prefetch_related("read_by")

    if status == "unread":
        questions = questions.exclude(read_by=request.user)
    elif status == "answered":
        questions = questions.filter(answer__isnull=False).exclude(answer="")
    elif status == "unanswered":
        questions = questions.filter(Q(answer__isnull=True) | Q(answer=""))

    questions = questions.order_by("-created_at")

    unread_count = ProductQuestion.objects.filter(is_deleted=False).exclude(read_by=request.user).count()
    unanswered_count = ProductQuestion.objects.filter(
        is_deleted=False
    ).filter(Q(answer__isnull=True) | Q(answer="")).count()

    context = {
        "questions": questions,
        "current_status": status,
        "unread_count": unread_count,
        "unanswered_count": unanswered_count,
    }
    return render(request, "chat/question_list.html", context)


@staff_member_required
@require_POST
def question_reply(request, question_id):
    question = get_object_or_404(ProductQuestion, id=question_id, is_deleted=False)

    try:
        data = json.loads(request.body)
        answer_text = (data.get("answer") or "").strip()
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"success": False, "message": "Invalid request."}, status=400)

    if not answer_text:
        return JsonResponse({"success": False, "message": "Answer cannot be empty."}, status=400)
    if len(answer_text) > 2000:
        return JsonResponse({"success": False, "message": "Answer is too long."}, status=400)

    question.answer = answer_text
    question.answered_at = timezone.now()
    question.answered_by = request.user
    question.save(update_fields=["answer", "answered_at", "answered_by"])

    # Replying implicitly marks it read for the replying staff member.
    question.read_by.add(request.user)

    return JsonResponse({
        "success": True,
        "message": "Reply posted.",
        "answered_at": question.answered_at.strftime("%b %d, %Y %I:%M %p"),
        "answered_by": request.user.get_full_name() or request.user.username,
    })


@staff_member_required
@require_POST
def question_mark_read(request, question_id):
    question = get_object_or_404(ProductQuestion, id=question_id, is_deleted=False)

    try:
        data = json.loads(request.body)
        read = bool(data.get("read", True))
    except (ValueError, TypeError, json.JSONDecodeError):
        read = True

    if read:
        question.read_by.add(request.user)
    else:
        question.read_by.remove(request.user)

    return JsonResponse({"success": True, "read": read})