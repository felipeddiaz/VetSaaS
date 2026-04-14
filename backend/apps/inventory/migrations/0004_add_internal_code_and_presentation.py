from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_product_sale_price'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        # internal_code nullable mientras no se ejecuta la migración de datos
        migrations.AddField(
            model_name='product',
            name='internal_code',
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
        migrations.CreateModel(
            name='Presentation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('base_unit', models.CharField(
                    max_length=20,
                    choices=[
                        ('tablet', 'Tableta'),
                        ('capsule', 'Cápsula'),
                        ('ml', 'ml'),
                        ('vial', 'Vial'),
                        ('ampoule', 'Ampolleta'),
                        ('piece', 'Pieza'),
                        ('bag', 'Bolsa'),
                        ('bottle', 'Frasco'),
                        ('tube', 'Tubo'),
                        ('kg', 'kg'),
                        ('g', 'g'),
                        ('unit', 'Unidad'),
                    ],
                )),
                ('quantity', models.DecimalField(decimal_places=2, default=1, max_digits=10)),
                ('sale_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('stock', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('min_stock', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('product', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='presentation',
                    to='inventory.product',
                )),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='presentation_set',
                    to='organizations.organization',
                )),
            ],
            options={
                'ordering': ['product__name'],
                'abstract': False,
            },
        ),
    ]
