from decimal import Decimal
import threading

from django.core.exceptions import ValidationError as DjValidationError
from django.db import IntegrityError, close_old_connections
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import cancel_invoice, confirm_invoice, pay_direct_sale, pay_invoice
from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.inventory.models import MedicalRecordProduct, Presentation, Product
from apps.medical_records.models import MedicalRecord, MedicalRecordService
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


def _seed_roles(org):
    wildcard, _ = Permission.objects.get_or_create(code='*.*')
    perms_map = {code: Permission.objects.get_or_create(code=code)[0] for code in PERMISSION_CODES}
    roles = {}
    for name, codes in PERMISSIONS.items():
        if name == 'ADMIN_SAAS':
            continue
        role, _ = Role.objects.get_or_create(
            name=name,
            organization=org,
            defaults={'is_system_role': True},
        )
        role.permissions.set([wildcard] if '*.*' in codes else [perms_map[c] for c in codes if c in perms_map])
        roles[name] = role
    return roles


class InvoiceConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.org = Organization.objects.create(
            name='Org Concurrency',
            timezone='UTC',
            tax_rate=Decimal('0.16'),
        )
        self.roles = _seed_roles(self.org)
        self.admin = User.objects.create_user(
            username='admin_concurrency',
            password='pass1234!',
            organization=self.org,
            role='ADMIN',
        )
        UserRole.objects.get_or_create(user=self.admin, role=self.roles['ADMIN'])

        self.owner = Owner.objects.create(
            name='Owner Concurrency',
            phone='5551234567',
            organization=self.org,
        )
        self.pet = Pet.objects.create(
            name='Firulais Concurrency',
            species='dog',
            owner=self.owner,
            organization=self.org,
        )
        self.medical_record = MedicalRecord.objects.create(
            pet=self.pet,
            veterinarian=self.admin,
            organization=self.org,
            diagnosis='dx',
            treatment='tx',
        )
        self.service = Service.objects.create(
            name='Consulta Concurrency',
            base_price=Decimal('250.00'),
            organization=self.org,
        )
        self.product = Product.objects.create(
            name='Antibiotico Concurrency',
            internal_code='CONC-001',
            organization=self.org,
        )
        self.presentation = Presentation.objects.create(
            product=self.product,
            name='Caja',
            base_unit='bottle',
            quantity=1,
            sale_price=Decimal('100.00'),
            stock=Decimal('10.00'),
            min_stock=Decimal('1.00'),
            organization=self.org,
        )

    def _run_parallel_requests(self, calls):
        barrier = threading.Barrier(len(calls))
        results = []
        errors = []

        def worker(spec):
            close_old_connections()
            client = APIClient()
            client.force_authenticate(self.admin)
            try:
                barrier.wait(timeout=5)
                method = getattr(client, spec['method'])
                response = method(spec['url'], spec.get('data'), format='json')
                results.append((spec['name'], response.status_code, getattr(response, 'data', None)))
            except Exception as exc:
                errors.append((spec['name'], exc))
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(spec,)) for spec in calls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(errors, msg=f'Parallel request errors: {errors}')
        return results

    def _run_parallel_functions(self, functions):
        barrier = threading.Barrier(len(functions))
        results = []

        def worker(name, fn):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                fn()
                results.append((name, 'ok'))
            except Exception as exc:
                results.append((name, exc))
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(name, fn)) for name, fn in functions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        return results

    def test_parallel_product_and_service_create_single_invoice(self):
        product_url = f'/api/medical-records/{self.medical_record.public_id}/products/'
        service_url = f'/api/medical-records/{self.medical_record.public_id}/services/'

        results = self._run_parallel_requests([
            {
                'name': 'product',
                'method': 'post',
                'url': product_url,
                'data': {'presentation': self.presentation.pk, 'quantity': '1.00'},
            },
            {
                'name': 'service',
                'method': 'post',
                'url': service_url,
                'data': {'service': self.service.pk, 'quantity': '1.00'},
            },
        ])

        self.assertEqual({code for _, code, _ in results}, {status.HTTP_201_CREATED})
        self.assertEqual(Invoice.objects.filter(medical_record=self.medical_record).count(), 1)
        invoice = Invoice.objects.get(medical_record=self.medical_record)
        self.assertEqual(
            InvoiceItem.objects.filter(invoice=invoice, is_active=True).count(),
            2,
        )
        self.assertEqual(MedicalRecordProduct.objects.filter(medical_record=self.medical_record).count(), 1)
        self.assertEqual(MedicalRecordService.objects.filter(medical_record=self.medical_record).count(), 1)

    def test_medical_record_product_create_integrity_error_does_not_decrement_stock(self):
        from django.db import transaction
        with transaction.atomic():
            mrp = MedicalRecordProduct(
                medical_record=self.medical_record,
                presentation=self.presentation,
                quantity=Decimal('2.00'),
                organization=self.org,
            )
            mrp.save()
        self.presentation.refresh_from_db()
        stock_after_first = self.presentation.stock

        duplicate = MedicalRecordProduct(
            medical_record=self.medical_record,
            presentation=self.presentation,
            quantity=Decimal('3.00'),
            organization=self.org,
        )

        with self.assertRaises((IntegrityError, DjValidationError)):
            with transaction.atomic():
                duplicate.save()

        self.presentation.refresh_from_db()
        self.assertEqual(self.presentation.stock, stock_after_first)

    def test_cancel_invoice_parallel_pay_and_cancel_keeps_single_final_state(self):
        invoice = Invoice.objects.create(
            owner=self.owner,
            pet=self.pet,
            organization=self.org,
            status='draft',
            invoice_type='direct_sale',
            tax_rate=self.org.tax_rate,
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            presentation=self.presentation,
            description=str(self.presentation),
            quantity=Decimal('1.00'),
            unit_price=self.presentation.sale_price,
            organization=self.org,
        )
        confirm_invoice(invoice, self.admin)
        self.presentation.refresh_from_db()
        stock_after_confirm = self.presentation.stock

        results = self._run_parallel_functions([
            ('pay', lambda: pay_invoice(invoice, self.admin, 'cash')),
            ('cancel', lambda: cancel_invoice(invoice, self.admin, 'race test')),
        ])

        invoice.refresh_from_db()
        self.presentation.refresh_from_db()
        self.assertIn(invoice.status, {'paid', 'cancelled'})
        self.assertEqual(sum(1 for _, result in results if result == 'ok'), 1)
        self.assertEqual(sum(1 for _, result in results if isinstance(result, DjValidationError)), 1)
        expected_stock = Decimal('10.00') if invoice.status == 'cancelled' else stock_after_confirm
        self.assertEqual(self.presentation.stock, expected_stock)

    def _direct_sale_draft(self, quantity=Decimal('2.00')):
        invoice = Invoice.objects.create(
            owner=self.owner,
            pet=self.pet,
            organization=self.org,
            status='draft',
            invoice_type='direct_sale',
            tax_rate=self.org.tax_rate,
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            presentation=self.presentation,
            description=str(self.presentation),
            quantity=quantity,
            unit_price=self.presentation.sale_price,
            organization=self.org,
        )
        return invoice

    def test_two_parallel_pay_direct_sale_serialize(self):
        """2 POSTs paralelos a /direct-pay/ sobre la misma invoice draft:
        exactamente uno gana (200 + paid + stock descontado UNA vez),
        el otro recibe 400 con error de estado."""
        invoice = self._direct_sale_draft(quantity=Decimal('2.00'))
        self.presentation.refresh_from_db()
        original_stock = self.presentation.stock

        url = f'/api/billing/invoices/{invoice.public_id}/direct-pay/'
        results = self._run_parallel_requests([
            {'name': 'pay_a', 'method': 'post', 'url': url, 'data': {'payment_method': 'cash'}},
            {'name': 'pay_b', 'method': 'post', 'url': url, 'data': {'payment_method': 'cash'}},
        ])

        codes = sorted(code for _, code, _ in results)
        self.assertEqual(codes, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST],
                         msg=f'Expected exactly one 200 and one 400, got {results}')

        invoice.refresh_from_db()
        self.presentation.refresh_from_db()
        self.assertEqual(invoice.status, 'paid')
        self.assertEqual(self.presentation.stock, original_stock - Decimal('2.00'),
                         "Stock se descontó más de una vez (lost-update)")

    def test_two_parallel_invoice_patch_serialize(self):
        """2 PATCHes paralelos a /api/billing/invoices/<pk>/: ambos en draft,
        ambos succeed serializados (lock garantiza orden). Estado final coherente,
        sin corrupción de campos."""
        invoice = self._direct_sale_draft(quantity=Decimal('1.00'))
        url = f'/api/billing/invoices/{invoice.public_id}/'
        # InvoiceSerializer.validate() exige pet/owner incluso en PATCH parcial
        # (bug pre-existente fuera del scope de Día 1-2). Incluimos para que el
        # test mida solo la concurrencia, no la validación.
        base_payload = {'pet': self.pet.pk, 'owner': self.owner.pk}

        results = self._run_parallel_requests([
            {'name': 'patch_a', 'method': 'patch', 'url': url, 'data': {**base_payload, 'notes': 'A'}},
            {'name': 'patch_b', 'method': 'patch', 'url': url, 'data': {**base_payload, 'notes': 'B'}},
        ])

        for name, code, body in results:
            self.assertEqual(code, status.HTTP_200_OK,
                             msg=f'{name} returned {code} body={body}')

        invoice.refresh_from_db()
        self.assertIn(invoice.notes, {'A', 'B'},
                      f'Notes corruptas tras 2 PATCH paralelos: {invoice.notes!r}')
        self.assertEqual(invoice.status, 'draft')

    def test_parallel_pay_direct_sale_and_cancel_keep_consistent_stock(self):
        """pay_direct_sale (draft→paid) y cancel_invoice paralelos sobre misma
        invoice. cancel_invoice rechaza draft (solo cancela confirmed), por lo
        que el resultado canónico: pay_direct_sale gana → paid + stock -1.
        Si cancel_invoice corre antes, ValidationError. Nunca corrupción."""
        invoice = self._direct_sale_draft(quantity=Decimal('1.00'))
        self.presentation.refresh_from_db()
        original_stock = self.presentation.stock

        # Necesitamos refs frescas en cada thread (los modelos pasan por value)
        invoice_pk = invoice.pk

        def do_pay():
            inv = Invoice.objects.get(pk=invoice_pk)
            pay_direct_sale(inv, self.admin, 'cash')

        def do_cancel():
            inv = Invoice.objects.get(pk=invoice_pk)
            cancel_invoice(inv, self.admin, 'race test')

        results = self._run_parallel_functions([
            ('pay', do_pay),
            ('cancel', do_cancel),
        ])

        invoice.refresh_from_db()
        self.presentation.refresh_from_db()

        ok_count = sum(1 for _, r in results if r == 'ok')
        err_count = sum(1 for _, r in results if isinstance(r, DjValidationError))

        # cancel_invoice sobre draft DEBE lanzar ValidationError SIEMPRE.
        # pay_direct_sale sobre draft DEBE quedar paid.
        # Si cancel corre antes que pay y la cancela, pay_direct_sale rechaza.
        # Ambos casos: solo una operación "ok", la otra ValidationError.
        self.assertEqual(ok_count + err_count, 2,
                         msg=f'Resultados inesperados (errores no-DjValidation): {results}')
        self.assertGreaterEqual(ok_count, 1,
                                msg=f'Ninguna operación tuvo éxito: {results}')
        self.assertIn(invoice.status, {'paid', 'cancelled', 'draft'})

        # Invariante de stock: o paid (-1) o sin cambio (cancel sobre draft lanza pero no toca stock)
        if invoice.status == 'paid':
            self.assertEqual(self.presentation.stock, original_stock - Decimal('1.00'))
        else:
            self.assertEqual(self.presentation.stock, original_stock)

    def test_parallel_add_and_delete_same_product_keeps_correct_stock(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        add_url = f'/api/medical-records/{self.medical_record.public_id}/products/'
        initial = client.post(add_url, {'presentation': self.presentation.pk, 'quantity': '1.00'}, format='json')
        self.assertEqual(initial.status_code, status.HTTP_201_CREATED)

        mrp = MedicalRecordProduct.objects.get(medical_record=self.medical_record, presentation=self.presentation)
        delete_url = f'/api/medical-records/{self.medical_record.public_id}/products/{mrp.pk}/'

        results = self._run_parallel_requests([
            {
                'name': 'add',
                'method': 'post',
                'url': add_url,
                'data': {'presentation': self.presentation.pk, 'quantity': '1.00'},
            },
            {
                'name': 'delete',
                'method': 'delete',
                'url': delete_url,
            },
        ])

        self.assertTrue(all(code < 500 for _, code, _ in results), msg=results)
        self.presentation.refresh_from_db()
        remaining_qty = sum(
            MedicalRecordProduct.objects.filter(
                medical_record=self.medical_record,
                presentation=self.presentation,
            ).values_list('quantity', flat=True),
            Decimal('0.00'),
        )
        self.assertEqual(self.presentation.stock + remaining_qty, Decimal('10.00'))

        invoice = Invoice.objects.get(medical_record=self.medical_record)
        item = InvoiceItem.objects.filter(invoice=invoice, presentation=self.presentation, is_active=True).first()
        if item is None:
            self.assertEqual(remaining_qty, Decimal('0.00'))
        else:
            self.assertEqual(item.quantity, remaining_qty)
