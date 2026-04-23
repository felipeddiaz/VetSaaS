"""
seed_permissions — Puebla Permission, Role y permisos por organización.

Idempotente: se puede correr N veces sin efectos secundarios.
Se ejecuta automáticamente en cada deploy (ver Procfile).

Si agregas nuevos permisos en PERMISSION_CODES / PERMISSIONS,
el próximo deploy los crea automáticamente.
"""
import logging

from django.core.management.base import BaseCommand

from apps.core.models import Permission, Role
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)

# Roles que pertenecen a la plataforma — no se crean por organización
_PLATFORM_ROLES = {"ADMIN_SAAS"}


class Command(BaseCommand):
    help = "Seed RBAC: permisos y roles de sistema por organización (idempotente)"

    def handle(self, *args, **kwargs):
        self._seed_permissions()
        self._seed_roles()
        self.stdout.write(self.style.SUCCESS("seed_permissions completado"))

    def _seed_permissions(self):
        created = 0
        for code in PERMISSION_CODES:
            _, is_new = Permission.objects.get_or_create(code=code)
            if is_new:
                created += 1

        existing = len(PERMISSION_CODES) - created
        self.stdout.write(f"  Permissions: {created} creados, {existing} ya existían")

    def _seed_roles(self):
        # Construye mapa code → Permission una sola vez
        perms_map = {p.code: p for p in Permission.objects.filter(code__in=PERMISSION_CODES)}

        org_role_definitions = {
            role_code: perm_codes
            for role_code, perm_codes in PERMISSIONS.items()
            if role_code not in _PLATFORM_ROLES
        }

        orgs = list(Organization.objects.all())
        roles_created = 0
        roles_updated = 0

        for org in orgs:
            for role_code, perm_codes in org_role_definitions.items():
                role, created = Role.objects.get_or_create(
                    name=role_code,
                    organization=org,
                    defaults={"is_system_role": True},
                )

                if not created and not role.is_system_role:
                    role.is_system_role = True
                    role.save(update_fields=["is_system_role"])

                valid_perms = [perms_map[c] for c in perm_codes if c in perms_map]
                role.permissions.set(valid_perms)

                if created:
                    roles_created += 1
                else:
                    roles_updated += 1

        self.stdout.write(
            f"  Roles: {roles_created} creados, {roles_updated} actualizados "
            f"en {len(orgs)} organización(es)"
        )
