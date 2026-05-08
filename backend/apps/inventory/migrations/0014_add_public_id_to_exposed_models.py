import uuid
from django.db import migrations, models


def populate_presentation_public_ids(apps, schema_editor):
    Presentation = apps.get_model('inventory', 'Presentation')
    for obj in Presentation.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


def populate_product_public_ids(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    for obj in Product.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0013_alter_presentation_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='presentation',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_presentation_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='presentation',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='product',
            name='public_id',
            field=models.UUIDField(db_index=True, null=True, editable=False),
        ),
        migrations.RunPython(populate_product_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='product',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
