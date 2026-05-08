import uuid
from django.db import migrations, models


def populate_invoice_public_ids(apps, schema_editor):
    Invoice = apps.get_model('billing', 'Invoice')
    for obj in Invoice.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


def populate_service_public_ids(apps, schema_editor):
    Service = apps.get_model('billing', 'Service')
    for obj in Service.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_alter_invoice_pet'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_invoice_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='invoice',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='service',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_service_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='service',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
