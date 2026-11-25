from django.db import migrations

GATEWAYS = [
    # code, name, sandbox, live, sort
    ("jazzcash", "JazzCash", "https://sandbox.jazzcash.com.pk", "https://payments.jazzcash.com.pk", 20),
    ("easypaisa", "Easypaisa", "https://easypaystg.easypaisa.com.pk", "https://easypay.easypaisa.com.pk", 30),
    ("stripe", "Stripe (cards)", "https://api.stripe.com", "https://api.stripe.com", 40),
    ("test", "Test gateway (sandbox)", "", "", 90),
]


def seed(apps, schema_editor):
    G = apps.get_model("payments", "PaymentGateway")
    G.objects.filter(code="safepay").update(sort_order=10)
    for code, name, sandbox, live, sort in GATEWAYS:
        G.objects.get_or_create(code=code, defaults=dict(
            name=name, environment="sandbox", is_active=False, sandbox_base_url=sandbox, live_base_url=live,
            sort_order=sort))


def unseed(apps, schema_editor):
    apps.get_model("payments", "PaymentGateway").objects.filter(code__in=[g[0] for g in GATEWAYS]).delete()


class Migration(migrations.Migration):
    dependencies = [("payments", "0004_gateway_options")]
    operations = [migrations.RunPython(seed, unseed)]
