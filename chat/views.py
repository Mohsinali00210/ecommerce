from django.shortcuts import render

# Create your views here.

from django.contrib.auth.models import User
from django.http import JsonResponse
from Web.models import ChatThread
from products.models import Product
from django.contrib.auth.decorators import login_required

def admin_threads(request):
    threads = ChatThread.objects.all().order_by("-created_at")

    data = []
    for t in threads:
        product_name = None
        if t.product_id:
            product = Product.objects.filter(id=t.product_id).first()
            product_name = product.name if product else None

        data.append({
            "id": t.id,
            "user": t.user.full_name,
            "product_id": t.product_id,
            "product_name": product_name
        })

    return JsonResponse(data, safe=False)
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