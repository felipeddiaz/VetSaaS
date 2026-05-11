"""
Capa 2 — MedicalRecord closed_at provenance.

Adds:
- MedicalRecord.closed_at_source (CharField with choices)
- AlterField on closed_at to mark editable=False

Existing closed rows lose nothing — but we cannot retroactively distinguish
between rows closed via the canonical service writer and rows previously
backfilled by migration 0014. Mark them all as 'legacy' to flag uncertain
provenance. Going forward, close_medical_record() writes 'service'.
"""

from django.db import migrations, models


def mark_existing_closed_as_legacy(apps, schema_editor):
    MedicalRecord = apps.get_model('medical_records', 'MedicalRecord')
    MedicalRecord.objects.filter(
        status='closed', closed_at__isnull=False,
    ).update(closed_at_source='legacy')


def reverse_noop(apps, schema_editor):
    pass


SOURCE_CHOICES = [
    ('service', 'View writer (close_medical_record)'),
    ('fallback', 'Backfilled from updated_at'),
    ('legacy', 'Existed before provenance tracking'),
]


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('medical_records', '0014_medicalrecord_closed_status_requires_closed_at'),
    ]

    operations = [
        # editable=False on closed_at is non-DB metadata. Avoid ALTER TABLE
        # which would conflict with existing CHECK constraint triggers from 0014.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='medicalrecord',
                    name='closed_at',
                    field=models.DateTimeField(blank=True, editable=False, null=True),
                ),
            ],
            database_operations=[],
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='closed_at_source',
            field=models.CharField(
                choices=SOURCE_CHOICES, default='service',
                editable=False, max_length=24,
            ),
        ),
        migrations.RunPython(mark_existing_closed_as_legacy, reverse_noop),
    ]
