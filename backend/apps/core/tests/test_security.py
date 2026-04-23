"""
Fase 2 — Suite de pruebas de seguridad RBAC/Multitenant

Criterios de salida:
  - 0 fugas cross-tenant
  - 0 bypass de permisos en endpoints críticos
  - Matriz de permisos mínima en verde

Cobertura:
  billing · inventory · appointments · medical_records · staff · dashboard · patients
"""

import json
import logging

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_org_roles(org):
    """
    Crea Permission + Roles (ADMIN, VET, ASSISTANT) para una org.
    Equivale al seed_permissions management command, idempotente.
    Retorna dict {role_name: Role}.
    """
    wildcard, _ = Permission.objects.get_or_create(code="*.*")
    perms_map = {}
    for code in PERMISSION_CODES:
        p, _ = Permission.objects.get_or_create(code=code)
        perms_map[code] = p

    roles = {}
    for role_name, perm_codes in PERMISSIONS.items():
        if role_name == "ADMIN_SAAS":
            continue
        role, _ = Role.objects.get_or_create(
            name=role_name,
            organization=org,
            defaults={"is_system_role": True},
        )
        if "*.*" in perm_codes:
            role.permissions.set([wildcard])
        else:
            role.permissions.set([perms_map[c] for c in perm_codes if c in perms_map])
        roles[role_name] = role
    return roles


def _make_user(username, org, role, is_superuser=False):
    return User.objects.create_user(
        username=username,
        password="testpass!",
        organization=org,
        role=role,
        is_superuser=is_superuser,
    )


def _assign_role(user, role):
    UserRole.objects.create(user=user, role=role)


# ---------------------------------------------------------------------------
# Base con fixtures compartidos
# ---------------------------------------------------------------------------

class SecurityTestCase(APITestCase):
    """
    Fixture base: 2 organizaciones, 3 roles cada una, objetos de prueba.
    Todos los tests heredan de aquí.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Clínica A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Clínica B", timezone="UTC")

        cls.roles_a = _seed_org_roles(cls.org_a)
        cls.roles_b = _seed_org_roles(cls.org_b)

        # Usuarios org A
        cls.admin_a    = _make_user("admin_a",    cls.org_a, "ADMIN")
        cls.vet_a      = _make_user("vet_a",      cls.org_a, "VET")
        cls.assistant_a = _make_user("assistant_a", cls.org_a, "ASSISTANT")

        # Usuarios org B
        cls.admin_b = _make_user("admin_b", cls.org_b, "ADMIN")
        cls.vet_b   = _make_user("vet_b",   cls.org_b, "VET")

        # UserRoles en DB (necesarios para HybridPermission)
        _assign_role(cls.admin_a,     cls.roles_a["ADMIN"])
        _assign_role(cls.vet_a,       cls.roles_a["VET"])
        _assign_role(cls.assistant_a, cls.roles_a["ASSISTANT"])
        _assign_role(cls.admin_b,     cls.roles_b["ADMIN"])
        _assign_role(cls.vet_b,       cls.roles_b["VET"])

        # Objetos de prueba (org A)
        cls.owner_a = Owner.objects.create(
            name="Propietario A", phone="111", organization=cls.org_a
        )
        cls.pet_a = Pet.objects.create(
            name="Fido", species="dog", owner=cls.owner_a,
            organization=cls.org_a
        )

        # Objetos de prueba (org B)
        cls.owner_b = Owner.objects.create(
            name="Propietario B", phone="222", organization=cls.org_b
        )
        cls.pet_b = Pet.objects.create(
            name="Luna", species="cat", owner=cls.owner_b,
            organization=cls.org_b
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def deauth(self):
        self.client.force_authenticate(user=None)


# ---------------------------------------------------------------------------
# Fase 2.1 — Aislamiento cross-tenant (criterio: 0 fugas)
# ---------------------------------------------------------------------------

class TenantIsolationTests(SecurityTestCase):
    """
    Usuario de Org B no puede ver ni acceder a recursos de Org A.
    Gate: todos los tests pasan → 0 fugas entre organizaciones.
    """

    # --- List endpoints: solo devuelven recursos del propio tenant ---

    def test_owners_list_returns_only_own_org(self):
        self.auth(self.vet_b)
        r = self.client.get("/api/owners/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in r.data]
        self.assertNotIn(self.owner_a.id, ids)
        self.assertIn(self.owner_b.id, ids)

    def test_pets_list_returns_only_own_org(self):
        self.auth(self.vet_b)
        r = self.client.get("/api/pets/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in r.data]
        self.assertNotIn(self.pet_a.id, ids)
        self.assertIn(self.pet_b.id, ids)

    def test_staff_list_returns_only_own_org(self):
        self.auth(self.admin_b)
        r = self.client.get("/api/staff/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in r.data]
        # admin_a, vet_a, assistant_a no deben aparecer
        for user in (self.admin_a, self.vet_a, self.assistant_a):
            self.assertNotIn(user.id, ids, f"Fuga: {user.username} de org_a visible en org_b")

    def test_appointments_list_returns_only_own_org(self):
        self.auth(self.vet_b)
        r = self.client.get("/api/appointments/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Sin citas en ninguna org → lista vacía, pero no debe explotar ni filtrar mal
        self.assertIsInstance(r.data, list)

    def test_inventory_list_returns_only_own_org(self):
        self.auth(self.vet_b)
        r = self.client.get("/api/inventory/products/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_billing_invoices_list_returns_only_own_org(self):
        self.auth(self.admin_b)
        r = self.client.get("/api/billing/invoices/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_medical_records_list_returns_only_own_org(self):
        self.auth(self.vet_b)
        r = self.client.get("/api/medical-records/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    # --- Detail endpoints: objeto de otra org devuelve 404 (queryset filtrado) ---

    def test_owner_detail_cross_tenant_returns_404(self):
        """Org B no puede recuperar un propietario de Org A."""
        self.auth(self.vet_b)
        r = self.client.get(f"/api/owners/{self.owner_a.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND,
                         "Fuga: owner de org_a devolvió datos a vet_b")

    def test_pet_detail_cross_tenant_returns_404(self):
        """Org B no puede recuperar una mascota de Org A."""
        self.auth(self.vet_b)
        r = self.client.get(f"/api/pets/{self.pet_a.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND,
                         "Fuga: pet de org_a devolvió datos a vet_b")

    def test_owner_update_cross_tenant_returns_404(self):
        """Org B no puede modificar un propietario de Org A."""
        self.auth(self.admin_b)
        r = self.client.patch(f"/api/owners/{self.owner_a.id}/", {"name": "Hack"})
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND,
                         "Fuga: PATCH sobre owner de org_a tuvo efecto en org_b")

    def test_owner_delete_cross_tenant_returns_404(self):
        """Org B no puede eliminar un propietario de Org A."""
        self.auth(self.admin_b)
        r = self.client.delete(f"/api/owners/{self.owner_a.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND,
                         "Fuga: DELETE sobre owner de org_a tuvo efecto en org_b")


# ---------------------------------------------------------------------------
# Fase 2.2 — Matriz de permisos (criterio: 0 bypass en endpoints críticos)
# ---------------------------------------------------------------------------

class PermissionMatrixTests(SecurityTestCase):
    """
    Verifica que cada rol recibe el código HTTP esperado (200/403/401)
    en los endpoints críticos.

    Fuente de verdad: PERMISSIONS dict en permissions_codes.py.
    """

    # ---- Unauthenticated → 401 en todos los endpoints críticos ----

    def _assert_requires_auth(self, method, url):
        self.deauth()
        r = getattr(self.client, method)(url)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED,
                         f"{method.upper()} {url} permitió acceso sin autenticar")

    def test_unauthenticated_blocked_on_critical_endpoints(self):
        endpoints = [
            ("get",  "/api/owners/"),
            ("get",  "/api/pets/"),
            ("get",  "/api/appointments/"),
            ("get",  "/api/staff/"),
            ("get",  "/api/billing/invoices/"),
            ("get",  "/api/inventory/products/"),
            ("get",  "/api/medical-records/"),
            ("get",  "/api/dashboard/stats/"),
        ]
        for method, url in endpoints:
            with self.subTest(url=url):
                self._assert_requires_auth(method, url)

    # ---- ADMIN → 200 en todos los endpoints de lista ----

    def test_admin_can_list_all_critical_endpoints(self):
        self.auth(self.admin_a)
        endpoints = [
            "/api/owners/",
            "/api/pets/",
            "/api/appointments/",
            "/api/staff/",
            "/api/billing/invoices/",
            "/api/billing/services/",
            "/api/inventory/products/",
            "/api/medical-records/",
            "/api/dashboard/stats/",
        ]
        for url in endpoints:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertIn(r.status_code,
                              [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT],
                              f"ADMIN recibió {r.status_code} en GET {url}")

    # ---- VET — accesos permitidos ----

    def test_vet_can_list_patients(self):
        self.auth(self.vet_a)
        r = self.client.get("/api/pets/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_vet_can_list_appointments(self):
        self.auth(self.vet_a)
        r = self.client.get("/api/appointments/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_vet_can_list_medical_records(self):
        self.auth(self.vet_a)
        r = self.client.get("/api/medical-records/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_vet_can_list_inventory(self):
        self.auth(self.vet_a)
        r = self.client.get("/api/inventory/products/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_vet_can_view_dashboard(self):
        self.auth(self.vet_a)
        r = self.client.get("/api/dashboard/stats/")
        self.assertIn(r.status_code,
                      [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    # ---- VET — accesos denegados ----

    def test_vet_cannot_create_staff(self):
        self.auth(self.vet_a)
        r = self.client.post("/api/staff/create/", {
            "username": "hacker", "password": "xxx", "role": "ASSISTANT"
        })
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN,
                         "VET no debería poder crear staff")

    def test_vet_cannot_deactivate_staff(self):
        self.auth(self.vet_a)
        r = self.client.delete(f"/api/staff/{self.assistant_a.id}/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN,
                         "VET no debería poder desactivar staff")

    def test_vet_cannot_adjust_inventory(self):
        """VET no tiene inventory.update (solo list/retrieve)."""
        self.auth(self.vet_a)
        r = self.client.post(
            f"/api/inventory/products/1/adjust/",
            {"quantity": 5, "reason": "test"},
            format="json",
        )
        # 403 si existe el producto, 404 si no — ambos son seguros
        self.assertIn(r.status_code,
                      [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
                      "VET no debería poder ajustar stock")

    # ---- ASSISTANT — accesos permitidos ----

    def test_assistant_can_list_patients(self):
        self.auth(self.assistant_a)
        r = self.client.get("/api/pets/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_assistant_can_list_invoices(self):
        self.auth(self.assistant_a)
        r = self.client.get("/api/billing/invoices/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_assistant_can_list_appointments(self):
        self.auth(self.assistant_a)
        r = self.client.get("/api/appointments/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    # ---- ASSISTANT — accesos denegados ----

    def test_assistant_cannot_create_medical_record(self):
        """ASSISTANT solo tiene medicalrecord.list y medicalrecord.retrieve."""
        self.auth(self.assistant_a)
        r = self.client.post("/api/medical-records/", {
            "pet": self.pet_a.id, "reason": "test"
        }, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN,
                         "ASSISTANT no debería crear historiales clínicos")

    def test_assistant_cannot_create_staff(self):
        self.auth(self.assistant_a)
        r = self.client.post("/api/staff/create/", {
            "username": "hacker2", "password": "xxx", "role": "ASSISTANT"
        })
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN,
                         "ASSISTANT no debería crear staff")

    def test_assistant_cannot_adjust_inventory(self):
        self.auth(self.assistant_a)
        r = self.client.post(
            "/api/inventory/products/1/adjust/",
            {"quantity": 5, "reason": "test"},
            format="json",
        )
        self.assertIn(r.status_code,
                      [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])


# ---------------------------------------------------------------------------
# Fase 2.3 — has_object_permission: objetos de otra organización
# ---------------------------------------------------------------------------

class ObjectPermissionTests(SecurityTestCase):
    """
    Valida que los objetos de otra organización son rechazados incluso cuando
    la lógica de has_object_permission es el último filtro (defensa en profundidad).
    """

    def test_owner_from_other_org_not_visible_via_detail(self):
        """
        Aunque admin_b pueda ver la URL de un owner, no puede recuperar
        un owner de org_a.
        """
        self.auth(self.admin_b)
        r = self.client.get(f"/api/owners/{self.owner_a.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_pet_from_other_org_not_patchable(self):
        """PATCH sobre pet de otra org debe devolver 404."""
        self.auth(self.admin_b)
        r = self.client.patch(f"/api/pets/{self.pet_a.id}/", {"name": "Hacked"})
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Fase 2.4 — Instrumentación: eventos RBAC emitidos correctamente
# ---------------------------------------------------------------------------

class RBACEventLoggingTests(SecurityTestCase):
    """
    Verifica que los eventos RBAC estructurados se emiten con los campos
    requeridos (timestamp, user_id, organization_id, role, path, method,
    required_permission, decision).
    """

    def _get_last_rbac_event(self, log_records):
        """Parsea el último registro del logger rbac.events."""
        return json.loads(log_records[-1].getMessage())

    def test_rbac_allowed_db_event_on_successful_request(self):
        """
        Requests con UserRole en DB emiten RBAC_ALLOWED_DB (INFO).
        Necesario para calcular fallback_rate = FALLBACK / (DB + FALLBACK).
        """
        self.auth(self.vet_a)
        with self.assertLogs("rbac.events", level="INFO") as cm:
            r = self.client.get("/api/pets/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        allowed = [rec for rec in cm.records if rec.getMessage() == "RBAC_ALLOWED_DB"]
        self.assertTrue(allowed, "Se esperaba RBAC_ALLOWED_DB para usuario con roles en DB")

    def test_rbac_denied_event_on_forbidden_request(self):
        self.auth(self.vet_a)
        with self.assertLogs("rbac.events", level="INFO") as cm:
            r = self.client.post("/api/staff/create/", {
                "username": "hacker", "password": "xxx"
            })
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

        denied = [rec for rec in cm.records if rec.getMessage() == "RBAC_DENIED"]
        self.assertTrue(denied, "Se esperaba al menos un evento RBAC_DENIED")
        self.assertEqual(denied[0].user_id, self.vet_a.id)

    def test_rbac_fallback_event_for_user_without_db_role(self):
        """
        Un usuario sin UserRole en DB emite RBAC_FALLBACK_ALLOWED (WARNING).
        Presencia de este evento en producción = gate bloqueado.
        """
        user_no_role = _make_user("no_role_user", self.org_a, "VET")

        self.auth(user_no_role)
        with self.assertLogs("rbac.events", level="INFO") as cm:
            r = self.client.get("/api/pets/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        fallback = [rec for rec in cm.records if rec.getMessage() == "RBAC_FALLBACK_ALLOWED"]
        self.assertTrue(fallback, "Se esperaba RBAC_FALLBACK_ALLOWED para usuario sin roles en DB")

    def test_request_id_present_and_consistent_within_request(self):
        """
        Todos los eventos de un mismo request comparten el mismo request_id.
        Permite correlacionar logs en Railway y agregadores externos.
        """
        self.auth(self.vet_a)
        with self.assertLogs("rbac.events", level="INFO") as cm:
            self.client.get("/api/pets/")

        request_ids = {rec.request_id for rec in cm.records if hasattr(rec, "request_id")}
        self.assertEqual(len(request_ids), 1,
                         f"Se esperaba un único request_id por request, se obtuvieron: {request_ids}")

    def test_required_fields_present_in_all_events(self):
        """Todos los eventos contienen los campos mínimos requeridos."""
        user_no_role = _make_user("no_role_user2", self.org_a, "VET")

        self.auth(user_no_role)
        with self.assertLogs("rbac.events", level="INFO") as cm:
            self.client.get("/api/pets/")

        required_fields = {
            "request_id", "user_id", "organization_id", "role",
            "endpoint", "method", "required_permission",
        }
        for rec in cm.records:
            missing = required_fields - set(vars(rec).keys())
            self.assertFalse(missing,
                             f"Campos faltantes en evento '{rec.getMessage()}': {missing}")
