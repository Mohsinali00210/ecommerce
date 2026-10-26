from django.db import migrations, models


def normalize_simple_and_grouped(apps, schema_editor):
    """
    * product_type is stored as '1' (Simple) / '2' (Grouped); old rows may hold the
      words 'simple' / 'grouped'.
    * Simple product  -> exactly one default variant.
    * Anything marked simple that really has 2+ variants becomes Grouped.
    """
    Product = apps.get_model('products', 'Product')
    ProductVariant = apps.get_model('products', 'ProductVariant')
    db = schema_editor.connection.alias

    for product in Product.objects.using(db).all().iterator():
        variants = ProductVariant.objects.using(db).filter(product_id=product.pk).order_by('pk')
        count = variants.count()
        simple = str(product.product_type) in ('1', 'simple')

        if simple and count > 1:
            simple = False  # it is really a grouped product

        if not simple:
            Product.objects.using(db).filter(pk=product.pk).update(product_type='2')
            continue

        Product.objects.using(db).filter(pk=product.pk).update(product_type='1')
        if count == 0:
            base = (product.sku or f'P{product.pk}')[:100]
            sku, n = base, 1
            while ProductVariant.objects.using(db).filter(sku=sku).exists():
                suffix = f'-{product.pk}-{n}'
                sku = f'{base[:100 - len(suffix)]}{suffix}'
                n += 1
            ProductVariant.objects.using(db).create(
                product_id=product.pk,
                name='Default',
                sku=sku,
                price=product.price,
                stock_quantity=product.stock_quantity,
                created_by_id=product.created_by_id,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0043_productvariant_images_alter_productvariant_image'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='product_type',
            field=models.CharField(choices=[('1', 'Simple'), ('2', 'Grouped')], default='1', max_length=20),
        ),
        migrations.RunPython(normalize_simple_and_grouped, migrations.RunPython.noop),
    ]
