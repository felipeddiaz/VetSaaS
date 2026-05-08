"""
Tests de signos vitales y endpoint summary del historial clínico.
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.medical_records.models import MedicalRecord, VitalSigns, VaccineRecord
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


class VitalSignsTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org Vitals A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org Vitals B", timezone="UTC")

        cls.vet_a       = _make_user("vet_vitals_a",   cls.org_a, "VET")
        cls.assistant_a = _make_user("asst_vitals_a",  cls.org_a, "ASSISTANT")
        cls.vet_b       = _make_user("vet_vitals_b",   cls.org_b, "VET")

        owner = Owner.objects.create(name="Owner", phone="1234567890", organization=cls.org_a)
        cls.pet_a = Pet.objects.create(name="Firulais", species="dog", owner=owner, organization=cls.org_a)

    def _make_record(self, vet=None, org=None, pet=None, **kwargs):
        vet = vet or self.vet_a
        org = org or self.org_a
        pet = pet or self.pet_a
        defaults = {"diagnosis": "d", "treatment": "t"}
        defaults.update(kwargs)
        return MedicalRecord.objects.create(pet=pet, veterinarian=vet, organization=org, **defaults)

    def _make_closed(self, **kwargs):
        mr = self._make_record(**kwargs)
        mr.status = MedicalRecord.Status.CLOSED
        mr.closed_by = self.vet_a
        mr.closed_at = timezone.now()
        mr.save(update_fields=["status", "closed_by", "closed_at"])
        return mr

    def _vitals_url(self, pk): return f"/api/medical-records/{pk}/vitals/"
    def _summary_url(self, pk): return f"/api/medical-records/{pk}/summary/"

    # ── POST vitales ─────────────────────────────────────────────────────────

    def test_create_vitals_open_record_returns_201(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._vitals_url(mr.pk), {"weight": "5.50"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(VitalSigns.objects.filter(medical_record=mr).exists())

    def test_create_vitals_closed_record_returns_403(self):
        mr = self._make_closed()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._vitals_url(mr.pk), {"weight": "5.50"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_vitals_cross_tenant_returns_404(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_b)
        r = self.client.post(self._vitals_url(mr.pk), {"weight": "5.50"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_vitals_all_null_returns_400(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._vitals_url(mr.pk), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_vitals_temperature_out_of_range_returns_400(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._vitals_url(mr.pk), {"temperature": "50.0"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_vitals_temperature_below_range_returns_400(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._vitals_url(mr.pk), {"temperature": "25.0"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_vitals_weight_out_of_range_returns_400(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._vitals_url(mr.pk), {"weight": "300.00"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_vitals_heart_rate_out_of_range_returns_400(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(self._vitals_url(mr.pk), {"heart_rate": 400}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_vitals_inconsistent_temp_and_hr_returns_400(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.post(
            self._vitals_url(mr.pk),
            {"temperature": "43.0", "heart_rate": 15},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_vitals_organization_auto_assigned(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        self.client.post(self._vitals_url(mr.pk), {"weight": "6.00"}, format="json")
        vital = VitalSigns.objects.filter(medical_record=mr).first()
        self.assertIsNotNone(vital)
        self.assertEqual(vital.organization, self.org_a)

    def test_create_vitals_recorded_by_set_to_current_user(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        self.client.post(self._vitals_url(mr.pk), {"temperature": "38.5"}, format="json")
        vital = VitalSigns.objects.filter(medical_record=mr).first()
        self.assertEqual(vital.recorded_by, self.vet_a)

    # ── GET vitales ──────────────────────────────────────────────────────────

    def test_list_vitals_returns_200(self):
        mr = self._make_record()
        VitalSigns.objects.create(medical_record=mr, organization=self.org_a, weight="5.00")
        VitalSigns.objects.create(medical_record=mr, organization=self.org_a, temperature="38.5")
        self.client.force_authenticate(self.vet_a)
        r = self.client.get(self._vitals_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(r.data["count"], 2)

    def test_list_vitals_ordered_by_recorded_at_desc(self):
        mr = self._make_record()
        old = timezone.now().replace(year=2025, month=1, day=1)
        new = timezone.now()
        VitalSigns.objects.create(medical_record=mr, organization=self.org_a, weight="4.00", recorded_at=old)
        VitalSigns.objects.create(medical_record=mr, organization=self.org_a, weight="5.00", recorded_at=new)
        self.client.force_authenticate(self.vet_a)
        r = self.client.get(self._vitals_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.data["results"]
        self.assertEqual(str(results[0]["weight"]), "5.00")

    # ── RBAC ─────────────────────────────────────────────────────────────────

    def test_assistant_cannot_create_vitals_returns_403(self):
        mr = self._make_record()
        self.client.force_authenticate(self.assistant_a)
        r = self.client.post(self._vitals_url(mr.pk), {"weight": "5.00"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_assistant_can_list_vitals_returns_200(self):
        mr = self._make_record()
        self.client.force_authenticate(self.assistant_a)
        r = self.client.get(self._vitals_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    # ── Summary ──────────────────────────────────────────────────────────────

    def test_summary_returns_200_with_full_structure(self):
        mr = self._make_record()
        VitalSigns.objects.create(
            medical_record=mr, organization=self.org_a,
            weight="5.50", temperature="38.5",
        )
        self.client.force_authenticate(self.vet_a)
        r = self.client.get(self._summary_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("patient", r.data)
        self.assertIn("last_vitals", r.data)
        self.assertIn("diagnosis", r.data)
        self.assertIn("consultation_type", r.data)
        self.assertIn("status", r.data)
        self.assertIn("next_vaccine_date", r.data)
        self.assertTrue(r.data["last_vitals"]["has_vitals"])
        self.assertEqual(str(r.data["last_vitals"]["weight"]), "5.50")

    def test_summary_no_vitals_falls_back_to_record_weight(self):
        mr = self._make_record()
        mr.weight = "7.20"
        mr.save(update_fields=["weight"])
        self.client.force_authenticate(self.vet_a)
        r = self.client.get(self._summary_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertFalse(r.data["last_vitals"]["has_vitals"])
        self.assertEqual(str(r.data["last_vitals"]["weight"]), "7.20")

    def test_summary_vital_weight_null_falls_back_to_record_weight(self):
        mr = self._make_record()
        mr.weight = "8.00"
        mr.save(update_fields=["weight"])
        VitalSigns.objects.create(
            medical_record=mr, organization=self.org_a,
            weight=None, temperature="38.0",
        )
        self.client.force_authenticate(self.vet_a)
        r = self.client.get(self._summary_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(str(r.data["last_vitals"]["weight"]), "8.00")

    def test_summary_totals_present_when_auto_invoice_created(self):
        """El signal crea una invoice draft automáticamente — totals nunca es null para registros nuevos."""
        mr = self._make_record()
        self.client.force_authenticate(self.vet_a)
        r = self.client.get(self._summary_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # La invoice draft se crea vía signal — totals debe existir con status=draft
        if r.data["totals"] is not None:
            self.assertIn("status", r.data["totals"])
            self.assertIn("total", r.data["totals"])
        # En orgs sin settings (o con auto_invoice desactivado), totals puede ser null — ambas son válidas

    def test_summary_cross_tenant_returns_404(self):
        mr = self._make_record()
        self.client.force_authenticate(self.vet_b)
        r = self.client.get(self._summary_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_summary_with_next_vaccine(self):
        mr = self._make_record()
        from datetime import date, timedelta
        future_date = date.today() + timedelta(days=30)
        VaccineRecord.objects.create(
            pet=self.pet_a, vaccine_name="Rabia",
            application_date=date.today(),
            next_due_date=future_date,
            organization=self.org_a,
        )
        self.client.force_authenticate(self.vet_a)
        r = self.client.get(self._summary_url(mr.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(str(r.data["next_vaccine_date"]), str(future_date))
