"""
Capa 2 — Invoice anchor completeness (DDL part).

Adds new columns:
- Invoice.confirmed_at (DateTimeField, editable=False)
- Invoice.cancelled_at (DateTimeField, editable=False)
- Invoice.paid_at_source / confirmed_at_source / cancelled_at_source

Marks Invoice.paid_at as editable=False (no DB-level effect; metadata only).

Backfill + CHECK constraints live in migration 0017 to keep DDL and data
phases separate (PostgreSQL refuses ALTER TABLE + UPDATE on the same table
in the same migration when the table already carries CHECK constraints).
"""

from django.db import migrations, models


SOURCE_CHOICES = [
    ('service', 'Service writer'),
    ('audit_log', 'Backfilled from InvoiceAuditLog timestamp'),
    ('fallback', 'Backfilled from updated_at / created_at fallback'),
    ('unresolved', 'No reliable source — anchor left NULL'),
    ('legacy', 'Existed before provenance tracking was introduced'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0015_invoice_paid_status_requires_paid_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='cancelled_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='paid_at_source',
            field=models.CharField(
                choices=SOURCE_CHOICES, default='service',
                editable=False, max_length=24,
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='confirmed_at_source',
            field=models.CharField(
                choices=SOURCE_CHOICES, default='service',
                editable=False, max_length=24,
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='cancelled_at_source',
            field=models.CharField(
                choices=SOURCE_CHOICES, default='service',
                editable=False, max_length=24,
            ),
        ),
        # editable=False on paid_at is a non-DB attribute. We use
        # SeparateDatabaseAndState with no DB ops to keep model state in sync
        # without ALTER TABLE (which would conflict with the existing CHECK
        # constraint trigger added in migration 0015).
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='invoice',
                    name='paid_at',
                    field=models.DateTimeField(blank=True, editable=False, null=True),
                ),
            ],
            database_operations=[],
        ),
    ]
