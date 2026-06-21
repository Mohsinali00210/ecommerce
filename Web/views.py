from django.shortcuts import render, get_object_or_404,redirect
from products.models import Product, Promotion,ProductReview,ProductVariant
from django.utils import timezone
import json
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import Cart, CartItem,SupportTicket,OrderItem, Notification, NotificationRecipient
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticatedOrReadOnly,IsAuthenticated

from rest_framework import status
from .serializers import CheckoutSerializer,AddressSerializer,PlaceOrderSerializer,NotificationSerializer,CartSerializer

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import Address

from products.models import Picture
def Index(request):
    Products = Product.objects.filter()
    freeshipping = Product.objects.filter(
            free_shipping=True
        ).prefetch_related('images')
    current_date = timezone.now().date()
    promotions =  Promotion.objects.filter(end_date__gte=current_date).prefetch_related("products")
    for promo in promotions:
        for product in promo.products.all():
            product.final_price = promo.get_discounted_price(product.price)
            product.has_discount = product.final_price != product.price
    picture = Picture.objects.filter(is_active=True,picture_type="slider").order_by('-created_at')


    img_promotions = Promotion.objects.filter( is_active=True, show_on_home=True, start_date__lte=current_date, end_date__gte=current_date,
    ).only("id", "name", "web_image", "mobile_image", "promo_code")
    context = { 'Products': Products, "freeshipping":freeshipping,"promotions":promotions,"sliderPictures":picture,"img_promotions":img_promotions }
    return render(request, "Web/index.html",context)

def PromotionDetail(request, id):
    now = timezone.now()
    promo = get_object_or_404(  Promotion, id=id, is_active=True, show_on_home=True, start_date__lte=now, end_date__gte=now )
    products = promo.products.all().prefetch_related("images")
    for product in products:
        product.final_price = promo.get_discounted_price(product.price)
        product.has_discount = product.final_price != product.price
    context = { "promo": promo, "products": products, }
    return render(request, "Web/promotion_detail.html", context)


def ProductDetails(request, id):
    product = get_object_or_404(
        Product.objects.prefetch_related("images", "variants", "variant_options"),
        id=id
    )
    
    max_handling_days = product.handling_time
    estimated_date = timezone.now() + timedelta(days=max_handling_days)
    now = timezone.now()

    # Product promotions
    promotions = Promotion.objects.filter(products=product, start_date__lte=now, end_date__gte=now)
    if promotions.exists():
        promo = promotions.first()
        product.final_price = promo.get_discounted_price(product.price)
        promo.discounted_price = promo.get_discounted_price(product.price) 
        promo.off_price = promo.get_off_price(product.price) 
    else:
        product.final_price = product.price
        product.off_price = product.old_price-product.final_price
    # Related products
    related_products = (
        Product.objects.filter(category__in=product.category.all(), brand=product.brand)
        .prefetch_related('images', "promotions")[:5]  # adjust number as needed
    )

    for prd in related_products:
        promo = prd.promotions.filter(start_date__lte=now, end_date__gte=now).first()
        if promo:
            prd.final_price = promo.get_discounted_price(prd.price)
            prd.discounted_price = promo.get_discounted_price(prd.price)
            prd.off_price = promo.get_off_price(prd.price)
        else:
            prd.final_price = prd.price
            prd.discounted_price = prd.price
            prd.off_price = prd.old_price-prd.final_price

    Reviews = product.reviews.filter(
        is_active=True,
        is_deleted=False,
        product=product
    ).select_related('user').order_by('-created_at')
    
    variants = product.variants.select_related("image")
    variant_data = []
    for v in variants:
        promotions = Promotion.objects.filter(products=product,start_date__lte=now,end_date__gte=now)

        if promotions.exists():
            promo = promotions.first()
            final_price = promo.get_discounted_price(v.price)
            off_price = promo.get_off_price(v.price)
        else:
            final_price = v.price
            off_price = product.old_price-final_price

        variant_data.append({ "id": v.id, "name": v.name, "price": float(v.price), "final_price": float(final_price), "off_price": float(off_price),
            "stock": v.stock_quantity
        })

    variants_json = json.dumps(variant_data, cls=DjangoJSONEncoder)
    can_review = OrderItem.objects.filter(
        order__user=request.user,
        order__status="delivered",
        product=product
    ).exists()
    wishlist_ids = []
    if request.user.is_authenticated:           
        wishlist_ids = Wishlist.objects.filter(
            user=request.user
        ).values_list("product_id", flat=True)
    context = {
        "product": product,
        "promotions": promotions,
        "images": product.images.all(),       
        # "variant_images": variants.image.all(),       
        "variants": variants, 
        "variants_json": variants_json,
        "options": product.variant_options.all(),  
        "related_products":related_products,
        "Reviews":Reviews,
        "can_review":can_review,
        "estimated_date":estimated_date,
        "user_wishlist_ids": wishlist_ids
    }

    return render(request, "Web/ProductDetails.html", context)





class AddToCartAPIView(APIView):
    authentication_classes = [SessionAuthentication]

    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data

        product = get_object_or_404(Product, id=data.get("product_id"))
        variant = None

        if data.get("variant_id"):
            variant = get_object_or_404(ProductVariant, id=data["variant_id"])

        quantity = int(data.get("quantity", 1))
        
        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create( user=request.user, is_active=True )
        else:
            if not request.session.session_key:
                request.session.create()
            cart, _ = Cart.objects.get_or_create( session_key=request.session.session_key, is_active=True )
        print("request.user.is_authenticated ",request.user.is_authenticated)
        price = variant.price if variant else product.price

        cart_item, created = CartItem.objects.get_or_create( cart=cart, product=product, variant=variant, defaults={"price": price,"quantity": quantity, } )

        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        return Response({ "message": "Item added to cart", "cart_id": cart.id, "item_id": cart_item.id, "quantity": cart_item.quantity, })

class CartDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated:
            cart = Cart.objects.filter(user=request.user, is_active=True).select_related("items")
        else:
            cart = Cart.objects.filter( session_key=request.session.session_key, is_active=True ).select_related("items")

        if not cart:
            return Response({"items": []})

        serializer = CartSerializer(cart)
        return Response(serializer.data)

from decimal import Decimal
from datetime import timedelta

def MyCart(request):
    if request.user.is_authenticated:
        cart = (
            Cart.objects
            .filter(user=request.user,is_active=True)
            .prefetch_related(
                "items",
                "items__product",
                "items__variant",
                "items__product__images",
            )
            .first()
        )
    else:

        cart = (
            Cart.objects
            .filter(session_key=request.session.session_key, is_active=True)
            .prefetch_related(
                "items",
                "items__product",
                "items__variant",
                "items__product__images",
            )
            .first()
        )
    shipping_total = Decimal(0)
    additional_total = Decimal(0)
    subtotal = Decimal(0)
    total_price_without_discount = Decimal(0)
    total_off_price = Decimal(0)
    handling_days = []
    if cart:
        current_date = timezone.now()

        for cartitem in cart.items.all():
            product = cartitem.product
            product.total_price_without_discount = cartitem.variant.price

            promo = (
                product.promotions
                .filter(start_date__lte=current_date, end_date__gte=current_date)
                .first()
            )
            if promo:
                final_price = promo.get_discounted_price(cartitem.variant.price)

                product.final_price = final_price
                product.off_price = promo.get_off_price(cartitem.variant.price) 

                product.discounted_price = final_price
                product.discount_type = promo.discount_type
                product.discount_value = promo.discount_value
                product.has_discount = final_price < cartitem.variant.price
            else:
                product.final_price = cartitem.variant.price
                product.off_price = 0 
                product.discounted_price = cartitem.variant.price
                product.discount_type = None
                product.discount_value = None
                product.has_discount = False
            
            total_price_without_discount += cartitem.variant.price * cartitem.quantity
            handling_days.append(product.handling_time)
            subtotal += product.final_price * cartitem.quantity
            shipping_total += product.shipping_charges
            additional_total += product.additional_shipping_charges
            total_off_price += product.off_price

            print("shipping_charges ",product.shipping_charges)
            print("additional_shipping_charges ",product.additional_shipping_charges)

    max_handling_days = max(handling_days) if handling_days else 0
    estimated_date = timezone.now() + timedelta(days=max_handling_days)
    context = {
        "cart": cart,
        "subtotal": subtotal,
        "shipping_total": shipping_total,
        "additional_total": additional_total,
        "final_total": subtotal + shipping_total + additional_total,
        "estimated_date":estimated_date,
        "total_price_without_discount":total_price_without_discount,
        "total_off_price":total_off_price,
    }
    return render(request, "Web/cart.html", context)

def cart_drawer(request):

    if request.user.is_authenticated:
        cart = Cart.objects.filter(
            user=request.user,
            is_active=True
        ).prefetch_related(
            "items",
            "items__product",
            "items__variant",
            "items__product__images"
        ).first()

    else:
        cart = Cart.objects.filter(
            session_key=request.session.session_key,
            is_active=True
        ).prefetch_related(
            "items",
            "items__product",
            "items__variant",
            "items__product__images"
        ).first()
    shipping_total = Decimal(0)
    additional_total = Decimal(0)
    subtotal = Decimal(0)
    handling_days = []
    if cart:
        current_date = timezone.now()

        for cartitem in cart.items.all():
            product = cartitem.product

            promo = (
                product.promotions
                .filter(start_date__lte=current_date, end_date__gte=current_date)
                .first()
            )
            if promo:
                final_price = promo.get_discounted_price(cartitem.variant.price)

                product.final_price = final_price
                product.discounted_price = final_price
                product.discount_type = promo.discount_type
                product.discount_value = promo.discount_value
                product.has_discount = final_price < cartitem.variant.price
                product.off_price = promo.get_off_price(cartitem.variant.price) 

            else:
                product.final_price = cartitem.variant.price
                product.discounted_price = cartitem.variant.price
                product.discount_type = None
                product.discount_value = None
                product.has_discount = False
                product.off_price = 0
    return render(request,"Web/cart_drawer.html",{"cart":cart})

from decimal import Decimal
from django.utils import timezone

def CheckoutPage(request):

    defaultaddresses = Address.objects.filter(user=request.user, is_default=True)
    addresses = Address.objects.filter(user=request.user)

    checkout_items = request.session.get("checkout_items", [])
    print("checkout_items ",checkout_items)
    # create lookup dict
    checkout_lookup = {str(i["cart_item_id"]): i for i in checkout_items}
    print("checkout_lookup ",checkout_lookup)
    if request.user.is_authenticated:
        cart = (
            Cart.objects
            .filter(user=request.user, is_active=True)
            .prefetch_related(
                "items",
                "items__product",
                "items__variant",
                "items__product__images",
            )
            .first()
        )
    else:
        cart = (
            Cart.objects
            .filter(session_key=request.session.session_key, is_active=True)
            .prefetch_related(
                "items",
                "items__product",
                "items__variant",
                "items__product__images",
            )
            .first()
        )

    shipping_total = Decimal(0)
    additional_total = Decimal(0)
    subtotal = Decimal(0)
    total_off_price = Decimal(0)
    total_price_without_discount = Decimal(0)
    handling_days = []

    filtered_items = []

    if cart:
        current_date = timezone.now()

        for cartitem in cart.items.all():

            # skip if not selected for checkout
            if str(cartitem.id) not in checkout_lookup:
                continue

            session_item = checkout_lookup[str(cartitem.id)]
            quantity = session_item.get("quantity", cartitem.quantity)

            product = cartitem.product

            product.total_price_without_discount = cartitem.variant.price
            promo = (
                product.promotions
                .filter(start_date__lte=current_date, end_date__gte=current_date)
                .first()
            )

            if promo:
                final_price = promo.get_discounted_price(cartitem.variant.price)

                product.final_price = final_price
                product.discounted_price = final_price
                product.discount_type = promo.discount_type
                product.discount_value = promo.discount_value
                product.has_discount = final_price < cartitem.variant.price
                product.off_price = promo.get_off_price(cartitem.variant.price) 

            else:
                product.final_price = cartitem.variant.price
                product.discounted_price = cartitem.variant.price
                product.discount_type = None
                product.discount_value = None
                product.has_discount = False
                product.off_price = 0
            handling_days.append(product.handling_time)
            subtotal += product.final_price * quantity
            total_price_without_discount += cartitem.variant.price * quantity
            shipping_total += product.shipping_charges
            total_off_price += product.off_price
            additional_total += product.additional_shipping_charges

            cartitem.quantity = quantity
            filtered_items.append(cartitem)
    max_handling_days = max(handling_days) if handling_days else 0
    estimated_date = timezone.now() + timedelta(days=max_handling_days)
    context = {
        "cart_items": filtered_items,
        "subtotal": subtotal,
        "shipping_total": shipping_total,
        "total_off_price": total_off_price,
        "additional_total": additional_total,
        "final_total": subtotal + shipping_total + additional_total,
        "estimated_date":estimated_date,
        "total_price_without_discount":total_price_without_discount
    }

    return render(
        request,
        "Web/checkout.html",
        {
            "items": context,
            "defaultaddresses": defaultaddresses,
            "addresses": addresses
        }
    )
    # defaultaddresses = Address.objects.filter(user=request.user,is_default=True)
    # addresses = Address.objects.filter(user=request.user)
    # checkout_items = request.session.get("checkout_items", [])

    # updated_icheckout_items = request.session.get("checkout_items", [])
    # updated_items = []
    # shipping_total = Decimal(0)
    # additional_total = Decimal(0)
    # subtotal = Decimal(0)
    # if checkout_items:
    #     product_ids = [item["product_id"] for item in checkout_items]
    #     variant_ids = [item.get("variant_id") for item in checkout_items if item.get("variant_id")]

    #     products = (Product.objects.filter(id__in=product_ids).prefetch_related("images", "promotions"))
    #     variants = (ProductVariant.objects.filter(id__in=variant_ids).select_related("product"))

    #     product_map = {p.id: p for p in products}
    #     variant_map = {v.id: v for v in variants}

    #     now = timezone.now()

    #     for item in checkout_items:
    #         product_id = int(item["product_id"])          # 🔥 FIX
    #         variant_id = int(item["variant_id"]) if item.get("variant_id") else None

    #         product = product_map.get(product_id)
    #         variant = variant_map.get(variant_id)
            

    #         if not product:
    #             continue

    #         base_price = variant.price if variant else product.price

    #         promo = product.promotions.filter(
    #             start_date__lte=now,
    #             end_date__gte=now
    #         ).first()

    #         final_price = promo.get_discounted_price(base_price) if promo else base_price
            
    #         subtotal += final_price * item.get("qty", 1)
    #         shipping_total += product.shipping_charges
    #         additional_total += product.additional_shipping_charges

    #         updated_items.append({
    #             "product_id": product.id,
    #             "variant_id": variant.id if variant else None,
    #             "name": product.name,
    #             "variant_name": variant.name if variant else "",
    #             "qty": item.get("qty", 1),
    #             "price": base_price,
    #             "final_price": final_price,
    #             "subtotal": subtotal,
    #             "shipping_total": shipping_total,
    #             "additional_total": additional_total,
    #             "discounted_price": final_price,
    #             "discount_type": promo.discount_type if promo else None,
    #             "image": (
    #                 variant.image.image.url
    #                 if variant and variant.image
    #                 else product.images.first().image.url
    #                 if product.images.exists()
    #                 else ""
    #             ),
    #         })
    #     print(updated_items)
    #     # persist clean data back to session
    #     # request.session["checkout_items"] = updated_items
    #     # request.session.modified = True

    
    # return render( request, "Web/checkout.html",  {"items": updated_items,"defaultaddresses":defaultaddresses,"addresses":addresses})

class RemoveCartItemAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        item_id = request.data.get("item_id")

        cart_item = get_object_or_404(CartItem, id=item_id)

        cart_item.is_active=False
        cart_item.is_deleted=True

        return Response({
            "success": True,
            "item_id": item_id
        })



class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            order = serializer.save()
            return Response(
                {
                    "success": True,
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "payment_method": order.payment_method,
                    "total_amount": order.total_amount,
                    "status": order.status,
                },
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )




@require_POST
def SaveCheckoutSession(request):
    try:
        data = json.loads(request.body)
        items = data.get("items", [])

        if not items:
            return JsonResponse(
                {"success": False, "message": "No items selected"},
                status=400
            )

        request.session["checkout_items"] = items
        request.session.modified = True

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=500
        )



def OrderSuccess(request):

    if request.user.is_authenticated:
        cart = Cart.objects.filter(
            user=request.user,
            is_active=True
        ).prefetch_related(
            "items",
            "items__product",
            "items__variant",
            "items__product__images",
        ).first()
    else:
        cart = Cart.objects.filter(
            session_key=request.session.session_key,
            is_active=True
        ).prefetch_related(
            "items",
            "items__product",
            "items__variant",
            "items__product__images",
        ).first()
    if cart:
        cart.is_active = False
        cart.save()
    request.session.pop("checkout_items", None)

    return render(request, "Web/order_success.html")



class AddressAPIView(APIView):
    authentication_classes = [SessionAuthentication]

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create new address
        """
        serializer = AddressSerializer(data=request.data)

        if serializer.is_valid():
            if serializer.validated_data.get("is_default"):
                Address.objects.filter(
                    user=request.user
                ).update(is_default=False)

            address = serializer.save(user=request.user)

            return Response(
                {
                    "message": "Address added successfully",
                    "address": AddressSerializer(address).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        """
        Update existing address
        """
        address = get_object_or_404(Address, id=pk, user=request.user)

        serializer = AddressSerializer(
            address, data=request.data, partial=True
        )

        if serializer.is_valid():
            if serializer.validated_data.get("is_default"):
                Address.objects.filter(
                    user=request.user
                ).exclude(id=address.id).update(is_default=False)

            serializer.save()

            return Response(
                {
                    "message": "Address updated successfully",
                    "address": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    def get(self, request, pk):
        adss = get_object_or_404(Address, pk=pk, user=request.user)

        return Response({
            "id": adss.id,
            "address_type": adss.address_type,
            "full_name": adss.full_name,
            "phone": adss.phone,
            "street_address": adss.street_address,
            "city": adss.city,
            "state": adss.state,
            "country": adss.country,
            "postal_code": adss.postal_code,
            "is_default": adss.is_default,
        })






class PlaceOrderAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PlaceOrderSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            order = serializer.save()
            notification = Notification.objects.create(
                title="Order Placed Successfully",
                message=f"Your order #{order.id} has been placed successfully. Total: {order.total_amount}",
                notification_type="order",
                is_general=False,
                is_active=True,
                order=order
            )
            NotificationRecipient.objects.create(notification=notification,user=request.user,is_read=False)
            return Response(
                {
                    "message": "Order placed successfully",
                    "order_id": order.id,
                    "total": order.total_amount,
                },
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



from django.contrib.auth.decorators import login_required
from .models import OrderRequest, Order

@login_required
def MyOrders(request):
    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related("items", "items__product", "items__product__images","requests")
        .order_by("-created_at")
    )

    return render(request, "Web/MyOrders.html", {
        "orders": orders
    })

from rest_framework.generics import RetrieveAPIView
from .serializers import OrderDetailSerializer


class OrderDetailAPIView(RetrieveAPIView):
    queryset = Order.objects.select_related(
        "user",
        "shipping_address",
        "billing_address",
    ).prefetch_related(
        "items",
        "items__product",
        "items__variant",
        "requests"
    )
    serializer_class = OrderDetailSerializer
    permission_classes = [IsAuthenticated]
def Contact(request):

    data = {}
    success = False
    error = None

    if request.method == "POST":

        name = request.POST.get("name")
        email = request.POST.get("email")
        support_type = request.POST.get("support_type")
        subject = request.POST.get("subject")
        message = request.POST.get("message")
        attachment = request.FILES.get("attachment")

        # Preserve values if error
        data = {
            "name": name,
            "email": email,
            "subject": subject,
            "message": message,
        }

        if not name or not email or not subject or not message:
            error = "All required fields must be filled."
        else:
            SupportTicket.objects.create(
                user=request.user if request.user.is_authenticated else None,
                name=name,
                email=email,
                support_type=support_type,
                subject=subject,
                message=message,
                attachment=attachment
            )
            success = True
            data = {}  # clear form after success

    return render(request, "Web/Contact.html", {"success": success,"error": error,"data": data})


from .serializers import OrderRequestSerializer,ProductReviewSerializer

class OrderRequestAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data.copy()
        order_id = data.get("order_id")

        # Validate order exists and belongs to user
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        data["order"] = order.id
        data["user"] = request.user.id

        # Fix invalid "undefined" for nullable choices
        preferred_action = data.get("preferred_action")
        if preferred_action in [None, "", "undefined"]:
            data["preferred_action"] = None

        serializer = OrderRequestSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "order_request": serializer.data}, status=status.HTTP_201_CREATED)
        
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

from rest_framework.generics import CreateAPIView
class ProductReviewCreateAPIView(CreateAPIView):
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

from products.models import Wishlist

@login_required
def toggle_wishlist(request, product_id):
    product = Product.objects.get(id=product_id)

    wishlist_item, created = Wishlist.objects.get_or_create(
        user=request.user,
        product=product
    )

    if not created:
        wishlist_item.delete()
        return JsonResponse({"status": "removed"})

    return JsonResponse({"status": "added"})


# views.py

from django.db.models import Q, OuterRef, Subquery, BooleanField, Value
from django.db.models.functions import Coalesce



class UserNotificationAPIView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        # Subquery to get is_read from NotificationRecipient
        recipient_subquery = NotificationRecipient.objects.filter(
            notification=OuterRef('pk'),
            user=user
        ).values('is_read')[:1]

        notifications = Notification.objects.filter(
            is_active=True
        ).filter(
            Q(is_general=True) |
            Q(order__user=user)
        ).annotate(
            is_read=Coalesce(
                Subquery(recipient_subquery, output_field=BooleanField()),
                Value(False)
            )
        ).order_by('-created_at')

        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)


from django.db.models import Q, F
from products.models import Product, ProductVariant, Category, Brand
from django.db.models import Count
def product_list(request):
    products = Product.objects.filter(status='active', visible_individually=True)
    categories = Category.objects.annotate(
        product_count=Count('products', filter=Q(products__status='active', products__visible_individually=True))
    ).filter(product_count__gt=0)
    brands = Brand.objects.all()

    # ===== Filters =====
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category__id=category_id)

    brand_id = request.GET.get('brand')
    if brand_id:
        products = products.filter(brand_id=brand_id)

    price_min = request.GET.get('price_min')
    price_max = request.GET.get('price_max')
    if price_min:
        products = products.filter(price__gte=float(price_min))
    if price_max:
        products = products.filter(price__lte=float(price_max))

    availability = request.GET.get('availability')
    if availability:
        if availability == 'in_stock':
            products = products.filter(stock_status='in_stock')
        elif availability == 'low_stock':
            products = products.filter(stock_status='low_stock')
        elif availability == 'out_of_stock':
            products = products.filter(stock_status='out_of_stock')

    rating_min = request.GET.get('rating')
    if rating_min:
        products = products.filter(star_count__gte=int(rating_min))

    search = request.GET.get('search')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search) |
            Q(brief_description__icontains=search)
        )

    # ===== Sorting =====
    sort = request.GET.get('sort')
    if sort == 'price_asc':
        products = products.order_by('price')
    elif sort == 'price_desc':
        products = products.order_by('-price')
    elif sort == 'popularity':
        products = products.order_by('-sold')
    elif sort == 'new_arrivals':
        products = products.order_by('-id')  # assuming id increments with new products
    elif sort == 'discount':
        products = products.order_by('-discount_percentage')

    context = {
        "products": products.distinct(),
        "categories": categories,
        "brands": brands,
        "filters": request.GET
    }

    return render(request, 'web/product_list.html', context)




from django.db.models import Sum

class UserCartCountAPIView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.is_authenticated:
            cart = (
                Cart.objects
                .filter(user=request.user,is_active=True)
                .prefetch_related(
                    "items",
                    "items__product",
                    "items__variant",
                    "items__product__images",
                )
                .first()
            )
        else:

            cart = (
                Cart.objects
                .filter(session_key=request.session.session_key, is_active=True)
                .prefetch_related(
                    "items",
                    "items__product",
                    "items__variant",
                    "items__product__images",
                )
                .first()
            )
        shipping_total = Decimal(0)
        additional_total = Decimal(0)
        subtotal = Decimal(0)
        cart_products_count=0
        cart_items_count=0
        if cart:
            current_date = timezone.now()

            for cartitem in cart.items.all():
                product = cartitem.product

                promo = (
                    product.promotions
                    .filter(start_date__lte=current_date, end_date__gte=current_date)
                    .first()
                )
                if promo:
                    final_price = promo.get_discounted_price(product.price)

                    product.final_price = final_price
                    product.discounted_price = final_price
                    product.discount_type = promo.discount_type
                    product.discount_value = promo.discount_value
                    product.has_discount = final_price < product.price
                else:
                    product.final_price = product.price
                    product.discounted_price = product.price
                    product.discount_type = None
                    product.discount_value = None
                    product.has_discount = False
                
                subtotal += product.final_price * cartitem.quantity
                shipping_total += product.shipping_charges
                additional_total += product.additional_shipping_charges

            cart_items_count = cart.items.aggregate(total=Sum("quantity"))["total"] or 0
            cart_products_count = cart.items.count()
        context = {
            "cart": CartSerializer(cart).data,
            "subtotal": subtotal,
            "shipping_total": shipping_total,
            "additional_total": additional_total,
            "final_total": subtotal + shipping_total + additional_total,
            "cart_items_count": cart_items_count,
            "cart_products_count": cart_products_count,
        }

        return Response(context)




from rest_framework_simplejwt.tokens import RefreshToken

@login_required
def get_token_for_logged_in_user(request):
    user = request.user
    refresh = RefreshToken.for_user(user)
    
    return JsonResponse({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    })

import json

from .models import ChatThread, ChatMessage

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from .models import ChatThread, ChatMessage


@csrf_exempt
def send_message(request):
    if request.method == "POST":
        data = json.loads(request.body)

        user = request.user
        message = data.get("message")
        product_id = data.get("product_id")
        variant_id = data.get("variant_id")
        thread = ChatThread.objects.get(product_id=product_id, user=user)
        if thread:
            pass
        else:
            thread, created = ChatThread.objects.get_or_create(
                user=user,
                product_id=product_id,
                variant_id=variant_id
            )

        # ✅ Save message
        msg = ChatMessage.objects.create(
            thread=thread,
            sender_type="user",
            message=message
        )

        return JsonResponse({
            "success": True,
            "thread_id": thread.id,
            "message": msg.message
        })

def get_messages(request, product_id):
    user = request.user

    try:
        thread = ChatThread.objects.get(user=user,product_id=product_id)
    except ChatThread.DoesNotExist:
        return JsonResponse({"messages": []})

    messages = thread.messages.all().order_by("created_at")

    data = [
        {
            "sender": m.sender_type,
            "message": m.message,
            "time": m.created_at.strftime("%H:%M")
        }
        for m in messages
    ]

    return JsonResponse({
        "thread_id": thread.id,
        "messages": data
    })

def get_cat(request):
    categories = Category.objects.annotate(
        product_count=Count(
            'products',
            filter=Q(products__status='active', products__visible_individually=True)
        )
    ).filter(product_count__gt=0)

    data = []
    for c in categories:
        data.append({
            "id": c.id,
            "name": c.name,
            "product_count": c.product_count
        })

    return JsonResponse({"categories": data})

from .models import WishToBuy
@login_required
def wish_to_buy(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            product_id = data.get("product_id")
            variant_id = data.get("variant_id")

            if not product_id:
                return JsonResponse({
                    "status": "error",
                    "message": "Product ID missing"
                }, status=400)

            product = Product.objects.get(id=product_id)
            variant = ProductVariant.objects.filter(id=variant_id).first()

            obj, created = WishToBuy.objects.get_or_create(
                user=request.user,
                product=product,
                variant=variant
            )

            return JsonResponse({
                "status": "success",
                "created": created,
                "message": "Saved Successfully" if created else "Already requested"
            })

        except Product.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "Product not found"
            }, status=404)

        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            }, status=500)