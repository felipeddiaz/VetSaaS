from decimal import Decimal

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


class InvoiceStateMachineTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Org SM Test", timezone="UTC")
        cls.admin = _make_user("adm_sm", cls.org, "ADMIN")
        cls.owner = Owner.objects.create(name="Cliente SM", phone="5551111111", organization=cls.org)
        cls.pet = Pet.objects.create(name="Firulais SM", species="dog", owner=cls.owner, organization=cls.org)
        cls.service = Service.objects.create(name="Consulta SM", base_price=Decimal("300.00"), organization=cls.org)

    def _make_invoice(self):
        return Invoice.objects.create(
            owner=self.owner, pet=self.pet, organization=self.org,
            status='draft', invoice_type='direct_sale',
        )

    def _add_service_item(self, invoice):
        InvoiceItem.objects.create(
            invoice=invoice, service=self.service,
            description=self.service.name, quantity=1,
            unit_price=self.service.base_price, organization=self.org,
        )

    def _url(self, invoice, suffix=''):
        return f'/api/billing/invoices/{invoice.public_id}/{suffix}'

    def setUp(self):
        self.client.force_authenticate(self.admin)

    # --- confirm ---

    def test_confirm_empty_invoice_returns_400(self):
        invoice = self._make_invoice()
        r = self.client.patch(self._url(invoice, 'confirm/'))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_with_item_returns_200(self):
        invoice = self._make_invoice()
        self._add_service_item(invoice)
        r = self.client.patch(self._url(invoice, 'confirm/'))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'confirmed')

    # --- pay ---

    def test_pay_draft_invoice_returns_400(self):
        invoice = self._make_invoice()
        self._add_service_item(invoice)
        r = self.client.patch(self._url(invoice, 'pay/'), {'payment_method': 'cash'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pay_confirmed_invoice_succeeds(self):
        invoice = self._make_invoice()
        self._add_service_item(invoice)
        self.client.patch(self._url(invoice, 'confirm/'))
        r = self.client.patch(self._url(invoice, 'pay/'), {'payment_method': 'cash'})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'paid')

    # --- edit state machine ---

    def test_edit_confirmed_invoice_returns_400(self):
        invoice = self._make_invoice()
        self._add_service_item(invoice)
        self.client.patch(self._url(invoice, 'confirm/'))
        r = self.client.patch(self._url(invoice), {'notes': 'intento editar'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_edit_cancelled_invoice_returns_400(self):
        invoice = self._make_invoice()
        self._add_service_item(invoice)
        self.client.patch(self._url(invoice, 'confirm/'))
        self.client.patch(self._url(invoice, 'cancel/'))
        r = self.client.patch(self._url(invoice), {'notes': 'intento editar'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_edit_paid_invoice_returns_400(self):
        invoice = self._make_invoice()
        self._add_service_item(invoice)
        self.client.patch(self._url(invoice, 'confirm/'))
        self.client.patch(self._url(invoice, 'pay/'), {'payment_method': 'cash'})
        r = self.client.patch(self._url(invoice), {'notes': 'intento editar'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # --- total protection ---

    def test_invoice_total_not_overridable_from_client(self):
        invoice = self._make_invoice()
        self._add_service_item(invoice)
        invoice.refresh_from_db()
        real_total = invoice.total
        self.client.patch(self._url(invoice), {'total': '99999.00'}, format='json')
        invoice.refresh_from_db()
        self.assertEqual(invoice.total, real_total)


class LazyInvoiceCreationTests(APITestCase):
    """Tests para creación lazy de facturas (sin Signal A, con Signal B corregida)."""

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import OrganizationSettings

        cls.org = Organization.objects.create(name="Org Lazy Test", timezone="UTC")
        # Asegurar toggles ON — update_or_create para que sea idempotente
        # incluso si la data migration ya creó la fila con default=False
        settings, _ = OrganizationSettings.objects.get_or_create(organization=cls.org)
        settings.auto_create_invoice_on_done = True
        settings.auto_create_medical_record = True
        settings.save(update_fields=['auto_create_invoice_on_done', 'auto_create_medical_record'])

        cls.vet = _make_user("vet_lazy", cls.org, "VET")
        cls.owner = Owner.objects.create(name="Cliente Lazy", phone="5552222222", organization=cls.org)
        cls.pet = Pet.objects.create(name="Max Lazy", species="cat", owner=cls.owner, organization=cls.org)
        cls.service = Service.objects.create(name="Consulta Lazy", base_price=Decimal("250.00"), organization=cls.org)

    def setUp(self):
        self.client.force_authenticate(self.vet)

    def test_walk_in_no_auto_invoice(self):
        """Walk-in: crear MedicalRecord sin cita → NO se crea Invoice automáticamente."""
        from apps.medical_records.models import MedicalRecord

        r = self.client.post('/api/medical-records/', {
            'pet': self.pet.id,
            'consultation_type': 'general',
            'diagnosis': 'Consulta walk-in',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mr_id = r.data['id']

        # Verificar que NO existe factura vinculada
        self.assertFalse(Invoice.objects.filter(medical_record_id=mr_id).exists())

    def test_product_sync_creates_invoice_lazy(self):
        """Walk-in: agregar producto → Invoice creada lazy."""
        from apps.medical_records.models import MedicalRecord
        from apps.inventory.models import Product, Presentation

        # Crear consulta walk-in
        r = self.client.post('/api/medical-records/', {
            'pet': self.pet.id,
            'consultation_type': 'general',
            'diagnosis': 'Consulta con producto',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mr = MedicalRecord.objects.get(pk=r.data['id'])

        # Crear producto con presentacion
        product = Product.objects.create(
            name="Producto Lazy",
            internal_code="LAZY001",
            category='medication',
            organization=self.org,
        )
        presentation = Presentation.objects.create(
            product=product,
            name="Caja 10 und",
            base_unit='unit',
            stock=10,
            sale_price=Decimal("50.00"),
            organization=self.org,
        )

        # Agregar producto a la consulta
        r = self.client.post(f'/api/medical-records/{mr.public_id}/products/', {
            'presentation': presentation.id,
            'quantity': '1',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        # Verificar que AHORA existe factura vinculada
        self.assertTrue(Invoice.objects.filter(medical_record=mr).exists())
        invoice = Invoice.objects.get(medical_record=mr)
        self.assertEqual(invoice.status, 'draft')

    def test_appointment_done_creates_invoice_with_link(self):
        """Cita → done → Invoice creada con link a cita Y consulta."""
        from apps.medical_records.models import MedicalRecord
        from apps.appointments.models import Appointment

        # Crear cita con reason (required field)
        appt = Appointment.objects.create(
            pet=self.pet,
            date='2026-06-01',
            start_time='10:00',
            end_time='11:00',
            status='in_progress',
            reason='Consulta rutinaria',
            veterinarian=self.vet,
            organization=self.org,
        )

        # Marcar como done (esto crea MedicalRecord y factura)
        r = self.client.patch(f'/api/appointments/{appt.public_id}/status/', {'status': 'done'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # Verificar que existe MedicalRecord
        mr = MedicalRecord.objects.filter(appointment=appt).first()
        self.assertIsNotNone(mr)

        # Verificar que existe factura vinculada a AMBOS
        invoice = Invoice.objects.filter(appointment=appt).first()
        self.assertIsNotNone(invoice)
        if invoice:
            self.assertEqual(invoice.medical_record, mr)
            self.assertEqual(invoice.status, 'draft')

    def test_orphan_invoice_recovery_on_sync(self):
        """Invoice de cita sin medical_record → agregar servicio → linkeada."""
        from apps.medical_records.models import MedicalRecord
        from apps.appointments.models import Appointment
        from apps.billing.models import Invoice

        # Crear cita
        appt = Appointment.objects.create(
            pet=self.pet,
            date='2026-06-02',
            start_time='14:00',
            end_time='15:00',
            status='in_progress',
            reason='Seguimiento',
            veterinarian=self.vet,
            organization=self.org,
        )

        # Marcar como done
        r = self.client.patch(f'/api/appointments/{appt.public_id}/status/', {'status': 'done'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        mr = MedicalRecord.objects.filter(appointment=appt).first()
        self.assertIsNotNone(mr)

        # Simular race: invoice creada sin medical_record
        invoice = Invoice.objects.filter(appointment=appt).first()
        if invoice:
            invoice.medical_record = None
            invoice.save(update_fields=['medical_record'])
            invoice.refresh_from_db()
            self.assertIsNone(invoice.medical_record)

            # Agregar servicio → debería linkear la invoice huérfana
            r = self.client.post(f'/api/medical-records/{mr.public_id}/services/', {
                'service': self.service.id,
                'quantity': '1',
            }, format='json')
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)

            # Verificar que la invoice ahora está linkeada
            invoice.refresh_from_db()
            self.assertEqual(invoice.medical_record, mr)
