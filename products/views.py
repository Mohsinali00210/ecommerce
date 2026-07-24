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
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from rest_framework.permissions import BasePermission

class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )
# Create your views here.
class IsAdminRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_staff



class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsSuperUser]

   
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
    permission_classes = [IsSuperUser]

   
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
    permission_classes = [IsSuperUser]
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


# Changes vs. your current ProductViewSet:
#   1. Inherits ErrorLoggingMixin -> gives you log_validation_error() and
#      log_exception() (both already referenced in your code but weren't
#      defined anywhere).
#   2. create()/update()/partial_update() now wrap the DB-touching part in
#      try/except IntegrityError/Exception, so a bad insert on Product OR
#      any nested table (ProductVariant, ProductVariantOption, Promotion,
#      ProductImage) gets logged with the field+table name and returned
#      to the frontend, instead of an unhandled 500.

# from django.db import IntegrityError, transaction
# from rest_framework import status, viewsets, filters
# from rest_framework.exceptions import ValidationError as DRFValidationError
# from rest_framework.response import Response
# from django_filters.rest_framework import DjangoFilterBackend

# from .error_logging_mixin import ErrorLoggingMixin  # adjust import path as needed


# class ProductViewSet(ErrorLoggingMixin, viewsets.ModelViewSet):
#     serializer_class = ProductSerializer
#     permission_classes = [IsSuperUser]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['category', 'status', 'stock_status', 'free_shipping']
#     search_fields = ['name', 'sku', 'description']
#     ordering_fields = ['price', 'created_at']

#     def get_queryset(self):
#         return Product.objects.filter(is_deleted=False) \
#             .prefetch_related('variants', 'images', 'promotions') \
#             .order_by('-id')

#     def create(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)

#         if not serializer.is_valid():
#             log_validation_error(self, request, serializer.errors)
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             with transaction.atomic():
#                 self.perform_create(serializer)
#         except DRFValidationError as exc:
#             log_validation_error(self, request, exc.detail)
#             return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
#         except IntegrityError as exc:
#             return self.handle_db_exception(request, exc, table_name='Product')
#         except Exception as exc:
#             return self.handle_db_exception(request, exc, table_name='Product')

#         headers = self.get_success_headers(serializer.data)
#         return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

#     def update(self, request, *args, **kwargs):
#         instance = self.get_object()
#         serializer = self.get_serializer(instance, data=request.data)

#         if not serializer.is_valid():
#             log_validation_error(self, request, serializer.errors)
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             with transaction.atomic():
#                 self.perform_update(serializer)
#         except DRFValidationError as exc:
#             log_validation_error(self, request, exc.detail)
#             return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
#         except IntegrityError as exc:
#             return self.handle_db_exception(request, exc, table_name='Product')
#         except Exception as exc:
#             return self.handle_db_exception(request, exc, table_name='Product')

#         return Response(serializer.data)

#     def partial_update(self, request, *args, **kwargs):
#         instance = self.get_object()
#         serializer = self.get_serializer(instance, data=request.data, partial=True)

#         if not serializer.is_valid():
#             log_validation_error(self, request, serializer.errors)
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             with transaction.atomic():
#                 self.perform_update(serializer)
#         except DRFValidationError as exc:
#             log_validation_error(self, request, exc.detail)
#             return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
#         except IntegrityError as exc:
#             return self.handle_db_exception(request, exc, table_name='Product')
#         except Exception as exc:
#             return self.handle_db_exception(request, exc, table_name='Product')

#         return Response(serializer.data)

#     def destroy(self, request, *args, **kwargs):
#         try:
#             instance = self.get_object()
#             instance.is_deleted = True  # soft delete, matches your original behavior
#             instance.save()
#             return Response(status=status.HTTP_204_NO_CONTENT)
#         except Exception as exc:
#             return self.handle_db_exception(request, exc, table_name='Product')

#     def retrieve(self, request, *args, **kwargs):
#         instance = self.get_object()
#         serializer = self.get_serializer(instance)
#         return Response(serializer.data)

#     def perform_create(self, serializer):
#         serializer.save(created_by=self.request.user)

#     def perform_update(self, serializer):
#         serializer.save(modified_by=self.request.user)


# # log_validation_error was called in your original code but never defined
# # anywhere in the files you shared. ErrorLoggingMixin now provides it as
# # self.log_validation_error(...) — this free function keeps your exact
# # original call signature (log_validation_error(self, request, errors))
# # working without touching every call site.
# def log_validation_error(view, request, errors):
#     view.log_validation_error(request, errors)


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsSuperUser]
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

    def retrieve(self, request, *args, **kwargs):
        print("kwargs =", kwargs)
        print("pk =", kwargs.get("pk"))
        queryset = self.get_queryset()
        print("Exists =", queryset.filter(pk=kwargs.get("pk")).exists())
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

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
    permission_classes = [IsSuperUser]
    
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
    permission_classes = [IsSuperUser]
    
    def get_queryset(self):
        return Attribute_Types.objects.filter(is_deleted=False)
@login_required
def categories(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "categories/categories.html")

@login_required
def attributes(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "Other/attributes.html")
@login_required
def brands(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "Other/brands.html")

@login_required(login_url='login')
def addProduct(request, product_id =None):
    if not request.user.is_superuser:
        return redirect('login')   
    tax_categories = TaxCategory.objects.filter(is_active=True, is_deleted=False)
    context = { 'tax_categories': tax_categories }
    return render(request, "products/addProduct.html",context)

@login_required(login_url='login')
def editProduct(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "products/addProduct.html")
@login_required(login_url='login')
def editProduct(request, id=None):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "products/addProduct.html", {
        "product_id": id
    })

@login_required(login_url='login')
def products(request):
    if not request.user.is_superuser:
        return redirect('login')
 
    product_qs = Product.objects.filter(is_deleted=False).order_by('-id')
 
    search = request.GET.get('search', '').strip()
    category = request.GET.get('category')
    stock_status = request.GET.get('stock_status')
    status = request.GET.get('status')
 
    if search:
        product_qs = product_qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
    if category:
        product_qs = product_qs.filter(category__id=category)
    if stock_status:
        product_qs = product_qs.filter(stock_status=stock_status)
    if status:
        product_qs = product_qs.filter(status=status)
 
    context = {
        'products': product_qs.distinct(),
        'categories': Category.objects.filter(is_deleted=False, is_active=True),
        'filters': {
            'search': search, 'category': category,
            'stock_status': stock_status, 'status': status,
        },
    }
    return render(request, 'products/products.html', context)
 

@login_required(login_url='login')
def ProductPreview(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "products/ProductPreview.html")

@login_required(login_url='login')
def orders(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "orders/Orders.html")

@login_required(login_url='login')
def OrdersByStatus(request, status):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "orders/OrdersByStatus.html",{"status":status})


# views.py

from rest_framework import generics, permissions
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from .serializers import OrderSerializer
from Web.models import OrderSeenLog
from django.db.models import Exists, OuterRef


class OrdersListAPIView(generics.ListAPIView):
    serializer_class = OrderSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsSuperUser]
    def get_queryset(self):
        user = self.request.user
        seen_log = OrderSeenLog.objects.filter( order=OuterRef('pk'), user=user )
        qs = (Order.objects.annotate(is_seen=Exists(seen_log)).order_by("-created_at"))

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
from Web.models import Order,OrderSeenLog
from .serializers import OrderDetailSerializer
from django.utils import timezone


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
    permission_classes = [IsSuperUser]

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        order = self.get_object()
        user = request.user
        log, created = OrderSeenLog.objects.get_or_create(
            order=order,
            user=user,
            defaults={
                "is_seen_by_admin": True,
                "created_at": timezone.now()
            }
        )

        # If log exists but not marked as seen, update it
        if not created and not log.is_seen_by_admin:
            log.is_seen_by_admin = True
            log.save(update_fields=["is_seen_by_admin"])

        return response

class OrderUpdateStatusAPIView(UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderDetailSerializer
    permission_classes = [IsSuperUser]

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
from Web.models import SupportTicket

@login_required
def support_ticket_list_view(request):
    if not request.user.is_superuser:
        return redirect('login') 
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
    permission_classes = [IsSuperUser]
    
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
    permission_classes = [IsSuperUser]


class AdminReviewUpdateAPIView(UpdateAPIView):
    queryset = ProductReview.objects.all()
    serializer_class = AdminProductReviewSerializer
    permission_classes = [IsSuperUser]
@login_required
def admin_reviews_page(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "products/admin_reviews.html")

from django.db.models import Count

@login_required(login_url='login')
def wishlist_page(request):
    if not request.user.is_superuser:
        return redirect('login') 
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
    permission_classes = [IsSuperUser]



@login_required(login_url='login')
def promotions_page(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "promotions/promotions.html")

@login_required
def inventory_page(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "Inventory/Inventory.html")

from .models import ProductVariantInventory
from .serializers import ProductVariantInventorySerializer

class VariantInventoryViewSet(viewsets.ModelViewSet):

    queryset = ProductVariantInventory.objects.select_related(
        "variant",
        "variant__product"
    )

    serializer_class = ProductVariantInventorySerializer
    permission_classes = [IsSuperUser]


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
    permission_classes = [IsSuperUser]


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


from .models import Picture
from .serializers import PictureSerializer
class PictureViewSet(viewsets.ModelViewSet):
    queryset = Picture.objects.all().order_by('-created_at')
    serializer_class = PictureSerializer
    permission_classes = [IsSuperUser]

    def get_queryset(self):
        queryset = Picture.objects.filter(is_active=True).order_by('-created_at')

        picture_type = self.request.query_params.get('picture_type')

        if picture_type:
            queryset = queryset.filter(picture_type=picture_type)

        return queryset

@login_required
def picture_page(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "Other/pictures.html")



# views.py
@login_required(login_url='login')
def wish_to_buy_admin(request):
    if not request.user.is_superuser:
        return redirect('login') 
    return render(request, "Other/wish_to_buy.html")

# views.py
from django.http import JsonResponse
from Web.models import WishToBuy
@login_required(login_url='login')
def wish_to_buy_list(request):
    data = []

    queryset = WishToBuy.objects.select_related("user", "product", "variant").order_by("-created_at")

    for obj in queryset:
        data.append({
            "id": obj.id,
            "user": obj.user.full_name,
            "product": obj.product.name if obj.product else "",
            "variant": str(obj.variant.name) if obj.variant else "-",
            "date": obj.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    return JsonResponse(data, safe=False)



import json
 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db import transaction
from django.db.models import Q
 
from .models import Product, Category, ProductVariant, ProductVariantOption, ProductImage, Promotion, Tag
from .forms import (
    ProductForm, ProductVariantForm, ProductImageForm, PromotionForm, TagAddForm,
)
 
 
# ---------------------------------------------------------------------------
# Product list
# ---------------------------------------------------------------------------
@login_required
def product_list(request):
    products = Product.objects.filter(is_deleted=False).order_by('-id')
 
    search = request.GET.get('search', '').strip()
    category = request.GET.get('category')
    stock_status = request.GET.get('stock_status')
    status = request.GET.get('status')
 
    if search:
        products = products.filter(Q(name__icontains=search) | Q(sku__icontains=search))
    if category:
        products = products.filter(category__id=category)
    if stock_status:
        products = products.filter(stock_status=stock_status)
    if status:
        products = products.filter(status=status)
 
    context = {
        'products': products.distinct(),
        'categories': Category.objects.filter(is_deleted=False, is_active=True),
        'filters': {
            'search': search, 'category': category,
            'stock_status': stock_status, 'status': status,
        },
    }
    return render(request, 'products/products.html', context)
 
 
# ---------------------------------------------------------------------------
# Product add / edit (core fields only)
# ---------------------------------------------------------------------------
@login_required
def product_form_view(request, pk=None):
    product = get_object_or_404(Product, pk=pk, is_deleted=False) if pk else None
 
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            instance = form.save(commit=False)
            if product is None:
                instance.created_by = request.user
            else:
                instance.modified_by = request.user
            instance.save()
            form.save_m2m()
            messages.success(request, f"Product '{instance.name}' saved successfully.")
            return redirect('product_edit', pk=instance.pk)
        messages.error(request, "Please fix the errors highlighted below.")
    else:
        form = ProductForm(instance=product)
 
    context = {
        'form': form,
        'product': product,
    }
    return render(request, 'products/product_form.html', context)
 
 
# ---------------------------------------------------------------------------
# Shared helper: modal add/edit views all follow the same GET/POST shape:
#   GET  -> return {"html": "<form partial>"}                (to fill the modal)
#   POST (invalid) -> return {"success": false, "html": "..."} (re-render with errors)
#   POST (valid)   -> return {"success": true, "message": "..."} (JS closes + reloads)
# ---------------------------------------------------------------------------
 
@login_required
def variant_add_modal(request, product_id):
    """Returns the multi-variant builder partial (option groups -> generated
    combination table). Saving happens via variant_bulk_create, not here."""
    product = get_object_or_404(Product, pk=product_id)
    html = render_to_string(
        'products/partials/variant_form.html',
        {'product': product, 'mode': 'add'}, request=request,
    )
    return JsonResponse({'html': html})
 
 
@login_required
def variant_edit_modal(request, product_id, variant_id):
    product = get_object_or_404(Product, pk=product_id)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
 
    if request.method == 'POST':
        form = ProductVariantForm(request.POST, instance=variant, product=product)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.product = product
            instance.modified_by = request.user
            instance.save()
            return JsonResponse({'success': True, 'message': 'Variant saved successfully.'})
        html = render_to_string(
            'products/partials/variant_form.html',
            {'form': form, 'product': product, 'variant': variant, 'mode': 'edit'}, request=request,
        )
        return JsonResponse({'success': False, 'html': html})
 
    form = ProductVariantForm(instance=variant, product=product)
    html = render_to_string(
        'products/partials/variant_form.html',
        {'form': form, 'product': product, 'variant': variant, 'mode': 'edit'}, request=request,
    )
    return JsonResponse({'html': html})
 
 
@login_required
def variant_delete(request, product_id, variant_id):
    variant = get_object_or_404(ProductVariant, pk=variant_id, product_id=product_id)
    variant.delete()
    messages.success(request, "Variant deleted.")
    return redirect('product_edit', pk=product_id)
 
 
@login_required
def variant_bulk_create(request, product_id):
    """Saves every row generated by the variant-combination builder (name/options ->
    cartesian product table) in one go, plus the ProductVariantOption definitions
    they were built from. Mirrors the old DRF create() logic, minus DRF."""
    product = get_object_or_404(Product, pk=product_id)
 
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)
 
    raw_variants = request.POST.get('variants')
    raw_options = request.POST.get('options')
    print(" raw_variants ",raw_variants)
    print("raw_options ",raw_options)
    if not raw_variants:
        return JsonResponse({
            'success': False,
            'message': 'No variants were generated. Add at least one variant option and click "Add Variant" first.',
        })
 
    try:
        variants_data = json.loads(raw_variants)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'message': 'Variant data was malformed. Please try again.'})
 
    if not variants_data:
        return JsonResponse({
            'success': False,
            'message': 'No variants were generated. Add at least one variant option and click "Add Variant" first.',
        })
 
    options_data = []
    if raw_options:
        try:
            options_data = json.loads(raw_options)
        except (json.JSONDecodeError, TypeError):
            return JsonResponse({'success': False, 'message': 'Variant option data was malformed. Please try again.'})
 
    # ---- Validate every row up front so we either save everything or nothing ----
    errors = []
    seen_skus = set()
    for index, variant_data in enumerate(variants_data, start=1):
        sku = (variant_data.get('sku') or '').strip()
        price = variant_data.get('price')
 
        if not sku:
            errors.append(f"Row {index}: SKU is required.")
        elif sku in seen_skus:
            errors.append(f"Row {index}: SKU '{sku}' is duplicated in this batch.")
        elif ProductVariant.objects.filter(sku=sku).exists():
            errors.append(f"Row {index}: SKU '{sku}' already exists.")
        seen_skus.add(sku)
 
        if price in (None, ''):
            errors.append(f"Row {index}: Price is required.")
 
    if errors:
        return JsonResponse({'success': False, 'message': ' '.join(errors)})
 
    with transaction.atomic():
        created_variants = []
        for index, variant_data in enumerate(variants_data):
            variant = ProductVariant.objects.create(
                product=product,
                name=variant_data.get('name', ''),
                sku=variant_data.get('sku'),
                price=variant_data.get('price') or 0,
                stock_quantity=variant_data.get('stock_quantity') or 0,
                created_by=request.user,
            )
            image_file = request.FILES.get(f'variants[{index}][image]')
            if image_file:
                product_image = ProductImage.objects.create(
                    product=product, image=image_file, created_by=request.user,
                )
                variant.image = product_image
                variant.save()
            created_variants.append(variant)
 
        for item in options_data:
            option_name = item.get('option_name')
            option_values = item.get('option', [])
            color_values = item.get('value', [])
            if not option_name or not option_values:
                continue
            for i, value in enumerate(option_values):
                color_code = color_values[i] if option_name.lower() == 'color' and i < len(color_values) else None
                ProductVariantOption.objects.create(
                    product=product,
                    option_name=option_name,
                    option=value,
                    value=color_code,
                    created_by=request.user,
                )
 
    return JsonResponse({
        'success': True,
        'message': f'{len(created_variants)} variant(s) created successfully.',
    })
 
 
@login_required
def image_modal(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
 
    if request.method == 'POST':
        form = ProductImageForm(request.POST, request.FILES)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.product = product
            instance.created_by = request.user
            instance.save()
            return JsonResponse({'success': True, 'message': 'Image added successfully.'})
        html = render_to_string(
            'products/partials/image_form.html',
            {'form': form, 'product': product}, request=request,
        )
        return JsonResponse({'success': False, 'html': html})
 
    form = ProductImageForm()
    html = render_to_string(
        'products/partials/image_form.html',
        {'form': form, 'product': product}, request=request,
    )
    return JsonResponse({'html': html})
 
 
@login_required
def image_delete(request, product_id, image_id):
    image = get_object_or_404(ProductImage, pk=image_id, product_id=product_id)
    image.delete()
    messages.success(request, "Image removed.")
    return redirect('product_edit', pk=product_id)
 
 
@login_required
def promotion_modal(request, product_id, promotion_id=None):
    product = get_object_or_404(Product, pk=product_id)
    promotion = get_object_or_404(Promotion, pk=promotion_id, products=product) if promotion_id else None
 
    if request.method == 'POST':
        form = PromotionForm(request.POST, instance=promotion)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.created_by = request.user if promotion is None else instance.created_by
            instance.modified_by = request.user
            instance.save()
            instance.products.add(product)
            return JsonResponse({'success': True, 'message': 'Promotion saved successfully.'})
        html = render_to_string(
            'products/partials/promotion_form.html',
            {'form': form, 'product': product, 'promotion': promotion}, request=request,
        )
        return JsonResponse({'success': False, 'html': html})
 
    form = PromotionForm(instance=promotion)
    html = render_to_string(
        'products/partials/promotion_form.html',
        {'form': form, 'product': product, 'promotion': promotion}, request=request,
    )
    return JsonResponse({'html': html})
 
 
@login_required
def promotion_delete(request, product_id, promotion_id):
    promotion = get_object_or_404(Promotion, pk=promotion_id, products__id=product_id)
    promotion.products.remove(product_id)
    messages.success(request, "Promotion removed from this product.")
    return redirect('product_edit', pk=product_id)
 
 
@login_required
def tag_modal(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
 
    if request.method == 'POST':
        form = TagAddForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['tag_name'].strip()
            tag, _ = Tag.objects.get_or_create(name=name)
            product.tags.add(tag)
            return JsonResponse({'success': True, 'message': f"Tag '{name}' added."})
        html = render_to_string(
            'products/partials/tag_form.html',
            {'form': form, 'product': product}, request=request,
        )
        return JsonResponse({'success': False, 'html': html})
 
    form = TagAddForm()
    html = render_to_string(
        'products/partials/tag_form.html',
        {'form': form, 'product': product}, request=request,
    )
    return JsonResponse({'html': html})
 
 
@login_required
def tag_remove(request, product_id, tag_id):
    product = get_object_or_404(Product, pk=product_id)
    product.tags.remove(tag_id)
    messages.success(request, "Tag removed.")
    return redirect('product_edit', pk=product_id)