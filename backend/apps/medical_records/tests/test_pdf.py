from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Service
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.inventory.models import Presentation, Product
from apps.medical_records.models import (
    MedicalRecord, MedicalRecordService, VitalSigns,
)
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.prescriptions.models import Prescription, PrescriptionItem
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


def _extract_pdf_text(content):
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


class MedicalRecordPdfTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Clinica MR PDF", timezone="UTC")
        cls.org_other = Organization.objects.create(name="Otra Clinica", timezone="UTC")

        cls.admin = _make_user("adm_mr_pdf", cls.org, "ADMIN")
        cls.vet = _make_user("vet_mr_pdf", cls.org, "VET")

        cls.owner = Owner.objects.create(name="Carlos Gomez", phone="5559876543",
                                          organization=cls.org)
        cls.pet = Pet.objects.create(name="Ñoño", species="cat", breed="Siames",
                                     owner=cls.owner, organization=cls.org)

        cls.service = Service.objects.create(name="Vacunación", base_price=Decimal("300"),
                                              organization=cls.org)
        cls.product = Product.objects.create(name="Antibiotico X", internal_code="ABX1",
                                              organization=cls.org, requires_prescription=True)
        cls.presentation = Presentation.objects.create(
            product=cls.product, name="Frasco 10ml", base_unit="ml",
            sale_price=Decimal("250"), stock=Decimal("100"), organization=cls.org,
        )

    def _make_record(self, with_extras=True, notes=""):
        rec = MedicalRecord.objects.create(
            organization=self.org, pet=self.pet, veterinarian=self.vet,
            diagnosis="Diagnóstico de prueba",
            treatment="Tratamiento de prueba",
            notes=notes,
            consultation_type=MedicalRecord.ConsultationType.GENERAL,
        )
        if with_extras:
            VitalSigns.objects.create(
                medical_record=rec, organization=self.org,
                weight=Decimal("4.5"), temperature=Decimal("38.5"),
                heart_rate=120, respiratory_rate=30,
                recorded_by=self.vet, recorded_at=timezone.now(),
            )
            MedicalRecordService.objects.create(
                medical_record=rec, service=self.service,
                quantity=Decimal("1"), organization=self.org,
            )
            prescription = Prescription.objects.create(
                organization=self.org, pet=self.pet, veterinarian=self.vet,
                medical_record=rec, notes="Aplicar 2 veces al día",
            )
            PrescriptionItem.objects.create(
                prescription=prescription, product=self.product,
                organization=self.org, dose="5ml",
                quantity=Decimal("1"), duration="7 días",
                instructions="Con alimento",
            )
        return rec

    def _url(self, record):
        return f'/api/medical-records/{record.public_id}/pdf/'

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_full_record_returns_pdf(self):
        rec = self._make_record(with_extras=True)
        r = self.client.get(self._url(rec))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertIn(f'consulta_{rec.id}', r['Content-Disposition'])
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_empty_record_works(self):
        rec = MedicalRecord.objects.create(
            organization=self.org, pet=self.pet, veterinarian=self.vet,
            consultation_type=MedicalRecord.ConsultationType.GENERAL,
        )
        r = self.client.get(self._url(rec))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_long_notes_does_not_crash(self):
        rec = self._make_record(with_extras=False, notes="A" * 4000)
        r = self.client.get(self._url(rec))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_cross_tenant_404(self):
        other_owner = Owner.objects.create(name="X", phone="555", organization=self.org_other)
        other_pet = Pet.objects.create(name="OtherPet", species="dog",
                                       owner=other_owner, organization=self.org_other)
        rec_other = MedicalRecord.objects.create(
            organization=self.org_other, pet=other_pet,
            consultation_type=MedicalRecord.ConsultationType.GENERAL,
        )
        r = self.client.get(self._url(rec_other))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_pdf_text_contains_markers(self):
        rec = self._make_record(with_extras=True)
        r = self.client.get(self._url(rec))
        text = _extract_pdf_text(r.content)
        self.assertIn("Ñoño", text)
        self.assertIn("Vacunación", text)
        self.assertIn("Antibiotico X", text)

    def test_n_plus_one_guard(self):
        small = self._make_record(with_extras=True)
        # Crear un record con más items
        big = MedicalRecord.objects.create(
            organization=self.org, pet=self.pet, veterinarian=self.vet,
            consultation_type=MedicalRecord.ConsultationType.GENERAL,
        )
        # 5 servicios
        for i in range(5):
            svc = Service.objects.create(name=f"Servicio {i}", base_price=Decimal("100"),
                                          organization=self.org)
            MedicalRecordService.objects.create(
                medical_record=big, service=svc, quantity=Decimal("1"),
                organization=self.org,
            )

        self.client.get(self._url(small))  # warmup

        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx_small:
            self.client.get(self._url(small))
        with CaptureQueriesContext(connection) as ctx_big:
            self.client.get(self._url(big))

        # Permitir un margen de 2 queries por diferencias de cache de permisos
        # entre requests, pero NO crecimiento lineal con N items.
        self.assertLessEqual(len(ctx_big), len(ctx_small) + 2,
                             msg=f"N+1 detectado: small={len(ctx_small)} big={len(ctx_big)}")
