from django.db import migrations


def populate_presentation_fks(apps, schema_editor):
    StockMovement = apps.get_model('inventory', 'StockMovement')
    MedicalRecordProduct = apps.get_model('inventory', 'MedicalRecordProduct')
    Presentation = apps.get_model('inventory', 'Presentation')

    # Mapa product_id → presentation_id para evitar queries N+1
    pres_map = {p.product_id: p.id for p in Presentation.objects.all()}

    for movement in StockMovement.objects.filter(product_id__isnull=False):
        pres_id = pres_map.get(movement.product_id)
        if pres_id:
            StockMovement.objects.filter(pk=movement.pk).update(presentation_id=pres_id)

    for mrp in MedicalRecordProduct.objects.filter(product_id__isnull=False):
        pres_id = pres_map.get(mrp.product_id)
        if pres_id:
            MedicalRecordProduct.objects.filter(pk=mrp.pk).update(presentation_id=pres_id)


def reverse_populate(apps, schema_editor):
    # La reversa simplemente deja presentation_id en NULL (estado previo a 0006)
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_add_presentation_fks_to_movements'),
    ]

    operations = [
        migrations.RunPython(populate_presentation_fks, reverse_populate),
    ]
