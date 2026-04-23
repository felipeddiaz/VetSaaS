import logging

from apps.core.models import clear_tenant_context, set_current_user

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Gestión del contexto de usuario para audit trail (created_by / updated_by).

    Para requests JWT (DRF): TenantJWTAuthentication setea set_current_user()
    después de validar el token. Este middleware lo hace como fallback para
    session auth (admin panel).

    Cleanup garantizado en finally.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            if request.user.is_authenticated:
                set_current_user(request.user)
            else:
                set_current_user(None)

            return self.get_response(request)

        finally:
            clear_tenant_context()
