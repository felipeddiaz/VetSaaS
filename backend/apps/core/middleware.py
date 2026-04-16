import logging

from apps.core.models import clear_tenant_context, set_current_org, set_current_user

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Inyecta el contexto de organización y usuario actual en thread-locals.

    Debe ser el PRIMER middleware en settings.MIDDLEWARE para garantizar
    que el contexto esté disponible antes de cualquier acceso al ORM.

    El bloque finally limpia el contexto al finalizar cada request,
    evitando que valores queden pegados entre requests en el mismo thread.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            if request.user.is_authenticated and hasattr(request.user, 'organization'):
                org = request.user.organization
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

            # Mantener compatibilidad con código que use request.organization
            request.organization = get_current_org() if hasattr(request, 'user') else None

            return self.get_response(request)

        finally:
            clear_tenant_context()


def get_current_org():
    from apps.core.models import get_current_org as _get
    return _get()
