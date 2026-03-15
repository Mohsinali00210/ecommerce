from django.shortcuts import render
from rest_framework import viewsets, status, permissions, parsers, filters
from rest_framework.response import Response
from rest_framework.exceptions import APIException, ValidationError
import traceback
import json
from .models import Category, ProductAttribute, Attribute_Types, Brand, Product, Promotion,TaxCategory,ProductReview,Wishlist
from accounts.models import ErrorLog

from .serializers import OrderSerializer,AdminOrderRequestUpdateSerializer,CategorySerializer, ProductAttributeSerializer,AttributeTypesSerializer,BrandSerializer, ProductSerializer, PromotionSerializer
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import generics
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from Web.models import Order

# Create your views here.
class IsAdminRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_staff



class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

   
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            log_validation_error(self, request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as exc:
            self.log_exception(
                request,
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            raise

   

    def get_queryset(self):
        queryset = Category.objects.filter(is_deleted=False)
        parent_id = self.request.query_params.get('parent')
        
        if parent_id == 'null' or parent_id is None and self.request.path.endswith('/'):
            # If we are on the main page, show only top-level categories
            if parent_id == 'null':
                return queryset.filter(parent__isnull=True)
            return queryset
        
        if parent_id:
            return queryset.filter(parent_id=parent_id)
            
        return queryset

    def perform_create(self, serializer):
        # Automatically set the created_by field to the logged-in user
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        # Soft delete logic: instead of deleting from DB, mark as deleted
        instance.is_deleted = True
        instance.save()



class ProductAttributeViewSet(viewsets.ModelViewSet):
    serializer_class = ProductAttributeSerializer
    permission_classes = [permissions.IsAuthenticated]

   
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            log_validation_error(self, request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as exc:
            self.log_exception(
                request,
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            raise

   

    def get_queryset(self):
        return ProductAttribute.objects.filter(is_deleted=False).select_related('attribute_type').prefetch_related('categories')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()

class BrandViewSet(viewsets.ModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [permissions.IsAuthenticated]
    # parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
   
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            log_validation_error(self, request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as exc:
            self.log_exception(
                request,
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            raise

    def get_queryset(self):
        return Brand.objects.filter(is_deleted=False).prefetch_related('categories')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'status','stock_status', 'free_shipping']
    search_fields = ['name', 'sku', 'description']
    ordering_fields = ['price', 'created_at']

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as exc:
            self.log_exception(
                request,
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            raise
    def get_queryset(self):
        # return Product.objects.filter(is_deleted=False).prefetch_related('variants', 'images', 'promotions')
        return Product.objects.filter(is_deleted=False)\
            .prefetch_related('variants', 'images', 'promotions')\
            .order_by('-id')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(modified_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        # Soft delete implementation
        instance = self.get_object()
        instance.is_deleted = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

class PromotionViewSet(viewsets.ModelViewSet):
    serializer_class = PromotionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)

        if not serializer.is_valid():
            log_validation_error(self,request, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as exc:
            self.log_exception(
                request,
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            raise
    def get_queryset(self):
        return Promotion.objects.filter(is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(modified_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        # Soft delete implementation
        instance = self.get_object()
        instance.is_deleted = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


def log_validation_error(self, request, errors):
    ErrorLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        endpoint=request.path,
        method=request.method,
        error_message=str(errors),
        status_code=status.HTTP_400_BAD_REQUEST,
        request_data=request.data,
    )


def log_exception(self, request, exc, status_code):
    ErrorLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        endpoint=request.path,
        method=request.method,
        error_message=str(exc),
        stack_trace=traceback.format_exc(),
        status_code=status_code,
        request_data=request.data if request.method != "GET" else None,
        query_params=request.query_params.dict(),
    )

class AttributeTypesViewSet(viewsets.ModelViewSet):
    serializer_class = AttributeTypesSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Attribute_Types.objects.filter(is_deleted=False)

def categories(request):
    return render(request, "categories/categories.html")


def attributes(request):
    return render(request, "Other/attributes.html")

def brands(request):
    return render(request, "Other/brands.html")

def addProduct(request):
    tax_categories = TaxCategory.objects.filter(is_active=True, is_deleted=False)
    context = { 'tax_categories': tax_categories }
    return render(request, "products/addProduct.html",context)

def editProduct(request):
    return render(request, "products/addProduct.html")
def editProduct(request, id=None):
    return render(request, "products/addProduct.html", {
        "product_id": id
    })


def products(request):
    return render(request, "products/products.html")

def ProductPreview(request):
    return render(request, "products/ProductPreview.html")


def orders(request):
    return render(request, "orders/Orders.html")


# views.py

from rest_framework import generics, permissions
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from .serializers import OrderSerializer


class OrdersListAPIView(generics.ListAPIView):
    serializer_class = OrderSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Order.objects.order_by("-created_at")

        status_filter = self.request.GET.get("status")
        payment_filter = self.request.GET.get("payment")
        date_from = self.request.GET.get("from")
        date_to = self.request.GET.get("to")
        search = self.request.GET.get("search")
        print("status_filter ",payment_filter)
        if status_filter and status_filter.lower() != "all":
            qs = qs.filter(status__iexact=status_filter)

        if payment_filter and payment_filter.lower() != "all":
            qs = qs.filter(payment_status__iexact=payment_filter)

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        if search:
            qs = qs.filter(order_number__icontains=search)

        return qs

# class OrdersListAPIView(generics.ListCreateAPIView):
#     serializer_class = OrderSerializer
#     authentication_classes = [SessionAuthentication, TokenAuthentication]
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         qs = Order.objects.all().order_by("-created_at")

#         # Optional filters
#         status_filter = self.request.data.get("status")
#         payment_filter = self.request.data.get("payment")
#         date_from = self.request.data.get("from")
#         date_to = self.request.data.get("to")
#         search = self.request.data.get("search")

#         if status_filter and status_filter.lower() != "all":
#             qs = qs.filter(status__iexact=status_filter)
#         if payment_filter and payment_filter.lower() != "all":
#             qs = qs.filter(payment_method__iexact=payment_filter)
#         if date_from:
#             qs = qs.filter(created_at__date__gte=date_from)
#         if date_to:
#             qs = qs.filter(created_at__date__lte=date_to)
#         if search:
#             qs = qs.filter(
#                 id__icontains=search
#             )  # or filter by customer name if needed

#         return qs

from rest_framework.generics import RetrieveAPIView, UpdateAPIView
from rest_framework.permissions import IsAuthenticated
from Web.models import Order
from .serializers import OrderDetailSerializer


class OrderDetailAPIView(RetrieveAPIView):
    queryset = Order.objects.select_related(
        "user",
        "shipping_address",
        "billing_address"
    ).prefetch_related(
        "items",
        "items__product",
        "items__variant",
        "requests",
    )
    serializer_class = OrderDetailSerializer
    permission_classes = [IsAuthenticated]

class OrderUpdateStatusAPIView(UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderDetailSerializer
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        order = self.get_object()

        order.status = request.data.get("status", order.status)
        order.payment_status = request.data.get("payment_status", order.payment_status)
        order.save()
        message_text = (
                f"Your Order #{order.order_number} status "
                f"has been change to {order.status}"
            )
        notification = Notification.objects.create(
            title=f"Order has been {order.status}",
            message=message_text,
            notification_type="order_status",
            is_general=False,
            is_active=True,
            order=order
        )

        NotificationRecipient.objects.create(
            notification=notification,
            user=order.user,
            is_read=False
        )

        return Response({"message": "Order updated successfully"})

# views.py
from django.contrib.auth.decorators import login_required
from Web.models import SupportTicket

@login_required
def support_ticket_list_view(request):
    tickets = SupportTicket.objects.all().order_by("-created_at")
    return render(request, "Other/support_ticket_list.html", {"tickets": tickets})





from django.db import transaction
from rest_framework.permissions import IsAdminUser
from rest_framework.generics import UpdateAPIView
from Web.models import OrderRequest,OrderRequestComment,UserWalletTransaction,UserWallet,Notification,NotificationRecipient

from django.db import transaction

class AdminOrderRequestUpdateAPIView(UpdateAPIView):
    queryset = OrderRequest.objects.select_related("order", "order__user")
    serializer_class = AdminOrderRequestUpdateSerializer
    permission_classes = [IsAdminUser]
    
    @transaction.atomic
    def perform_update(self, serializer):

        instance = serializer.save()
        comment_text = serializer.validated_data.get("comment", "")

        # ✅ Save Status History
        OrderRequestComment.objects.create(
            request=instance,
            user=self.request.user,
            status=instance.status,
            is_admin=True,
            comment=comment_text
        )

        order = instance.order
        user = order.user
        # Only apply business logic when approved
        if instance.status != "approved":

            # 🔔 Notify User (Rejected Case)
            notification = Notification.objects.create(
                title="Order Request Rejected",
                message=f"Your {instance.request_type} request for Order #{order.order_number} was rejected.",
                notification_type="order_request",
                is_general=False,
                is_active=True,
                order=order
            )

            NotificationRecipient.objects.create(
                notification=notification,
                user=order.user,
                is_read=False
            )
            return


        # ================= CANCEL =================
        if instance.request_type == "cancel":
            order.status = "cancelled"
            order.save()
            message_text = f"Your cancel request for Order #{order.order_number} has been approved."

        # ================= RETURN =================
        elif instance.request_type == "return":

            # Prevent double refund
            if UserWalletTransaction.objects.filter(order=order).exists():
                return

            order.status = "returned"
            order.save()


            wallet, _ = UserWallet.objects.get_or_create(user=user)

            wallet.balance += order.total_amount
            wallet.save()

            UserWalletTransaction.objects.create(
                user=user,
                wallet=wallet,
                transaction_type="credit",
                amount=order.total_amount,
                description=f"Refund for Order #{order.order_number}",
                order=order
            )
            message_text = (
                f"Your return request for Order #{order.order_number} "
                f"has been approved. Amount refunded to wallet."
            )
        notification = Notification.objects.create(
            title="Order Request Approved",
            message=message_text,
            notification_type="order_request",
            is_general=False,
            is_active=True,
            order=order
        )

        NotificationRecipient.objects.create(
            notification=notification,
            user=order.user,
            is_read=False
        )

from rest_framework.generics import ListAPIView
from .serializers import AdminProductReviewSerializer
class AdminReviewListAPIView(ListAPIView):
    queryset = ProductReview.objects.select_related("product", "user")
    serializer_class = AdminProductReviewSerializer
    permission_classes = [IsAdminUser]


class AdminReviewUpdateAPIView(UpdateAPIView):
    queryset = ProductReview.objects.all()
    serializer_class = AdminProductReviewSerializer
    permission_classes = [IsAdminUser]

def admin_reviews_page(request):
    return render(request, "products/admin_reviews.html")

from django.db.models import Count

@login_required
def wishlist_page(request):
    wishlist_items = (Wishlist.objects
                      .filter(user=request.user)
                      .select_related("product")
                      .values("product__id", "product__name", "product__price", "product__images")
                      .annotate(quantity=Count("product"))
                      .order_by("product__name"))

    # Calculate subtotal for each item
    for item in wishlist_items:
        item['subtotal'] = item['product__price'] * item['quantity']

    # Total price
    total_price = sum(item['subtotal'] for item in wishlist_items)

    return render(request, "products/wishlist.html", {
        "wishlist_items": wishlist_items,
        "total_price": total_price,
    })


from .serializers import PromotionsSerializer

class PromotionsViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionsSerializer
    permission_classes = [permissions.IsAuthenticated]



@login_required
def promotions_page(request):
    
    return render(request, "promotions/promotions.html")

@login_required
def inventory_page(request):
    
    return render(request, "Inventory/Inventory.html")

from .models import ProductVariantInventory
from .serializers import ProductVariantInventorySerializer

class VariantInventoryViewSet(viewsets.ModelViewSet):

    queryset = ProductVariantInventory.objects.select_related(
        "variant",
        "variant__product"
    )

    serializer_class = ProductVariantInventorySerializer
    permission_classes = [permissions.IsAuthenticated]


    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        self.perform_create(serializer)

        return Response(serializer.data, status=201)


    def partial_update(self, request, *args, **kwargs):

        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        self.perform_update(serializer)

        return Response(serializer.data)



from rest_framework import viewsets, permissions
from .models import ProductVariant
from .serializers import ProductVariant2Serializer


class ProductVariantViewSet(viewsets.ModelViewSet):

    queryset = ProductVariant.objects.select_related('product')
    serializer_class = ProductVariant2Serializer
    permission_classes = [permissions.IsAuthenticated]


    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        self.perform_create(serializer)

        return Response(serializer.data, status=201)


    def partial_update(self, request, *args, **kwargs):

        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        self.perform_update(serializer)

        return Response(serializer.data)