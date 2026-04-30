"""
Tests de cierre de consultas médicas y bloqueo cuando status=closed.
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Service
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.inventory.models import Presentation, Product
from apps.medical_records.models import MedicalRecord
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


def _seed_roles(org):
    wildcard, _ = Permission.objects.get_or_create(code="*.*")
    perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}
    roles = {}
    for name, codes in PERMISSIONS.items():
        if name == "ADMIN_SAAS":
            continue
        role, _ = Role.objects.get_or_create(name=name, organization=org, defaults={"is_system_role": True})
        role.permissions.set([wildcard] if "*.*" in codes else [perms_map[c] for c in codes if c in perms_map])
        roles[name] = role
    return roles


def _make_user(username, org, role_name):
    u = User.objects.create_user(username=username, password="pass", organization=org, role=role_name)
    roles = _seed_roles(org)
    UserRole.objects.get_or_create(user=u, role=roles[role_name])
    return u


class CloseMedicalRecordTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org Close A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org Close B", timezone="UTC")

        cls.vet_a   = _make_user("vet_close_a",  cls.org_a, "VET")
        cls.vet_a2  = _make_user("vet_close_a2", cls.org_a, "VET")
        cls.admin_a = _make_user("adm_close_a",  cls.org_a, "ADMIN")
        cls.vet_b   = _make_user("vet_close_b",  cls.org_b, "VET")

    def _make_record(self, vet=None, org=None):
        vet = vet or self.vet_a
        org = org or self.org_a
        owner = Owner.objects.create(name="O", phone="2", organization=org)
        pet   = Pet.objects.create(name="P", species="dog", owner=owner, organization=org)
        return MedicalRecord.objects.create(
            pet=pet, veterinarian=vet, organization=org,
            diagnosis="d", treatment="t",
        )

    def _make_closed(self):
        mr = self._make_record()
        mr.status = MedicalRecord.Status.CLOSED
        mr.closed_by = self.vet_a
        mr.closed_at = timezone.now()
        mr.save(update_fields=["status", "closed_by", "closed_at"])
        return mr

    def _close_url(self, pk):  return f"/api/medical-records/{pk}/close/"
    def _detail_url(self, pk): return f"/api/medical-records/{pk}/"

    # ── open → closed ────────────────────────────────────────────────────────

    def test_close_open_record_returns_200(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._close_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        mr.refresh_from_db()
        self.assertEqual(mr.status, MedicalRecord.Status.CLOSED)
        self.assertIsNotNone(mr.closed_at)
        self.assertEqual(mr.closed_by, self.vet_a)

    def test_close_already_closed_is_idempotent_200(self):
        mr = self._make_closed()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._close_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_admin_can_close_any_record(self):
        mr = self._make_record(vet=self.vet_a)
        self.client.force_authenticate(self.admin_a)
        r = self.client.post(self._close_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_vet_not_owner_cannot_close_403(self):
        mr = self._make_record(vet=self.vet_a)
        self.client.force_authenticate(self.vet_a2)
        r = self.client.post(self._close_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_tenant_close_returns_404(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_b)
        r = self.client.post(self._close_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    # ── bloqueos en consulta cerrada ─────────────────────────────────────────

    def test_update_closed_record_returns_403(self):
        mr = self._make_closed()
        self.client.force_authenticate(self.vet_a)
        r = self.client.patch(self._detail_url(mr.pk), {"notes": "hack"})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_closed_record_returns_403(self):
        mr = self._make_closed()
        self.client.force_authenticate(self.admin_a)
        r = self.client.delete(self._detail_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_product_to_closed_record_returns_403(self):
        mr = self._make_closed()
        product = Product.objects.create(
            name="ClosedProd", internal_code="CP-1",
            organization=self.org_a, requires_prescription=False,
        )
        pres = Presentation.objects.create(
            product=product, name="pres", base_unit="unit",
            sale_price="10.00", stock="100", min_stock="0",
            organization=self.org_a,
        )
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(
            f"/api/medical-records/{mr.pk}/products/",
            {"presentation": pres.id, "quantity": 1}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_service_to_closed_record_returns_403(self):
        mr = self._make_closed()
        svc = Service.objects.create(name="Svc", base_price="50.00", organization=self.org_a)
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(
            f"/api/medical-records/{mr.pk}/services/",
            {"service": svc.id, "quantity": 1}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    # ── logs ─────────────────────────────────────────────────────────────────

    def test_close_emits_closed_log(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        with self.assertLogs("medical_records.events", level="INFO") as cm:
            self.client.post(self._close_url(mr.pk))
        self.assertIn("MEDICAL_RECORD_CLOSED", [r.getMessage() for r in cm.records])

    def test_close_idempotent_emits_idempotent_log(self):
        mr = self._make_closed()
        self.client.force_authenticate(self.vet_a)
        with self.assertLogs("medical_records.events", level="INFO") as cm:
            self.client.post(self._close_url(mr.pk))
        self.assertIn("MEDICAL_RECORD_CLOSE_IDEMPOTENT", [r.getMessage() for r in cm.records])

    def test_ownership_denied_emits_log(self):
        mr = self._make_record(vet=self.vet_a)
        self.client.force_authenticate(self.vet_a2)
        with self.assertLogs("medical_records.events", level="WARNING") as cm:
            self.client.post(self._close_url(mr.pk))
        self.assertIn("MEDICAL_RECORD_OWNERSHIP_DENIED", [r.getMessage() for r in cm.records])

    def test_closed_denied_emits_log(self):
        mr = self._make_closed()
        product = Product.objects.create(
            name="LogProd", internal_code="LP-1",
            organization=self.org_a, requires_prescription=False,
        )
        pres = Presentation.objects.create(
            product=product, name="pres", base_unit="unit",
            sale_price="10.00", stock="100", min_stock="0",
            organization=self.org_a,
        )
        self.client.force_authenticate(self.vet_a)
        with self.assertLogs("medical_records.events", level="WARNING") as cm:
            self.client.post(
                f"/api/medical-records/{mr.pk}/products/",
                {"presentation": pres.id, "quantity": 1}, format="json",
            )
        self.assertIn("MEDICAL_RECORD_CLOSED_DENIED", [r.getMessage() for r in cm.records])

    # ── idempotencia ─────────────────────────────────────────────────────────

    def test_close_concurrent_safe_via_idempotency(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        for _ in range(3):
            r = self.client.post(self._close_url(mr.pk))
            self.assertEqual(r.status_code, status.HTTP_200_OK)
        mr.refresh_from_db()
        self.assertEqual(mr.status, MedicalRecord.Status.CLOSED)
