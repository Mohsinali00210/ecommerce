from decimal import Decimal

from django.db import migrations

METHODS = [  # code, name, enabled, sort
    ("jazzcash", "JazzCash", True, 10),
    ("easypaisa", "Easypaisa", True, 20),
    ("bank", "Bank Transfer", True, 30),
    ("stripe", "Stripe", False, 40),
]


def seed(apps, schema_editor):
    M = apps.get_model("payments", "PayoutMethod")
    for code, name, enabled, sort in METHODS:
        M.objects.get_or_create(code=code, defaults=dict(
            name=name, is_enabled=enabled, sort_order=sort, mode="manual", min_amount=Decimal("500.00")))


def unseed(apps, schema_editor):
    apps.get_model("payments", "PayoutMethod").objects.filter(code__in=[m[0] for m in METHODS]).delete()


class Migration(migrations.Migration):
    dependencies = [("payments", "0006_withdrawal_fees")]
    operations = [migrations.RunPython(seed, unseed)]
