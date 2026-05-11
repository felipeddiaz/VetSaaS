import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='organizations.Organization')
def initialize_organization(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .models import OrganizationSettings
        OrganizationSettings.objects.get_or_create(organization=instance)

        from apps.patients.models import Owner, Pet
        generic_owner, _ = Owner.objects.get_or_create(
            organization=instance,
            is_generic=True,
            defaults={'name': 'Público General', 'phone': '0000000000'},
        )
        Pet.objects.get_or_create(
            owner=generic_owner,
            is_generic=True,
            defaults={
                'name': 'Paciente Anónimo',
                'species': 'otro',
                'organization': instance,
            }
        )

        _seed_roles_for_org(instance)

    except Exception as e:
        logger.error("Error inicializando organización %s: %s", instance.pk, e)
        # No re-raise: la org debe quedar creada aunque el setup auxiliar falle


def _seed_roles_for_org(org):
    """
    Crea los Roles RBAC de sistema para una organización recién creada.
    Equivale a seed_permissions pero acotado a una sola org.
    Idempotente: usa get_or_create.
    """
    from apps.core.models import Permission, Role
    from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS

    wildcard, _ = Permission.objects.get_or_create(code="*.*")
    perms_map = {c: Permission.objects.get_or_create(code=c)[0] for c in PERMISSION_CODES}

    for role_name, codes in PERMISSIONS.items():
        if role_name == "ADMIN_SAAS":
            continue
        role, _ = Role.objects.get_or_create(
            name=role_name,
            organization=org,
            defaults={"is_system_role": True},
        )
        role.is_system_role = True
        role.permissions.set(
            [wildcard] if "*.*" in codes
            else [perms_map[c] for c in codes if c in perms_map]
        )
        role.save(update_fields=["is_system_role"])

    logger.info(
        "initialize_organization: Roles RBAC creados | org=%s", org.pk
    )
