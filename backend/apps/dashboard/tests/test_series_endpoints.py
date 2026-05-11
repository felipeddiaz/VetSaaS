"""
Capa 5 read endpoint tests (JSON-first; no UI yet).

Validates:
- Every datapoint carries explicit source ('snapshot'|'live') and
  lifecycle_state.
- Today is always source='live', lifecycle_state=null, computed via the
  same compute_daily_metrics service used by the snapshot job.
- Snapshot rows with lifecycle_state='corrupt' are filtered out
  (surfaced via /analytics-health/, never via dashboard endpoints).
- Days with no snapshot yet appear as lifecycle_state='missing' with
  zeroed metrics + a `notes` entry — never silently omitted.
- Cardinality limit (365 days) is enforced at the view layer with
  a structured 400 + meta.
- RBAC:
    operations  → ASSISTANT, VET, ADMIN
    financial   → ADMIN only (ASSISTANT and VET get 403)
- Tenant isolation: org A's response never includes org B's data.
- Decimal fields render as strings (no float drift in JSON).
"""
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

from rest_framework.test import APIClient, APITestCase

from apps.analytics.models import DailyOrgMetrics, LIFECYCLE_CORRUPT, LIFECYCLE_FROZEN
from apps.analytics.services import apply_snapshot
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import confirm_invoice, pay_invoice
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


def _seed_roles(org):
    wildcard, _ = Permission.objects.get_or_create(code="*.*")
    perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}
    out = {}
    for name, codes in PERMISSIONS.items():
        if name == "ADMIN_SAAS":
            continue
        role, _ = Role.objects.get_or_create(name=name, organization=org, defaults={"is_system_role": True})
        role.permissions.set([wildcard] if "*.*" in codes else [perms_map[c] for c in codes if c in perms_map])
        out[name] = role
    return out


def _make_user(username, org, role_name):
    u = User.objects.create_user(username=username, password="x", organization=org, role=role_name)
    roles = _seed_roles(org)
    UserRole.objects.get_or_create(user=u, role=roles[role_name])
    return u


def _utc_dt(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=dt_timezone.utc)


class _FixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="DS Org", timezone="UTC")
        cls.other_org = Organization.objects.create(name="DS Other", timezone="UTC")
        cls.admin = _make_user("ds_admin", cls.org, "ADMIN")
        cls.vet = _make_user("ds_vet", cls.org, "VET")
        cls.asst = _make_user("ds_asst", cls.org, "ASSISTANT")

    def _seed_snapshot(self, day, *, lifecycle=LIFECYCLE_FROZEN, **fields):
        return DailyOrgMetrics.objects.create(
            organization=self.org, date=day,
            org_timezone_at_snapshot='UTC',
            lifecycle_state=lifecycle,
            metrics_schema_version=1,
            **fields,
        )


class OperationsSeriesTests(_FixtureMixin, APITestCase):
    def test_default_range_30d_with_today_live(self):
        client = APIClient()
        client.force_authenticate(user=self.vet)
        r = client.get('/api/v1/dashboard/operations/series/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('range', r.data)
        self.assertIn('series', r.data)
        self.assertIn('today', r.data)
        # Today payload always source=live, lifecycle null.
        self.assertEqual(r.data['today']['source'], 'live')
        self.assertIsNone(r.data['today']['lifecycle_state'])

    def test_assistant_can_access_operations(self):
        client = APIClient()
        client.force_authenticate(user=self.asst)
        r = client.get('/api/v1/dashboard/operations/series/')
        self.assertEqual(r.status_code, 200)

    def test_admin_can_access_operations(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        r = client.get('/api/v1/dashboard/operations/series/')
        self.assertEqual(r.status_code, 200)

    def test_anonymous_rejected(self):
        r = APIClient().get('/api/v1/dashboard/operations/series/')
        self.assertIn(r.status_code, (401, 403))

    def test_snapshot_lifecycle_state_exposed(self):
        client = APIClient()
        client.force_authenticate(user=self.vet)
        day = date(2026, 4, 1)
        self._seed_snapshot(
            day, appointments_total=5, appointments_done=3,
            appointments_no_show=1, medical_records_closed=2,
        )
        r = client.get(f'/api/v1/dashboard/operations/series/?from={day.isoformat()}&to={day.isoformat()}&include_today=false')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['series']), 1)
        dp = r.data['series'][0]
        self.assertEqual(dp['source'], 'snapshot')
        self.assertEqual(dp['lifecycle_state'], LIFECYCLE_FROZEN)
        self.assertEqual(dp['metrics']['appointments_total'], 5)

    def test_corrupt_snapshot_excluded(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        day = date(2026, 4, 2)
        self._seed_snapshot(
            day, lifecycle=LIFECYCLE_CORRUPT,
            appointments_total=99, appointments_done=99,
            appointments_no_show=99, medical_records_closed=99,
            excluded_anchor_missing=3,
        )
        r = client.get(f'/api/v1/dashboard/operations/series/?from={day.isoformat()}&to={day.isoformat()}&include_today=false')
        self.assertEqual(r.status_code, 200)
        # Corrupt row is excluded — day appears as 'missing' with zeros.
        dp = r.data['series'][0]
        self.assertEqual(dp['lifecycle_state'], 'missing')
        self.assertEqual(dp['metrics']['appointments_total'], 0)

    def test_missing_day_marked_and_noted(self):
        client = APIClient()
        client.force_authenticate(user=self.vet)
        day = date(2026, 4, 3)
        r = client.get(f'/api/v1/dashboard/operations/series/?from={day.isoformat()}&to={day.isoformat()}&include_today=false')
        dp = r.data['series'][0]
        self.assertEqual(dp['source'], 'snapshot')
        self.assertEqual(dp['lifecycle_state'], 'missing')
        self.assertTrue(any('no snapshot yet' in n for n in r.data['notes']))


class FinancialSeriesRBACTests(_FixtureMixin, APITestCase):
    def test_admin_can_access(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        r = client.get('/api/v1/dashboard/financial/series/')
        self.assertEqual(r.status_code, 200)

    def test_vet_forbidden(self):
        client = APIClient()
        client.force_authenticate(user=self.vet)
        r = client.get('/api/v1/dashboard/financial/series/')
        self.assertEqual(r.status_code, 403)

    def test_assistant_forbidden(self):
        client = APIClient()
        client.force_authenticate(user=self.asst)
        r = client.get('/api/v1/dashboard/financial/series/')
        self.assertEqual(r.status_code, 403)

    def test_revenue_rendered_as_string_not_float(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        day = date(2026, 4, 4)
        self._seed_snapshot(
            day, revenue_paid=Decimal('1234.56'),
            revenue_accrual=Decimal('1234.56'),
            invoices_paid_count=2,
        )
        r = client.get(f'/api/v1/dashboard/financial/series/?from={day.isoformat()}&to={day.isoformat()}&include_today=false')
        dp = r.data['series'][0]
        self.assertEqual(dp['metrics']['revenue_paid'], '1234.56')
        self.assertIsInstance(dp['metrics']['revenue_paid'], str)


class CardinalityLimitTests(_FixtureMixin, APITestCase):
    def test_range_over_365d_rejected(self):
        client = APIClient()
        client.force_authenticate(user=self.vet)
        r = client.get('/api/v1/dashboard/operations/series/?from=2024-01-01&to=2026-01-01')
        self.assertEqual(r.status_code, 400)
        self.assertIn('max_range_days', r.data['meta'])

    def test_invalid_date_format_rejected(self):
        client = APIClient()
        client.force_authenticate(user=self.vet)
        r = client.get('/api/v1/dashboard/operations/series/?from=not-a-date')
        self.assertEqual(r.status_code, 400)

    def test_inverted_range_rejected(self):
        client = APIClient()
        client.force_authenticate(user=self.vet)
        r = client.get('/api/v1/dashboard/operations/series/?from=2026-05-01&to=2026-04-01')
        self.assertEqual(r.status_code, 400)


class TenantIsolationTests(_FixtureMixin, APITestCase):
    def test_other_org_snapshots_not_returned(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        day = date(2026, 4, 5)
        # Plant a snapshot for OTHER org with very loud values.
        DailyOrgMetrics.objects.create(
            organization=self.other_org, date=day,
            org_timezone_at_snapshot='UTC',
            lifecycle_state=LIFECYCLE_FROZEN,
            metrics_schema_version=1,
            revenue_paid=Decimal('999999.99'),
            revenue_accrual=Decimal('999999.99'),
            invoices_paid_count=999,
        )
        r = client.get(f'/api/v1/dashboard/financial/series/?from={day.isoformat()}&to={day.isoformat()}&include_today=false')
        dp = r.data['series'][0]
        # Should be 'missing' for org A — not the OTHER org's row.
        self.assertEqual(dp['lifecycle_state'], 'missing')
        self.assertEqual(dp['metrics']['revenue_paid'], '0.00')
        self.assertNotIn('999', dp['metrics']['revenue_paid'])


class IncludeTodayParamTests(_FixtureMixin, APITestCase):
    def test_include_today_false_excludes_today(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        r = client.get('/api/v1/dashboard/financial/series/?include_today=false')
        self.assertIsNone(r.data['today'])

    def test_include_today_true_default(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        r = client.get('/api/v1/dashboard/financial/series/')
        self.assertIsNotNone(r.data['today'])
        self.assertEqual(r.data['today']['source'], 'live')
