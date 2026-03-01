from django.shortcuts import render, get_object_or_404,redirect
from products.models import Product, Promotion,ProductReview,ProductVariant
from django.utils import timezone
import json
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import Cart, CartItem,SupportTicket,OrderItem
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticatedOrReadOnly,IsAuthenticated

from rest_framework import status
from .serializers import CheckoutSerializer,AddressSerializer,PlaceOrderSerializer

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import Address



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
    context = { 'Products': Products, "freeshipping":freeshipping,"promotions":promotions }
    return render(request, "Web/index.html",context)

def ProductDetails(request, id):
    product = get_object_or_404(
        Product.objects.prefetch_related("images", "variants", "variant_options"),
        id=id
    )

    now = timezone.now()

    # Product promotions
    promotions = Promotion.objects.filter(products=product, start_date__lte=now, end_date__gte=now)
    if promotions.exists():
        promo = promotions.first()
        product.final_price = promo.get_discounted_price(product.price)
        promo.discounted_price = promo.get_discounted_price(product.price)
    else:
        product.final_price = product.price

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
        else:
            prd.final_price = prd.price
            prd.discounted_price = prd.price
    Reviews = product.reviews.filter(
        is_active=True,
        is_deleted=False,
        product=product
    ).select_related('user').order_by('-created_at')
    
    variants = product.variants.select_related("image")
    variants_json = json.dumps(
        list(variants.values("name", "price","product","id")),
        cls=DjangoJSONEncoder
    )
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
            

    context = {
        "cart": cart
    }
    return render(request, "Web/cart.html", context)


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


def CheckoutPage(request):

    defaultaddresses = Address.objects.filter(user=request.user,is_default=True)
    addresses = Address.objects.filter(user=request.user)
    checkout_items = request.session.get("checkout_items", [])

    updated_icheckout_items = request.session.get("checkout_items", [])
    updated_items = []

    if checkout_items:
        product_ids = [item["product_id"] for item in checkout_items]
        variant_ids = [item.get("variant_id") for item in checkout_items if item.get("variant_id")]

        products = (Product.objects.filter(id__in=product_ids).prefetch_related("images", "promotions"))
        variants = (ProductVariant.objects.filter(id__in=variant_ids).select_related("product"))

        product_map = {p.id: p for p in products}
        variant_map = {v.id: v for v in variants}

        now = timezone.now()

        for item in checkout_items:
            product_id = int(item["product_id"])          # 🔥 FIX
            variant_id = int(item["variant_id"]) if item.get("variant_id") else None

            product = product_map.get(product_id)
            variant = variant_map.get(variant_id)
            

            if not product:
                continue

            base_price = variant.price if variant else product.price

            promo = product.promotions.filter(
                start_date__lte=now,
                end_date__gte=now
            ).first()

            final_price = promo.get_discounted_price(base_price) if promo else base_price

            updated_items.append({
                "product_id": product.id,
                "variant_id": variant.id if variant else None,
                "name": product.name,
                "variant_name": variant.name if variant else "",
                "qty": item.get("qty", 1),
                "price": base_price,
                "final_price": final_price,
                "discounted_price": final_price,
                "discount_type": promo.discount_type if promo else None,
                "image": (
                    variant.image.image.url
                    if variant and variant.image
                    else product.images.first().image.url
                    if product.images.exists()
                    else ""
                ),
            })
        print(updated_items)
        # persist clean data back to session
        # request.session["checkout_items"] = updated_items
        # request.session.modified = True

    
    return render(
        request,
        "Web/checkout.html",
        {"items": updated_items,"defaultaddresses":defaultaddresses,"addresses":addresses}
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
            return Response(
                {
                    "message": "Order placed successfully",
                    "order_id": order.id,
                    "total": order.total,
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

        serializer = OrderRequestSerializer(data=data,context={'request': request} )
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