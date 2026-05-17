"""
P0 #9 (ADR p14) — tenant isolation en PrescriptionItem(Write)Serializer.

Antes de Día 3, PrescriptionItemSerializer y PrescriptionItemWriteSerializer
no validaban que `product` perteneciera a la organización del request.user.
Cliente podía crear recetas con productos cross-org, y el PDF
(prescription_pdf) imprimía el nombre/presentación de productos cross-tenant.
"""
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.inventory.models import Presentation, Product
from apps.medical_records.models import MedicalRecord
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.users.models import User


def _seed_roles(org):
    wildcard, _ = Permission.objects.get_or_create(code="*.*")
    perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}
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


def _make_user(username, org, role_name):
    u = User.objects.create_user(
        username=username, password="pass", organization=org, role=role_name,
    )
    _seed_roles(org)
    role = Role.objects.get(name=role_name, organization=org)
    UserRole.objects.get_or_create(user=u, role=role)
    return u


class PrescriptionMultitenancyTests(APITestCase):
    """
    Cobra:
    - PrescriptionItemSerializer (nested) — POST /api/prescriptions/ con items
    - PrescriptionItemWriteSerializer — POST /api/prescriptions/<id>/items/
    - PrescriptionSerializer (pre-existente) — validate_medical_record, validate_pet
    - Observabilidad — TENANT_VALIDATION_REJECTED en WARNING
    - PATCH nested edge cases
    """

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org RX A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org RX B", timezone="UTC")

        cls.vet_a = _make_user("vet_rx_a", cls.org_a, "VET")
        cls.vet_b = _make_user("vet_rx_b", cls.org_b, "VET")
        # ADMIN_A para PATCH tests (VET no tiene prescription.update)
        cls.admin_a = _make_user("adm_rx_a", cls.org_a, "ADMIN")

        # Org A
        cls.owner_a = Owner.objects.create(name="Own RX A", phone="5550010001", organization=cls.org_a)
        cls.pet_a = Pet.objects.create(name="Pet RX A", species="dog", owner=cls.owner_a, organization=cls.org_a)
        cls.medical_record_a = MedicalRecord.objects.create(
            pet=cls.pet_a, veterinarian=cls.vet_a, organization=cls.org_a,
            diagnosis="dx A", treatment="tx A",
        )
        cls.product_a_rx = Product.objects.create(
            name="Antibiotico A", internal_code="ABA1",
            requires_prescription=True, organization=cls.org_a,
        )
        Presentation.objects.create(
            product=cls.product_a_rx, name="Frasco A", base_unit="bottle",
            sale_price=Decimal("100"), stock=Decimal("20"), organization=cls.org_a,
        )
        cls.product_a_otc = Product.objects.create(
            name="Vitamina A", internal_code="VITA1",
            requires_prescription=False, organization=cls.org_a,
        )

        # Org B (cross-tenant resources)
        cls.owner_b = Owner.objects.create(name="Own RX B", phone="5550020001", organization=cls.org_b)
        cls.pet_b = Pet.objects.create(name="Pet RX B", species="cat", owner=cls.owner_b, organization=cls.org_b)
        cls.medical_record_b = MedicalRecord.objects.create(
            pet=cls.pet_b, veterinarian=cls.vet_b, organization=cls.org_b,
            diagnosis="dx B", treatment="tx B",
        )
        cls.product_b_rx = Product.objects.create(
            name="Antibiotico B", internal_code="ABB1",
            requires_prescription=True, organization=cls.org_b,
        )
        Presentation.objects.create(
            product=cls.product_b_rx, name="Frasco B", base_unit="bottle",
            sale_price=Decimal("100"), stock=Decimal("20"), organization=cls.org_b,
        )

    def setUp(self):
        self.client.force_authenticate(self.vet_a)

    # --- Nested PrescriptionItemSerializer (POST con items) -------------------

    def test_create_prescription_with_nested_cross_tenant_product_returns_400(self):
        r = self.client.post('/api/prescriptions/', {
            'medical_record': self.medical_record_a.pk,
            'pet': self.pet_a.pk,
            'notes': 'rx test',
            'items': [
                {'product': self.product_b_rx.pk, 'dose': '1ml', 'quantity': '1.00'},
            ],
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        # ExceptionHandler envuelve en {code, errors}
        errors = r.data['errors']
        self.assertIn('items', errors)
        # Items is a list; el primero (índice 0) tiene el error de product
        items_err = errors['items']
        self.assertTrue(
            any('Acceso inválido' in str(e) for e in items_err),
            msg=f"Esperaba 'Acceso inválido' en items errors: {items_err}",
        )
        # Verifica que ningún Prescription ni PrescriptionItem se creó
        self.assertFalse(Prescription.objects.filter(medical_record=self.medical_record_a).exists())
        self.assertFalse(PrescriptionItem.objects.filter(product=self.product_b_rx).exists())

    def test_create_prescription_with_nested_same_org_product_succeeds(self):
        r = self.client.post('/api/prescriptions/', {
            'medical_record': self.medical_record_a.pk,
            'pet': self.pet_a.pk,
            'notes': 'rx ok',
            'items': [
                {'product': self.product_a_rx.pk, 'dose': '5ml cada 8h', 'quantity': '2.00'},
            ],
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, msg=r.data)
        rx = Prescription.objects.get(medical_record=self.medical_record_a)
        self.assertEqual(rx.items.count(), 1)
        self.assertEqual(rx.items.first().product_id, self.product_a_rx.pk)

    # --- Endpoint /items/ con PrescriptionItemWriteSerializer -----------------

    def _create_prescription(self):
        r = self.client.post('/api/prescriptions/', {
            'medical_record': self.medical_record_a.pk,
            'pet': self.pet_a.pk,
            'notes': 'base',
            'items': [
                {'product': self.product_a_rx.pk, 'dose': '5ml', 'quantity': '1.00'},
            ],
        }, format='json')
        assert r.status_code == 201, r.data
        return Prescription.objects.get(medical_record=self.medical_record_a)

    def test_add_item_endpoint_cross_tenant_product_returns_400(self):
        rx = self._create_prescription()
        r = self.client.post(f'/api/prescriptions/{rx.pk}/items/', {
            'product': self.product_b_rx.pk,
            'dose': '1ml',
            'quantity': '1.00',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['errors'], {'product': ['Acceso inválido.']})

    def test_add_item_endpoint_same_org_product_without_requires_prescription_returns_domain_error(self):
        """Verifica orden: tenant primero, requires_prescription después.
        Producto mismo-org con requires_prescription=False → mensaje de dominio,
        NO 'Acceso inválido'."""
        rx = self._create_prescription()
        r = self.client.post(f'/api/prescriptions/{rx.pk}/items/', {
            'product': self.product_a_otc.pk,
            'dose': '1ml',
            'quantity': '1.00',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product', r.data['errors'])
        self.assertNotIn('Acceso inválido', str(r.data['errors']['product']))
        self.assertIn('no requiere receta', str(r.data['errors']['product']))

    # --- Observabilidad -------------------------------------------------------

    def test_cross_tenant_emits_tenant_validation_rejected_log(self):
        with self.assertLogs('apps.tenant_validation', level='WARNING') as cm:
            self.client.post('/api/prescriptions/', {
                'medical_record': self.medical_record_a.pk,
                'pet': self.pet_a.pk,
                'items': [
                    {'product': self.product_b_rx.pk, 'dose': '1ml', 'quantity': '1.00'},
                ],
            }, format='json')
        records = [r for r in cm.records if r.getMessage() == 'TENANT_VALIDATION_REJECTED']
        self.assertGreaterEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.source, 'serializer')
        self.assertEqual(rec.serializer, 'PrescriptionItemSerializer')
        self.assertEqual(rec.field, 'product')
        self.assertEqual(rec.user_org_id, self.org_a.pk)
        self.assertEqual(rec.resource_org_id, self.org_b.pk)
        self.assertEqual(rec.resource_pk, self.product_b_rx.pk)

    # --- PATCH nested edge cases ----------------------------------------------

    def test_patch_prescription_replace_items_cross_tenant_product_returns_400(self):
        rx = self._create_prescription()
        # PATCH requiere prescription.update — autenticar como ADMIN
        self.client.force_authenticate(self.admin_a)
        # PATCH con items reemplaza todo el array (PrescriptionSerializer.update()
        # hace all_objects.filter(...).delete() + create). Tenant check debe
        # rechazar el producto cross-org y NO ejecutar el delete.
        r = self.client.patch(f'/api/prescriptions/{rx.public_id}/', {
            'items': [
                {'product': self.product_b_rx.pk, 'dose': '2ml', 'quantity': '1.00'},
            ],
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, msg=r.data)
        # Items originales preservados (no delete por rollback)
        rx.refresh_from_db()
        self.assertEqual(rx.items.count(), 1)
        self.assertEqual(rx.items.first().product_id, self.product_a_rx.pk)

    def test_patch_prescription_notes_only_does_not_touch_items(self):
        rx = self._create_prescription()
        original_item_id = rx.items.first().pk
        # PATCH requiere prescription.update — autenticar como ADMIN
        self.client.force_authenticate(self.admin_a)
        r = self.client.patch(f'/api/prescriptions/{rx.public_id}/', {
            'notes': 'actualizado',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, msg=r.data)
        rx.refresh_from_db()
        self.assertEqual(rx.notes, 'actualizado')
        self.assertEqual(rx.items.count(), 1)
        self.assertEqual(rx.items.first().pk, original_item_id)
