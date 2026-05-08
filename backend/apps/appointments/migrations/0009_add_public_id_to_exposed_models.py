import uuid
from django.db import migrations, models


def populate_public_ids(apps, schema_editor):
    Appointment = apps.get_model('appointments', 'Appointment')
    for obj in Appointment.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0008_appointmentstatuschange'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='appointment',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
