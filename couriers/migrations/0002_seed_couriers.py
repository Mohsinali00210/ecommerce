from django.db import migrations

# (courier_status, match, shipment_status, order_status, notify, priority)
LEOPARDS_RULES = [
    # returns first - "Returned to shipper" also contains "shipper"/"delivered"-like words
    ("returned to shipper", "contains", "returned", "returned", True, 10),
    ("return to shipper", "contains", "returned", "returned", True, 10),
    ("being return", "contains", "return_in_transit", "return_in_transit", True, 12),
    ("ready for return", "contains", "return_in_transit", "return_in_transit", True, 12),
    ("return in process", "contains", "return_in_transit", "return_in_transit", True, 12),
    ("returned", "contains", "return_in_transit", "return_in_transit", True, 14),
    ("cancel", "contains", "cancelled", "", False, 15),
    ("undelivered", "contains", "delivery_failed", "", True, 20),
    ("refused", "contains", "delivery_failed", "", True, 20),
    ("not available", "contains", "delivery_failed", "", True, 20),
    ("pending", "exact", "delivery_failed", "", True, 22),
    ("delivered", "exact", "delivered", "delivered", True, 30),
    ("delivered to", "contains", "delivered", "delivered", True, 31),
    ("assigned to courier", "contains", "out_for_delivery", "out_for_delivery", True, 40),
    ("assign to courier", "contains", "out_for_delivery", "out_for_delivery", True, 40),
    ("out for delivery", "contains", "out_for_delivery", "out_for_delivery", True, 40),
    ("arrived at station", "contains", "in_transit", "shipped", False, 50),
    ("dispatched", "contains", "in_transit", "shipped", True, 50),
    ("in transit", "contains", "in_transit", "shipped", False, 50),
    ("missroute", "contains", "in_transit", "", False, 50),
    ("shipment picked", "contains", "picked_up", "shipped", True, 55),
    ("picked", "contains", "picked_up", "shipped", True, 56),
    ("drop off", "contains", "picked_up", "shipped", True, 56),
    ("pickup request", "contains", "booked", "booked", False, 60),
    ("consignment booked", "contains", "booked", "booked", False, 60),
]

# Apply to every courier (useful defaults for new couriers)
GLOBAL_RULES = [
    ("booked", "exact", "booked", "booked", False, 200),
    ("delivered", "exact", "delivered", "delivered", True, 200),
    ("out for delivery", "contains", "out_for_delivery", "out_for_delivery", True, 210),
    ("in transit", "contains", "in_transit", "shipped", False, 210),
    ("returned", "contains", "returned", "returned", True, 210),
    ("cancelled", "contains", "cancelled", "", False, 210),
]


def seed(apps, schema_editor):
    Provider = apps.get_model("couriers", "CourierProvider")
    Mapping = apps.get_model("couriers", "StatusMapping")

    leopards, _ = Provider.objects.get_or_create(code="leopards", defaults=dict(
        name="Leopards Courier", adapter="leopards", environment="sandbox",
        live_base_url="https://merchantapi.leopardscourier.com/api/",
        sandbox_base_url="https://merchantapistaging.leopardscourier.com/api/",
        is_active=True, is_default=True, auto_book_enabled=False, auto_book_on_status="processing",
        auto_book_payment_methods="cod", default_weight_grams=500,
        default_shipment_type="overnight", sort_order=1,
    ))
    Provider.objects.get_or_create(code="manual", defaults=dict(
        name="Other courier (manual)", adapter="manual", environment="live",
        is_active=True, is_default=False, sort_order=99,
    ))
    for cs, mt, ss, os_, notify, prio in LEOPARDS_RULES:
        Mapping.objects.get_or_create(provider=leopards, courier_status=cs, match_type=mt, defaults=dict(
            shipment_status=ss, order_status=os_, notify_customer=notify, priority=prio))
    for cs, mt, ss, os_, notify, prio in GLOBAL_RULES:
        Mapping.objects.get_or_create(provider=None, courier_status=cs, match_type=mt, defaults=dict(
            shipment_status=ss, order_status=os_, notify_customer=notify, priority=prio))


class Migration(migrations.Migration):
    dependencies = [("couriers", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
