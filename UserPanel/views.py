"""
Home page view for the AUGUST storefront (index1.html).

ASSUMPTIONS — you only sent cart/order/notification models, not
products/models.py, so this view assumes the following fields exist
on products.models.Product / ProductVariant / Category. Rename to
match your real schema:

    Product:
        name            CharField
        slug            SlugField                (used for product-details URL)
        category        FK -> Category (has .name)
        price           Decimal
        compare_at_price Decimal (nullable)       -> "was" price / strike-through
        image           ImageField/URLField       -> primary image
        hover_image     ImageField/URLField (nullable, optional)
        is_active       Boolean
        is_featured     Boolean
        created_at      DateTime
        sold            Integer                  (already used in models.py you sent)
        rating          Decimal/Integer (nullable, optional)

    ProductVariant:
        product         FK -> Product
        stock_quantity  Integer                  (already used in models.py you sent)
        color / color_hex   (optional, for the color-dot swatches)

    Category:
        name            CharField
        slug            SlugField
        image           ImageField/URLField (optional, for the "Shop by Category" tiles)

If your real field names differ, adjust the query below and the
`.name` / `.price` / etc. attribute access in the template + partial.
"""

from django.shortcuts import render,get_object_or_404
from django.utils import timezone
from django.db.models import Sum

from products.models import Product, Category,Promotion  # adjust import path/names if different

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
    """Returns the Cart for the logged-in user, or the anonymous session cart."""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user, defaults={"is_active": True})
        return cart

    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    cart, _ = Cart.objects.get_or_create(
        session_key=session_key, user=None, defaults={"is_active": True}
    )
    return cart


def _cart_count(request):
    cart = _get_or_create_cart(request)
    total = CartItem.objects.filter(cart=cart, is_deleted=False).aggregate(
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


def home(request):
    active_products = Product.objects.filter(is_active=True)

    
    current_date = timezone.now()

    featured_products = Product.objects.prefetch_related(
        "images",
        "variants",
        "category",
        "promotions"
    )

    # Active promotions
    promotions = Promotion.objects.filter(
        start_date__lte=current_date,
        end_date__gte=current_date,
        is_active=True
    ).prefetch_related("products")

    # Attach promotion info to products
    for product in featured_products:
        product.final_price = product.price
        product.has_discount = False
        product.discount_percent = 0
        product.promotion = None

        promo = product.promotions.filter(
            start_date__lte=current_date,
            end_date__gte=current_date,
            is_active=True
        ).first()

        if promo:
            product.promotion = promo
            product.final_price = promo.get_discounted_price(product.price)
            product.has_discount = product.final_price != product.price

            if promo.discount_type == "percentage":
                product.discount_percent = int(promo.discount_value)

    
    print("product ",product)
    best_sellers = active_products.order_by("-sold")[:PRODUCTS_PER_ROW_SECTION]

    new_arrivals = active_products.order_by("-created_at")[:PRODUCTS_PER_ROW_SECTION]

    categories = Category.objects.filter(parent__isnull=True)

    context = {
        "featured_products": featured_products,
        "best_sellers": best_sellers,
        "new_arrivals": new_arrivals,
        "categories": categories,
        "cart_count": _cart_count(request),
        "wishlist_count": _wishlist_count(request),
        "notification_count": _unread_notification_count(request),
        "recent_notifications": (
            NotificationRecipient.objects.filter(user=request.user)
            .select_related("notification")
            .order_by("-notification__created_at")[:3]
            if request.user.is_authenticated
            else []
        ),
        "sale_ends_at": timezone.now() + timezone.timedelta(hours=6),  # for the countdown widget
    }
    return render(request, "home/index.html", context)

def ProductDetails(request, slug, sku=None):
    """
    URLs:
      /product/<slug>/           -> plain product page, no variant preselected
      /product/<slug>/<sku>/     -> product page with that variant preselected
    """
    product = get_object_or_404(
        Product.objects.prefetch_related("images", "variants", "variant_options"),
        slug=slug,
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
        product.off_price = product.old_price - product.final_price
 
    # Related products
    related_products = (
        Product.objects.filter(category__in=product.category.all(), brand=product.brand)
        .exclude(id=product.id)
        .prefetch_related("images", "promotions")[:5]
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
            prd.off_price = prd.old_price - prd.final_price
 
    Reviews = product.reviews.filter(
        is_active=True,
        is_deleted=False,
        product=product,
    ).select_related("user").order_by("-created_at")
 
    variants = product.variants.select_related("image")
    variant_data = []
    selected_variant = None
 
    for v in variants:
        variant_promotions = Promotion.objects.filter(products=product, start_date__lte=now, end_date__gte=now)
 
        if variant_promotions.exists():
            promo = variant_promotions.first()
            final_price = promo.get_discounted_price(v.price)
            off_price = promo.get_off_price(v.price)
        else:
            final_price = v.price
            off_price = product.old_price - final_price
 
        entry = {
            "id": v.id,
            "sku": v.sku,  # used to build /product/<slug>/<sku>/ links and to preselect on load
            "name": v.name,
            "price": float(v.price),
            "final_price": float(final_price),
            "off_price": float(off_price),
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
        "promotions": promotions,
        "images": product.images.all(),
        "variants": variants,
        "variants_json": variants_json,
        "options": product.variant_options.all(),
        "related_products": related_products,
        "Reviews": Reviews,
        "can_review": can_review,
        "estimated_date": estimated_date,
        "user_wishlist_ids": wishlist_ids,
        "show_message_box": True,
        "selected_variant": selected_variant,  # None if no sku in URL or sku didn't match any variant
    }
 
    return render(request, "home/product_details.html", context)



from accounts.models import Address
from decimal import Decimal

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
        "home/checkout.html",
        {
            "items": context,
            "defaultaddresses": defaultaddresses,
            "addresses": addresses
        }
    )



from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch

@login_required
def MyCart(request):
    cart = (
        Cart.objects
        .filter(user=request.user, is_active=True)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.filter(
                    is_active=True,
                    is_deleted=False
                ).select_related(
                    "product",
                    "variant"
                ).prefetch_related(
                    "product__images"
                )
            )
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
            base_price=0
            product = cartitem.product
            if cartitem.variant:
                base_price = cartitem.variant.price
            else:
                base_price = product.price
            product.total_price_without_discount = base_price

            promo = (
                product.promotions
                .filter(start_date__lte=current_date, end_date__gte=current_date)
                .first()
            )
            if promo:
                final_price = promo.get_discounted_price(base_price)

                product.final_price = final_price
                product.off_price = promo.get_off_price(base_price) 

                product.discounted_price = final_price
                product.discount_type = promo.discount_type
                product.discount_value = promo.discount_value
                product.has_discount = final_price < base_price
            else:
                product.final_price = base_price
                product.off_price = 0 
                product.discounted_price = base_price
                product.discount_type = None
                product.discount_value = None
                product.has_discount = False
            
            total_price_without_discount += base_price * cartitem.quantity
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
            return redirect("home:Contact")


    return render(request, "home/Contact.html", {"success": success,"error": error,"data": data})







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