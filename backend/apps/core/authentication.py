import logging

from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.models import set_current_org, set_current_user

logger = logging.getLogger(__name__)


class TenantJWTAuthentication(JWTAuthentication):
    """
    Extiende JWTAuthentication para inyectar el contexto de tenant
    inmediatamente después de validar el token.

    Por qué es necesario:
      TenantMiddleware corre antes de que DRF procese el JWT.
      En ese momento request.user es AnonymousUser (sesión Django, no JWT).
      El contexto queda en None y TenantManager devuelve .none() vacío.

    Solución:
      authenticate() corre durante View.initial(), después del middleware,
      con el usuario ya validado. Es el momento correcto para setear contexto.

    Cleanup:
      TenantMiddleware.finally siempre limpia al terminar el request,
      sin importar qué auth class seteó el contexto.
    """

    def authenticate(self, request):
        result = super().authenticate(request)

        if result is None:
            return None

        user, token = result

        set_current_user(user)
        set_current_org(getattr(user, 'organization', None))

        if getattr(user, 'organization', None) is None:
            logger.warning(
                "JWT autenticado pero sin organización | user_id=%s",
                user.pk,
            )

        return (user, token)
