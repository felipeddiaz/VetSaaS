from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0009_add_public_id_to_exposed_models'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='pet',
            constraint=models.UniqueConstraint(
                condition=models.Q(is_generic=True),
                fields=['organization'],
                name='unique_generic_pet_per_organization',
            ),
        ),
    ]
