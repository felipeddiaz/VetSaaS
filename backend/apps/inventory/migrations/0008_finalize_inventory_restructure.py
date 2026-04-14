from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_data_populate_presentation_fks'),
    ]

    operations = [
        # ── StockMovement ────────────────────────────────────────────────────
        # Hacer presentation no-nullable
        migrations.AlterField(
            model_name='stockmovement',
            name='presentation',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='movements',
                to='inventory.presentation',
            ),
        ),
        # Eliminar FK vieja a product
        migrations.RemoveField(
            model_name='stockmovement',
            name='product',
        ),

        # ── MedicalRecordProduct ─────────────────────────────────────────────
        # Limpiar unique_together viejo (referencia 'product')
        migrations.AlterUniqueTogether(
            name='medicalrecordproduct',
            unique_together=set(),
        ),
        # Hacer presentation no-nullable
        migrations.AlterField(
            model_name='medicalrecordproduct',
            name='presentation',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='medical_record_usages',
                to='inventory.presentation',
            ),
        ),
        # Eliminar FK vieja a product
        migrations.RemoveField(
            model_name='medicalrecordproduct',
            name='product',
        ),
        # Agregar nuevo unique_together con presentation
        migrations.AlterUniqueTogether(
            name='medicalrecordproduct',
            unique_together={('medical_record', 'presentation')},
        ),

        # ── Product: eliminar campos que pasan a Presentation ────────────────
        migrations.RemoveField(model_name='product', name='unit'),
        migrations.RemoveField(model_name='product', name='stock'),
        migrations.RemoveField(model_name='product', name='min_stock'),
        migrations.RemoveField(model_name='product', name='sale_price'),

        # ── Product: finalizar internal_code ─────────────────────────────────
        # Hacer no-nullable y agregar unique_together con organization
        migrations.AlterField(
            model_name='product',
            name='internal_code',
            field=models.CharField(db_index=True, max_length=100),
        ),
        migrations.AlterUniqueTogether(
            name='product',
            unique_together={('organization', 'internal_code')},
        ),
    ]
