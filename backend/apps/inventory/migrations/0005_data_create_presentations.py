from django.db import migrations


UNIT_MAP = {
    'tableta': 'tablet',
    'tabletas': 'tablet',
    'tablet': 'tablet',
    'capsula': 'capsule',
    'cápsula': 'capsule',
    'capsule': 'capsule',
    'ml': 'ml',
    'vial': 'vial',
    'ampolleta': 'ampoule',
    'ampoule': 'ampoule',
    'pieza': 'piece',
    'piezas': 'piece',
    'piece': 'piece',
    'bolsa': 'bag',
    'bag': 'bag',
    'frasco': 'bottle',
    'bottle': 'bottle',
    'tubo': 'tube',
    'tube': 'tube',
    'kg': 'kg',
    'g': 'g',
}


def create_presentations(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    Presentation = apps.get_model('inventory', 'Presentation')

    for product in Product.objects.all():
        # Código único por organización: PROD-{org_id}-{product_pk}
        if not product.internal_code:
            product.internal_code = f'PROD-{product.organization_id}-{product.pk:04d}'
            product.save()

        # Mapear unidad libre a catálogo cerrado
        raw_unit = (product.unit or '').strip().lower()
        base_unit = UNIT_MAP.get(raw_unit, 'unit')

        # El precio debe ser > 0; si estaba en 0 ponemos 1 como placeholder
        sale_price = product.sale_price if product.sale_price > 0 else 1

        Presentation.objects.create(
            product=product,
            organization=product.organization,
            name=product.name,
            base_unit=base_unit,
            quantity=1,
            sale_price=sale_price,
            stock=product.stock,
            min_stock=product.min_stock,
        )


def reverse_presentations(apps, schema_editor):
    Presentation = apps.get_model('inventory', 'Presentation')
    Presentation.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_add_internal_code_and_presentation'),
    ]

    operations = [
        migrations.RunPython(create_presentations, reverse_presentations),
    ]
