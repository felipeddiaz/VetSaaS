"""
Capa 2 anti-regression tests for full anchor completeness:
- confirmed_at and cancelled_at writers + CHECK constraints
- Provenance fields populated correctly
- bulk operations (queryset.update / bulk_update / raw SQL) cannot
  bypass the CHECK constraints
- Walk-in flag set on creation
- audit_anchor_integrity command exits cleanly on a clean DB
"""
from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.appointments.models import Appointment, AppointmentStatusChange
from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import cancel_invoice, confirm_invoice, pay_invoice
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


class _FixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="AC Org", timezone="UTC")
        cls.user = User.objects.create_user(
            username="ac_admin", password="x", organization=cls.org, role="ADMIN",
        )
        cls.owner = Owner.objects.create(
            name="AC Owner", phone="5559990000", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="AC Pet", species="dog", owner=cls.owner, organization=cls.org,
        )
        cls.service = Service.objects.create(
            name="AC Servicio", base_price=Decimal("50.00"), organization=cls.org,
        )

    def _draft_invoice(self):
        invoice = Invoice.objects.create(
            owner=self.owner, pet=self.pet, organization=self.org,
            status='draft', invoice_type='direct_sale',
        )
        InvoiceItem.objects.create(
            invoice=invoice, service=self.service,
            description=self.service.name, quantity=1,
            unit_price=self.service.base_price, organization=self.org,
        )
        return invoice


class ConfirmedAtAuthorityTests(_FixtureMixin, TestCase):
    def test_confirm_invoice_sets_confirmed_at_and_source(self):
        invoice = self._draft_invoice()
        confirm_invoice(invoice, user=self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'confirmed')
        self.assertIsNotNone(invoice.confirmed_at)
        self.assertEqual(invoice.confirmed_at_source, 'service')

    def test_pay_invoice_preserves_confirmed_at(self):
        invoice = self._draft_invoice()
        confirm_invoice(invoice, user=self.user)
        confirmed_at_before = Invoice.objects.get(pk=invoice.pk).confirmed_at
        pay_invoice(invoice, user=self.user, payment_method='cash')
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'paid')
        self.assertEqual(invoice.confirmed_at, confirmed_at_before)
        self.assertIsNotNone(invoice.paid_at)
        self.assertEqual(invoice.paid_at_source, 'service')

    def test_check_blocks_confirmed_status_without_anchor(self):
        invoice = self._draft_invoice()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.all_objects.filter(pk=invoice.pk).update(
                    status='confirmed', confirmed_at=None,
                )

    def test_check_blocks_paid_status_without_confirmed_anchor(self):
        # status='paid' implies confirmed_at must exist (per CHECK)
        invoice = self._draft_invoice()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                from django.utils import timezone
                Invoice.all_objects.filter(pk=invoice.pk).update(
                    status='paid', paid_at=timezone.now(), confirmed_at=None,
                )


class CancelledAtAuthorityTests(_FixtureMixin, TestCase):
    def test_cancel_draft_invoice_sets_cancelled_at_and_source(self):
        invoice = self._draft_invoice()
        cancel_invoice(invoice, user=self.user, notes='test')
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'cancelled')
        self.assertIsNotNone(invoice.cancelled_at)
        self.assertEqual(invoice.cancelled_at_source, 'service')

    def test_cancel_confirmed_invoice_preserves_confirmed_at(self):
        invoice = self._draft_invoice()
        confirm_invoice(invoice, user=self.user)
        confirmed_at_before = Invoice.objects.get(pk=invoice.pk).confirmed_at
        cancel_invoice(invoice, user=self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'cancelled')
        self.assertEqual(invoice.confirmed_at, confirmed_at_before)
        self.assertIsNotNone(invoice.cancelled_at)

    def test_check_blocks_cancelled_without_anchor(self):
        invoice = self._draft_invoice()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.all_objects.filter(pk=invoice.pk).update(
                    status='cancelled', cancelled_at=None,
                )


class BulkBypassResistanceTests(_FixtureMixin, TestCase):
    """The CHECK constraints must survive every bulk path."""

    def test_bulk_update_cannot_bypass_paid_invariant(self):
        invoice = self._draft_invoice()
        confirm_invoice(invoice, user=self.user)
        invoice.refresh_from_db()
        invoice.status = 'paid'
        invoice.paid_at = None
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.all_objects.bulk_update([invoice], ['status', 'paid_at'])

    def test_raw_sql_cannot_bypass_paid_invariant(self):
        invoice = self._draft_invoice()
        confirm_invoice(invoice, user=self.user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE billing_invoice SET status='paid', paid_at=NULL WHERE id=%s",
                    [invoice.pk],
                )

    def test_failed_invariant_rolls_back_transaction(self):
        # If the violating UPDATE is in an atomic block alongside a legitimate
        # write, the legitimate write must roll back too.
        invoice = self._draft_invoice()
        confirm_invoice(invoice, user=self.user)
        invoice.refresh_from_db()
        original_notes = invoice.notes
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.all_objects.filter(pk=invoice.pk).update(notes='legit edit')
                Invoice.all_objects.filter(pk=invoice.pk).update(
                    status='cancelled', cancelled_at=None,
                )
        invoice.refresh_from_db()
        self.assertEqual(invoice.notes, original_notes)


class WalkInFieldTests(_FixtureMixin, TestCase):
    def test_walk_in_view_sets_flag_true(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)

        # Add walk-in permission to admin's role (admin has wildcard via RBAC)
        response = client.post('/api/appointments/walk-in/', {
            'pet': self.pet.pk,
            'veterinarian': self.user.pk,
            'reason': 'Walk-in test',
        }, format='json')
        # Walk-in requires the vet to have appointment.create_walkin permission;
        # in this test setup the admin user has wildcard so it should pass.
        self.assertIn(response.status_code, (200, 201),
                      msg=f"unexpected response {response.status_code}: {response.content}")
        appt_pk = response.data.get('id') or response.data.get('public_id')
        if isinstance(appt_pk, str):
            appt = Appointment.objects.get(public_id=appt_pk)
        else:
            appt = Appointment.objects.get(pk=appt_pk)
        self.assertTrue(appt.walk_in)

    def test_regular_appointment_has_walk_in_false(self):
        appt = Appointment.objects.create(
            organization=self.org, pet=self.pet, veterinarian=self.user,
            date=date(2026, 6, 1), start_time=time(9, 0), end_time=time(9, 30),
            reason="regular", status='scheduled',
        )
        self.assertFalse(appt.walk_in)


class AuditAnchorIntegrityCommandTests(_FixtureMixin, TestCase):
    def test_command_succeeds_on_clean_db(self):
        # Confirm + pay one invoice so distribution is non-empty.
        invoice = self._draft_invoice()
        confirm_invoice(invoice, user=self.user)
        pay_invoice(invoice, user=self.user, payment_method='cash')

        out = StringIO()
        with self.assertRaises(SystemExit) as cm:
            call_command('audit_anchor_integrity', stdout=out)
        self.assertEqual(cm.exception.code, 0)
        self.assertIn('All invariants hold', out.getvalue())

    def test_command_json_mode(self):
        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command('audit_anchor_integrity', '--json', stdout=out)
        import json as _json
        data = _json.loads(out.getvalue())
        self.assertIn('invariant_findings', data)
        self.assertIn('provenance_distribution', data)
        self.assertIn('exit_code', data)
