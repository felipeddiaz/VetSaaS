# Migración Paso 8: eliminar campo product legacy de InvoiceItem
# y aplicar XOR constraint (service XOR presentation).
#
# Estrategia de datos antes de aplicar constraint:
#   1. Items con product!=NULL y presentation!=NULL → product=NULL (ya migrados)
#   2. Item id=1 (description='Consulta general', org=2) → asignar service_id=1
#   3. Items id=40-43 (test data sin servicio ni producto) → eliminar

from django.db import migrations, models
from django.db.models import Q


def clean_product_field(apps, schema_editor):
    InvoiceItem = apps.get_model('billing', 'InvoiceItem')

    # 1. Items con product y presentation: limpiar product (redundante)
    InvoiceItem.objects.filter(
        product__isnull=False,
        presentation__isnull=False,
    ).update(product=None)

    # 2. Item 'Consulta general' sin service ni presentation → asignar service
    #    Solo si existe ese servicio (seguro para re-runs)
    Service = apps.get_model('billing', 'Service')
    try:
        svc = Service.objects.get(id=1, organization_id=2)
        InvoiceItem.objects.filter(
            id=1,
            service__isnull=True,
            presentation__isnull=True,
        ).update(service=svc)
    except Service.DoesNotExist:
        pass

    # 3. Items de prueba sin ninguna referencia → eliminar
    InvoiceItem.objects.filter(
        service__isnull=True,
        presentation__isnull=True,
        product__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    # atomic=False: necesario porque mezclamos DML (RunPython con deletes)
    # y DDL (RemoveField + AddConstraint) en PostgreSQL.
    atomic = False

    dependencies = [
        ('billing', '0007_remove_invoiceitem_billing_inv_organiz_6da732_idx_and_more'),
    ]

    operations = [
        # 1. Data migration: limpiar y asignar antes de aplicar constraints
        migrations.RunPython(
            clean_product_field,
            reverse_code=migrations.RunPython.noop,
        ),

        # 2. Eliminar campo legacy product
        migrations.RemoveField(
            model_name='invoiceitem',
            name='product',
        ),

        # 3. XOR constraint — ahora todos los items tienen service XOR presentation
        migrations.AddConstraint(
            model_name='invoiceitem',
            constraint=models.CheckConstraint(
                condition=(
                    Q(service__isnull=False, presentation__isnull=True) |
                    Q(service__isnull=True,  presentation__isnull=False)
                ),
                name='invoiceitem_exactly_one_source',
            ),
        ),
    ]
