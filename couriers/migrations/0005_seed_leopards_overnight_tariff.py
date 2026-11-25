"""Seeds the default tariff: Leopards Overnight, C.O.D. tariff charges.

Weight                Within city   Zone A (same province)   Zone B (other province)
0 - 250 g             Rs 160        Rs 180                   Rs 200
250 - 500 g           Rs 180        Rs 200                   Rs 230
500 g - 1 kg          Rs 180        Rs 230                   Rs 250

Parcels over 1 kg: the 1 kg price + the "extra" amounts per 500 g (0 until set in
Shipping > Shipping rates).
"""
from decimal import Decimal

from django.db import migrations

NAME = "Leopards Overnight - COD"
SLABS = [
    (250, "160.00", "180.00", "200.00"),
    (500, "180.00", "200.00", "230.00"),
    (1000, "180.00", "230.00", "250.00"),
]


def seed(apps, schema_editor):
    Provider = apps.get_model("couriers", "CourierProvider")
    Tariff = apps.get_model("couriers", "ShippingTariff")
    Slab = apps.get_model("couriers", "TariffSlab")
    if Tariff.objects.filter(name=NAME).exists():
        return
    Tariff.objects.filter(is_default=True).update(is_default=False)
    t = Tariff.objects.create(
        name=NAME, provider=Provider.objects.filter(code="leopards").first(), service_type="overnight",
        extra_step_grams=500, is_active=True, is_default=True,
        notes="Leopards Courier Overnight - C.O.D. tariff charges",
    )
    for max_g, city, zone_a, zone_b in SLABS:
        Slab.objects.create(tariff=t, max_grams=max_g, within_city=Decimal(city),
                            same_province=Decimal(zone_a), other_province=Decimal(zone_b))


def unseed(apps, schema_editor):
    apps.get_model("couriers", "ShippingTariff").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("couriers", "0004_weight_shipping")]
    operations = [migrations.RunPython(seed, unseed)]
