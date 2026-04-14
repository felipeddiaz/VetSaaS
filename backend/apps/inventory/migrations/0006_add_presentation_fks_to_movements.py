from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_data_create_presentations'),
    ]

    operations = [
        # Agregar FK a presentation en StockMovement (nullable mientras se migran datos)
        migrations.AddField(
            model_name='stockmovement',
            name='presentation',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='movements',
                to='inventory.presentation',
            ),
        ),
        # Agregar FK a presentation en MedicalRecordProduct (nullable mientras se migran datos)
        migrations.AddField(
            model_name='medicalrecordproduct',
            name='presentation',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='medical_record_usages',
                to='inventory.presentation',
            ),
        ),
    ]
