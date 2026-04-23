import logging

from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.models import set_current_user

logger = logging.getLogger(__name__)


class TenantJWTAuthentication(JWTAuthentication):
    """
    Extiende JWTAuthentication para cargar el user con select_related('organization')
    y setear el contexto de audit trail (created_by / updated_by).
    """

    def authenticate(self, request):
        result = super().authenticate(request)

        if result is None:
            return None

        user, token = result

        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.select_related('organization').get(pk=user.pk)

        set_current_user(user)

        if user.organization is None:
            logger.warning(
                "JWT autenticado pero sin organización | user_id=%s",
                user.pk,
            )

        return (user, token)
