from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Invoice, Service
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.inventory.models import Presentation, Product
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
