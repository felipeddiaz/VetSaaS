"""
Dashboard consistency tests — cross-endpoint contract validation.

T11: Series ↔ Summary temporal KPI parity.
Plus structural smoke tests for metrics_schema_version and source fields.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import confirm_invoice, pay_invoice
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User

FINANCIAL_SERIES_URL = '/api/v1/dashboard/financial/series/'
SUMMARY_URL = '/api/v1/dashboard/summary/'


def _seed_roles(org):
    wildcard, _ = Permission.objects.get_or_create(code="*.*")
    perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}
    out = {}
    for name, codes in PERMISSIONS.items():
        if name == "ADMIN_SAAS":
            continue
        role, _ = Role.objects.get_or_create(
            name=name, organization=org, defaults={"is_system_role": True},
        )
        role.permissions.set(
            [wildcard] if "*.*" in codes
            else [perms_map[c] for c in codes if c in perms_map]
        )
        out[name] = role
    return out


def _make_user(username, org, role_name):
    u = User.objects.create_user(
        username=username, password="x", organization=org, role=role_name,
    )
    roles = _seed_roles(org)
    UserRole.objects.get_or_create(user=u, role=roles[role_name])
    return u


class DashboardConsistencyTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Consistency Org", timezone="UTC")
        cls.admin = _make_user("cons_admin", cls.org, "ADMIN")
        cls.vet = _make_user("cons_vet", cls.org, "VET")

        cls.owner = Owner.objects.create(
            name="Owner Consistency", phone="5550000001", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="Pet Consistency", species="canino", owner=cls.owner,
            organization=cls.org,
        )
        cls.service = Service.objects.create(
            name="Consulta Consistency", base_price=Decimal("150.00"),
            organization=cls.org,
        )

        cls.today = timezone.localtime(timezone.now()).date()

    def setUp(self):
        cache.clear()

    # ------------------------------------------------------------------
    # T11: Validate summary and series have consistent shape (NOT revenue parity).
    #      The true parity gate (snapshot == live recompute bit-exact) lives in
    #      analytics/tests/test_snapshot_v1.py::ReplayParityTests.test_historical_replay_parity
    # ------------------------------------------------------------------
    def test_summary_and_series_have_consistent_shape_today(self):
        """Validates shape consistency between /summary/ and /series/ endpoints.
        The summary does not expose revenue_paid — this test is structural, not a
        financial parity gate."""
        invoice = Invoice.objects.create(
            owner=self.owner, pet=self.pet, organization=self.org,
            status='draft', invoice_type='direct_sale',
        )
        InvoiceItem.objects.create(
            invoice=invoice, service=self.service,
            description=self.service.name, quantity=2,
            unit_price=self.service.base_price, organization=self.org,
        )
        confirm_invoice(invoice, user=self.admin)
        invoice.refresh_from_db()
        pay_invoice(invoice, user=self.admin, payment_method='cash')
        invoice.refresh_from_db()
        expected_revenue = invoice.total

        self.client.force_authenticate(self.admin)
        r = self.client.get(
            f'{FINANCIAL_SERIES_URL}?include_today=true'
            f'&from={self.today.isoformat()}&to={self.today.isoformat()}'
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(r.data['today'])
        self.assertEqual(r.data['today']['source'], 'live')
        series_revenue = r.data['today']['metrics']['revenue_paid']
        self.assertEqual(series_revenue, str(expected_revenue))

        r2 = self.client.get(SUMMARY_URL)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertIn('kpis', r2.data)
        self.assertIn('source', r2.data)
        self.assertEqual(r2.data['source'], 'live_summary')

    # ------------------------------------------------------------------
    # Structural: summary carries metrics_schema_version and source
    # ------------------------------------------------------------------
    def test_summary_response_has_schema_version_and_source(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('metrics_schema_version', r.data)
        self.assertIn('source', r.data)
        self.assertEqual(r.data['metrics_schema_version'], 1)
        self.assertIsInstance(r.data['metrics_schema_version'], int)

    # ------------------------------------------------------------------
    # Series today payload carries source='live'
    # ------------------------------------------------------------------
    def test_series_today_has_source_live(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(
            f'{FINANCIAL_SERIES_URL}?include_today=true'
            f'&from={self.today.isoformat()}&to={self.today.isoformat()}'
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(r.data['today'])
        self.assertEqual(r.data['today']['source'], 'live')
        self.assertIsNone(r.data['today']['lifecycle_state'])

    # ------------------------------------------------------------------
    # Summary source field equals 'live_summary'
    # ------------------------------------------------------------------
    def test_summary_source_is_live_summary(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['source'], 'live_summary')
