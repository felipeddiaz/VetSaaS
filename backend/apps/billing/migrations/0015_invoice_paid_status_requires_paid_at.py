"""
Analytics event-authority hardening (Capa 1).

Añade CHECK constraint a Invoice: si status='paid', paid_at no puede ser NULL.
Bloquea bypasses vía queryset.update() o admin que dejarían rows con
status='paid' AND paid_at IS NULL, corrompiendo silenciosamente las métricas
de revenue cash-basis.

Ver docs/analytics-schema-audit.md §2.15 y docs/dashboard-metrics-contract.md §2.7.

Backfill defensivo previo: si quedaran rows con status='paid' AND paid_at NULL,
les asigna `updated_at` como aproximación. Esto no debería ocurrir en datos
limpios; existe para que la migración no falle al aplicar el constraint.
"""

from django.db import migrations, models


def backfill_paid_at(apps, schema_editor):
    Invoice = apps.get_model('billing', 'Invoice')
    InvoiceAuditLog = apps.get_model('billing', 'InvoiceAuditLog')

    paid_without_anchor = Invoice.all_objects.filter(
        status='paid', paid_at__isnull=True,
    ) if hasattr(Invoice, 'all_objects') else Invoice.objects.filter(
        status='paid', paid_at__isnull=True,
    )

    for invoice in paid_without_anchor:
        audit = InvoiceAuditLog.objects.filter(
            invoice=invoice, new_status='paid',
        ).order_by('-created_at').first()
        invoice.paid_at = audit.created_at if audit else invoice.updated_at
        invoice.save(update_fields=['paid_at'])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0014_service_base_price_positive'),
    ]

    operations = [
        migrations.RunPython(backfill_paid_at, reverse_noop),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=~models.Q(status='paid') | models.Q(paid_at__isnull=False),
                name='invoice_paid_status_requires_paid_at',
            ),
        ),
    ]
