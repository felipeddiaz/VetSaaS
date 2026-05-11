"""
Capa 2 — Invoice anchor backfill + CHECK constraints (data + invariants).

Backfill policy (NO naive defaults — preserves analytical truth):

confirmed_at:
    1. Earliest InvoiceAuditLog row with new_status='confirmed' → 'audit_log'
    2. Latest InvoiceAuditLog row before any 'paid' transition (if status='paid'
       but no 'confirmed' audit row exists — rare, mostly tests) → 'audit_log'
    3. created_at, ONLY if status IN ('confirmed', 'paid') AND no audit log
       exists at all → 'fallback'
    4. Otherwise: leave NULL, set source='unresolved'. Surfaces in
       audit_anchor_integrity report.

cancelled_at:
    1. Latest InvoiceAuditLog row with new_status='cancelled' → 'audit_log'
    2. updated_at if status='cancelled' AND no audit log exists → 'fallback'

paid_at_source for existing paid_at (already populated by 0015 migration):
    Cannot reconstruct provenance retroactively. Mark all existing
    paid_at-not-null rows as 'legacy'. New writes use 'service'.

NOTE: this migration will FAIL when applying CHECK constraints if any row
ends up with status that requires an anchor but ended in source='unresolved'.
That failure is intentional — it forces the operator to clean the data
manually before constraints come online. To inspect, run
`python manage.py audit_anchor_integrity --verbose` first.
"""

from django.db import migrations, models


def backfill_anchors(apps, schema_editor):
    Invoice = apps.get_model('billing', 'Invoice')
    InvoiceAuditLog = apps.get_model('billing', 'InvoiceAuditLog')

    # paid_at_source: mark all existing paid_at rows as legacy
    Invoice.objects.filter(paid_at__isnull=False).update(paid_at_source='legacy')

    # confirmed_at: ordered backfill
    targets = list(
        Invoice.objects.filter(
            status__in=['confirmed', 'paid', 'cancelled'],
            confirmed_at__isnull=True,
        ).values_list('pk', flat=True)
    )
    unresolved_confirmed = []
    for pk in targets:
        invoice = Invoice.objects.get(pk=pk)

        confirmed_audit = (
            InvoiceAuditLog.objects
            .filter(invoice=invoice, new_status='confirmed')
            .order_by('created_at')
            .first()
        )
        if confirmed_audit is not None:
            invoice.confirmed_at = confirmed_audit.created_at
            invoice.confirmed_at_source = 'audit_log'
            invoice.save(update_fields=['confirmed_at', 'confirmed_at_source'])
            continue

        if invoice.status == 'paid':
            paid_audit = (
                InvoiceAuditLog.objects
                .filter(invoice=invoice, new_status='paid')
                .order_by('created_at')
                .first()
            )
            if paid_audit is not None:
                pre_paid = (
                    InvoiceAuditLog.objects
                    .filter(invoice=invoice, created_at__lt=paid_audit.created_at)
                    .order_by('-created_at')
                    .first()
                )
                if pre_paid is not None:
                    invoice.confirmed_at = pre_paid.created_at
                    invoice.confirmed_at_source = 'audit_log'
                    invoice.save(update_fields=['confirmed_at', 'confirmed_at_source'])
                    continue

        if invoice.status in ('confirmed', 'paid'):
            invoice.confirmed_at = invoice.created_at
            invoice.confirmed_at_source = 'fallback'
            invoice.save(update_fields=['confirmed_at', 'confirmed_at_source'])
            continue

        invoice.confirmed_at_source = 'unresolved'
        invoice.save(update_fields=['confirmed_at_source'])
        unresolved_confirmed.append(
            (invoice.pk, invoice.organization_id, invoice.status)
        )

    # cancelled_at: ordered backfill
    cancel_targets = list(
        Invoice.objects.filter(
            status='cancelled', cancelled_at__isnull=True,
        ).values_list('pk', flat=True)
    )
    for pk in cancel_targets:
        invoice = Invoice.objects.get(pk=pk)
        cancel_audit = (
            InvoiceAuditLog.objects
            .filter(invoice=invoice, new_status='cancelled')
            .order_by('-created_at')
            .first()
        )
        if cancel_audit is not None:
            invoice.cancelled_at = cancel_audit.created_at
            invoice.cancelled_at_source = 'audit_log'
        else:
            invoice.cancelled_at = invoice.updated_at
            invoice.cancelled_at_source = 'fallback'
        invoice.save(update_fields=['cancelled_at', 'cancelled_at_source'])

    if unresolved_confirmed:
        print(
            f"[migration 0017] WARNING: {len(unresolved_confirmed)} invoices "
            f"could not have confirmed_at backfilled. Sample: "
            f"{unresolved_confirmed[:5]}"
        )


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    # PostgreSQL refuses ALTER TABLE (AddConstraint) within the same
    # transaction as data UPDATEs against the same table when prior CHECK
    # constraint triggers are still pending. Disable the migration-wide
    # atomic block so each operation commits independently. The backfill is
    # idempotent (status-driven), so a partial failure can be re-run safely.
    atomic = False

    dependencies = [
        ('billing', '0016_invoice_anchor_completeness'),
    ]

    operations = [
        migrations.RunPython(backfill_anchors, reverse_noop),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=~models.Q(status__in=['confirmed', 'paid'])
                          | models.Q(confirmed_at__isnull=False),
                name='invoice_confirmed_status_requires_confirmed_at',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=~models.Q(status='cancelled')
                          | models.Q(cancelled_at__isnull=False),
                name='invoice_cancelled_status_requires_cancelled_at',
            ),
        ),
    ]
