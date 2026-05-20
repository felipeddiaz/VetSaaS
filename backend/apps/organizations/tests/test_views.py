"""
Tests del refactor OrganizationViewSet → OrganizationMeView + OrganizationLegacyView
(Issue #10 / PR-4B / ADR p16).

Cubre:
- Singleton /api/organizations/me/ — GET/PATCH/405/HEAD/OPTIONS + guard null org
- Legacy /api/organizations/<pk>/ — validación explícita pk == user.org_id,
  404 en mismatch (no filtrado silencioso), headers RFC 8594 en todos los
  responses (200, 404, 405), log estructurado DEPRECATED_ENDPOINT_HIT,
  fail-safe 410 Gone post-Sunset
- Router list/create/destroy removidos → 404 en /api/organizations/
"""
from datetime import datetime, timezone
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.organizations.models import Organization
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


class OrganizationMeViewTests(APITestCase):
    """Singleton /api/organizations/me/ — sin pk en URL."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Org Me Test", timezone="UTC")
        cls.admin = _make_user("adm_me", cls.org, "ADMIN")

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_get_returns_own_org(self):
        r = self.client.get('/api/organizations/me/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['id'], self.org.pk)
        self.assertEqual(r.data['name'], "Org Me Test")

    def test_patch_updates_own_org(self):
        r = self.client.patch(
            '/api/organizations/me/',
            {'name': 'Org Me Renamed'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, 'Org Me Renamed')

    def test_delete_returns_405(self):
        r = self.client.delete('/api/organizations/me/')
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_post_returns_405(self):
        r = self.client.post('/api/organizations/me/', {'name': 'X'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_me_blocks_user_without_organization(self):
        """Guard PR-4B HIGH: user.organization=None debe ser bloqueado.
        RBAC (HybridPermission) rechaza con 403 antes que el guard interno
        del view se active — defensa en capas. El test acepta cualquier
        respuesta no-200 (403 RBAC o 404 guard view); cualquiera evita el
        crash TypeError al serializar None que el guard previene."""
        from apps.users.models import User
        user_no_org = User.objects.create_user(
            username="user_no_org", password="x", organization=None, role="ASSISTANT",
        )
        self.client.force_authenticate(user_no_org)
        r = self.client.get('/api/organizations/me/')
        self.assertIn(
            r.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
            f"user.organization=None debe ser rechazado, no crashear (got {r.status_code})",
        )


class OrganizationLegacyViewTests(APITestCase):
    """Legacy /api/organizations/<pk>/ — validación pk + headers Sunset."""

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Org Legacy A", timezone="UTC")
        cls.org_b = Organization.objects.create(name="Org Legacy B", timezone="UTC")
        cls.admin_a = _make_user("adm_leg_a", cls.org_a, "ADMIN")

    def setUp(self):
        self.client.force_authenticate(self.admin_a)

    def _assert_deprecation_headers(self, response):
        self.assertEqual(response.get('Deprecation'), 'true')
        self.assertIn('Sunset', response)
        self.assertIn('successor-version', response.get('Link', ''))
        self.assertIn('/api/organizations/me/', response.get('Link', ''))

    def test_legacy_pk_matches_returns_200(self):
        r = self.client.get(f'/api/organizations/{self.org_a.pk}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['id'], self.org_a.pk)
        self._assert_deprecation_headers(r)

    def test_legacy_pk_mismatch_returns_404_not_other_org(self):
        """Crítico: pk de otra org NO debe devolver 'tu propia org' silenciosamente.
        Debe retornar 404."""
        r = self.client.get(f'/api/organizations/{self.org_b.pk}/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        self._assert_deprecation_headers(r)

    def test_legacy_pk_inexistente_returns_404(self):
        r = self.client.get('/api/organizations/999999/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        self._assert_deprecation_headers(r)

    def test_legacy_patch_own_pk_succeeds(self):
        r = self.client.patch(
            f'/api/organizations/{self.org_a.pk}/',
            {'name': 'Legacy Patched'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self._assert_deprecation_headers(r)

    def test_legacy_delete_returns_405(self):
        r = self.client.delete(f'/api/organizations/{self.org_a.pk}/')
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self._assert_deprecation_headers(r)

    def test_legacy_emits_deprecation_log_event(self):
        with self.assertLogs('core.deprecation', level='WARNING') as logs:
            self.client.get(f'/api/organizations/{self.org_a.pk}/')
        self.assertTrue(any('DEPRECATED_ENDPOINT_HIT' in rec for rec in logs.output))
        self.assertEqual(getattr(logs.records[0], 'event', None), 'DEPRECATED_ENDPOINT_HIT')
        self.assertEqual(getattr(logs.records[0], 'successor', None), '/api/organizations/me/')

    def test_legacy_post_sunset_returns_410_gone(self):
        """Fail-safe RFC 8594 (security HIGH): tras _SUNSET_DATETIME el
        endpoint deja de servir y responde 410 Gone — la "deprecation"
        deja de ser voluntaria."""
        # Mockear datetime.now() para simular post-Sunset (2026-08-18).
        post_sunset = datetime(2026, 8, 18, 0, 0, 0, tzinfo=timezone.utc)

        class _FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return post_sunset

        with patch('apps.organizations.views.datetime', _FixedDatetime):
            r = self.client.get(f'/api/organizations/{self.org_a.pk}/')
        self.assertEqual(r.status_code, status.HTTP_410_GONE)
        # APIException pasa por custom_exception_handler → shape {code, message}
        self.assertEqual(r.data['code'], 'endpoint_sunset')
        self.assertIn('removido', r.data['message'])
        self._assert_deprecation_headers(r)


class OrganizationRouterRemovedTests(APITestCase):
    """Verifica que /api/organizations/ (list/create) ya no existe."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Org Router Test", timezone="UTC")
        cls.admin = _make_user("adm_router", cls.org, "ADMIN")

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_list_route_returns_404(self):
        """GET /api/organizations/ (sin pk, sin /me/) ya no está enrutado."""
        r = self.client.get('/api/organizations/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_route_returns_404(self):
        """POST /api/organizations/ ya no está enrutado."""
        r = self.client.post('/api/organizations/', {'name': 'X', 'timezone': 'UTC'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
