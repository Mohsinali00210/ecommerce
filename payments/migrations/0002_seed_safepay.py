from django.db import migrations


def seed(apps, schema_editor):
    G = apps.get_model("payments", "PaymentGateway")
    G.objects.get_or_create(code="safepay", defaults=dict(
        name="Safepay", environment="sandbox", is_active=False,
        sandbox_base_url="https://sandbox.api.getsafepay.com",
        live_base_url="https://api.getsafepay.com",
    ))


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
