import uuid
from django.db import migrations, models


def populate_owner_public_ids(apps, schema_editor):
    Owner = apps.get_model('patients', 'Owner')
    for obj in Owner.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


def populate_pet_public_ids(apps, schema_editor):
    Pet = apps.get_model('patients', 'Pet')
    for obj in Pet.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0008_pet_is_generic'),
    ]

    operations = [
        migrations.AddField(
            model_name='owner',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_owner_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='owner',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='pet',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_pet_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='pet',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
