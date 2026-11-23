from django.db import migrations

DEFAULTS = [
    ("bi-truck", "Free Shipping", "On orders over PKR {threshold}"),
    ("bi-cash-coin", "Cash on Delivery", "Pay when you receive"),
    ("bi-arrow-repeat", "7 Days Returns", "Hassle free returns"),
    ("bi-shield-check", "100% Secure Payment", "Secure shopping guarantee"),
]


def seed(apps, schema_editor):
    HomeFeature = apps.get_model("storefront", "HomeFeature")
    if HomeFeature.objects.exists():
        return
    for i, (icon, title, sub) in enumerate(DEFAULTS, 1):
        HomeFeature.objects.create(icon=icon, title=title, subtitle=sub, sort_order=i * 10)


class Migration(migrations.Migration):
    dependencies = [("storefront", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
