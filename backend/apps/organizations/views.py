"""
Views de Organization — PR-4B / ADR p16.

Cambios respecto al modelo anterior (`OrganizationViewSet ModelViewSet`):

1. **Singleton `/api/organizations/me/`** (`OrganizationMeView`): única forma
   semánticamente correcta de acceder/editar la org propia. Sin pk en URL,
   sin exposición del PK secuencial interno.

2. **Legacy `/api/organizations/<pk>/`** (`OrganizationLegacyView`):
   mantiene retrocompat 90 días pero con validación EXPLÍCITA `pk ==
   request.user.organization_id` → 404 si mismatch. NO devuelve silenciosamente
   "tu org" cuando el pk no calza (rompe expectativas REST).
   Headers RFC 8594 en TODO response (200, 404, 405).

3. **Router DELETE/POST/list removidos**: dos views explícitas reemplazan al
   ModelViewSet completo. No hay forma de listar/crear/borrar orgs vía API.

Rollback: revertir config/urls.py + este archivo. Sin schema migration.
"""
import logging
from datetime import datetime, timezone

from rest_framework import generics
from rest_framework.exceptions import APIException, NotFound

from apps.core.permissions import HybridPermission
from apps.organizations.models import Organization, OrganizationSettings
from apps.organizations.serializers import (
    OrganizationSerializer,
    OrganizationSettingsSerializer,
)


_deprecation_logger = logging.getLogger('core.deprecation')


# Headers RFC 8594. Sunset = fecha tras la cual /<pk>/ responde 410 Gone
# (gate sin más extensiones — ADR p15 §6). Fijada a +90 días del release.
_SUNSET_DATETIME = datetime(2026, 8, 17, 23, 59, 59, tzinfo=timezone.utc)
_SUNSET_DATE = 'Mon, 17 Aug 2026 23:59:59 GMT'


class _EndpointSunsetException(APIException):
    """410 Gone para endpoints removidos post-Sunset RFC 8594.
    Pasa por custom_exception_handler — shape {code, message} canónico."""
    status_code = 410
    default_detail = "Este endpoint fue removido. Usa /api/organizations/me/."
    default_code = 'endpoint_sunset'
_DEPRECATION_HEADERS = {
    'Deprecation': 'true',
    'Sunset': _SUNSET_DATE,
    'Link': '</api/organizations/me/>; rel="successor-version"',
}


class OrganizationMeView(generics.RetrieveUpdateAPIView):
    """Singleton: GET/PATCH sobre la org propia. PK nunca aparece en URL."""
    serializer_class = OrganizationSerializer
    permission_classes = [HybridPermission]
    resource_name = "organization"
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        # request.user.organization viene cargado por TenantJWTAuthentication
        # con select_related — no genera query nueva.
        # Guard: TenantJWTAuthentication permite user.organization=None con
        # warning log. Sin esta guard, get_object() devuelve None y
        # RetrieveUpdateAPIView crash al serializar (TypeError).
        org = self.request.user.organization
        if org is None:
            raise NotFound("Organización no asignada al usuario.")
        return org


class OrganizationLegacyView(generics.RetrieveUpdateAPIView):
    """
    Endpoint legacy con pk explícito. Mantenido por retrocompat hasta
    Sunset (ver _SUNSET_DATETIME). Cualquier pk distinto a la org del
    request devuelve 404 — NO se filtra silenciosamente a la org del
    usuario. Post-Sunset → 410 Gone automático.
    """
    serializer_class = OrganizationSerializer
    permission_classes = [HybridPermission]
    resource_name = "organization"
    http_method_names = ['get', 'patch', 'head', 'options']

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Fail-safe RFC 8594: post-Sunset el endpoint deja de servir.
        # Raise APIException → custom_exception_handler convierte a 410 con
        # renderer setup correcto. Sin esto, "deprecation" sería voluntaria.
        # ADR p15 §6 prometía 410 Gone automático.
        if datetime.now(timezone.utc) > _SUNSET_DATETIME:
            raise _EndpointSunsetException()

    def get_object(self):
        pk = self.kwargs.get('pk')
        try:
            pk_int = int(pk)
        except (TypeError, ValueError):
            raise NotFound("El recurso solicitado no existe.")
        if pk_int != self.request.user.organization_id:
            raise NotFound("El recurso solicitado no existe.")
        # Defensa adicional contra user.organization=None (mismo riesgo
        # que OrganizationMeView). Si organization_id es None, el `!= pk_int`
        # arriba ya falla y retorna 404 — pero esto cubre el caso edge donde
        # alguien pasa pk=0 + organization_id=0.
        org = self.request.user.organization
        if org is None:
            raise NotFound("Organización no asignada al usuario.")
        return org

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        # Headers Sunset/Deprecation/Link en TODO response (200, 404, 405)
        # para que clientes con caches o monitoring puedan detectar la
        # deprecación incluso en errores.
        for header, value in _DEPRECATION_HEADERS.items():
            response[header] = value
        # Log estructurado de adopción — sirve para decidir si cortar a 410
        # post-Sunset (gate: 0 hits durante 7 días).
        _deprecation_logger.warning(
            "DEPRECATED_ENDPOINT_HIT",
            extra={
                "event": "DEPRECATED_ENDPOINT_HIT",
                "endpoint": request.path,
                "method": request.method,
                "user_id": getattr(request.user, 'pk', None),
                "org_id": getattr(request.user, 'organization_id', None),
                "successor": "/api/organizations/me/",
                "sunset": _SUNSET_DATE,
            },
        )
        return response


class OrganizationSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSettingsSerializer
    permission_classes = [HybridPermission]
    resource_name = "organization"
    http_method_names = ['get', 'patch']

    def get_object(self):
        org = self.request.user.organization
        settings, _ = OrganizationSettings.objects.get_or_create(organization=org)
        return settings
