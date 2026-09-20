
from django.shortcuts import render,get_object_or_404
from django.utils import timezone
from django.db.models import Sum
from django.core.exceptions import ValidationError
from products.models import Product, Category,Promotion,ProductQuestion,ProductReview  # adjust import path/names if different

# All of Cart, CartItem, WishToBuy, Notification, NotificationRecipient came from the
# single models.py you sent — I'm assuming that app is called "orders". Change this
# import if your app label is different (e.g. "cart", "store", etc).
from Web.models import Cart, CartItem, WishToBuy,SupportTicket, Notification,OrderItem, NotificationRecipient
from datetime import timedelta
import json
from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from products.models import Product, Promotion,  Wishlist 

PRODUCTS_PER_ROW_SECTION = 8

def _get_or_create_cart(request):
    """Return the active cart for the logged-in user or anonymous session."""

    if request.user.is_authenticated:

        cart = (
            Cart.objects
            .filter(
                user=request.user,
                is_active=True
            )
            .order_by("-id")
            .first()
        )

        if cart:
            return cart

        return Cart.objects.create(
            user=request.user,
            is_active=True
        )

    # Anonymous user
    if not request.session.session_key:
        request.session.create()

    session_key = request.session.session_key

    cart = (
        Cart.objects
        .filter(
            session_key=session_key,
            user__isnull=True,
            is_active=True
        )
        .order_by("-id")
        .first()
    )

    if cart:
        return cart

    return Cart.objects.create(
        session_key=session_key,
        user=None,
        is_active=True
    )

def _cart_count(request):
    cart = _get_or_create_cart(request)
    total = CartItem.objects.filter(cart=cart, is_deleted=False,
                    product__status="active").aggregate(
        qty=Sum("quantity")
    )["qty"]
    return total or 0


def _wishlist_count(request):
    if not request.user.is_authenticated:
        return 0
    return WishToBuy.objects.filter(user=request.user, is_deleted=False).count()


def _unread_notification_count(request):
    if not request.user.is_authenticated:
        return 0
    return NotificationRecipient.objects.filter(
        user=request.user, is_read=False
    ).count()

def header_counts(request):
    """Single endpoint backing the navbar badges (cart, wishlist, notifications)."""
    return JsonResponse({
        "cart_count": _cart_count(request),
        "wishlist_count": _wishlist_count(request),
        "notification_count": _unread_notification_count(request),
    })
from django.db.models import Exists, OuterRef
from products.models import Wishlist as WishlistModel
from django.utils import timezone
# views.py
def product_quick_view(request, product_id):
    product = get_object_or_404(
        Product.objects.prefetch_related("images", "variants", "variant_options"),
        id=product_id,
    )
    now = timezone.now()

    promo = Promotion.objects.filter(products=product, start_date__lte=now, end_date__gte=now).first()
    if promo:
        product.final_price = promo.get_discounted_price(product.price)
    else:
        product.final_price = product.price

    variants = product.variants.select_related("image")
    variant_data = []
    for v in variants:
        vp = Promotion.objects.filter(products=product, start_date__lte=now, end_date__gte=now).first()
        final_price = vp.get_discounted_price(v.price) if vp else v.price
        off_price = vp.get_off_price(v.price) if vp else 0
        variant_data.append({
            "id": v.id, "sku": v.sku, "name": v.name,
            "price": float(v.price), "final_price": float(final_price),
            "off_price": float(off_price), "stock": v.stock_quantity,
        })

    return render(request, "home/partials/product_quick_view.html", {
        "product": product,
        "images": product.images.all(),
        "options": product.variant_options.all(),
        "variants_json": json.dumps(variant_data, cls=DjangoJSONEncoder),
    })

def home(request):

    current_date = timezone.now()

    # =========================================================
    # WISHLIST CHECK
    # =========================================================

    if request.user.is_authenticated:

        wishlist_exists = WishlistModel.objects.filter(
            user=request.user,
            product=OuterRef("pk")
        )

    else:

        # Empty queryset for guest users
        wishlist_exists = WishlistModel.objects.none()


    # =========================================================
    # FEATURED PRODUCTS
    # =========================================================

    featured_products = (
        Product.objects
        .filter(status="active")
        .annotate(
            is_wishlisted=Exists(wishlist_exists)
        )
        .prefetch_related(
            "images",
            "variants",
            "category",
            "promotions"
        )
    )


    # =========================================================
    # ACTIVE PROMOTIONS
    # =========================================================

    promotions = (
        Promotion.objects
        .filter(
            start_date__lte=current_date,
            end_date__gte=current_date,
            is_active=True
        )
        .prefetch_related("products")
    )


    # =========================================================
    # APPLY PROMOTION INFORMATION
    # =========================================================

    for product in featured_products:

        product.final_price = product.price
        product.has_discount = False
        product.discount_percent = 0
        product.promotion = None

        promo = (
            product.promotions
            .filter(
                start_date__lte=current_date,
                end_date__gte=current_date,
                is_active=True
            )
            .first()
        )

        if promo:

            product.promotion = promo

            product.final_price = promo.get_discounted_price(
                product.price
            )

            product.has_discount = (
                product.final_price != product.price
            )

            if promo.discount_type == "percentage":

                product.discount_percent = int(
                    promo.discount_value
                )


    # =========================================================
    # ACTIVE PRODUCTS
    # =========================================================

    active_products = (
        Product.objects
        .filter(is_active=True)
        .annotate(
            is_wishlisted=Exists(wishlist_exists)
        )
    )


    # =========================================================
    # BEST SELLERS
    # =========================================================

    best_sellers = (
        active_products
        .order_by("-sold")
        [:PRODUCTS_PER_ROW_SECTION]
    )


    # =========================================================
    # NEW ARRIVALS
    # =========================================================

    new_arrivals = (
        active_products
        .order_by("-created_at")
        [:PRODUCTS_PER_ROW_SECTION]
    )


    # =========================================================
    # CATEGORIES
    # =========================================================

    categories = Category.objects.filter(
        parent__isnull=True
    )


    # =========================================================
    # CONTEXT
    # =========================================================

    context = {

        "featured_products": featured_products,

        "best_sellers": best_sellers,

        "new_arrivals": new_arrivals,

        "categories": categories,

        "cart_count": _cart_count(request),

        "wishlist_count": _wishlist_count(request),

        "notification_count": _unread_notification_count(request),

        "recent_notifications": (
            NotificationRecipient.objects
            .filter(user=request.user)
            .select_related("notification")
            .order_by("-notification__created_at")[:3]
            if request.user.is_authenticated
            else []
        ),

        "sale_ends_at": (
            timezone.now() +
            timezone.timedelta(hours=6)
        ),
    }


    # =========================================================
    # RETURN RESPONSE
    # =========================================================

    return render(
        request,
        "home/index.html",
        context
    )
# views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json

@login_required
@require_POST
def submit_review(request):
    try:
        data = json.loads(request.body)
        product_id = data.get("product_id")
        rating = int(data.get("rating", 0))
        comment = (data.get("comment") or "").strip()
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"success": False, "message": "Invalid request."}, status=400)

    if rating < 1 or rating > 5:
        return JsonResponse({"success": False, "message": "Rating must be between 1 and 5."}, status=400)
    if not comment:
        return JsonResponse({"success": False, "message": "Please write a review comment."}, status=400)

    product = get_object_or_404(Product, id=product_id)

    # Must have received a delivered order containing this product — same rule
    # as `can_review` in the PDP view, so it can't be bypassed via direct POST.
    has_purchased = OrderItem.objects.filter(
        order__user=request.user,
        order__status="delivered",
        product=product,
    ).exists()
    if not has_purchased:
        return JsonResponse(
            {"success": False, "message": "You can review this item after it's delivered to you."},
            status=403,
        )

    if ProductReview.objects.filter(product=product, user=request.user).exists():
        return JsonResponse(
            {"success": False, "message": "You've already reviewed this product."},
            status=409,
        )

    ProductReview.objects.create(
        product=product,
        user=request.user,
        rating=rating,
        comment=comment,
    )

    return JsonResponse({"success": True, "message": "Review submitted — thank you!"})
# # views.py
@login_required
@require_POST
def submit_question(request):
    try:
        data = json.loads(request.body)
        product_id = data.get("product_id")
        print("product_id ",product_id)
        question = (data.get("question") or "").strip()
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"success": False, "message": "Invalid request."}, status=400)

    if len(question) < 5:
        return JsonResponse({"success": False, "message": "Please enter a more complete question."}, status=400)
    if len(question) > 1000:
        return JsonResponse({"success": False, "message": "Question is too long."}, status=400)

    product = get_object_or_404(Product, id=product_id)

    ProductQuestion.objects.create(
        product=product,
        user=request.user,
        question=question,
    )

    return JsonResponse({
        "success": True,
        "message": "Question submitted — we'll answer it soon.",
    })
# def ProductDetails(request, slug, sku=None):
#     """
#     URLs:
#       /product/<slug>/           -> plain product page, no variant preselected
#       /product/<slug>/<sku>/     -> product page with that variant preselected
#     """
#     product = get_object_or_404(
#         Product.objects.prefetch_related("images", "variants", "variant_options"),
#         slug=slug,
#     )
 
#     max_handling_days = product.handling_time
#     estimated_date = timezone.now() + timedelta(days=max_handling_days)
#     now = timezone.now()
 
#     # Product promotions
#     promotions = Promotion.objects.filter(products=product, start_date__lte=now, end_date__gte=now)
#     if promotions.exists():
#         promo = promotions.first()
#         product.final_price = promo.get_discounted_price(product.price)
#         promo.discounted_price = promo.get_discounted_price(product.price)
#         promo.off_price = promo.get_off_price(product.price)
#     else:
#         product.final_price = product.price
#         product.off_price = product.old_price - product.final_price
 
#     # Related products
#     related_products = (
#         Product.objects.filter(category__in=product.category.all(), brand=product.brand)
#         .exclude(id=product.id)
#         .prefetch_related("images", "promotions")[:5]
#     )
 
#     for prd in related_products:
#         promo = prd.promotions.filter(start_date__lte=now, end_date__gte=now).first()
#         if promo:
#             prd.final_price = promo.get_discounted_price(prd.price)
#             prd.discounted_price = promo.get_discounted_price(prd.price)
#             prd.off_price = promo.get_off_price(prd.price)
#         else:
#             prd.final_price = prd.price
#             prd.discounted_price = prd.price
#             prd.off_price = prd.old_price - prd.final_price
 
#     questions_qs = product.questions.filter(is_deleted=False).select_related("user", "answered_by")

#     if request.user.is_authenticated:
#         Questions = questions_qs.filter(
#             Q(answer__isnull=False) | Q(user=request.user)
#         ).order_by("-created_at")
#     else:
#         Questions = questions_qs.filter(answer__isnull=False).order_by("-created_at")

#     Reviews = product.reviews.filter(
#         is_active=True,
#         is_deleted=False,
#         product=product,
#     ).select_related("user").order_by("-created_at")
 
#     variants = product.variants.select_related("image")
#     variant_data = []
#     selected_variant = None
 
#     for v in variants:
#         variant_promotions = Promotion.objects.filter(products=product, start_date__lte=now, end_date__gte=now)
 
#         if variant_promotions.exists():
#             promo = variant_promotions.first()
#             final_price = promo.get_discounted_price(v.price)
#             off_price = promo.get_off_price(v.price)
#         else:
#             final_price = v.price
#             off_price = product.old_price - final_price
 
#         entry = {
#             "id": v.id,
#             "sku": v.sku,  # used to build /product/<slug>/<sku>/ links and to preselect on load
#             "name": v.name,
#             "price": float(v.price),
#             "final_price": float(final_price),
#             "off_price": float(off_price),
#             "stock": v.stock_quantity,
#         }
#         variant_data.append(entry)
 
#         if sku and v.sku == sku:
#             selected_variant = entry
 
#     variants_json = json.dumps(variant_data, cls=DjangoJSONEncoder)
 
#     can_review = False

#     if request.user.is_authenticated:
#         can_review = OrderItem.objects.filter(
#             order__user=request.user,
#             order__status="delivered",
#             product=product,
#         ).exists()
 
#     wishlist_ids = []
#     if request.user.is_authenticated:
#         wishlist_ids = WishToBuy.objects.filter(
#             user=request.user,
#         ).values_list("product_id", flat=True)
 
#     context = {
#         "product": product,
#         "promotions": promotions,
#         "images": product.images.all(),
#         "variants": variants,
#         "variants_json": variants_json,
#         "options": product.variant_options.all(),
#         "related_products": related_products,
#         "Reviews": Reviews,
#         "Questions": Questions,
#         "can_review": can_review,
#         "estimated_date": estimated_date,
#         "user_wishlist_ids": wishlist_ids,
#         "show_message_box": True,
#         "selected_variant": selected_variant,  # None if no sku in URL or sku didn't match any variant
#     }
 
#     return render(request, "home/product_details.html", context)

import json
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

# Keep your existing model imports (Product, Promotion, OrderItem, WishToBuy, ...)

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")
 
# Shipping in the cart never exceeds this amount (RS).
MAX_SHIPPING_CHARGE = Decimal("450.00")

def get_active_promotion(product, now):
    """One query per product. Newest running promotion wins."""
    return (
        Promotion.objects
        .filter(products=product, start_date__lte=now, end_date__gte=now)
        .order_by("-start_date")
        .first()
    )
def promo_for_qty(promo, qty):
    """Return the promotion only if `qty` reaches its minimum quantity, else None."""
    if promo and int(qty) >= promo_min_qty(promo):
        return promo
    return None
def item_shipping(product):
    if product.free_shipping:
        return ZERO
    return (product.shipping_charges or ZERO) + (product.additional_shipping_charges or ZERO)
 
 
def cap_shipping(raw_total):
    """Cart shipping = sum of the lines, but never more than MAX_SHIPPING_CHARGE."""
    return min(Decimal(raw_total), MAX_SHIPPING_CHARGE)
def promo_min_qty(promo):
    """
    Minimum quantity the customer must buy for the promotion to apply.
    Read from Promotion.compare_at  (0 or 1 = applies at any quantity).
    """
    return int(promo.compare_at or 0) if promo else 0
 
 
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


def active_promos_prefetch(now=None):
    """
    For querysets of CartItem: prefetches each product's running promotions in ONE query
    into `product.active_promos` (newest first).
 
        CartItem.objects.select_related("product", "variant").prefetch_related(active_promos_prefetch())
    """
    now = now or timezone.now()
    return Prefetch(
        "product__promotions",
        queryset=Promotion.objects.filter(start_date__lte=now, end_date__gte=now).order_by("-start_date"),
        to_attr="active_promos",
    )
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
def ProductDetails(request, slug, sku=None):
    """
    URLs:
      /product/<slug>/           -> plain product page, no variant preselected
      /product/<slug>/<sku>/     -> product page with that variant preselected
    """
    now = timezone.now()

    # Active promotions, prefetched once for the related-products loop below
    active_promos_qs = (
        Promotion.objects
        .filter(start_date__lte=now, end_date__gte=now)
        .order_by("-start_date")
    )

    product = get_object_or_404(
        Product.objects.prefetch_related("images", "variants", "variant_options"),
        slug=slug,
    )

    estimated_date = now + timedelta(days=product.handling_time)

    # ---- Product-level pricing ----
    promo = get_active_promotion(product, now)
    pricing = build_pricing(product.price, promo)

    # ---- Related products (no per-item promotion queries) ----
    related_products = list(
        Product.objects
        .filter(category__in=product.category.all(), brand=product.brand)
        .exclude(id=product.id)
        .distinct()
        .prefetch_related(
            "images",
            Prefetch("promotions", queryset=active_promos_qs, to_attr="active_promos"),
        )[:5]
    )
    for prd in related_products:
        prd_promo = prd.active_promos[0] if prd.active_promos else None
        prd.pricing = build_pricing(prd.price, prd_promo)

    # ---- Q&A ----
    questions_qs = product.questions.filter(is_deleted=False).select_related("user", "answered_by")
    if request.user.is_authenticated:
        Questions = questions_qs.filter(
            Q(answer__isnull=False) | Q(user=request.user)
        ).order_by("-created_at")
    else:
        Questions = questions_qs.filter(answer__isnull=False).order_by("-created_at")

    Reviews = product.reviews.filter(
        is_active=True,
        is_deleted=False,
    ).select_related("user").order_by("-created_at")

    # ---- Variants: real price + discounted price per variant ----
    variants = product.variants.select_related("image")
    variant_data = []
    selected_variant = None

    for v in variants:
        vp = build_pricing(v.price, promo)  # same promo, computed once above
        entry = {
            "id": v.id,
            "sku": v.sku,
            "name": v.name,
            "price": float(vp["price"]),
            "final_price": float(vp["final"]),
            "was_price": float(vp["was"]) if vp["was"] else None,
            "percent_off": float(vp["percent_off"]),
            "stock": v.stock_quantity,
        }
        variant_data.append(entry)

        if sku and v.sku == sku:
            selected_variant = entry

    variants_json = json.dumps(variant_data, cls=DjangoJSONEncoder)

    can_review = False
    if request.user.is_authenticated:
        can_review = OrderItem.objects.filter(
            order__user=request.user,
            order__status="delivered",
            product=product,
        ).exists()

    wishlist_ids = []
    if request.user.is_authenticated:
        wishlist_ids = WishToBuy.objects.filter(
            user=request.user,
        ).values_list("product_id", flat=True)
    
    context = {
        "product": product,
        "promo": promo,
        "pricing": pricing,  # template uses pricing.final / .was / .percent_off
        "images": product.images.all(),
        "variants": variants,
        
        "variants_json": variants_json,
        # "options": product.variant_options.all(),
        "options": product.variant_options.order_by("option_name", "id"),
        "related_products": related_products,
        "Reviews": Reviews,
        "Questions": Questions,
        "can_review": can_review,
        "estimated_date": estimated_date,
        "user_wishlist_ids": wishlist_ids,
        "show_message_box": True,
        "selected_variant": selected_variant,
    }

    return render(request, "home/product_details.html", context)

from accounts.models import Address
from decimal import Decimal

def _checkout_quantity(session_item, item):
    """
    Quantity chosen on the cart page, sanitised: a whole number >= 1 and never above the stock.
    (The browser sent it, so never trust it as is.)
    """
    try:
        qty = int(session_item.get("quantity", item.quantity))
    except (TypeError, ValueError):
        qty = item.quantity
 
    stock = item.variant.stock_quantity if item.variant else item.product.stock_quantity
    qty = max(1, qty)
    return min(qty, stock) if stock > 0 else qty
 
 
@login_required   # the view reads request.user.* straight away, so anonymous users crashed anyway
def CheckoutPage(request):
    now = timezone.now()
 
    defaultaddresses = Address.objects.filter(user=request.user, is_default=True)
    addresses = Address.objects.filter(user=request.user)
 
    # {cart_item_id: {"quantity": ..}} for the items ticked on the cart page
    checkout_items = request.session.get("checkout_items", [])
    checkout_lookup = {str(i["cart_item_id"]): i for i in checkout_items}
 
    cart = (
        Cart.objects
        .filter(user=request.user, is_active=True)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.filter(
                    is_active=True,
                    is_deleted=False,
                    product__status="active",
                )
                .select_related("product", "variant")
                .prefetch_related("product__images", active_promos_prefetch(now)),
            )
        )
        .first()
    )
 
    filtered_items = []
    lines = []
    handling_days = []
 
    if cart:
        for item in cart.items.all():
 
            # skip items that weren't selected for checkout
            session_item = checkout_lookup.get(str(item.id))
            if session_item is None:
                continue
 
            qty = _checkout_quantity(session_item, item)
            item.quantity = qty
 
            line = price_cart_item(item, qty)
            lines.append(line)
 
            # what the template shows for this line
            item.unit_price = line["full"]["price"]        # variant price
            item.unit_final = line["applied"]["final"]     # after the promotion
            item.percent_off = line["applied"]["percent_off"]
            item.line_original = line["line_original"]
            item.line_saved = line["line_saved"]
            item.line_final = line["line_final"]
 
            handling_days.append(item.product.handling_time)
            filtered_items.append(item)
 
    totals = summarize_lines(lines)
 
    estimated_date = now + timedelta(days=max(handling_days) if handling_days else 0)
 
    context = {
        "cart_items": filtered_items,
        "subtotal": totals["subtotal"],               # at list (variant) prices
        "total_off_price": totals["discount"],        # promotion savings
        "shipping_raw": totals["shipping_raw"],
        "shipping_total": totals["shipping_total"],   # capped, free-shipping products add 0
        "shipping_capped": totals["shipping_capped"],
        "max_shipping": MAX_SHIPPING_CHARGE,
        "final_total": totals["final_total"],
        "estimated_date": estimated_date,
    }
 
    return render(
        request,
        "home/checkout.html",
        {
            "items": context,
            "defaultaddresses": defaultaddresses,
            "addresses": addresses,
        },
    )


 
@login_required
def MyCart(request):
    now = timezone.now()
 
    cart = (
        Cart.objects
        .filter(user=request.user, is_active=True)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.filter(
                    is_active=True,
                    is_deleted=False,
                    product__status="active",
                )
                .select_related("product", "variant")
                .prefetch_related("product__images", active_promos_prefetch(now)),
            )
        )
        .first()
    )
 
    items = list(cart.items.all()) if cart else []
 
    lines = []          # price_cart_item() result per item
    browser_lines = {}  # per-item pricing rules for the page's JavaScript
    handling_days = []
 
    for item in items:
        line = price_cart_item(item, item.quantity)
        lines.append(line)
 
        item.unit_price = line["full"]["price"]
        item.unit_final = line["applied"]["final"]
        item.unit_saved = line["applied"]["off"]
        item.percent_off = line["applied"]["percent_off"]
        item.line_saved = line["line_saved"]
 
        product, variant = item.product, item.variant
        handling_days.append(product.handling_time)
 
        browser_lines[str(item.id)] = {
            "price": float(line["full"]["price"]),
            "promo_price": float(line["full"]["final"]) if line["full"]["was"] else None,
            "promo_percent": float(line["full"]["percent_off"]),
            "min_qty": promo_min_qty(line["promo"]),
            "shipping": float(line["shipping"]),   # 0 when the product ships free
            "stock": variant.stock_quantity if variant else product.stock_quantity,
        }
 
    totals = summarize_lines(lines)
 
    estimated_date = now + timedelta(days=max(handling_days) if handling_days else 0)
 
    cart_json = json.dumps(
        {"lines": browser_lines, "max_shipping": float(MAX_SHIPPING_CHARGE)},
        cls=DjangoJSONEncoder,
    )
 
    context = {
        "cart": cart,
        "items": items,
        "subtotal": totals["subtotal"],            # at list price, before discounts
        "total_off_price": totals["discount"],     # "You saved"
        "shipping_raw": totals["shipping_raw"],
        "shipping_total": totals["shipping_total"],  # capped
        "shipping_capped": totals["shipping_capped"],
        "max_shipping": MAX_SHIPPING_CHARGE,
        "final_total": totals["final_total"],
        "estimated_date": estimated_date,
        "cart_json": cart_json,
    }
    return render(request, "home/cart.html", context)
from Web.models import OrderRequest, Order

@login_required
def MyOrders(request):
    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related("items", "items__product", "items__product__images","requests")
        .order_by("-created_at")
    )

    return render(request, "home/orders.html", {
        "orders": orders
    })

@login_required
def OrderDetail(request, order_number):
    order = get_object_or_404(
        Order.objects
        .select_related("user", "shipping_address", "billing_address")
        .prefetch_related(
            "items",
            "items__product",
            "items__product__images",
            "items__variant",
            "requests",
        ),
        order_number=order_number,
        user=request.user,
    )
 
    return render(request, "home/OrderDetail.html", {"order": order})



 
@login_required
def Wishlist(request):
    wishlist_items = (
        WishToBuy.objects
        .filter(user=request.user)
        .select_related("product", "variant")
        .prefetch_related("product__images")
        .order_by("-created_at")
    )
 
    return render(request, "home/wishlist.html", {
        "wishlist_items": wishlist_items,
    })
 
 
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
 
    elif request.method == "DELETE":
        try:
            data = json.loads(request.body)
 
            product_id = data.get("product_id")
            variant_id = data.get("variant_id")
 
            if not product_id:
                return JsonResponse({
                    "status": "error",
                    "message": "Product ID missing"
                }, status=400)
 
            deleted_count, _ = WishToBuy.objects.filter(
                user=request.user,
                product_id=product_id,
                variant_id=variant_id
            ).delete()
 
            if deleted_count:
                return JsonResponse({"status": "success", "message": "Removed from wishlist"})
            return JsonResponse({"status": "error", "message": "Item not found in wishlist"}, status=404)
 
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            }, status=500)
 
    return JsonResponse({
        "status": "error",
        "message": "Method not allowed"
    }, status=405)



from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Q
from django.shortcuts import render

from products.models import Brand, Category, Product, ProductVariantOption, Tag  # adjust import path


PAGE_SIZE = 24

SORT_OPTIONS = {
    "relevance": "Relevance",
    "newest": "Newest",
    "price_asc": "Price: Low to High",
    "price_desc": "Price: High to Low",
    "popularity": "Best Selling",
}

SORT_FIELD_MAP = {
    "newest": "-created_at",
    "price_asc": "price",
    "price_desc": "-price",
    "popularity": "-sold",
}


def search_products(request):
    q = request.GET.get("q", "").strip()
    min_price_raw = request.GET.get("min_price", "").strip()
    max_price_raw = request.GET.get("max_price", "").strip()
    category_ids = [c for c in request.GET.getlist("category") if c]
    brand_ids = [b for b in request.GET.getlist("brand") if b]
    tag_slugs = [t for t in request.GET.getlist("tag") if t]
    sort = request.GET.get("sort", "relevance")
    if sort not in SORT_OPTIONS:
        sort = "relevance"

    min_price = _to_decimal(min_price_raw)
    max_price = _to_decimal(max_price_raw)

    # Dynamic variant-option filters, e.g. ?opt_Color=Red&opt_Color=Blue&opt_Size=XL
    selected_options = {}
    for key in request.GET:
        if key.startswith("opt_"):
            option_name = key[4:]
            values = [v for v in request.GET.getlist(key) if v]
            if values:
                selected_options[option_name] = values

    def apply_common_filters(base_qs):
        """Keyword + price + category + brand + tag filters (everything except
        the dynamic option filters — used both for the final result set and
        as the base for facet counts)."""
        qs = base_qs
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(description__icontains=q)
                | Q(brief_description__icontains=q)
                | Q(sku__icontains=q)
                | Q(meta_title__icontains=q)
                | Q(focus_keywords__icontains=q)
                | Q(tags__name__icontains=q)
                | Q(variants__name__icontains=q)
                | Q(variants__sku__icontains=q)
                | Q(variant_options__option__icontains=q)
                | Q(variant_options__option_name__icontains=q)
            )
        if category_ids:
            qs = qs.filter(category__id__in=category_ids)
        if brand_ids:
            qs = qs.filter(brand__id__in=brand_ids)
        if tag_slugs:
            qs = qs.filter(tags__slug__in=tag_slugs)
        if min_price is not None:
            qs = qs.filter(price__gte=min_price)
        if max_price is not None:
            qs = qs.filter(price__lte=max_price)
        return qs.distinct()

    base_qs = Product.objects.filter(status__in=["active", "featured"])
    facet_base_qs = apply_common_filters(base_qs)

    # ----- Facets are computed from facet_base_qs (pre option-filter), so
    # ----- checking one option value doesn't make the others disappear.
    category_facets = (
        Category.objects.filter(products__in=facet_base_qs)
        .annotate(count=Count("products", filter=Q(products__in=facet_base_qs), distinct=True))
        .filter(count__gt=0)
        .order_by("name")
    )
    brand_facets = (
        Brand.objects.filter(product__in=facet_base_qs)
        .annotate(count=Count("product", filter=Q(product__in=facet_base_qs), distinct=True))
        .filter(count__gt=0)
        .order_by("name")
    )
    tag_facets = (
        Tag.objects.filter(product__in=facet_base_qs)
        .annotate(count=Count("product", filter=Q(product__in=facet_base_qs), distinct=True))
        .filter(count__gt=0)
        .order_by("name")
    )
    option_facets = _build_option_facets(facet_base_qs)
    for option_name, entries in option_facets.items():
        selected_values = set(selected_options.get(option_name, []))
        for entry in entries:
            entry["selected"] = entry["value"] in selected_values

    # ----- Apply the dynamic option filters on top to get the actual result set -----
    qs = facet_base_qs
    for option_name, values in selected_options.items():
        value_q = Q()
        for v in values:
            value_q |= Q(option__icontains=v)
        matching_product_ids = list(
            ProductVariantOption.objects
            .filter(product__in=qs, option_name=option_name)
            .filter(value_q)
            .values_list("product_id", flat=True)
        )
        qs = qs.filter(id__in=matching_product_ids)

    qs = qs.select_related("brand").prefetch_related("images", "tags", "category")

    if sort in SORT_FIELD_MAP:
        qs = qs.order_by(SORT_FIELD_MAP[sort])
    else:
        qs = qs.order_by("-mark_as_new", "-sold", "name")

    price_bounds = Product.objects.filter(status__in=["active", "featured"]).aggregate(
        min_price=Min("price"), max_price=Max("price")
    )

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Preserve every current filter except "page" for pagination links
    querydict = request.GET.copy()
    querydict.pop("page", None)

    return render(request, "home/SearchResults.html", {
        "products": page_obj,
        "query": q,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "min_price": min_price_raw,
        "max_price": max_price_raw,
        "price_bounds": price_bounds,
        "category_facets": category_facets,
        "brand_facets": brand_facets,
        "tag_facets": tag_facets,
        "option_facets": option_facets,
        "selected_category_ids": category_ids,
        "selected_brand_ids": brand_ids,
        "selected_tag_slugs": tag_slugs,
        "selected_options": selected_options,
        "base_querystring": querydict.urlencode(),
        "result_count": paginator.count,
    })


def _to_decimal(raw_value):
    if not raw_value:
        return None
    try:
        return Decimal(raw_value)
    except InvalidOperation:
        return None


def _build_option_facets(qs):
    """
    ProductVariantOption stores its values as a single comma-separated string
    (e.g. option_name="Color", option="Red,Blue,Green") rather than one row
    per value, so faceting has to happen in Python rather than via a plain
    annotate/Count. Fine at catalog sizes where this fits in memory; if the
    catalog grows large, this is the first thing to move into either a
    proper through-table or a search index (Elasticsearch/Postgres GIN).
    """
    rows = (
        ProductVariantOption.objects
        .filter(product__in=qs)
        .values("product_id", "option_name", "option")
    )

    # option_name -> value -> set(product_id)
    tally = defaultdict(lambda: defaultdict(set))
    for row in rows:
        values = [v.strip() for v in (row["option"] or "").split(",") if v.strip()]
        for v in values:
            tally[row["option_name"]][v].add(row["product_id"])

    facets = {}
    for option_name, value_map in tally.items():
        facets[option_name] = sorted(
            [{"value": v, "count": len(pids)} for v, pids in value_map.items()],
            key=lambda item: item["value"].lower()
        )
    return dict(sorted(facets.items()))

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from Web.models import Order, UserWallet, WishToBuy  # adjust import path to match your app


@login_required
def profile(request):
    user = request.user

    wallet, _ = UserWallet.objects.get_or_create(user=user)
    recent_transactions = wallet.transactions.order_by("-created_at")[:5]

    orders_count = (
        Order.objects.filter(user=user)
        .exclude(status__in=["cancelled", "returned", "failed"])
        .count()
    )
    pending_orders_count = Order.objects.filter(
        user=user, status__in=["pending", "processing", "shipped"]
    ).count()
    wishlist_count = WishToBuy.objects.filter(user=user).count()

    return render(request, "home/Profile.html", {
        "wallet": wallet,
        "recent_transactions": recent_transactions,
        "orders_count": orders_count,
        "pending_orders_count": pending_orders_count,
        "wishlist_count": wishlist_count,
    })
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProfileEditForm  # adjust import path to match your app


@login_required
def edit_profile(request):
    user = request.user

    if request.method == "POST":
        form = ProfileEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            email_changed = form.cleaned_data["email"] != (user.email or "")
            updated_user = form.save(commit=False)

            if email_changed:
                # Re-verification required after an email change
                updated_user.is_varified = False

            updated_user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("home:user-profile")
    else:
        form = ProfileEditForm(instance=user)

    return render(request, "home/EditProfile.html", {"form": form})


from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import render

from Web.models import UserWallet, UserWalletTransaction  # adjust import path to match your app

PAGE_SIZE = 15


@login_required
def wallet_view(request):
    wallet, _ = UserWallet.objects.get_or_create(user=request.user)

    txn_type = request.GET.get("type", "")
    valid_types = dict(UserWalletTransaction.TRANSACTION_TYPES)

    transactions = wallet.transactions.select_related("order").order_by("-created_at")
    if txn_type in valid_types:
        transactions = transactions.filter(transaction_type=txn_type)

    paginator = Paginator(transactions, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    totals = wallet.transactions.aggregate(
        total_credit=Sum("amount", filter=Q(transaction_type__in=["credit", "returnorder"])),
        total_debit=Sum("amount", filter=Q(transaction_type="debit")),
    )

    return render(request, "home/Wallet.html", {
        "wallet": wallet,
        "transactions": page_obj,
        "selected_type": txn_type,
        "transaction_types": UserWalletTransaction.TRANSACTION_TYPES,
        "total_credit": totals["total_credit"] or 0,
        "total_debit": totals["total_debit"] or 0,
        "result_count": paginator.count,
    })

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .forms import AddressForm  # adjust import path to match your app
from accounts.models import Address


@login_required
def addresses(request):
    address_list = Address.objects.filter(user=request.user).order_by("-is_default", "address_type", "-id")
    return render(request, "home/Addresses.html", {"addresses": address_list})


@login_required
def address_detail(request, address_id):
    """Returns an address as JSON so the modal can be pre-filled for editing."""
    address = get_object_or_404(Address, id=address_id, user=request.user)
    return JsonResponse({
        "id": address.id,
        "address_type": address.address_type,
        "full_name": address.full_name,
        "phone": address.phone,
        "street_address": address.street_address,
        "city": address.city,
        "state": address.state or "",
        "country": address.country,
        "postal_code": address.postal_code,
        "is_default": address.is_default,
    })


@login_required
def address_save(request):
    """Handles both create (no address_id) and update (address_id present)."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed"}, status=405)

    address_id = request.POST.get("address_id")
    instance = None
    if address_id:
        instance = get_object_or_404(Address, id=address_id, user=request.user)

    form = AddressForm(request.POST, instance=instance)
    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors}, status=400)

    address = form.save(commit=False)
    address.user = request.user

    if address.is_default:
        # Only one default per address type (billing / shipping)
        Address.objects.filter(
            user=request.user, address_type=address.address_type
        ).exclude(pk=address.pk).update(is_default=False)

    address.save()

    return JsonResponse({
        "success": True,
        "message": "Address updated" if address_id else "Address added",
    })


@login_required
def address_delete(request, address_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed"}, status=405)

    address = get_object_or_404(Address, id=address_id, user=request.user)
    address.delete()
    return JsonResponse({"success": True, "message": "Address removed"})


@login_required
def address_set_default(request, address_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed"}, status=405)

    address = get_object_or_404(Address, id=address_id, user=request.user)
    Address.objects.filter(user=request.user, address_type=address.address_type).update(is_default=False)
    address.is_default = True
    address.save(update_fields=["is_default"])
    return JsonResponse({"success": True, "message": "Default address updated"})


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from Web.models import SupportTicket, SupportTicketReply


def Contact(request):

    data = {}
    error = None

    if request.method == "POST":

        name = request.POST.get("name")
        email = request.POST.get("email")
        support_type = request.POST.get("support_type")
        subject = request.POST.get("subject")
        message = request.POST.get("message")
        attachment = request.FILES.get("attachment")

        data = {
            "name": name,
            "email": email,
            "subject": subject,
            "message": message,
            "support_type": support_type,
        }

        if not name or not email or not subject or not message:
            error = "All required fields must be filled."
        elif support_type not in dict(SupportTicket.SUPPORT_CHOICES):
            error = "Please choose a valid support type."
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
            messages.success(
                request,
                "Thanks — your message has been received. We'll get back to you shortly."
            )
            return redirect("home:Contact")

    return render(request, "home/Contact.html", {
        "error": error,
        "data": data,
        "support_choices": SupportTicket.SUPPORT_CHOICES,
    })


@login_required
def ContactHistory(request):
    tickets = SupportTicket.objects.filter(user=request.user)
    return render(request, "home/ContactHistory.html", {"tickets": tickets})


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

        return redirect("home:TicketDetail", ticket_id=ticket.id)

    return render(request, "home/TicketDetail.html", {
        "ticket": ticket,
        "replies": ticket.replies.select_related("sender"),
    })







from django.core.paginator import Paginator
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, Q, Value, When
from django.shortcuts import render


PAGE_SIZE = 24

SORT_OPTIONS = {
    "discount": "Biggest Discount",
    "newest": "Newest",
    "price_asc": "Price: Low to High",
    "price_desc": "Price: High to Low",
    "popularity": "Best Selling",
}

SORT_FIELD_MAP = {
    "newest": "-created_at",
    "price_asc": "price",
    "price_desc": "-price",
    "popularity": "-sold",
}


def best_deals(request):
    category_ids = [c for c in request.GET.getlist("category") if c]
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    sort = request.GET.get("sort", "discount")
    if sort not in SORT_OPTIONS:
        sort = "discount"

    deals_qs = Product.objects.filter(status__in=["active", "featured"]).filter(
        Q(discount_percentage__gt=0) | Q(compare_at_price__gt=F("price"))
    )

    # Effective discount %, whichever source it comes from, so sorting/badges
    # work consistently regardless of which field a given product actually used.
    deals_qs = deals_qs.annotate(
        effective_discount=Case(
            When(discount_percentage__gt=0, then=F("discount_percentage")),
            When(
                compare_at_price__gt=F("price"),
                then=ExpressionWrapper(
                    (F("compare_at_price") - F("price")) * 100 / F("compare_at_price"),
                    output_field=FloatField(),
                ),
            ),
            default=Value(0),
            output_field=FloatField(),
        )
    )

    if category_ids:
        deals_qs = deals_qs.filter(category__id__in=category_ids)
    if min_price:
        try:
            deals_qs = deals_qs.filter(price__gte=float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            deals_qs = deals_qs.filter(price__lte=float(max_price))
        except ValueError:
            pass

    deals_qs = deals_qs.distinct()

    category_facets = (
        Category.objects.filter(products__in=deals_qs)
        .annotate(count=Count("products", filter=Q(products__in=deals_qs), distinct=True))
        .filter(count__gt=0)
        .order_by("name")
    )

    hero_deal = deals_qs.order_by("-effective_discount", "-sold").first()

    if sort in SORT_FIELD_MAP:
        deals_qs = deals_qs.order_by(SORT_FIELD_MAP[sort])
    else:
        deals_qs = deals_qs.order_by("-effective_discount", "-sold")

    deals_qs = deals_qs.select_related("brand").prefetch_related("images", "category")

    paginator = Paginator(deals_qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "home/BestDeals.html", {
        "products": page_obj,
        "hero_deal": hero_deal,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "category_facets": category_facets,
        "selected_category_ids": category_ids,
        "min_price": min_price,
        "max_price": max_price,
        "result_count": paginator.count,
    })



from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import BlogCategory, BlogPost, BTag  # adjust import path to match your app

PAGE_SIZE = 9


def blog_list(request):
    q = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "")
    tag_slug = request.GET.get("tag", "")

    posts = BlogPost.objects.filter(status="published").select_related("author", "category").prefetch_related("tags")

    if q:
        posts = posts.filter(
            Q(title__icontains=q) | Q(excerpt__icontains=q) | Q(content__icontains=q)
        )
    if category_slug:
        posts = posts.filter(category__slug=category_slug)
    if tag_slug:
        posts = posts.filter(tags__slug=tag_slug)

    posts = posts.distinct().order_by("-published_at")

    featured_post = posts.first() if not q and not category_slug and not tag_slug else None
    grid_posts = posts.exclude(pk=featured_post.pk) if featured_post else posts

    paginator = Paginator(grid_posts, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = BlogCategory.objects.filter(posts__status="published").distinct().order_by("name")
    recent_posts = BlogPost.objects.filter(status="published").order_by("-published_at")[:5]
    popular_tags = BTag.objects.filter(blog_posts__status="published").distinct().order_by("name")[:20]

    return render(request, "home/Blog.html", {
        "featured_post": featured_post,
        "posts": page_obj,
        "categories": categories,
        "recent_posts": recent_posts,
        "popular_tags": popular_tags,
        "query": q,
        "selected_category": category_slug,
        "selected_tag": tag_slug,
        "result_count": paginator.count,
    })


def blog_detail(request, slug):
    post = get_object_or_404(
        BlogPost.objects.select_related("author", "category").prefetch_related("tags"),
        slug=slug, status="published"
    )

    # Naive view counter — fine for a low/medium traffic blog; move to a
    # session-based or async increment if this needs to resist refresh-spam.
    BlogPost.objects.filter(pk=post.pk).update(views=post.views + 1)

    related_posts = (
        BlogPost.objects.filter(status="published", category=post.category)
        .exclude(pk=post.pk)
        .order_by("-published_at")[:3]
    )
    if not related_posts and post.tags.exists():
        related_posts = (
            BlogPost.objects.filter(status="published", tags__in=post.tags.all())
            .exclude(pk=post.pk)
            .distinct()
            .order_by("-published_at")[:3]
        )

    recent_posts = BlogPost.objects.filter(status="published").exclude(pk=post.pk).order_by("-published_at")[:5]

    return render(request, "home/BlogDetail.html", {
        "post": post,
        "related_posts": related_posts,
        "recent_posts": recent_posts,
    })

from django.db.models import Q, OuterRef, Subquery, Value, BooleanField
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.views import APIView
from .serializer import NotificationSerializer
from django.http import JsonResponse
from django.db.models import Q, OuterRef, Subquery, Value, BooleanField
from django.db.models.functions import Coalesce
from django.utils import timezone


def user_notifications(request):

    if not request.user.is_authenticated:
        return JsonResponse({
            "success": False,
            "message": "Authentication required",
            "notifications": []
        }, status=401)

    user = request.user

    recipient_subquery = NotificationRecipient.objects.filter(
        notification=OuterRef("pk"),
        user=user
    ).values("is_read")[:1]

    now = timezone.now()

    notifications = (
        Notification.objects
        .filter(is_active=True)
        .filter(
            Q(is_general=True) |
            Q(order__user=user)
        )
        .filter(
            ~Q(
                notification_type="promotion"
            )
            |
            Q(
                notification_type="promotion",
                promotion__is_active=True,
                promotion__end_date__gte=now
            )
        )
        .annotate(
            is_read=Coalesce(
                Subquery(
                    recipient_subquery,
                    output_field=BooleanField()
                ),
                Value(False)
            )
        )
        .order_by("-created_at")
    )

    data = []

    for notification in notifications:
        data.append({
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "is_read": notification.is_read,
            "created_at": notification.created_at.isoformat()
                if notification.created_at else None,
        })

    return JsonResponse({
        "success": True,
        "notifications": data
    })

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST


PAGE_SIZE = 15


@login_required
def all_notifications(request):
    type_filter = request.GET.get("type", "")
    read_filter = request.GET.get("read", "")  # "unread" | "read" | ""

    recipients = (
        NotificationRecipient.objects
        .filter(user=request.user)
        .select_related("notification", "notification__order", "notification__promotion")
        .order_by("-notification__created_at")
    )

    if type_filter:
        recipients = recipients.filter(notification__notification_type=type_filter)
    if read_filter == "unread":
        recipients = recipients.filter(is_read=False)
    elif read_filter == "read":
        recipients = recipients.filter(is_read=True)

    paginator = Paginator(recipients, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    unread_count = NotificationRecipient.objects.filter(user=request.user, is_read=False).count()

    return render(request, "home/Notifications.html", {
        "recipients": page_obj,
        "notification_types": Notification.NOTIFICATION_TYPES,
        "selected_type": type_filter,
        "selected_read": read_filter,
        "unread_count": unread_count,
        "result_count": paginator.count,
    })


@login_required
@require_POST
def mark_notification_read(request, recipient_id):
    recipient = get_object_or_404(NotificationRecipient, id=recipient_id, user=request.user)
    if not recipient.is_read:
        recipient.is_read = True
        recipient.seen_at = timezone.now()
        recipient.save(update_fields=["is_read", "seen_at"])
    return JsonResponse({"success": True})


@login_required
@require_POST
def mark_all_notifications_read(request):
    NotificationRecipient.objects.filter(user=request.user, is_read=False).update(
        is_read=True, seen_at=timezone.now()
    )
    return JsonResponse({"success": True})






from .serializer import TrackOrderThrottle,TrackOrderSerializer
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from django.views.generic import TemplateView
from rest_framework.response import Response

# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
class TrackOrderAPIView(APIView):
    """
    GET /api/track-order/?q=ORD-1A2B3C4D
    GET /api/track-order/ORD-1A2B3C4D/
    `q` can be the order number or the tracking number.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [TrackOrderThrottle]
 
    def get(self, request, number=None):
        number = (number or request.query_params.get("q") or "").strip()
 
        if not number or len(number) > 100:
            return Response(
                {"success": False, "message": "Enter an order number or tracking number."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        order = (
            Order.objects  # noqa: F821
            .filter(is_deleted=False)
            .filter(Q(order_number__iexact=number) | Q(tracking_number__iexact=number))
            .select_related("shipping_address")
            .prefetch_related("items__product__images", "items__variant")
            .first()
        )
 
        if not order:
            return Response(
                {"success": False, "message": "No order found with this order or tracking number."},
                status=status.HTTP_404_NOT_FOUND,
            )
 
        data = TrackOrderSerializer(order, context={"request": request}).data
        return Response({"success": True, "order": data})
 
 
class TrackOrderPageView(TemplateView):
    template_name = "orders/track_order.html"