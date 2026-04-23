"""
core/permissions.py — Sistema RBAC de VetCare SaaS
===================================================

FASES IMPLEMENTADAS:
  Fase 1 — RolePermission: control estático basado en PERMISSIONS dict
  Fase 3 — HybridPermission: DB-backed con cache + fallback estático

REGLAS:
  1. Permisos en formato "resource.action"
  2. has_object_permission SIEMPRE valida organization primero (multitenant)
  3. Acciones custom SIEMPRE definen required_permission en la view
  4. Nunca lógica de roles en views
  5. PERMISSION_CODES es la fuente única de verdad
  6. Wildcard global es "*.*"
  7. Excepciones documentadas explícitamente (ej: acceso a propio usuario)
"""
import logging

from rest_framework.permissions import BasePermission

from .permissions_codes import PERMISSIONS

logger = logging.getLogger(__name__)
rbac_logger = logging.getLogger("rbac.events")


# ---------------------------------------------------------------------------
# Observabilidad — eventos RBAC estructurados (stdout en producción)
# ---------------------------------------------------------------------------
# Eventos emitidos:
#   RBAC_ALLOWED_DB          (INFO)    — permitido por roles en DB (fuente de verdad)
#   RBAC_FALLBACK_ALLOWED    (WARNING) — permitido por fallback estático (sin UserRole en DB)
#   RBAC_DENIED              (WARNING) — acceso denegado (cualquier fuente)
#   TENANT_MISMATCH_DETECTED (ERROR)   — intento de acceso a recurso de otra organización
#
# Los cuatro eventos permiten calcular:
#   fallback_rate = RBAC_FALLBACK_ALLOWED / (RBAC_ALLOWED_DB + RBAC_FALLBACK_ALLOWED)
#   denied_rate   = RBAC_DENIED / total_requests (por endpoint)
#
# Gate Fase 4: ausencia de RBAC_FALLBACK_ALLOWED y TENANT_MISMATCH_DETECTED en 7 días
# con ≥500 requests totales y ≥1 request por cada endpoint crítico.

import uuid


def _get_request_id(request) -> str:
    """
    ID de correlación por request — permite agrupar todos los eventos RBAC
    de una misma petición HTTP en Railway logs o cualquier agregador.
    Se genera una sola vez y se cachea en el objeto request.
    """
    if not hasattr(request, "_rbac_request_id"):
        request._rbac_request_id = uuid.uuid4().hex[:12]
    return request._rbac_request_id


def _rbac_extra(request, user, required: str | None) -> dict:
    return {
        "request_id": _get_request_id(request),
        "user_id": getattr(user, "id", None),
        "organization_id": getattr(user, "organization_id", None),
        "role": getattr(user, "role", None),
        "endpoint": getattr(request, "path", None),
        "method": getattr(request, "method", None),
        "required_permission": required,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _method_to_action(method: str, view) -> str:
    """
    Deriva el nombre de acción DRF a partir del método HTTP.
    Usado como fallback cuando la view no es un ViewSet.
    """
    method = method.upper()
    if method == "GET":
        # Distingue list vs retrieve por la presencia de pk/id en kwargs
        kwargs = getattr(view, "kwargs", {}) or {}
        if any(k in kwargs for k in ("pk", "id")):
            return "retrieve"
        return "list"
    return {
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "destroy",
    }.get(method, "list")


def _resolve_required(request, view) -> str | None:
    """
    Determina el permiso requerido para una request+view.

    Orden de resolución:
      1. view.required_permission (siempre tiene precedencia — acciones custom)
      2. f"{resource}.{action}" construido desde basename/resource_name + action
      3. None si no se puede determinar (view sin recurso definido)
    """
    required = getattr(view, "required_permission", None)
    if required:
        return required

    # Soporte ViewSets (basename) y generic views (resource_name)
    resource = getattr(view, "basename", None) or getattr(view, "resource_name", None)
    if not resource:
        return None

    # Soporte ViewSets (action) y generic views (derivado del método HTTP)
    action = getattr(view, "action", None) or _method_to_action(request.method, view)
    return f"{resource}.{action}"


def _is_allowed(required: str, allowed: list) -> bool:
    """
    Evalúa si `required` está cubierto por `allowed`.
    Soporta wildcards: "*.*" (global) y "resource.*" (por recurso).
    """
    if not required:
        return True

    resource = required.split(".")[0]
    return (
        "*.*" in allowed
        or f"{resource}.*" in allowed
        or required in allowed
    )


# ---------------------------------------------------------------------------
# Fase 1 — RolePermission (control estático)
# ---------------------------------------------------------------------------

class RolePermission(BasePermission):
    """
    Control de acceso basado en el rol estático del usuario (campo role en User).

    Fuente de permisos: PERMISSIONS dict en permissions_codes.py.

    Compatible con:
      - ViewSets (usa view.basename y view.action)
      - Generic class-based views (usa view.resource_name + método HTTP)
      - Function-based views (usa view.required_permission establecido en el handler)

    Prioridad de resolución del permiso requerido:
      view.required_permission > basename/resource_name + action
    """

    def has_permission(self, request, view) -> bool:
        if not request.user.is_authenticated:
            return False

        # Superadmin de plataforma siempre tiene acceso
        if request.user.is_superuser:
            return True

        role = request.user.role  # noqa: F841 (usado implícitamente vía PERMISSIONS)
        required = _resolve_required(request, view)

        # Si no se puede determinar el recurso, denegar acceso (fail-closed).
        # Toda view con RolePermission debe definir resource_name o required_permission.
        if required is None:
            return False

        allowed = PERMISSIONS.get(role, [])
        result = _is_allowed(required, allowed)
        extra = _rbac_extra(request, request.user, required)
        if result:
            rbac_logger.warning("RBAC_FALLBACK_ALLOWED", extra=extra)
        else:
            rbac_logger.warning("RBAC_DENIED", extra=extra)
        return result

    def has_object_permission(self, request, view, obj) -> bool:
        # Regla 1 (SIEMPRE PRIMERO): aislamiento multitenant
        if hasattr(obj, "organization_id"):
            if obj.organization_id != request.user.organization_id:
                rbac_logger.error("TENANT_MISMATCH_DETECTED", extra={
                    **_rbac_extra(request, request.user, _resolve_required(request, view)),
                    "resource_org": obj.organization_id,
                })
                return False

        # Excepción documentada: el usuario siempre accede a su propio registro
        if hasattr(obj, "user_id") and obj.user_id == request.user.id:
            return True  # acceso al propio usuario

        return self.has_permission(request, view)


# ---------------------------------------------------------------------------
# Fase 3 — HybridPermission (DB + cache + fallback estático)
# ---------------------------------------------------------------------------

class HybridPermission(BasePermission):
    """
    Control de acceso híbrido: consulta permisos en DB cuando existen,
    cae en fallback estático (PERMISSIONS dict) cuando no hay roles en DB.

    Cache: los permisos se almacenan en user._cached_permissions durante
    el ciclo de vida del request (no persiste entre requests).

    El fallback estático emite un WARNING por usuario — cuando los logs
    lleguen a 0, es seguro eliminar el fallback y el campo User.role.
    """

    def has_permission(self, request, view) -> bool:
        if not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        required = _resolve_required(request, view)
        if required is None:
            return False

        db_perms = self._get_db_permissions(request.user)

        if db_perms is not None:
            result = _is_allowed(required, db_perms)
            extra = _rbac_extra(request, request.user, required)
            if result:
                rbac_logger.info("RBAC_ALLOWED_DB", extra=extra)
            else:
                rbac_logger.warning("RBAC_DENIED", extra=extra)
            return result

        # Fallback estático — usuario sin UserRole en DB
        static_perms = PERMISSIONS.get(request.user.role, [])
        result = _is_allowed(required, static_perms)
        extra = _rbac_extra(request, request.user, required)
        if result:
            rbac_logger.warning("RBAC_FALLBACK_ALLOWED", extra=extra)
        else:
            rbac_logger.warning("RBAC_DENIED", extra=extra)
        return result

    def has_object_permission(self, request, view, obj) -> bool:
        # Regla 1 (SIEMPRE PRIMERO): aislamiento multitenant
        if hasattr(obj, "organization_id"):
            if obj.organization_id != request.user.organization_id:
                rbac_logger.error("TENANT_MISMATCH_DETECTED", extra={
                    **_rbac_extra(request, request.user, _resolve_required(request, view)),
                    "resource_org": obj.organization_id,
                })
                return False

        return self.has_permission(request, view)

    def _get_db_permissions(self, user) -> "set | None":
        """
        Retorna el conjunto de códigos de permiso asignados al usuario via DB.
        Retorna None si el usuario no tiene roles en DB (activa el fallback).

        Cache: almacena en user._cached_permissions para evitar queries
        repetidas dentro del mismo request.
        """
        # Cache hit
        if hasattr(user, "_cached_permissions"):
            return user._cached_permissions

        # Evita import circular — UserRole está en core.models
        from apps.core.models import UserRole

        user_roles = UserRole.objects.select_related("role").prefetch_related(
            "role__permissions"
        ).filter(user=user)

        if not user_roles.exists():
            user._cached_permissions = None
            return None

        perms: set[str] = set()
        for user_role in user_roles:
            perms.update(
                user_role.role.permissions.values_list("code", flat=True)
            )

        user._cached_permissions = perms
        return perms


# ---------------------------------------------------------------------------
# Factory: permiso específico para FBVs
# ---------------------------------------------------------------------------

def make_permission(code: str) -> type:
    """
    Crea una clase Permission que exige un código específico.

    Uso en function-based views que no pueden establecer resource_name:

        @api_view(['PATCH'])
        @permission_classes([make_permission("invoice.confirm")])
        def confirm_invoice(request, pk):
            ...

    Regla 3: acciones custom SIEMPRE definen required_permission.
    """
    class SpecificPermission(HybridPermission):
        def has_permission(self, request, view):
            view.required_permission = code
            return super().has_permission(request, view)

    SpecificPermission.__name__ = f"Permission_{code.replace('.', '_')}"
    return SpecificPermission
