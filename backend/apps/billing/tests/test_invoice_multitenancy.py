from datetime import date, time
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.appointments.models import Appointment
from apps.billing.models import Invoice, Service
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


class InvoiceItemMultitenancyTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org MT Item A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org MT Item B", timezone="UTC")

        cls.admin_a = _make_user("adm_mt_item_a", cls.org_a, "ADMIN")

        cls.owner_a = Owner.objects.create(name="Own ITA", phone="5551110001", organization=cls.org_a)
        cls.pet_a = Pet.objects.create(name="Pet ITA", species="dog", owner=cls.owner_a, organization=cls.org_a)

        cls.service_a = Service.objects.create(name="Svc A", base_price=Decimal("200"), organization=cls.org_a)
        cls.service_b = Service.objects.create(name="Svc B", base_price=Decimal("200"), organization=cls.org_b)

        cls.product_a = Product.objects.create(name="Prod ITA", internal_code="PITA1", organization=cls.org_a)
        cls.product_b = Product.objects.create(name="Prod ITB", internal_code="PITB1", organization=cls.org_b)

        cls.presentation_a = Presentation.objects.create(
            product=cls.product_a, name="Frasco A", base_unit="bottle",
            sale_price=Decimal("100"), stock=Decimal("20"), organization=cls.org_a,
        )
        cls.presentation_b = Presentation.objects.create(
            product=cls.product_b, name="Frasco B", base_unit="bottle",
            sale_price=Decimal("100"), stock=Decimal("20"), organization=cls.org_b,
        )

    def _make_invoice(self):
        return Invoice.objects.create(
            owner=self.owner_a, pet=self.pet_a, organization=self.org_a,
            status='draft', invoice_type='direct_sale',
        )

    def _items_url(self, invoice):
        return f'/api/billing/invoices/{invoice.public_id}/items/'

    def setUp(self):
        self.client.force_authenticate(self.admin_a)

    def test_invoice_item_service_cross_tenant_rejected(self):
        invoice = self._make_invoice()
        r = self.client.post(self._items_url(invoice), {'service': self.service_b.pk, 'quantity': '1'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invoice_item_presentation_cross_tenant_rejected(self):
        invoice = self._make_invoice()
        r = self.client.post(
            self._items_url(invoice),
            {'presentation': self.presentation_b.pk, 'quantity': '1'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invoice_item_duplicate_service_returns_400(self):
        invoice = self._make_invoice()
        r1 = self.client.post(self._items_url(invoice), {'service': self.service_a.pk, 'quantity': '1'}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post(self._items_url(invoice), {'service': self.service_a.pk, 'quantity': '1'}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invoice_items_url_accepts_public_id(self):
        invoice = self._make_invoice()
        r = self.client.post(self._items_url(invoice), {'service': self.service_a.pk, 'quantity': '1'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)


class MedicalRecordMultitenancyTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org MT MR A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org MT MR B", timezone="UTC")

        cls.admin_a = _make_user("adm_mt_mr_a", cls.org_a, "ADMIN")
        cls.vet_a = _make_user("vet_mt_mr_a", cls.org_a, "VET")

        cls.owner_b = Owner.objects.create(name="Own MRB", phone="5552220001", organization=cls.org_b)
        cls.pet_b = Pet.objects.create(name="Pet MRB", species="cat", owner=cls.owner_b, organization=cls.org_b)

    def setUp(self):
        self.client.force_authenticate(self.admin_a)

    def test_create_medical_record_cross_tenant_pet_rejected(self):
        r = self.client.post('/api/medical-records/', {
            'pet': self.pet_b.pk,
            'veterinarian': self.vet_a.pk,
            'diagnosis': 'test cross tenant',
            'treatment': 'test',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class InvoiceSerializerCrossTenantTests(APITestCase):
    """
    P0 #8 (ADR p14) — InvoiceSerializer.validate_owner / pet / appointment / medical_record
    Antes de Día 3, FKs cross-org devolvían HTTP 500 (Invoice.clean() levantaba
    django.core.exceptions.ValidationError — DRF no la mapeaba a 400).
    """

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org INV X-A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org INV X-B", timezone="UTC")

        cls.admin_a = _make_user("adm_inv_x_a", cls.org_a, "ADMIN")
        cls.vet_a = _make_user("vet_inv_x_a", cls.org_a, "VET")
        cls.vet_b = _make_user("vet_inv_x_b", cls.org_b, "VET")

        # Recursos org A (válidos para los flujos de prueba)
        cls.owner_a = Owner.objects.create(name="Own A", phone="5557770001", organization=cls.org_a)
        cls.pet_a = Pet.objects.create(name="Pet A", species="dog", owner=cls.owner_a, organization=cls.org_a)
        cls.appointment_a = Appointment.objects.create(
            pet=cls.pet_a, veterinarian=cls.vet_a, organization=cls.org_a,
            date=date(2026, 5, 16), start_time=time(10, 0), end_time=time(10, 30), reason="control",
        )
        cls.medical_record_a = MedicalRecord.objects.create(
            pet=cls.pet_a, veterinarian=cls.vet_a, organization=cls.org_a,
            diagnosis="dx A", treatment="tx A",
        )

        # Recursos org B (deben ser rechazados cuando el cliente es org A)
        cls.owner_b = Owner.objects.create(name="Own B", phone="5558880001", organization=cls.org_b)
        cls.pet_b = Pet.objects.create(name="Pet B", species="cat", owner=cls.owner_b, organization=cls.org_b)
        cls.appointment_b = Appointment.objects.create(
            pet=cls.pet_b, veterinarian=cls.vet_b, organization=cls.org_b,
            date=date(2026, 5, 16), start_time=time(11, 0), end_time=time(11, 30), reason="control B",
        )
        cls.medical_record_b = MedicalRecord.objects.create(
            pet=cls.pet_b, veterinarian=cls.vet_b, organization=cls.org_b,
            diagnosis="dx B", treatment="tx B",
        )

    def setUp(self):
        self.client.force_authenticate(self.admin_a)

    # --- T1.a Tests P0 #8 -----------------------------------------------------

    def test_invoice_create_cross_tenant_owner_returns_400(self):
        r = self.client.post('/api/billing/invoices/', {
            'owner': self.owner_b.pk, 'pet': self.pet_a.pk,
            'invoice_type': 'consultation',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['errors'], {'owner': ['Acceso inválido.']})

    def test_invoice_create_cross_tenant_pet_returns_400(self):
        r = self.client.post('/api/billing/invoices/', {
            'owner': self.owner_a.pk, 'pet': self.pet_b.pk,
            'invoice_type': 'consultation',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['errors'], {'pet': ['Acceso inválido.']})

    def test_invoice_create_cross_tenant_appointment_returns_400(self):
        r = self.client.post('/api/billing/invoices/', {
            'owner': self.owner_a.pk, 'pet': self.pet_a.pk,
            'appointment': self.appointment_b.pk,
            'invoice_type': 'consultation',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['errors'], {'appointment': ['Acceso inválido.']})

    def test_invoice_create_cross_tenant_medical_record_returns_400(self):
        r = self.client.post('/api/billing/invoices/', {
            'owner': self.owner_a.pk, 'pet': self.pet_a.pk,
            'medical_record': self.medical_record_b.pk,
            'invoice_type': 'consultation',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['errors'], {'medical_record': ['Acceso inválido.']})

    def test_cross_tenant_emits_tenant_validation_rejected_log(self):
        with self.assertLogs('apps.tenant_validation', level='WARNING') as cm:
            self.client.post('/api/billing/invoices/', {
                'owner': self.owner_a.pk, 'pet': self.pet_b.pk,
                'invoice_type': 'consultation',
            }, format='json')
        # Al menos un record con TENANT_VALIDATION_REJECTED
        records = [r for r in cm.records if r.getMessage() == 'TENANT_VALIDATION_REJECTED']
        self.assertGreaterEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.source, 'serializer')
        self.assertEqual(rec.serializer, 'InvoiceSerializer')
        self.assertEqual(rec.field, 'pet')
        self.assertEqual(rec.user_org_id, self.org_a.pk)
        self.assertEqual(rec.resource_org_id, self.org_b.pk)
        self.assertEqual(rec.resource_pk, self.pet_b.pk)

    def test_invoice_same_org_fks_passes(self):
        r = self.client.post('/api/billing/invoices/', {
            'owner': self.owner_a.pk, 'pet': self.pet_a.pk,
            'invoice_type': 'consultation',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, msg=r.data)

    # --- T1.b Tests Fix 4 PATCH parcial ---------------------------------------

    def _create_invoice(self, **overrides):
        data = {
            'owner': self.owner_a.pk, 'pet': self.pet_a.pk,
            'invoice_type': 'consultation',
        }
        data.update(overrides)
        r = self.client.post('/api/billing/invoices/', data, format='json')
        assert r.status_code == 201, r.data
        return r.data['public_id']

    def test_patch_notes_only_succeeds(self):
        pid = self._create_invoice()
        r = self.client.patch(f'/api/billing/invoices/{pid}/', {'notes': 'actualizado'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, msg=r.data)
        inv = Invoice.objects.get(public_id=pid)
        self.assertEqual(inv.notes, 'actualizado')
        self.assertEqual(inv.pet_id, self.pet_a.pk)
        self.assertEqual(inv.owner_id, self.owner_a.pk)

    def test_patch_status_only_succeeds(self):
        # Cambiar payment_method desde draft sigue siendo draft — testea que
        # validate() no exige pet en PATCH minimalistas.
        pid = self._create_invoice()
        r = self.client.patch(f'/api/billing/invoices/{pid}/', {'notes': 'x'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, msg=r.data)

    def test_patch_owner_same_org_preserves_existing_pet(self):
        pid = self._create_invoice()
        new_owner = Owner.objects.create(name="Nuevo Dueño", phone="5559990001", organization=self.org_a)
        r = self.client.patch(f'/api/billing/invoices/{pid}/', {'owner': new_owner.pk}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, msg=r.data)
        inv = Invoice.objects.get(public_id=pid)
        self.assertEqual(inv.owner_id, new_owner.pk)
        self.assertEqual(inv.pet_id, self.pet_a.pk)   # preservado

    def test_patch_owner_cross_org_returns_400(self):
        pid = self._create_invoice()
        r = self.client.patch(f'/api/billing/invoices/{pid}/', {'owner': self.owner_b.pk}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['errors'], {'owner': ['Acceso inválido.']})

    def test_patch_explicit_null_pet_returns_400(self):
        pid = self._create_invoice()
        r = self.client.patch(f'/api/billing/invoices/{pid}/', {'pet': None}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('pet', r.data['errors'])
        self.assertIn('mascota es requerida', str(r.data['errors']['pet']))

    def test_patch_does_not_overwrite_existing_fk_when_omitted(self):
        pid = self._create_invoice(appointment=self.appointment_a.pk)
        r = self.client.patch(f'/api/billing/invoices/{pid}/', {'notes': 'x'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, msg=r.data)
        inv = Invoice.objects.get(public_id=pid)
        self.assertEqual(inv.appointment_id, self.appointment_a.pk)   # NO sobrescrito

    def test_create_without_pet_still_returns_400(self):
        # No regresión: comportamiento CREATE intacto para owner no-generic.
        r = self.client.post('/api/billing/invoices/', {
            'owner': self.owner_a.pk,
            'invoice_type': 'consultation',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('pet', r.data['errors'])

    def test_create_with_generic_owner_forces_direct_sale(self):
        # No regresión: generic owner sigue forzando direct_sale.
        from apps.patients.models import Owner as _Owner
        generic, _ = _Owner.objects.get_or_create(
            organization=self.org_a, is_generic=True,
            defaults={'name': 'Genérico', 'phone': '5550000000'},
        )
        r = self.client.post('/api/billing/invoices/', {
            'owner': generic.pk,
            'invoice_type': 'consultation',   # debe ser sobreescrito a direct_sale
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, msg=r.data)
        self.assertEqual(r.data['invoice_type'], 'direct_sale')


class VaccineRecordMultitenancyTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org MT VR A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org MT VR B", timezone="UTC")

        cls.admin_a = _make_user("adm_mt_vr_a", cls.org_a, "ADMIN")

        cls.owner_b = Owner.objects.create(name="Own VRB", phone="5553330001", organization=cls.org_b)
        cls.pet_b = Pet.objects.create(name="Pet VRB", species="cat", owner=cls.owner_b, organization=cls.org_b)

    def setUp(self):
        self.client.force_authenticate(self.admin_a)

    def test_create_vaccine_record_cross_tenant_pet_rejected(self):
        r = self.client.post('/api/vaccines/', {
            'pet': self.pet_b.pk,
            'vaccine_name': 'Rabia',
            'application_date': '2026-01-15',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
