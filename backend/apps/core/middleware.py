import logging

from apps.core.models import clear_tenant_context, set_current_org, set_current_user

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Gestión de contexto multitenant para el ciclo de vida del request.

    Responsabilidades:
      1. Fallback para flows sin JWT: admin panel, session auth, login tradicional.
         Para esos casos, request.user ya está disponible aquí (Django AuthMiddleware).
      2. Cleanup garantizado: el bloque finally limpia el contexto siempre,
         sin importar qué auth class lo haya seteado (JWT, session, etc.).

    Para requests JWT (DRF):
      TenantJWTAuthentication setea el contexto DESPUÉS de validar el token,
      sobreescribiendo lo que este middleware haya seteado (None para anon).
      El cleanup final sigue siendo responsabilidad de este middleware.

    Orden en settings.MIDDLEWARE:
      Debe ir DESPUÉS de AuthenticationMiddleware para que request.user
      (Django session) esté disponible como fallback.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            # Fallback para session auth (admin, login tradicional).
            # Para JWT, TenantJWTAuthentication sobreescribe esto más adelante.
            if request.user.is_authenticated:
                org = getattr(request.user, 'organization', None)
                set_current_org(org)
                set_current_user(request.user)

                if org is None:
                    logger.warning(
                        "Usuario autenticado sin organización | user_id=%s path=%s",
                        request.user.pk, request.path,
                    )
            else:
                set_current_org(None)
                set_current_user(None)

            return self.get_response(request)

        finally:
            # Limpieza garantizada — sin importar qué auth class corrió
            clear_tenant_context()
