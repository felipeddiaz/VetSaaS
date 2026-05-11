"""
Tests for Capa 4 minimal v1 snapshot service.

Covers the rules the user explicitly asked to validate:

  1. Idempotency — running build 3x with the same inputs produces the
     same numbers, the same lifecycle_state, and an empty diff (apart
     from built_at, which advances ONLY on actual change).
  2. Today is rejected — snapshots are never built for today's date.
  3. Freeze logic comes from a single helper (is_bucket_frozen) and is
     respected: provisional inside window, frozen after window, rebuild
     requires --force.
  4. TZ freeze — org_timezone_at_snapshot is captured at build time and
     remains stable across rebuilds.
  5. Multi-tenant isolation — building org A's snapshot never touches
     org B's data.
  6. Corruption visible — when excluded_anchor_missing > 0, the row is
     persisted with lifecycle_state='corrupt' AND a corruption_detected
     audit row is written. The numbers are not silently dropped.
  7. Audit log entries record every state transition (build, rebuild,
     skip_frozen, corruption_detected).
"""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.analytics.models import (
    DailyOrgMetrics, DashboardSnapshotAudit,
    LIFECYCLE_CORRUPT, LIFECYCLE_FROZEN, LIFECYCLE_PROVISIONAL, LIFECYCLE_REBUILT,
)
from apps.analytics.services import (
    TODAY_REJECTED, V1_TABLE_FREEZE_DAYS,
    apply_snapshot, compute_daily_metrics, is_bucket_frozen,
)
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import confirm_invoice, pay_invoice
from apps.medical_records.models import MedicalRecord
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


def _utc_dt(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=dt_timezone.utc)


class _SnapshotFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Snap Org", timezone="UTC")
        cls.other_org = Organization.objects.create(name="Other Org", timezone="UTC")
        cls.user = User.objects.create_user(
            username="snap_admin", password="x", organization=cls.org, role="ADMIN",
        )
        cls.owner = Owner.objects.create(
            name="Snap Owner", phone="5551234567", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="Snap Pet", species="dog", owner=cls.owner, organization=cls.org,
        )
        cls.service = Service.objects.create(
            name="Snap Servicio", base_price=Decimal("100.00"), organization=cls.org,
        )

    def _paid_invoice_on(self, day):
        invoice = Invoice.objects.create(
            owner=self.owner, pet=self.pet, organization=self.org,
            status='draft', invoice_type='direct_sale',
        )
        InvoiceItem.objects.create(
            invoice=invoice, service=self.service,
            description=self.service.name, quantity=1,
            unit_price=self.service.base_price, organization=self.org,
        )
        confirm_invoice(invoice, user=self.user)
        pay_invoice(invoice, user=self.user, payment_method='cash')
        # Force anchors onto the target day for the test.
        Invoice.objects.filter(pk=invoice.pk).update(
            confirmed_at=_utc_dt(day.year, day.month, day.day, 9),
            paid_at=_utc_dt(day.year, day.month, day.day, 14),
        )
        return invoice

    def _appointment_on(self, day, status='done', hh=10):
        return Appointment.objects.create(
            organization=self.org, pet=self.pet, veterinarian=self.user,
            date=day, start_time=time(hh, 0), end_time=time(hh, 30),
            start_datetime=_utc_dt(day.year, day.month, day.day, hh),
            end_datetime=_utc_dt(day.year, day.month, day.day, hh, 30),
            reason="snap test", status=status,
        )


class FreezeHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="FH Org", timezone="UTC")

    def test_future_bucket_never_frozen(self):
        future = date(2099, 1, 1)
        self.assertFalse(is_bucket_frozen('v1_table', future, self.org))

    def test_today_not_frozen(self):
        today = date(2026, 5, 9)
        now = _utc_dt(2026, 5, 9, 12)
        self.assertFalse(is_bucket_frozen('v1_table', today, self.org, now=now))

    def test_yesterday_provisional(self):
        yesterday = date(2026, 5, 8)
        now = _utc_dt(2026, 5, 9, 12)
        # T+1 < V1_TABLE_FREEZE_DAYS (2)
        self.assertFalse(is_bucket_frozen('v1_table', yesterday, self.org, now=now))

    def test_three_days_old_frozen(self):
        old = date(2026, 5, 5)
        now = _utc_dt(2026, 5, 9, 12)
        # T+4 > V1_TABLE_FREEZE_DAYS (2)
        self.assertTrue(is_bucket_frozen('v1_table', old, self.org, now=now))


class IdempotencyTests(_SnapshotFixtureMixin, TestCase):
    def test_three_runs_produce_identical_state(self):
        day = date(2026, 5, 7)
        now = _utc_dt(2026, 5, 9, 12)
        self._paid_invoice_on(day)
        self._appointment_on(day, status='done')

        snap1 = apply_snapshot(self.org, day, now=now)
        built_at_1 = snap1.built_at
        baseline = {f: getattr(snap1, f) for f in (
            'revenue_paid', 'revenue_accrual', 'invoices_paid_count',
            'appointments_total', 'appointments_done', 'appointments_no_show',
            'medical_records_closed', 'lifecycle_state',
        )}

        snap2 = apply_snapshot(self.org, day, now=now)
        for f, v in baseline.items():
            self.assertEqual(getattr(snap2, f), v, msg=f"{f} drifted on run 2")
        self.assertEqual(snap2.built_at, built_at_1,
                         "built_at must NOT advance when there is no change")

        snap3 = apply_snapshot(self.org, day, now=now)
        for f, v in baseline.items():
            self.assertEqual(getattr(snap3, f), v, msg=f"{f} drifted on run 3")
        self.assertEqual(snap3.built_at, built_at_1)

        # Only ONE 'build' audit row should exist after three calls.
        builds = DashboardSnapshotAudit.objects.filter(
            organization=self.org, snapshot_date=day, kind='build',
        ).count()
        self.assertEqual(builds, 1, "Idempotent runs must not log spurious build events")

    def test_change_in_source_produces_diff_audit_row(self):
        day = date(2026, 5, 7)
        now = _utc_dt(2026, 5, 9, 12)
        self._paid_invoice_on(day)
        snap1 = apply_snapshot(self.org, day, now=now)
        first_built = snap1.built_at
        first_revenue = snap1.revenue_paid

        # Add another invoice → revenue should change → snapshot updates.
        self._paid_invoice_on(day)
        snap2 = apply_snapshot(self.org, day, now=now)
        self.assertNotEqual(snap2.revenue_paid, first_revenue)
        self.assertGreater(snap2.built_at, first_built)
        builds = DashboardSnapshotAudit.objects.filter(
            organization=self.org, snapshot_date=day,
        ).count()
        self.assertEqual(builds, 2, "Each value change must emit a new audit row")


class TodayRejectionTests(_SnapshotFixtureMixin, TestCase):
    def test_today_raises_today_rejected(self):
        now = _utc_dt(2026, 5, 9, 12)
        with self.assertRaises(TODAY_REJECTED):
            apply_snapshot(self.org, date(2026, 5, 9), now=now)

    def test_future_raises_today_rejected(self):
        now = _utc_dt(2026, 5, 9, 12)
        with self.assertRaises(TODAY_REJECTED):
            apply_snapshot(self.org, date(2026, 5, 10), now=now)


class FreezeTransitionTests(_SnapshotFixtureMixin, TestCase):
    def test_provisional_inside_window(self):
        day = date(2026, 5, 8)
        now = _utc_dt(2026, 5, 9, 12)
        snap = apply_snapshot(self.org, day, now=now)
        self.assertEqual(snap.lifecycle_state, LIFECYCLE_PROVISIONAL)

    def test_frozen_after_window(self):
        day = date(2026, 5, 1)
        now = _utc_dt(2026, 5, 9, 12)
        snap = apply_snapshot(self.org, day, now=now)
        self.assertEqual(snap.lifecycle_state, LIFECYCLE_FROZEN)

    def test_rebuild_requires_force(self):
        day = date(2026, 5, 1)
        now = _utc_dt(2026, 5, 9, 12)
        first = apply_snapshot(self.org, day, now=now)
        first_built = first.built_at
        # Subsequent run without --force must skip the frozen row.
        second = apply_snapshot(self.org, day, now=now)
        self.assertEqual(second.lifecycle_state, LIFECYCLE_FROZEN)
        self.assertEqual(second.built_at, first_built,
                         "Skipped frozen row must not re-touch built_at")
        skip_audits = DashboardSnapshotAudit.objects.filter(
            organization=self.org, snapshot_date=day, kind='skip_frozen',
        ).count()
        self.assertEqual(skip_audits, 1)

    def test_rebuild_with_force_marks_rebuilt(self):
        day = date(2026, 5, 1)
        now = _utc_dt(2026, 5, 9, 12)
        apply_snapshot(self.org, day, now=now)
        # Mutate source data to force a value change so diff is non-empty.
        self._paid_invoice_on(day)
        third = apply_snapshot(self.org, day, force=True, now=now)
        self.assertEqual(third.lifecycle_state, LIFECYCLE_REBUILT)
        rebuild_audits = DashboardSnapshotAudit.objects.filter(
            organization=self.org, snapshot_date=day, kind='rebuild',
        ).count()
        self.assertGreaterEqual(rebuild_audits, 1)


class TimezoneFreezeTests(_SnapshotFixtureMixin, TestCase):
    def test_org_timezone_captured_at_build(self):
        day = date(2026, 5, 8)
        now = _utc_dt(2026, 5, 9, 12)
        snap = apply_snapshot(self.org, day, now=now)
        self.assertEqual(snap.org_timezone_at_snapshot, 'UTC')

    def test_org_tz_change_does_not_rewrite_history(self):
        day = date(2026, 5, 8)
        now = _utc_dt(2026, 5, 9, 12)
        snap = apply_snapshot(self.org, day, now=now)
        original_tz = snap.org_timezone_at_snapshot

        # Change the org TZ, then re-build the same day.
        self.org.timezone = 'America/Mexico_City'
        self.org.save()
        snap2 = apply_snapshot(self.org, day, now=now)
        # Snapshot row's TZ field is NOT re-written even when called again.
        self.assertEqual(snap2.org_timezone_at_snapshot, original_tz)


class MultiTenantIsolationTests(_SnapshotFixtureMixin, TestCase):
    def test_org_a_snapshot_excludes_org_b_data(self):
        day = date(2026, 5, 8)
        now = _utc_dt(2026, 5, 9, 12)
        # Plant a paid invoice in org B for the same day.
        owner_b = Owner.objects.create(
            name="OB", phone="5559998888", organization=self.other_org,
        )
        pet_b = Pet.objects.create(
            name="PB", species="dog", owner=owner_b, organization=self.other_org,
        )
        svc_b = Service.objects.create(
            name="SB", base_price=Decimal("99.00"), organization=self.other_org,
        )
        admin_b = User.objects.create_user(
            username="admin_b", password="x", organization=self.other_org, role="ADMIN",
        )
        inv_b = Invoice.objects.create(
            owner=owner_b, pet=pet_b, organization=self.other_org,
            status='draft', invoice_type='direct_sale',
        )
        InvoiceItem.objects.create(
            invoice=inv_b, service=svc_b,
            description=svc_b.name, quantity=1, unit_price=svc_b.base_price,
            organization=self.other_org,
        )
        confirm_invoice(inv_b, user=admin_b)
        pay_invoice(inv_b, user=admin_b, payment_method='cash')
        Invoice.objects.filter(pk=inv_b.pk).update(
            confirmed_at=_utc_dt(day.year, day.month, day.day, 9),
            paid_at=_utc_dt(day.year, day.month, day.day, 14),
        )

        # Build snapshot for org A only — must report 0 revenue.
        snap = apply_snapshot(self.org, day, now=now)
        self.assertEqual(snap.revenue_paid, Decimal('0.00'))
        self.assertEqual(snap.invoices_paid_count, 0)
        # No DailyOrgMetrics row should exist for the OTHER org.
        self.assertFalse(
            DailyOrgMetrics.objects.filter(organization=self.other_org).exists()
        )


class CorruptionVisibilityTests(_SnapshotFixtureMixin, TestCase):
    def test_corrupt_marked_when_anchor_missing(self):
        """
        Defensive instrumentation: even though Capa 1 CHECK constraints make
        anchor-missing rows unreachable in production, the snapshot service
        must still mark a snapshot 'corrupt' rather than silently dropping
        the rows. Patch compute_daily_metrics to simulate the corrupted
        result without DDL gymnastics inside the test transaction.
        """
        from unittest.mock import patch
        day = date(2026, 5, 7)
        now = _utc_dt(2026, 5, 9, 12)

        fake_result = {
            'revenue_paid': Decimal('123.00'),
            'revenue_accrual': Decimal('123.00'),
            'invoices_paid_count': 1,
            'appointments_total': 0,
            'appointments_done': 0,
            'appointments_no_show': 0,
            'medical_records_closed': 0,
            'excluded_anchor_missing': 3,
            'provenance_mix': {'paid_at': {'service': 1}, 'confirmed_at': {'service': 1},
                               'closed_at': {}},
        }
        with patch('apps.analytics.services.compute_daily_metrics',
                   return_value=fake_result):
            snap = apply_snapshot(self.org, day, now=now)

        self.assertEqual(snap.lifecycle_state, LIFECYCLE_CORRUPT,
                         "Snapshot with anchor-missing rows MUST be marked corrupt")
        self.assertEqual(snap.excluded_anchor_missing, 3)
        self.assertEqual(snap.revenue_paid, Decimal('123.00'),
                         "Numbers persist for inspection — they are not silently dropped")
        # Audit row of kind corruption_detected must exist.
        self.assertTrue(
            DashboardSnapshotAudit.objects.filter(
                organization=self.org, snapshot_date=day,
                kind='corruption_detected',
            ).exists(),
            "corruption_detected audit row must be written so the failure is visible",
        )

    def test_corrupt_to_clean_transition_logged(self):
        """When a previously-corrupt snapshot becomes clean, lifecycle moves out
        of 'corrupt' and the diff is logged."""
        from unittest.mock import patch
        day = date(2026, 5, 7)
        now = _utc_dt(2026, 5, 9, 12)

        bad = {
            'revenue_paid': Decimal('0.00'), 'revenue_accrual': Decimal('0.00'),
            'invoices_paid_count': 0,
            'appointments_total': 0, 'appointments_done': 0, 'appointments_no_show': 0,
            'medical_records_closed': 0, 'excluded_anchor_missing': 1,
            'provenance_mix': {'paid_at': {}, 'confirmed_at': {}, 'closed_at': {}},
        }
        good = dict(bad, excluded_anchor_missing=0)
        with patch('apps.analytics.services.compute_daily_metrics', return_value=bad):
            snap1 = apply_snapshot(self.org, day, now=now)
        self.assertEqual(snap1.lifecycle_state, LIFECYCLE_CORRUPT)
        with patch('apps.analytics.services.compute_daily_metrics', return_value=good):
            snap2 = apply_snapshot(self.org, day, now=now)
        self.assertNotEqual(snap2.lifecycle_state, LIFECYCLE_CORRUPT)


class ProvenanceMixTests(_SnapshotFixtureMixin, TestCase):
    def test_provenance_captured_in_snapshot(self):
        day = date(2026, 5, 7)
        now = _utc_dt(2026, 5, 9, 12)
        self._paid_invoice_on(day)
        snap = apply_snapshot(self.org, day, now=now)
        self.assertIn('paid_at', snap.provenance_mix)
        self.assertIn('confirmed_at', snap.provenance_mix)
        # Service-written invoice → at least one 'service' entry.
        paid_mix = snap.provenance_mix['paid_at']
        self.assertGreaterEqual(paid_mix.get('service', 0), 1)
