import uuid
from django.db import migrations, models


def populate_prescription_public_ids(apps, schema_editor):
    Prescription = apps.get_model('prescriptions', 'Prescription')
    for obj in Prescription.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('prescriptions', '0003_remove_prescriptionitem_prescriptio_organiz_e427c3_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescription',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_prescription_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='prescription',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
