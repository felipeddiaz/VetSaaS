from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import tag
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.appointments.models import Appointment
from apps.billing.models import Invoice
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.inventory.models import Presentation, Product
from apps.medical_records.models import MedicalRecord
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User

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


class DashboardSummaryTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Summary Org", timezone="UTC")
        cls.admin = _make_user("sum_admin", cls.org, "ADMIN")
        cls.vet = _make_user("sum_vet", cls.org, "VET")
        cls.assistant = _make_user("sum_ast", cls.org, "ASSISTANT")

        cls.owner = Owner.objects.create(
            name="Dueño Summary", phone="5559999999", organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="Firulais", species="canino", owner=cls.owner, organization=cls.org,
        )
        cls.pet2 = Pet.objects.create(
            name="Max", species="felino", owner=cls.owner, organization=cls.org,
        )

        now = timezone.now()
        cls.today = timezone.localtime(now).date()

        # In-progress appointment
        cls.appt_in_progress = Appointment.objects.create(
            pet=cls.pet, veterinarian=cls.vet,
            date=cls.today,
            start_time='10:00',
            end_time='10:30',
            status='in_progress', reason='Consulta general',
            organization=cls.org,
        )
        cls.appt_in_progress.start_datetime = now - timedelta(hours=1)
        cls.appt_in_progress.end_datetime = now + timedelta(minutes=30)
        cls.appt_in_progress.save(update_fields=['start_datetime', 'end_datetime'])

        # Scheduled appointment (different pet)
        cls.appt_scheduled = Appointment.objects.create(
            pet=cls.pet2, veterinarian=cls.vet,
            date=cls.today,
            start_time='14:00',
            end_time='14:30',
            status='scheduled', reason='Seguimiento',
            organization=cls.org,
        )
        cls.appt_scheduled.start_datetime = now + timedelta(hours=1)
        cls.appt_scheduled.end_datetime = now + timedelta(hours=1, minutes=30)
        cls.appt_scheduled.save(update_fields=['start_datetime', 'end_datetime'])

        # Open medical records
        cls.mr_open = MedicalRecord.objects.create(
            pet=cls.pet, veterinarian=cls.vet,
            consultation_type='general', diagnosis='Test diagnosis',
            status='open', organization=cls.org,
        )

        cls.mr_stale = MedicalRecord.objects.create(
            pet=cls.pet, veterinarian=cls.vet,
            consultation_type='general', diagnosis='',
            status='open', organization=cls.org,
        )
        cls.mr_stale.created_at = now - timedelta(hours=48)
        cls.mr_stale.save(update_fields=['created_at'])

        # Low-stock product
        cls.product = Product.objects.create(
            name="Amoxicilina", category="medication",
            internal_code="PROD-TEST-001", organization=cls.org,
        )
        cls.presentation = Presentation.objects.create(
            product=cls.product, name="Amoxicilina 50mg",
            base_unit="tablet", sale_price=Decimal("15.00"),
            stock=2, min_stock=5, organization=cls.org,
        )

    def setUp(self):
        cache.clear()

    # ------------------------------------------------------------------
    # Permission tests
    # ------------------------------------------------------------------
    def test_assistant_can_access_summary(self):
        self.client.force_authenticate(self.assistant)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_vet_can_access_summary(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_admin_can_access_summary(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_unauthenticated_blocked(self):
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    # ------------------------------------------------------------------
    # Response structure
    # ------------------------------------------------------------------
    def test_response_has_required_top_level_keys(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        for key in ('kpis', 'timeline', 'waiting_room', 'backlog',
                     'stock_alerts', 'effective_timezone', 'local_today'):
            self.assertIn(key, r.data, f"Missing key: {key}")

    def test_kpis_have_required_keys_for_vet(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        kpis = r.data['kpis']
        for key in ('in_progress_now', 'pending_today', 'low_stock_count',
                     'patients_today'):
            self.assertIn(key, kpis, f"Missing KPI: {key}")

    def test_admin_sees_ar_outstanding(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(SUMMARY_URL)
        self.assertIn('ar_outstanding', r.data['kpis'])

    def test_non_admin_does_not_see_ar_outstanding(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertNotIn('ar_outstanding', r.data['kpis'])

    # ------------------------------------------------------------------
    # KPI accuracy
    # ------------------------------------------------------------------
    def test_in_progress_count(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.data['kpis']['in_progress_now'], 1)

    def test_pending_today_count(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.data['kpis']['pending_today'], 1)

    def test_low_stock_count(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.data['kpis']['low_stock_count'], 1)

    def test_patients_today_count(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.data['kpis']['patients_today'], 2)

    def test_ar_shows_zero_when_no_confirmed(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.data['kpis']['ar_outstanding'], '0.00')

    def test_admin_ar_shows_confirmed_total(self):
        Invoice.objects.create(
            owner=self.owner, pet=self.pet, status='confirmed',
            total=Decimal('500.00'), tax_rate=self.org.tax_rate,
            tax_amount=Decimal('0.00'), subtotal=Decimal('500.00'),
            confirmed_at=timezone.now(), organization=self.org,
        )
        self.client.force_authenticate(self.admin)
        r = self.client.get(SUMMARY_URL)
        self.assertEqual(r.data['kpis']['ar_outstanding'], '500.00')

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------
    def test_timeline_is_list(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        self.assertIsInstance(r.data['timeline'], list)
        self.assertGreaterEqual(len(r.data['timeline']), 1)

    def test_timeline_slot_has_time_and_appointment(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        slot = r.data['timeline'][0]
        self.assertIn('time', slot)
        self.assertIn('appointment', slot)

    # ------------------------------------------------------------------
    # Backlog
    # ------------------------------------------------------------------
    def test_backlog_counts_correct(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        backlog = r.data['backlog']
        self.assertGreaterEqual(backlog['open_total'], 2)
        self.assertGreaterEqual(backlog['needs_attention_count'], 1)
        self.assertGreaterEqual(backlog['without_diagnosis'], 1)
        self.assertGreaterEqual(backlog['returned_records'], 1)

    def test_backlog_open_records_oldest_first(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        records = r.data['backlog']['open_records']
        self.assertGreaterEqual(len(records), 2)
        oldest = records[0]
        self.assertFalse(oldest['has_diagnosis'])
        self.assertGreaterEqual(oldest['days_open'], 2)
        self.assertTrue(oldest['needs_attention'])

    # ------------------------------------------------------------------
    # Stock alerts
    # ------------------------------------------------------------------
    def test_stock_alerts_structure(self):
        self.client.force_authenticate(self.vet)
        r = self.client.get(SUMMARY_URL)
        alerts = r.data['stock_alerts']
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['product_name'], 'Amoxicilina')
        self.assertEqual(alerts[0]['stock'], '2.00')
        self.assertEqual(alerts[0]['severity'], 'warning')

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    @tag('cache')
    def test_summary_is_cached(self):
        self.client.force_authenticate(self.vet)
        r1 = self.client.get(SUMMARY_URL)
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        r2 = self.client.get(SUMMARY_URL)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.data, r1.data)

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------
    def test_tenant_isolation(self):
        org2 = Organization.objects.create(name="Other", timezone="UTC")
        vet2 = _make_user("vet_other", org2, "VET")

        self.client.force_authenticate(vet2)
        r = self.client.get(SUMMARY_URL)

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['kpis']['in_progress_now'], 0)
        self.assertEqual(r.data['kpis']['patients_today'], 0)
        self.assertEqual(r.data['backlog']['open_total'], 0)
        self.assertEqual(len(r.data['stock_alerts']), 0)
