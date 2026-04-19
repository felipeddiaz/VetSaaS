"""
migrate_users_to_roles — Migra usuarios del rol estático al RBAC dinámico (Fase 4)

Qué hace:
  1. Lee el campo User.role de cada usuario
  2. Busca el Role de sistema correspondiente en su organización
  3. Crea un UserRole asignando ese rol dinámico
  4. Valida que NINGÚN usuario quede sin rol (excepción si ocurre)

Prerequisito:
  - seed_permissions debe haberse ejecutado antes (crea los Roles de sistema)

Uso:
  python manage.py migrate_users_to_roles
  python manage.py migrate_users_to_roles --dry-run

Cuándo eliminar el fallback estático (Paso 10 del plan):
  - Ejecutar con --check: si logs de HybridPermission con "fallback estático" = 0
    durante uso real, es seguro eliminar el bloque `static_perms` en HybridPermission
    y el campo `role` en User.
"""
import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = "Migra usuarios de roles estáticos a roles dinámicos en DB (Fase 4 RBAC)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué haría sin ejecutar cambios",
        )

    def handle(self, *args, **options):
        from apps.core.models import Role, UserRole

        dry_run = options["dry_run"]

        users = (
            User.objects
            .select_related("organization")
            .filter(is_active=True, organization__isnull=False)
            .exclude(is_superuser=True)
        )

        if not users.exists():
            self.stdout.write("No hay usuarios a migrar.")
            return

        errors = []
        assignments = []

        for user in users:
            role_name = user.role
            if not role_name:
                errors.append(f"Usuario {user.id} ({user.username}) no tiene role asignado")
                continue

            try:
                db_role = Role.objects.get(
                    name=role_name,
                    organization=user.organization,
                    is_system_role=True,
                )
                assignments.append((user, db_role))
            except Role.DoesNotExist:
                errors.append(
                    f"Usuario {user.id} ({user.username}): rol '{role_name}' no encontrado "
                    f"en org '{user.organization}'. Ejecuta seed_permissions primero."
                )

        # Validación obligatoria: ningún usuario sin rol
        if errors:
            for err in errors:
                self.stderr.write(f"  ERROR: {err}")
            raise CommandError(
                f"{len(errors)} usuarios no pudieron ser migrados. "
                "Resuelve los errores antes de continuar."
            )

        if dry_run:
            self.stdout.write(f"[dry-run] {len(assignments)} usuarios a migrar:")
            for user, db_role in assignments:
                self.stdout.write(f"  {user.username} -> {db_role.name}")
            self.stdout.write("[dry-run] No se realizaron cambios.")
            return

        # Migración atómica
        with transaction.atomic():
            created_count = 0
            for user, db_role in assignments:
                _, created = UserRole.objects.get_or_create(
                    user=user,
                    role=db_role,
                )
                if created:
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n[OK] migrate_users_to_roles completado: "
            f"{created_count} nuevas asignaciones, "
            f"{len(assignments) - created_count} ya existian"
        ))
        self.stdout.write(
            "\nProximo paso (Paso 10): monitorear logs de HybridPermission.\n"
            "Cuando el WARNING 'usando fallback estatico' llegue a 0 durante\n"
            "uso real, es seguro eliminar el fallback en HybridPermission."
        )
