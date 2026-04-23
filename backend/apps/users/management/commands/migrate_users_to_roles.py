"""
migrate_users_to_roles — Migra usuarios sin UserRole al RBAC dinámico.

Cuándo usarlo:
  - Una sola vez, cuando hay usuarios activos sin UserRole en DB.
  - Tras crear una organización nueva (sus usuarios no tendrán UserRole todavía).
  - NO debe estar en el Procfile — es un comando de migración puntual.

Qué hace:
  Solo actúa sobre usuarios que NO tienen ningún UserRole asignado.
  Usuarios ya migrados (con al menos un UserRole) se ignoran completamente,
  lo que hace al comando seguro de correr múltiples veces sin efectos secundarios.

Prerequisito:
  - seed_permissions debe haberse ejecutado antes (crea los Roles de sistema).

Uso:
  python manage.py migrate_users_to_roles
  python manage.py migrate_users_to_roles --dry-run
"""
import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = "Asigna UserRole a usuarios sin ningún rol en DB (idempotente, seguro para re-run)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué haría sin ejecutar cambios",
        )

    def handle(self, *args, **options):
        from apps.core.models import Role, UserRole

        dry_run = options["dry_run"]

        # Solo usuarios SIN ningún UserRole — los ya migrados se omiten completamente.
        # Esto hace al comando seguro para re-runs y para correr en cada nueva org.
        users_without_roles = (
            User.objects
            .select_related("organization")
            .filter(is_active=True, organization__isnull=False)
            .exclude(is_superuser=True)
            .filter(user_roles__isnull=True)  # ← clave: solo los no migrados
            .distinct()
        )

        if not users_without_roles.exists():
            self.stdout.write(self.style.SUCCESS(
                "[OK] migrate_users_to_roles: todos los usuarios ya tienen roles en DB. "
                "Sin cambios."
            ))
            return

        errors = []
        assignments = []

        for user in users_without_roles:
            role_name = user.role
            if not role_name:
                errors.append(
                    f"Usuario {user.id} ({user.username}) no tiene User.role asignado"
                )
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
                self.stdout.write(f"  {user.username} ({user.organization}) -> {db_role.name}")
            self.stdout.write("[dry-run] No se realizaron cambios.")
            return

        with transaction.atomic():
            created_count = 0
            for user, db_role in assignments:
                _, created = UserRole.objects.get_or_create(user=user, role=db_role)
                if created:
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"[OK] migrate_users_to_roles completado: "
            f"{created_count} nuevas asignaciones."
        ))
