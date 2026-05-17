"""Tests del default `DEFAULT_PERMISSION_CLASSES = IsAuthenticated` (Issue #13, ADR p15).

Asegura que:
- El default está activo (views nuevas heredan IsAuthenticated, no AllowAny).
- Los endpoints públicos /api/token/ y /api/token/refresh/ siguen accesibles sin auth
  porque declaran permission_classes=[AllowAny] explícito.
"""
from django.test import TestCase
from django.urls import reverse


class DefaultPermissionClassesTests(TestCase):

    def test_settings_has_default_permission_classes(self):
        from django.conf import settings
        default_perms = settings.REST_FRAMEWORK.get('DEFAULT_PERMISSION_CLASSES')
        self.assertIsNotNone(
            default_perms,
            "DEFAULT_PERMISSION_CLASSES no configurado — views nuevas heredan AllowAny",
        )
        self.assertIn(
            'rest_framework.permissions.IsAuthenticated',
            list(default_perms),
            "Default debe incluir IsAuthenticated",
        )

    def test_token_endpoint_remains_public(self):
        """POST a /api/token/ sin auth debe responder 400/401 (credentials inválidas).
        NO 403 (que indicaría que el default IsAuthenticated bloqueó la vista)."""
        url = reverse('token_obtain_pair')
        resp = self.client.post(
            url,
            {'username': 'noexiste', 'password': 'x'},
            content_type='application/json',
        )
        self.assertIn(
            resp.status_code,
            (400, 401),
            f"Endpoint público de login bloqueado por permission default (status={resp.status_code})",
        )

    def test_token_refresh_endpoint_remains_public(self):
        url = reverse('token_refresh')
        resp = self.client.post(
            url,
            {'refresh': 'invalid'},
            content_type='application/json',
        )
        self.assertIn(
            resp.status_code,
            (400, 401),
            f"Endpoint público de refresh bloqueado por permission default (status={resp.status_code})",
        )
