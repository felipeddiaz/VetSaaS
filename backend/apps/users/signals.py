import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='users.User')
def assign_rbac_role_on_create(sender, instance, created, **kwargs):
    """
    Asigna UserRole automáticamente al crear cualquier usuario, sin importar
    el origen (Django admin, API, scripts, fixtures).

    Condiciones para actuar:
    - El usuario es nuevo (created=True)
    - Tiene organización asignada
    - Tiene role distinto de ADMIN_SAAS (ese rol es de plataforma, no de org)
    - No es superusuario sin org (el ADMIN_SAAS de Railway)

    Idempotente: usa get_or_create, seguro si _assign_rbac_role ya corrió.
    Si el Role no existe en DB, emite WARNING — señal de que seed_permissions
    no se ha ejecutado aún para esa org.
    """
    if not created:
        return
    if not instance.organization_id:
        return
    if instance.role == 'ADMIN_SAAS':
        return

    from apps.core.models import Role, UserRole
    try:
        db_role = Role.objects.get(
            name=instance.role,
            organization_id=instance.organization_id,
            is_system_role=True,
        )
        _, was_created = UserRole.objects.get_or_create(user=instance, role=db_role)
        if was_created:
            logger.info(
                "assign_rbac_role_on_create: UserRole asignado | "
                "user=%s org=%s role=%s",
                instance.id, instance.organization_id, instance.role,
            )
    except Role.DoesNotExist:
        logger.warning(
            "assign_rbac_role_on_create: rol '%s' no encontrado en org %s "
            "para usuario %s — ejecuta seed_permissions primero",
            instance.role, instance.organization_id, instance.id,
        )
