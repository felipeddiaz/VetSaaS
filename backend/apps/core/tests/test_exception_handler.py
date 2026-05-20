"""
Tests del handler ProtectedError bounded (PR-4B / ADR p16).

Verifica:
- isinstance EXACTO con ProtectedError (no IntegrityError ni broad Exception)
- Status 409 Conflict (override ADR p15 §8 — semántica REST correcta)
- Shape canónico {code, message, protected_count, protected_sample}
- Sample con dict {type, id, public_id} — NUNCA str(p)
- Probe bounded `[:6]`, COUNT solo si saturado, cap 1000
"""
from unittest.mock import patch

from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from rest_framework.test import APIRequestFactory

from django.test import TestCase

from apps.core.exceptions import custom_exception_handler, _handle_protected_error
from apps.medical_records.models import MedicalRecord
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet


class _FakeContext(dict):
    """Stub mínimo del context de DRF."""
    def __init__(self):
        super().__init__()
        self['view'] = None


class ProtectedErrorHandlerTests(TestCase):

    def setUp(self):
        self.ctx = _FakeContext()

    def _trigger_protected_error(self, num_children=1):
        """Crea org/owner/pets reales y captura el ProtectedError del cascade."""
        org = Organization.objects.create(name=f"Org PE {num_children}", timezone="UTC")
        owner = Owner.objects.create(name="Own PE", phone="555", organization=org)
        for i in range(num_children):
            Pet.objects.create(name=f"Pet {i}", species="dog", owner=owner, organization=org)
        try:
            owner.delete()
        except ProtectedError as exc:
            return exc
        self.fail("ProtectedError no se levantó — el setup no creó la condición.")

    def test_returns_409_conflict(self):
        exc = self._trigger_protected_error()
        response = custom_exception_handler(exc, self.ctx)
        self.assertEqual(response.status_code, 409)

    def test_response_shape(self):
        exc = self._trigger_protected_error()
        response = custom_exception_handler(exc, self.ctx)
        self.assertEqual(response.data['code'], 'resource_has_dependencies')
        self.assertIn('No se puede eliminar', response.data['message'])
        self.assertIn('protected_count', response.data)
        self.assertIn('protected_count_truncated', response.data)
        self.assertIn('protected_sample', response.data)
        # Tipo consistente: protected_count SIEMPRE int (cardinalidad o cap)
        self.assertIsInstance(response.data['protected_count'], int)
        self.assertIsInstance(response.data['protected_count_truncated'], bool)

    def test_sample_is_dict_not_string(self):
        """Sample NUNCA debe contener str(obj) — defensa contra PII leak + N+1."""
        exc = self._trigger_protected_error(num_children=2)
        response = custom_exception_handler(exc, self.ctx)
        sample = response.data['protected_sample']
        self.assertGreater(len(sample), 0)
        for entry in sample:
            self.assertIsInstance(entry, dict)
            self.assertIn('type', entry)
            self.assertIn('id', entry)
            self.assertIn('public_id', entry)
            # type es label "app.Model" — no expone PII
            self.assertEqual(entry['type'], 'patients.Pet')

    def test_count_exact_when_probe_not_saturated(self):
        """Con < PROBE_LIMIT (6) children, count debe ser int exacto."""
        exc = self._trigger_protected_error(num_children=3)
        response = custom_exception_handler(exc, self.ctx)
        self.assertEqual(response.data['protected_count'], 3)
        self.assertFalse(response.data['protected_count_truncated'])

    def test_sample_limited_to_5_even_if_more(self):
        exc = self._trigger_protected_error(num_children=5)
        response = custom_exception_handler(exc, self.ctx)
        self.assertLessEqual(len(response.data['protected_sample']), 5)

    def test_non_protected_integrity_error_not_handled(self):
        """Regresión: IntegrityError genérico NO debe disparar el handler de
        ProtectedError (mostraría status incorrecto)."""
        exc = IntegrityError("unique constraint violated")
        # No debe entrar al branch ProtectedError → cae al handler default DRF
        # que devolverá None porque IntegrityError no es DRF-known.
        response = custom_exception_handler(exc, self.ctx)
        # IntegrityError es excepción no-DRF → handler default retorna None
        # y nuestro custom_exception_handler genera 500. NO debe ser 409.
        self.assertNotEqual(response.status_code, 409)


class HandlerSaturationTests(TestCase):
    """Tests del path saturado. Como ProtectedError.protected_objects siempre
    es un `set` Python (Django Collector lo materializa), simulamos con set
    real — no necesitamos emular queryset-like ya que el handler resuelve
    via len() para sets/lists."""

    def _make_fake_objects(self, n):
        class _FakeObj:
            class _Meta:
                label = "fake.Stub"
            _meta = _Meta()
            public_id = None

            def __init__(self, pk):
                self.pk = pk

            def __hash__(self):
                return self.pk

            def __eq__(self, other):
                return getattr(other, 'pk', None) == self.pk

        return {_FakeObj(i) for i in range(n)}

    def test_saturated_probe_with_set_uses_len(self):
        """Probe saturado (>=6) con set → count int exacto, truncated=False."""
        fake_objects = self._make_fake_objects(42)
        exc = ProtectedError("msg", fake_objects)
        response = _handle_protected_error(exc)
        self.assertEqual(response.data['protected_count'], 42)
        self.assertFalse(response.data['protected_count_truncated'])

    def test_saturated_probe_above_cap_reports_threshold(self):
        """Probe saturado con cardinalidad >1000 → count=1000, truncated=True."""
        fake_objects = self._make_fake_objects(1500)
        exc = ProtectedError("msg", fake_objects)
        response = _handle_protected_error(exc)
        self.assertEqual(response.data['protected_count'], 1000)
        self.assertTrue(response.data['protected_count_truncated'])
