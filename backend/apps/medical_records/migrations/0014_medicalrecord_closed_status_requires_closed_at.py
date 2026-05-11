"""
Analytics event-authority hardening (Capa 1).

Añade CHECK constraint a MedicalRecord: si status='closed', closed_at no puede
ser NULL. Bloquea bypasses tipo `mr.status='closed'; mr.save()` desde shell o
queryset.update() que dejarían el registro "cerrado operacionalmente" pero
ausente de snapshots clínicos.

Ver docs/analytics-schema-audit.md §2.5 y docs/dashboard-metrics-contract.md §2.7.

Backfill defensivo previo: rows con status='closed' AND closed_at NULL reciben
`updated_at` como aproximación. No debería ocurrir en datos limpios.
"""

from django.db import migrations, models
from django.utils import timezone


def backfill_closed_at(apps, schema_editor):
    MedicalRecord = apps.get_model('medical_records', 'MedicalRecord')
    qs = MedicalRecord.objects.filter(status='closed', closed_at__isnull=True)
    for mr in qs:
        mr.closed_at = mr.updated_at or timezone.now()
        mr.save(update_fields=['closed_at'])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0013_create_vitalsigns'),
    ]

    operations = [
        migrations.RunPython(backfill_closed_at, reverse_noop),
        migrations.AddConstraint(
            model_name='medicalrecord',
            constraint=models.CheckConstraint(
                condition=~models.Q(status='closed') | models.Q(closed_at__isnull=False),
                name='medicalrecord_closed_status_requires_closed_at',
            ),
        ),
    ]
