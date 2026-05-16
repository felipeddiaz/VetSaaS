from decimal import Decimal
from io import BytesIO

from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Invoice, InvoiceItem, Service
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
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


def _make_role_without(name, org, missing_codes):
    """Crea un rol custom sin los codes indicados."""
    perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}
    role, _ = Role.objects.get_or_create(name=name, organization=org, defaults={"is_system_role": False})
    role.permissions.set([perms_map[c] for c in PERMISSION_CODES if c not in missing_codes])
    return role


def _extract_pdf_text(content):
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


class InvoicePdfTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Clinica PDF", timezone="UTC")
        cls.org_other = Organization.objects.create(name="Otra Clinica", timezone="UTC")

        cls.admin = _make_user("adm_pdf", cls.org, "ADMIN")
        cls.admin_other = _make_user("adm_pdf_other", cls.org_other, "ADMIN")

        cls.owner = Owner.objects.create(name="Maria Lopez", phone="5551234567", organization=cls.org)
        cls.pet = Pet.objects.create(name="Firulais", species="dog", breed="Labrador",
                                     owner=cls.owner, organization=cls.org)

        cls.service = Service.objects.create(name="Consulta General", base_price=Decimal("500.00"),
                                              organization=cls.org)

    def _make_invoice(self, status_value='draft', item_count=3):
        from django.utils import timezone as _tz
        kwargs = dict(
            owner=self.owner, pet=self.pet, organization=self.org,
            status=status_value, invoice_type='consultation',
            subtotal=Decimal("0"), tax_rate=Decimal("0.1600"),
            tax_amount=Decimal("0"), total=Decimal("0"),
        )
        now = _tz.now()
        if status_value in ('confirmed', 'paid'):
            kwargs['confirmed_at'] = now
        if status_value == 'paid':
            kwargs['paid_at'] = now
            kwargs['payment_method'] = 'cash'
        if status_value == 'cancelled':
            kwargs['cancelled_at'] = now
        inv = Invoice.objects.create(**kwargs)
        for i in range(item_count):
            svc = Service.objects.create(
                name=f"Servicio item {inv.pk}_{i}",
                base_price=Decimal("100.00"), organization=self.org,
            )
            InvoiceItem.objects.create(
                invoice=inv, service=svc, organization=self.org,
                description=f"Servicio numero {i+1}",
                quantity=Decimal("1"), unit_price=Decimal("100.00"),
                subtotal=Decimal("100.00"),
            )
        return inv

    def _url(self, invoice):
        return f'/api/billing/invoices/{invoice.public_id}/pdf/'

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_returns_pdf_for_draft(self):
        inv = self._make_invoice('draft')
        r = self.client.get(self._url(inv))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertIn('Firulais', r['Content-Disposition'])
        self.assertIn(f'factura_{inv.id}', r['Content-Disposition'])
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_works_for_all_statuses(self):
        for s in ['draft', 'confirmed', 'paid', 'cancelled']:
            inv = self._make_invoice(s)
            r = self.client.get(self._url(inv))
            self.assertEqual(r.status_code, status.HTTP_200_OK, msg=f"failed for status={s}")

    def test_cross_tenant_returns_404(self):
        inv_other = Invoice.objects.create(
            owner=Owner.objects.create(name="X", phone="555", organization=self.org_other),
            organization=self.org_other, status='draft', invoice_type='direct_sale',
        )
        r = self.client.get(self._url(inv_other))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(None)
        inv = self._make_invoice()
        r = self.client.get(self._url(inv))
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_user_without_permission_rejected(self):
        # Crear usuario con rol que NO tiene invoice.retrieve
        custom_role = _make_role_without("NO_INVOICE_RETRIEVE", self.org, {"invoice.retrieve"})
        u = User.objects.create_user(username="nopermuser", password="pass",
                                     organization=self.org, role="VET")
        UserRole.objects.all().filter(user=u).delete()
        UserRole.objects.create(user=u, role=custom_role)
        self.client.force_authenticate(u)
        inv = self._make_invoice()
        r = self.client.get(self._url(inv))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_n_plus_one_guard(self):
        """El conteo de queries no debe crecer linealmente con N items."""
        inv5 = self._make_invoice(item_count=5)
        inv15 = self._make_invoice(item_count=15)
        # Warmup para evitar primeras-queries (permission cache, etc.)
        self.client.get(self._url(inv5))

        with self.assertNumQueries(self._count_queries(inv5)):
            r5 = self.client.get(self._url(inv5))
        self.assertEqual(r5.status_code, 200)

        with self.assertNumQueries(self._count_queries(inv5)):
            r15 = self.client.get(self._url(inv15))
        self.assertEqual(r15.status_code, 200)

    def _count_queries(self, invoice):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(invoice))
        return len(ctx)

    def test_pdf_text_contains_markers(self):
        inv = self._make_invoice('paid', item_count=2)
        inv.payment_method = 'cash'
        inv.save(update_fields=['payment_method'])
        r = self.client.get(self._url(inv))
        text = _extract_pdf_text(r.content)
        self.assertIn(f"#{inv.id}", text)
        self.assertIn("Firulais", text)
        self.assertIn("Maria Lopez", text)
