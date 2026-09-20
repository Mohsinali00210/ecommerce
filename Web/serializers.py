from rest_framework import serializers
from .models import Cart, CartItem
from accounts.models import Address
from django.db import transaction
from django.utils import timezone
from .models import OrderRequest,Order, OrderItem
from products.models import Product, ProductVariant,Promotion
from django.core.exceptions import ValidationError
from decimal import Decimal

class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(),source="product")
    variant_id = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all(),source="variant",allow_null=True,required=False)

    class Meta:
        model = CartItem
        fields = ("id","product_id","variant_id","quantity","price",)
class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True)

    class Meta:
        model = Cart
        fields = ("id","user","session_key","items",)
        read_only_fields = ("user", "session_key")


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "address_type",
            "full_name",
            "phone",
            "street_address",
            "city",
            "state",
            "country",
            "postal_code",
        ]

class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)

class CheckoutSerializer(serializers.Serializer):
    billing_address = AddressSerializer()
    shipping_address = AddressSerializer()
    items = OrderItemCreateSerializer(many=True)

    payment_method = serializers.ChoiceField(
        choices=Order.PAYMENT_METHODS,
        default="cod"
    )
    shipping_charges = serializers.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        user = self.context["request"].user

        billing_data = validated_data.pop("billing_address")
        shipping_data = validated_data.pop("shipping_address")
        items_data = validated_data.pop("items")

        with transaction.atomic():
            # Save addresses
            billing_address = Address.objects.create(
                user=user, address_type="billing", **billing_data
            )
            shipping_address = Address.objects.create(
                user=user, address_type="shipping", **shipping_data
            )

            # Create order
            order = Order.objects.create(
                user=user,
                billing_address=billing_address,
                shipping_address=shipping_address,
                payment_method=validated_data.get("payment_method", "cod"),
                shipping_charges=validated_data.get("shipping_charges", 0),
                notes=validated_data.get("notes", ""),
                status="pending",
            )

            total_amount = 0

            for item in items_data:
                product = Product.objects.get(id=item["product_id"])
                variant = None

                if item.get("variant_id"):
                    variant = ProductVariant.objects.get(id=item["variant_id"])

                # Apply promotion if exists
                promo = product.promotions.filter(
                    end_date__gte=timezone.now()
                ).first()

                price = (
                    promo.get_discounted_price(product.price)
                    if promo else product.price
                )

                order_item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    variant=variant,
                    quantity=item["quantity"],
                    price=price,
                )

                total_amount += order_item.total

            order.total_amount = total_amount + order.shipping_charges
            order.save()

        return order




class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "address_type",
            "full_name",
            "phone",
            "street_address",
            "city",
            "state",
            "country",
            "postal_code",
            "is_default",
        ]

    def validate_phone(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits.")
        if len(value) < 10:
            raise serializers.ValidationError("Phone number is too short.")
        return value

    def validate(self, data):
        required_fields = [
            "full_name",
            "phone",
            "street_address",
            "city",
            "postal_code",
        ]
        for field in required_fields:
            if not data.get(field):
                raise serializers.ValidationError({field: "This field is required."})
        return data

from django.db.models import Prefetch, Q
from types import SimpleNamespace
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")
 
# Shipping in the cart never exceeds this amount (RS).
MAX_SHIPPING_CHARGE = Decimal("450.00")
# ---------------------------------------------------------------------------
# 1) Small change to your existing helper: let it prefetch from a Product
#    queryset as well as a CartItem queryset. Existing callers are unaffected.
# ---------------------------------------------------------------------------
def promo_min_qty(promo):
    """
    Minimum quantity the customer must buy for the promotion to apply.
    Read from Promotion.compare_at  (0 or 1 = applies at any quantity).
    """
    return int(promo.compare_at or 0) if promo else 0

def cap_shipping(raw_total):
    """Cart shipping = sum of the lines, but never more than MAX_SHIPPING_CHARGE."""
    return min(Decimal(raw_total), MAX_SHIPPING_CHARGE)
def summarize_lines(lines):
    """Totals for a list of price_cart_item() results."""
    subtotal = sum((l["line_original"] for l in lines), ZERO)
    discount = sum((l["line_saved"] for l in lines), ZERO)
    shipping_raw = sum((l["shipping"] for l in lines), ZERO)
    shipping_total = cap_shipping(shipping_raw)
 
    return {
        "subtotal": subtotal,                         # at list prices, before discounts
        "discount": discount,                         # promotion savings
        "shipping_raw": shipping_raw,                 # before the cap
        "shipping_total": shipping_total,             # capped
        "shipping_capped": shipping_raw > MAX_SHIPPING_CHARGE,
        "final_total": subtotal - discount + shipping_total,
    }
 
def promo_for_qty(promo, qty):
    """Return the promotion only if `qty` reaches its minimum quantity, else None."""
    if promo and int(qty) >= promo_min_qty(promo):
        return promo
    return None
def item_shipping(product):
    if product.free_shipping:
        return ZERO
    return (product.shipping_charges or ZERO) + (product.additional_shipping_charges or ZERO)
 
def build_pricing(price, promo):
    """
    Single source of truth for every price shown on the page
    (product, each variant, each related product).

    Returns:
      price        original / list price
      final        price after the promotion (== price when no discount)
      was          original price to strike through, or None when no discount
      off          amount saved
      percent_off  0 when no discount. For a percentage promotion this is
                   exactly promo.discount_value; for a fixed promotion it is
                   the computed, rounded percentage.
    """
    price = Decimal(price)
    final = price
    percent_off = Decimal("0")

    if promo and promo.discount_value:
        if promo.discount_type == "percentage":
            final = price - (price * promo.discount_value / Decimal("100"))
            percent_off = promo.discount_value
        elif promo.discount_type == "fixed":
            # discount_value = flat amount off. (The old code returned
            # promo.discounted_price, which is one number for the whole
            # promotion and can't work when variants have different prices.)
            final = price - promo.discount_value

    final = max(final, ZERO).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    has_discount = final < price

    if not has_discount:
        percent_off = Decimal("0")
    elif not percent_off and price > 0:
        percent_off = ((price - final) / price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    return {
        "price": price,
        "final": final,
        "was": price if has_discount else None,
        "off": (price - final) if has_discount else ZERO,
        "percent_off": percent_off,
    }
def price_cart_item(item, qty):
    product = item.product
    variant = item.variant
 
    # Real price = the variant's price (falls back to the product price)
    unit = variant.price if variant else product.price
 
    active = getattr(product, "active_promos", None)
    if active is None:
        promo = get_active_promotion(product, timezone.now())
    else:
        promo = active[0] if active else None
 
    full = build_pricing(unit, promo)                          # promotion at full effect
    applied = build_pricing(unit, promo_for_qty(promo, qty))   # what applies at THIS quantity
 
    return {
        "promo": promo,
        "full": full,
        "applied": applied,
        "qty": qty,
        "line_original": unit * qty,               # list price x qty
        "line_saved": applied["off"] * qty,        # promotion saving
        "line_final": applied["final"] * qty,      # what the customer pays for the goods
        "shipping": item_shipping(product),        # 0 when the product ships free
    }
def active_promos_prefetch(now=None, lookup="product__promotions"):
    """
    CartItem queryset:  .prefetch_related(active_promos_prefetch())
    Product queryset:   .prefetch_related(active_promos_prefetch(lookup="promotions"))
 
    Puts the running promotions (newest first) into `product.active_promos`.
    """
    now = now or timezone.now()
    return Prefetch(  # noqa: F821  (django.db.models.Prefetch, already imported in your module)
        lookup,
        queryset=Promotion.objects.filter(  # noqa: F821
            start_date__lte=now, end_date__gte=now
        ).order_by("-start_date"),
        to_attr="active_promos",
    )
 
 
# ---------------------------------------------------------------------------
# 2) Serializer
# ---------------------------------------------------------------------------
class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
 
    checkout_items = serializers.ListField(
        child=serializers.DictField(),
        required=False,
    )
 
    def validate_address_id(self, value):
        user = self.context["request"].user
 
        if not Address.objects.filter(id=value, user=user).exists():
            raise serializers.ValidationError("Invalid address.")
 
        return value
 
    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
 
        # -------------------------------------------------
        # CHECKOUT ITEMS (session only - the client never sends prices)
        # -------------------------------------------------
        checkout_items = request.session.get("checkout_items", [])
 
        if not checkout_items:
            raise serializers.ValidationError("No checkout items found.")
 
        address = Address.objects.get(id=validated_data["address_id"], user=user)
 
        # -------------------------------------------------
        # PRODUCT / VARIANT IDS
        # -------------------------------------------------
        product_ids = []
        variant_ids = []
 
        for item in checkout_items:
            try:
                product_ids.append(int(item["product_id"]))
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("Invalid product information.")
 
            if item.get("variant_id"):
                try:
                    variant_ids.append(int(item["variant_id"]))
                except (TypeError, ValueError):
                    raise serializers.ValidationError("Invalid variant information.")
 
        # -------------------------------------------------
        # LOAD PRODUCTS (with running promotions prefetched in one query)
        # -------------------------------------------------
        now = timezone.now()
 
        products = (
            Product.objects
            .filter(id__in=product_ids, status="active")
            .prefetch_related(active_promos_prefetch(now, lookup="promotions"))
        )
        product_map = {p.id: p for p in products}
 
        variant_map = {
            v.id: v for v in ProductVariant.objects.filter(id__in=variant_ids)
        }
 
        # -------------------------------------------------
        # VALIDATE + PRICE EVERY LINE (nothing written to the DB yet)
        # -------------------------------------------------
        lines = []  # (product, variant, qty, priced)
 
        for item in checkout_items:
            product_id = int(item["product_id"])
            product = product_map.get(product_id)
 
            if not product:
                raise serializers.ValidationError(
                    f"Product with ID {product_id} is no longer available."
                )
 
            # ---- variant
            variant = None
            if item.get("variant_id"):
                variant = variant_map.get(int(item["variant_id"]))
 
                if not variant:
                    raise serializers.ValidationError(
                        f"Selected variant for {product.name} is no longer available."
                    )
 
                if variant.product_id != product.id:
                    raise serializers.ValidationError("Invalid product variant.")
 
            # ---- quantity
            try:
                qty = int(item.get("quantity", 1))
            except (TypeError, ValueError):
                raise serializers.ValidationError(f"Invalid quantity for {product.name}.")
 
            if qty <= 0:
                raise serializers.ValidationError(f"Invalid quantity for {product.name}.")
 
            # ---- stock
            if variant:
                if hasattr(variant, "is_active") and not variant.is_active:
                    raise serializers.ValidationError(
                        f"Variant of {product.name} is inactive."
                    )
                available = variant.stock_quantity
            else:
                available = product.stock_quantity
 
            if available < qty:
                raise serializers.ValidationError(
                    f"Not enough stock available for {product.name}."
                )
 
            # ---- price: same function the cart uses
            priced = price_cart_item(SimpleNamespace(product=product, variant=variant), qty)
            lines.append((product, variant, qty, priced))
 
        if not lines:
            raise serializers.ValidationError("No valid products found for checkout.")
 
        # -------------------------------------------------
        # TOTALS: same function the cart uses (shipping is summed, then capped)
        # -------------------------------------------------
        totals = summarize_lines([priced for *_, priced in lines])
 
        goods_total = totals["subtotal"] - totals["discount"]  # after promotions
 
        # -------------------------------------------------
        # CREATE ORDER
        # -------------------------------------------------
        order = Order.objects.create(
            user=user,
            shipping_address=address,
            billing_address=address,
            payment_method="COD",
            status="pending",
            shipping_charges=totals["shipping_total"],
            subtotal=goods_total,
            total_amount=totals["final_total"],
            # If your Order model has a discount column, store it too:
            # discount_amount=totals["discount"],
        )
 
        # -------------------------------------------------
        # CREATE ORDER ITEMS (unit price = price after promotion at this qty)
        # -------------------------------------------------
        for product, variant, qty, priced in lines:
            OrderItem.objects.create(
                order=order,
                product=product,
                variant=variant,
                quantity=qty,
                price=priced["applied"]["final"],
            )
        purchased = Q()
        for product, variant, qty, priced in lines:
            purchased |= Q(product=product, variant=variant)  # variant=None matches NULL
        CartItem.objects.filter(cart__user=user).filter(purchased).delete()


        # Let the view read the breakdown without recalculating.
        self.pricing = totals
 
        # -------------------------------------------------
        # CLEAR CHECKOUT SESSION
        # -------------------------------------------------
        request.session.pop("checkout_items", None)
        request.session.modified = True
 
        return order


from rest_framework import serializers
from .models import Order, OrderItem

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "product_image", "quantity", "price"]

    def get_product_image(self, obj):
        image = obj.product.images.first()
        return image.image.url if image else None


# class OrderRequestSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = OrderRequest
#         fields = ["request_type", "comment", "status", "created_at"]


# class OrderDetailSerializer(serializers.ModelSerializer):
#     items = OrderItemSerializer(many=True)
#     # requests = OrderRequestSerializer(many=True)

#     class Meta:
#         model = Order
#         fields = [
#             "id",
#             "order_number",
#             "status",
#             "created_at",
#             "subtotal",
#             "discount",
#             "total_amount",
#             "shipping_method",
#             "tracking_number",
#             "shipping_address",
#             "estimated_delivery",
#             "customer_name",
#             "customer_email",
#             "customer_phone",
#             "items",
#         ]
from .models import OrderRequest, OrderItem

class OrderRequestSerializer(serializers.ModelSerializer):
    items = serializers.StringRelatedField(many=True)  # or use PrimaryKeyRelatedField if needed

    class Meta:
        model = OrderRequest
        fields = [
            "id",
            "request_type",
            "items",
            "reason",
            "preferred_action",
            "status",
            "created_at",
        ]
class OrderDetailSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    shipping_address_text = serializers.SerializerMethodField()
    billing_address_text = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, read_only=True)
    requests = OrderRequestSerializer(many=True, read_only=True)  # NEW

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "placed_at",
            "total_amount",
            "shipping_charges",
            "payment_method",
            "payment_status",
            "status",
            "transaction_id",
            "notes",
            "customer_name",
            "customer_email",
            "customer_phone",
            "shipping_address_text",
            "billing_address_text",
            "items",
            "qr_code",
            "requests",
        ]

    def get_customer_name(self, obj):
        if obj.shipping_address:
            return obj.shipping_address.full_name
        if obj.user:
            return getattr(obj.user, "email", "Guest")
        return "Guest"

    def get_customer_email(self, obj):
        return getattr(obj.user, "email", "")

    def get_customer_phone(self, obj):
        if obj.shipping_address:
            return obj.shipping_address.phone
        return ""

    def get_shipping_address_text(self, obj):
        if not obj.shipping_address:
            return ""
        addr = obj.shipping_address
        return f"{addr.street_address}, {addr.city}, {addr.state}, {addr.country}, {addr.postal_code}"

    def get_billing_address_text(self, obj):
        if not obj.billing_address:
            return ""
        addr = obj.billing_address
        return f"{addr.street_address}, {addr.city}, {addr.state}, {addr.country}, {addr.postal_code}"
        
class OrderRequestSerializer(serializers.ModelSerializer):
    items = serializers.PrimaryKeyRelatedField(
        queryset=OrderItem.objects.all(),
        many=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = OrderRequest
        fields = [
            "id",
            "order",
            "user",
            "request_type",
            "items",
            "reason",
            "preferred_action",
            "attachment",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "user", "status", "created_at"]

    def create(self, validated_data):
        # Pop items if provided; default to empty list
        items_data = validated_data.pop("items", [])

        # Set the user from context (request.user)
        user = self.context["request"].user
        validated_data["user"] = user

        # Create the order request
        order_request = OrderRequest.objects.create(**validated_data)

        # Handle items
        if not items_data:
            # If no items selected, attach all items of the order
            order_request.items.set(validated_data["order"].items.all())
        else:
            # Only attach valid items
            order_request.items.set(items_data)

        return order_request


from rest_framework import serializers
from .models import OrderItem
from products.models import ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductReview
        fields = ["id", "product", "rating", "comment"]

    def validate(self, attrs):
        user = self.context["request"].user
        product = attrs["product"]
        # Check if user bought this product and order shipped
       
        has_bought = OrderItem.objects.filter(
            order__user=user,
            order__status="delivered",
            product=product
        ).exists()

        if not has_bought:
            raise serializers.ValidationError(
                "You can review only purchased & shipped products."
            )

        # Prevent duplicate review
        if ProductReview.objects.filter(user=user, product=product).exists():
            raise serializers.ValidationError(
                "You already reviewed this product."
            )

        return attrs

# serializers.py

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification
        fields = [
            'id',
            'title',
            'message',
            'notification_type',
            # 'is_read',
            'created_at'
        ]