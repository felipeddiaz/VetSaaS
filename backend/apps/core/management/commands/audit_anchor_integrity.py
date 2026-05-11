"""
audit_anchor_integrity — validates that every analytics anchor invariant holds.

Invariants checked:
  Invoice.status='paid'      ⇒ paid_at IS NOT NULL
  Invoice.status='confirmed' ⇒ confirmed_at IS NOT NULL
  Invoice.status='paid'      ⇒ confirmed_at IS NOT NULL
  Invoice.status='cancelled' ⇒ cancelled_at IS NOT NULL
  MedicalRecord.status='closed' ⇒ closed_at IS NOT NULL
  Appointment.status='in_progress' AND created via walk_in flow ⇒ walk_in=True

Also reports provenance distribution per anchor (count by *_source).

Use cases:
  - Pre-snapshot validation: run BEFORE the nightly DailyOrgMetrics job to
    confirm no corrupted rows would be silently bucketed.
  - Post-deploy: catch regressions in service writers.
  - Post-import: validate that bulk ingest set anchors correctly.
  - Post-migration: confirm CHECK constraints did their job.
  - Nightly cron (eventually): emit a metric to monitoring.

Exit codes:
  0  all invariants hold; no unresolved provenance
  1  unresolved-provenance rows present (data warning, no analytics break)
  2  invariant violation present (DB CHECK should have caught this — investigate)

Usage:
  python manage.py audit_anchor_integrity
  python manage.py audit_anchor_integrity --org=12
  python manage.py audit_anchor_integrity --verbose       # sample row details
  python manage.py audit_anchor_integrity --json          # machine-readable
"""
import json
import sys
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count, Q


SAMPLE_SIZE = 5


class Command(BaseCommand):
    help = "Validate analytics anchor invariants across billing, medical_records, appointments."

    def add_arguments(self, parser):
        parser.add_argument('--org', type=int, default=None,
                            help="Restrict to a single organization id.")
        parser.add_argument('--verbose', action='store_true',
                            help="Print sample rows for each finding.")
        parser.add_argument('--json', action='store_true',
                            help="Emit a single JSON object instead of human-readable output.")

    def handle(self, *args, **options):
        from apps.billing.models import Invoice
        from apps.medical_records.models import MedicalRecord
        from apps.appointments.models import Appointment

        org_filter = Q(organization_id=options['org']) if options['org'] else Q()

        findings = []
        provenance = {}

        # ---------- Invariant checks ----------
        invariants = [
            (
                Invoice, 'invoice.paid_status_requires_paid_at',
                Q(status='paid', paid_at__isnull=True),
            ),
            (
                Invoice, 'invoice.confirmed_status_requires_confirmed_at',
                Q(status__in=['confirmed', 'paid'], confirmed_at__isnull=True),
            ),
            (
                Invoice, 'invoice.cancelled_status_requires_cancelled_at',
                Q(status='cancelled', cancelled_at__isnull=True),
            ),
            (
                MedicalRecord, 'medicalrecord.closed_status_requires_closed_at',
                Q(status='closed', closed_at__isnull=True),
            ),
        ]
        for model, name, violating_q in invariants:
            qs = model.objects.filter(violating_q & org_filter)
            count = qs.count()
            sample = list(qs.values('id', 'organization_id', 'status')[:SAMPLE_SIZE]) if count else []
            findings.append({
                'kind': 'invariant_violation',
                'name': name,
                'count': count,
                'sample': sample,
            })

        # ---------- Provenance distribution ----------
        for source_field in ('paid_at_source', 'confirmed_at_source', 'cancelled_at_source'):
            agg = (
                Invoice.objects.filter(org_filter)
                .values(source_field)
                .annotate(c=Count('id'))
                .order_by(source_field)
            )
            provenance[f'invoice.{source_field}'] = {row[source_field]: row['c'] for row in agg}

        agg = (
            MedicalRecord.objects.filter(org_filter)
            .values('closed_at_source')
            .annotate(c=Count('id'))
            .order_by('closed_at_source')
        )
        provenance['medicalrecord.closed_at_source'] = {row['closed_at_source']: row['c'] for row in agg}

        # ---------- Unresolved provenance ----------
        unresolved_q = Q(confirmed_at_source='unresolved') | Q(cancelled_at_source='unresolved')
        unresolved = Invoice.objects.filter(unresolved_q & org_filter)
        unresolved_count = unresolved.count()
        unresolved_sample = list(
            unresolved.values('id', 'organization_id', 'status',
                              'confirmed_at_source', 'cancelled_at_source')[:SAMPLE_SIZE]
        ) if unresolved_count else []

        # ---------- Walk-in suspicious row check ----------
        walk_in_suspect_q = (
            Q(walk_in=False, status__in=['in_progress', 'done'])
            & ~Q(status_changes__from_status='scheduled')
        )
        walk_in_suspect_count = (
            Appointment.objects.filter(walk_in_suspect_q & org_filter).distinct().count()
        )

        # ---------- Output ----------
        violation_total = sum(f['count'] for f in findings if f['kind'] == 'invariant_violation')
        exit_code = 0
        if violation_total > 0:
            exit_code = 2
        elif unresolved_count > 0:
            exit_code = 1

        report = {
            'invariant_findings': findings,
            'provenance_distribution': provenance,
            'unresolved_provenance': {
                'count': unresolved_count,
                'sample': unresolved_sample,
            },
            'walk_in_suspect_count': walk_in_suspect_count,
            'exit_code': exit_code,
        }

        if options['json']:
            self.stdout.write(json.dumps(report, default=str, indent=2))
        else:
            self._print_human(report, verbose=options['verbose'])

        sys.exit(exit_code)

    def _print_human(self, report, verbose):
        self.stdout.write(self.style.MIGRATE_HEADING("Anchor invariant audit"))
        self.stdout.write("")

        violations = [f for f in report['invariant_findings'] if f['count'] > 0]
        if not violations:
            self.stdout.write(self.style.SUCCESS("  ✓ All invariants hold."))
        else:
            for f in violations:
                self.stdout.write(self.style.ERROR(
                    f"  ✗ {f['name']}: {f['count']} violations"
                ))
                if verbose:
                    for row in f['sample']:
                        self.stdout.write(f"      - {row}")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Provenance distribution"))
        for anchor, dist in report['provenance_distribution'].items():
            self.stdout.write(f"  {anchor}: {dist}")
        self.stdout.write("")

        if report['unresolved_provenance']['count']:
            self.stdout.write(self.style.WARNING(
                f"  ! Unresolved provenance: {report['unresolved_provenance']['count']} rows"
            ))
            if verbose:
                for row in report['unresolved_provenance']['sample']:
                    self.stdout.write(f"      - {row}")

        if report['walk_in_suspect_count']:
            self.stdout.write(self.style.WARNING(
                f"  ! Walk-in suspect rows (status in_progress/done with no scheduled history "
                f"but walk_in=False): {report['walk_in_suspect_count']}"
            ))

        self.stdout.write("")
        self.stdout.write(f"Exit code: {report['exit_code']}")
