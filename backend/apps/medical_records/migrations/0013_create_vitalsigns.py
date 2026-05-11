import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0012_add_consultation_type'),
        ('organizations', '0005_organizationsettings'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VitalSigns',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('weight', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('temperature', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('heart_rate', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('respiratory_rate', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('recorded_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('medical_record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vital_signs', to='medical_records.medicalrecord')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='organizations.organization')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recorded_vitals', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-recorded_at', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='vitalsigns',
            index=models.Index(fields=['medical_record', '-recorded_at', '-created_at'], name='medical_rec_medical_9efa5c_idx'),
        ),
        migrations.AddIndex(
            model_name='vitalsigns',
            index=models.Index(fields=['-recorded_at', '-created_at'], name='medical_rec_recorde_f2a8b1_idx'),
        ),
    ]
