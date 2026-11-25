# Same name as the migration that was once generated on the server, so uploading this file
# replaces it and the migration history stays a single line on every machine.
# Storage is a callable (payments.models.get_private_storage): no machine-specific path.
import payments.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_alter_payment_proof'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='proof',
            field=models.FileField(blank=True, storage=payments.models.get_private_storage,
                                   upload_to='payment_proofs/%Y/%m/'),
        ),
    ]
