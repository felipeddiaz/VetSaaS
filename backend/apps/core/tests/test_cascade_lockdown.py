"""
Tests cascade lockdown PR-4B (Issue #11 / ADR p16).

Verifica que las 5 FKs flipadas a PROTECT efectivamente bloquean el cascade
con ProtectedError + mapeo a 409 vía custom_exception_handler.

Cobertura por FK:
- User.organization        — borrar Org con users PROTECTed
- Pet.owner                — borrar Owner con pets PROTECTed
- MedicalRecord.pet        — borrar Pet con MRs PROTECTed
- VaccineRecord.pet        — borrar Pet con vaccines PROTECTed
- Prescription.pet         — borrar Pet con prescriptions PROTECTed

Smoke positivo: borrar parent sin children debe funcionar (no falsos
positivos por bug en handler).
"""
from decimal import Decimal

from django.db.models import ProtectedError
from django.test import TestCase

from apps.medical_records.models import MedicalRecord, VaccineRecord
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.users.models import User
from apps.inventory.models import Product, Presentation


class CascadeLockdownTests(TestCase):
    """ORM-level: confirma ProtectedError, no testea HTTP layer."""

    def test_delete_organization_with_user_raises_protected(self):
        org = Organization.objects.create(name="Org Cascade", timezone="UTC")
        User.objects.create_user(username="u_casc", password="x", organization=org)
        with self.assertRaises(ProtectedError):
            org.delete()

    def test_delete_owner_with_pets_raises_protected(self):
        org = Organization.objects.create(name="Org Cascade O", timezone="UTC")
        owner = Owner.objects.create(name="Own C", phone="555", organization=org)
        Pet.objects.create(name="P", species="dog", owner=owner, organization=org)
        with self.assertRaises(ProtectedError):
            owner.delete()

    def test_delete_pet_with_medical_record_raises_protected(self):
        org = Organization.objects.create(name="Org Cascade P", timezone="UTC")
        owner = Owner.objects.create(name="Own P", phone="555", organization=org)
        pet = Pet.objects.create(name="P2", species="dog", owner=owner, organization=org)
        MedicalRecord.objects.create(pet=pet, organization=org)
        with self.assertRaises(ProtectedError):
            pet.delete()

    def test_delete_pet_with_vaccine_record_raises_protected(self):
        org = Organization.objects.create(name="Org Cascade V", timezone="UTC")
        owner = Owner.objects.create(name="Own V", phone="555", organization=org)
        pet = Pet.objects.create(name="P3", species="dog", owner=owner, organization=org)
        VaccineRecord.objects.create(
            pet=pet, vaccine_name="Rabia",
            application_date="2026-05-17", organization=org,
        )
        with self.assertRaises(ProtectedError):
            pet.delete()

    def test_delete_pet_with_prescription_raises_protected(self):
        """Prescription.pet flipado a PROTECT por consistencia NOM-046 con
        VaccineRecord — receta es documento legal, no debe destruirse."""
        org = Organization.objects.create(name="Org Cascade Rx", timezone="UTC")
        owner = Owner.objects.create(name="Own Rx", phone="555", organization=org)
        pet = Pet.objects.create(name="P4", species="dog", owner=owner, organization=org)
        mr = MedicalRecord.objects.create(pet=pet, organization=org)
        Prescription.objects.create(medical_record=mr, pet=pet, organization=org)
        with self.assertRaises(ProtectedError):
            pet.delete()

    # --- Smoke positivos (no falsos positivos) ---

    def test_delete_owner_without_pets_succeeds(self):
        org = Organization.objects.create(name="Org Clean", timezone="UTC")
        owner = Owner.objects.create(name="Own Empty", phone="555", organization=org)
        owner.delete()
        self.assertFalse(Owner.objects.filter(pk=owner.pk).exists())

    def test_delete_pet_without_records_succeeds(self):
        org = Organization.objects.create(name="Org Clean P", timezone="UTC")
        owner = Owner.objects.create(name="Own Empty P", phone="555", organization=org)
        pet = Pet.objects.create(name="P Empty", species="dog", owner=owner, organization=org)
        pet.delete()
        self.assertFalse(Pet.objects.filter(pk=pet.pk).exists())


class ChildDocumentDeleteDisabledTests(TestCase):
    """PR-4B HIGH (senior-qa): VaccineRecord y Prescription endpoints
    bloquean DELETE por consistencia con motivación NOM-007/046 que
    justificó VR.pet/Rx.pet PROTECT. Sin esto el lockdown sería asimétrico
    (Pet protegido pero documento child borrable directo)."""

    @classmethod
    def setUpTestData(cls):
        from apps.users.models import User
        from apps.core.models import Permission, Role, UserRole
        from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS

        cls.org = Organization.objects.create(name="Org Doc Delete", timezone="UTC")
        cls.owner = Owner.objects.create(name="Own DD", phone="555", organization=cls.org)
        cls.pet = Pet.objects.create(name="P DD", species="dog", owner=cls.owner, organization=cls.org)
        cls.mr = MedicalRecord.objects.create(pet=cls.pet, organization=cls.org)
        cls.vacc = VaccineRecord.objects.create(
            pet=cls.pet, vaccine_name="Rabia",
            application_date="2026-05-17", organization=cls.org,
        )
        cls.rx = Prescription.objects.create(
            medical_record=cls.mr, pet=cls.pet, organization=cls.org,
        )

        wildcard, _ = Permission.objects.get_or_create(code="*.*")
        perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}
        for name, codes in PERMISSIONS.items():
            if name == "ADMIN_SAAS":
                continue
            role, _ = Role.objects.get_or_create(name=name, organization=cls.org, defaults={"is_system_role": True})
            role.permissions.set([wildcard] if "*.*" in codes else [perms_map[c] for c in codes if c in perms_map])
        cls.admin = User.objects.create_user(username="adm_dd", password="x", organization=cls.org, role="ADMIN")
        UserRole.objects.get_or_create(user=cls.admin, role=Role.objects.get(name="ADMIN", organization=cls.org))

    def test_vaccine_record_delete_returns_405(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.admin)
        r = client.delete(f"/api/vaccines/{self.vacc.pk}/")
        self.assertEqual(r.status_code, 405)

    def test_prescription_delete_returns_405(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.admin)
        r = client.delete(f"/api/prescriptions/{self.rx.public_id}/")
        self.assertEqual(r.status_code, 405)
