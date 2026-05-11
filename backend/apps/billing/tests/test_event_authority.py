"""
Anti-regression tests for analytics event-authority (Capa 1 hardening).

These tests enforce the contract documented in
`docs/dashboard-metrics-contract.md §2.7` and the audit findings in
`docs/analytics-schema-audit.md`. They are intentionally narrow: each test
guards a single bypass path that, if reopened, would corrupt analytics
silently.

Failures here mean a code change introduced an analytics lie. Do not silence
without revisiting the contract.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import confirm_invoice, pay_invoice
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


class InvoicePaidAtAuthorityTests(TestCase):
    """`Invoice.status='paid'` must always coincide with `paid_at IS NOT NULL`."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="EA Org", timezone="UTC")
        cls.user = User.objects.create_user(
            username="ea_admin", password="x", organization=cls.org, role="ADMIN",
        )
        cls.owner = Owner.objects.create(
            name="EA Owner", phone="5551112222", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="EA Pet", species="dog", owner=cls.owner, organization=cls.org,
        )
        cls.service = Service.objects.create(
            name="EA Servicio", base_price=Decimal("100.00"), organization=cls.org,
        )

    def _make_confirmed_invoice(self):
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
        invoice.refresh_from_db()
        return invoice

    def test_pay_invoice_service_sets_paid_at(self):
        invoice = self._make_confirmed_invoice()
        result = pay_invoice(invoice, user=self.user, payment_method='cash')
        self.assertEqual(result.status, 'paid')
        self.assertIsNotNone(result.paid_at)

    def test_check_constraint_blocks_paid_without_anchor(self):
        invoice = self._make_confirmed_invoice()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.all_objects.filter(pk=invoice.pk).update(
                    status='paid', paid_at=None,
                )

    def test_pay_invoice_rejects_non_confirmed(self):
        invoice = Invoice.objects.create(
            owner=self.owner, pet=self.pet, organization=self.org,
            status='draft', invoice_type='direct_sale',
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            pay_invoice(invoice, user=self.user, payment_method='cash')

    def test_pay_invoice_rejects_invalid_payment_method(self):
        invoice = self._make_confirmed_invoice()
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            pay_invoice(invoice, user=self.user, payment_method='bitcoin')


class MedicalRecordClosedAtAuthorityTests(TestCase):
    """`MedicalRecord.status='closed'` must always coincide with `closed_at IS NOT NULL`."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="MR EA Org", timezone="UTC")
        cls.user = User.objects.create_user(
            username="mr_ea_user", password="x", organization=cls.org, role="VET",
        )
        cls.owner = Owner.objects.create(
            name="MR EA Owner", phone="5553334444", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="MR EA Pet", species="dog", owner=cls.owner, organization=cls.org,
        )

    def test_save_blocks_closed_without_closed_at(self):
        from apps.medical_records.models import MedicalRecord
        from django.core.exceptions import ValidationError

        mr = MedicalRecord.objects.create(
            pet=self.pet, organization=self.org, veterinarian=self.user,
            diagnosis="x", treatment="y",
        )
        mr.status = MedicalRecord.Status.CLOSED
        mr.closed_at = None
        with self.assertRaises(ValidationError):
            mr.save(update_fields=['status', 'closed_at'])

    def test_check_constraint_blocks_closed_without_anchor(self):
        from apps.medical_records.models import MedicalRecord

        mr = MedicalRecord.objects.create(
            pet=self.pet, organization=self.org, veterinarian=self.user,
            diagnosis="x", treatment="y",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MedicalRecord.all_objects.filter(pk=mr.pk).update(
                    status='closed', closed_at=None,
                )


class AppointmentDeleteAuditAuthorityTests(TestCase):
    """DELETE on an appointment must produce an `AppointmentStatusChange` row."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="AP EA Org", timezone="UTC")
        cls.user = User.objects.create_user(
            username="ap_ea_user", password="x", organization=cls.org, role="ADMIN",
        )
        cls.owner = Owner.objects.create(
            name="AP EA Owner", phone="5557778888", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="AP EA Pet", species="dog", owner=cls.owner, organization=cls.org,
        )

    def test_destroy_creates_status_change_row(self):
        from apps.appointments.models import Appointment, AppointmentStatusChange
        from datetime import date, time
        from rest_framework.test import APIClient

        appt = Appointment.objects.create(
            organization=self.org, pet=self.pet, veterinarian=self.user,
            date=date(2026, 5, 20), start_time=time(10, 0), end_time=time(10, 30),
            reason="anti-regression", status='scheduled',
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.delete(f"/api/appointments/{appt.public_id}/")
        self.assertEqual(response.status_code, 200)

        appt.refresh_from_db()
        self.assertEqual(appt.status, 'canceled')

        change = AppointmentStatusChange.objects.filter(
            appointment=appt, to_status='canceled',
        ).first()
        self.assertIsNotNone(
            change,
            "DELETE /appointments/<id>/ MUST create an AppointmentStatusChange row "
            "(see docs/analytics-schema-audit.md §2.1).",
        )
        self.assertEqual(change.from_status, 'scheduled')
        self.assertEqual(change.changed_by_id, self.user.id)
