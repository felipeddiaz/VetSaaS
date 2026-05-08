import uuid
from django.db import migrations, models


def populate_medicalrecord_public_ids(apps, schema_editor):
    MedicalRecord = apps.get_model('medical_records', 'MedicalRecord')
    for obj in MedicalRecord.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0009_allow_blank_diagnosis_treatment'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicalrecord',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_medicalrecord_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='medicalrecord',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
