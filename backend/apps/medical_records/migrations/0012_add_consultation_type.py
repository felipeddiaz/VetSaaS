from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0011_alter_medicalrecord_diagnosis_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicalrecord',
            name='consultation_type',
            field=models.CharField(
                choices=[
                    ('general', 'General'),
                    ('vaccine', 'Vacuna'),
                    ('surgery', 'Cirugía'),
                    ('emergency', 'Emergencia'),
                ],
                default='general',
                db_index=True,
                max_length=20,
            ),
        ),
    ]
