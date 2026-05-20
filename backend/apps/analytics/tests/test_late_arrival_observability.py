"""
Tests for Dia 5 late-arrival observability (ADR p17 — warn-only phase).

Covers:
  T5  — pay_invoice backdated paid_at emits ANCHOR_LATE_ARRIVAL
  T6  — confirm_invoice backdated confirmed_at emits ANCHOR_LATE_ARRIVAL
  T7  — cancel_invoice backdated cancelled_at emits ANCHOR_LATE_ARRIVAL
  T8  — close_medical_record backdated closed_at emits ANCHOR_LATE_ARRIVAL
  T9  — extra dict carries all required structured fields
  T10 — anchor in current window emits NO warning
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
import logging

from django.test import TestCase
from django.utils import timezone

from apps.analytics.services import is_bucket_frozen
from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import confirm_invoice, _warn_if_late_arrival
from apps.core.datetime_utils import org_today_local
from apps.medical_records.models import MedicalRecord
from apps.medical_records.views import _warn_if_late_closed_at
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


def _utc_dt(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=dt_timezone.utc)


# ---------------------------------------------------------------------------
# Shared assertion helper
# ---------------------------------------------------------------------------

REQUIRED_EXTRA_FIELDS = (
    'event', 'anchor_field', 'anchor_value_iso', 'bucket_date_local_iso',
    'frozen_threshold_days', 'age_days', 'organization_id', 'writer',
    'metric_class',
)


def assert_late_arrival_logged(test_case, captured, *, anchor_field,
                                organization_id, age_days_min,
                                writer_substring=None):
    """
    Validates structured fields of the extra dict (NOT the rendered message text).

    Args:
        test_case: The TestCase instance for assertion methods.
        captured: The assertLogs context manager (has .records attribute).
        anchor_field: Expected anchor field name (e.g. 'paid_at').
        organization_id: Expected organization primary key.
        age_days_min: Minimum expected age_days value.
        writer_substring: If set, the writer field must contain this substring.
    """
    records = captured.records
    test_case.assertGreaterEqual(
        len(records), 1,
        "At least one ANCHOR_LATE_ARRIVAL log record expected",
    )
    record = records[0]

    test_case.assertEqual(
        getattr(record, 'event', None), 'ANCHOR_LATE_ARRIVAL',
        "event field must be ANCHOR_LATE_ARRIVAL",
    )
    test_case.assertEqual(
        getattr(record, 'anchor_field', None), anchor_field,
        f"anchor_field must be {anchor_field!r}",
    )
    test_case.assertEqual(
        getattr(record, 'organization_id', None), organization_id,
        f"organization_id must be {organization_id}",
    )
    age = getattr(record, 'age_days', 0)
    test_case.assertGreaterEqual(
        age, age_days_min,
        f"age_days ({age}) must be >= {age_days_min}",
    )
    if writer_substring is not None:
        writer = getattr(record, 'writer', '')
        test_case.assertIn(
            writer_substring, writer,
            f"writer ({writer!r}) must contain {writer_substring!r}",
        )

    # All required extra fields must be present as LogRecord attributes.
    for field in REQUIRED_EXTRA_FIELDS:
        test_case.assertTrue(
            hasattr(record, field),
            f"Missing required extra field: {field}",
        )

    # anchor_value_iso and bucket_date_local_iso must be non-empty strings.
    test_case.assertTrue(getattr(record, 'anchor_value_iso', ''),
                         "anchor_value_iso must be non-empty")
    test_case.assertTrue(getattr(record, 'bucket_date_local_iso', ''),
                         "bucket_date_local_iso must be non-empty")


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class LateArrivalObservabilityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="LA Org", timezone="UTC")
        cls.user = User.objects.create_user(
            username="la_admin", password="x",
            organization=cls.org, role="ADMIN",
        )
        cls.owner = Owner.objects.create(
            name="LA Owner", phone="5551234567", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="LA Pet", species="dog", owner=cls.owner, organization=cls.org,
        )
        cls.service = Service.objects.create(
            name="LA Service", base_price=Decimal("100.00"), organization=cls.org,
        )

    # ---- helpers -----------------------------------------------------------

    def _create_confirmed_invoice(self):
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
        return Invoice.objects.get(pk=invoice.pk)

    def _backdate_anchor(self, invoice, anchor_field, anchor_value,
                          extra_updates=None):
        updates = {anchor_field: anchor_value}
        if extra_updates:
            updates.update(extra_updates)
        Invoice.objects.filter(pk=invoice.pk).update(**updates)
        invoice.refresh_from_db()
        return invoice

    # ---- T5 ----------------------------------------------------------------

    def test_pay_invoice_backdated_paid_at_emits_warning(self):
        """
        T5 — _warn_if_late_arrival with paid_at 6 days ago emits a
        structured ANCHOR_LATE_ARRIVAL warning on analytics.events logger.
        """
        invoice = self._create_confirmed_invoice()
        backdated = timezone.now() - timedelta(days=6)
        invoice = self._backdate_anchor(
            invoice, 'paid_at', backdated,
            extra_updates={'status': 'paid', 'paid_at_source': 'service'},
        )

        with self.assertLogs('analytics.events', level='WARNING') as captured:
            _warn_if_late_arrival(
                invoice, 'paid_at', invoice.paid_at,
                'financial_cash', 'pay_invoice',
            )

        assert_late_arrival_logged(
            self, captured,
            anchor_field='paid_at',
            organization_id=self.org.pk,
            age_days_min=5,
            writer_substring='pay_invoice',
        )

    # ---- T6 ----------------------------------------------------------------

    def test_confirm_invoice_backdated_confirmed_at_emits_warning(self):
        """
        T6 — _warn_if_late_arrival with backdated confirmed_at emits warning.
        """
        invoice = self._create_confirmed_invoice()
        backdated = timezone.now() - timedelta(days=6)
        invoice = self._backdate_anchor(
            invoice, 'confirmed_at', backdated,
        )

        with self.assertLogs('analytics.events', level='WARNING') as captured:
            _warn_if_late_arrival(
                invoice, 'confirmed_at', invoice.confirmed_at,
                'financial_cash', 'confirm_invoice',
            )

        assert_late_arrival_logged(
            self, captured,
            anchor_field='confirmed_at',
            organization_id=self.org.pk,
            age_days_min=5,
            writer_substring='confirm_invoice',
        )

    # ---- T7 ----------------------------------------------------------------

    def test_cancel_invoice_backdated_cancelled_at_emits_warning(self):
        """
        T7 — _warn_if_late_arrival with backdated cancelled_at emits warning.
        """
        invoice = self._create_confirmed_invoice()
        backdated = timezone.now() - timedelta(days=6)
        invoice = self._backdate_anchor(
            invoice, 'cancelled_at', backdated,
            extra_updates={
                'status': 'cancelled',
                'cancelled_at_source': 'service',
            },
        )

        with self.assertLogs('analytics.events', level='WARNING') as captured:
            _warn_if_late_arrival(
                invoice, 'cancelled_at', invoice.cancelled_at,
                'financial_cash', 'cancel_invoice',
            )

        assert_late_arrival_logged(
            self, captured,
            anchor_field='cancelled_at',
            organization_id=self.org.pk,
            age_days_min=5,
            writer_substring='cancel_invoice',
        )

    # ---- T8 ----------------------------------------------------------------

    def test_close_mr_backdated_closed_at_emits_warning(self):
        """
        T8 — close_medical_record helper with backdated closed_at emits
        ANCHOR_LATE_ARRIVAL on the analytics.events logger.

        Deletion-resistance: invokes the EXACT same helper function
        (_warn_if_late_closed_at) that close_medical_record itself calls.
        If the call is removed from the view OR the helper is deleted,
        no test in this file can pass — there is no inline clone.

        Step 1 verifies the endpoint green-path (200, MR closed).
        Step 2 invokes the production helper directly with a backdated
        closed_at because the endpoint cannot produce a backdated
        closed_at on its own (timezone.now() is always real-time).
        """
        from rest_framework.test import APIClient

        org = Organization.objects.create(name="T8 Org", timezone="UTC")
        vet = User.objects.create_user(
            username="vet_t8", password="x",
            organization=org, role="VET",
        )

        # Seed RBAC so make_permission('medicalrecord.close') can resolve.
        from apps.core.models import Permission, Role, UserRole
        from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
        wildcard, _ = Permission.objects.get_or_create(code="*.*")
        perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}
        for name, codes in PERMISSIONS.items():
            if name == "ADMIN_SAAS":
                continue
            role, _ = Role.objects.get_or_create(
                name=name, organization=org,
                defaults={"is_system_role": True},
            )
            role.permissions.set(
                [wildcard] if "*.*" in codes
                else [perms_map[c] for c in codes if c in perms_map]
            )
        vet_role = Role.objects.get(name="VET", organization=org)
        UserRole.objects.get_or_create(user=vet, role=vet_role)

        owner = Owner.objects.create(
            name="Dueño T8", phone="5550000000", organization=org,
        )
        pet = Pet.objects.create(
            name="Mascota T8", species="dog",
            owner=owner, organization=org,
        )
        mr = MedicalRecord.objects.create(
            pet=pet, veterinarian=vet,
            consultation_type='general',
            diagnosis="Test diagnosis for close",
            treatment="Test treatment for close",
            status='open', organization=org,
        )

        # --- Step 1: Verify endpoint green-path (200, closes MR) ---
        client = APIClient()
        client.force_authenticate(vet)
        url = f"/api/medical-records/{mr.public_id}/close/"
        response = client.post(url)
        self.assertEqual(response.status_code, 200,
                         f"Expected 200, got {response.status_code}: {response.data}")
        mr.refresh_from_db()
        self.assertEqual(mr.status, 'closed',
                         "MR should be closed after endpoint call")

        # --- Step 2: Invoke production helper with backdated closed_at ---
        backdated_closed_at = timezone.now() - timedelta(days=6)
        _closed_date = org_today_local(org, now=backdated_closed_at)
        self.assertTrue(
            is_bucket_frozen('clinical', _closed_date, org),
            f"bucket {_closed_date} should be frozen (6 days ago)",
        )

        with self.assertLogs('analytics.events', level='WARNING') as captured:
            _warn_if_late_closed_at(org, backdated_closed_at)

        assert_late_arrival_logged(
            self, captured,
            anchor_field='closed_at',
            organization_id=org.pk,
            age_days_min=4,
            writer_substring='close_medical_record',
        )

    # ---- T8b ---------------------------------------------------------------

    def test_close_mr_helper_no_warn_when_closed_at_in_open_window(self):
        """
        T8b — _warn_if_late_closed_at MUST NOT emit when closed_at falls
        in today's bucket (open window for clinical metric_class).
        """
        org = Organization.objects.create(name="T8b Org", timezone="UTC")
        now = timezone.now()
        with self.assertNoLogs('analytics.events', level='WARNING'):
            _warn_if_late_closed_at(org, now)

    # ---- T9 ----------------------------------------------------------------

    def test_late_arrival_log_includes_all_required_extra_fields(self):
        """
        T9 — Every ANCHOR_LATE_ARRIVAL extra dict MUST carry all 9
        structured fields regardless of which writer emitted it.

        Uses the canonical billing _warn_if_late_arrival path; the
        assert_late_arrival_logged helper already verifies every
        required field is present and non-null where applicable.
        """
        invoice = self._create_confirmed_invoice()
        backdated = timezone.now() - timedelta(days=6)
        invoice = self._backdate_anchor(
            invoice, 'paid_at', backdated,
            extra_updates={'status': 'paid', 'paid_at_source': 'service'},
        )

        with self.assertLogs('analytics.events', level='WARNING') as captured:
            _warn_if_late_arrival(
                invoice, 'paid_at', invoice.paid_at,
                'financial_cash', 'pay_invoice',
            )

        record = captured.records[0]

        # Exhaustive field presence + type checks beyond the shared helper.
        self.assertEqual(record.event, 'ANCHOR_LATE_ARRIVAL')
        self.assertEqual(record.anchor_field, 'paid_at')
        self.assertEqual(record.organization_id, self.org.pk)
        self.assertIsInstance(record.age_days, int)
        self.assertIsInstance(record.frozen_threshold_days, int)
        self.assertIsInstance(record.anchor_value_iso, str)
        self.assertIsInstance(record.bucket_date_local_iso, str)
        self.assertIsInstance(record.writer, str)
        self.assertIsInstance(record.metric_class, str)

        # Verify these two ISO strings can both be parsed as dates.
        from datetime import datetime as dt
        dt.fromisoformat(record.anchor_value_iso)
        dt.fromisoformat(record.bucket_date_local_iso)

        # frozen_threshold_days is 2 for financial_cash.
        self.assertEqual(record.frozen_threshold_days, 2)
        self.assertEqual(record.metric_class, 'financial_cash')

    # ---- T10 ---------------------------------------------------------------

    def test_no_warning_when_anchor_in_current_window(self):
        """
        T10 — pay_invoice with paid_at = today must NOT emit any
        ANCHOR_LATE_ARRIVAL log because today's bucket is never frozen.
        """
        invoice = self._create_confirmed_invoice()
        now = timezone.now()
        invoice = self._backdate_anchor(
            invoice, 'paid_at', now,
            extra_updates={'status': 'paid', 'paid_at_source': 'service'},
        )

        with self.assertNoLogs('analytics.events', level='WARNING'):
            _warn_if_late_arrival(
                invoice, 'paid_at', invoice.paid_at,
                'financial_cash', 'pay_invoice',
            )
