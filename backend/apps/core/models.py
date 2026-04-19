"""
core/models.py — Infraestructura multitenant de VetCare SaaS
=============================================================

CÓMO FUNCIONA EL TENANT MANAGER
---------------------------------
Cada request pasa por TenantMiddleware, que inyecta la organización del usuario
en un thread-local (_current_org). TenantManager lee ese contexto en cada query
y agrega automáticamente filter(organization=org, is_active=True).

Resultado: ningún código de negocio necesita filtrar por organización manualmente.

MANAGERS DISPONIBLES
---------------------
  Model.objects      → filtra por tenant activo + is_active=True  (usar siempre)
  Model.all_objects  → sin filtros  (solo migrations, admin, scripts)

SOFT DELETE
-----------
is_active=False marca el registro como eliminado. TenantManager lo excluye
automáticamente. Para borrado físico: qs.hard_delete() (explícito e intencional).
Regla: solo se aplica soft delete a catálogos y usuarios.
NO aplica a: historial clínico, prescripciones, facturas (registros inmutables).

LO QUE NO SE DEBE HACER
------------------------
  ❌ Model.objects.update(...)        — bypassa validaciones y tenant
  ❌ Model.objects.bulk_create(...)   — bypassa full_clean()
  ❌ Model.objects.raw(...)           — bypassa todo

  Si necesitas .update() por atomicidad (ej: stock):
    → usa Model.all_objects.filter(pk=pk).update(...)
    → documenta el motivo con un comentario

  Si necesitas .bulk_create():
    → llama full_clean() manualmente en cada objeto antes

THREADING VS ASYNC
------------------
MVP usa threading.local(). Migrar a contextvars cuando haya ASGI o Celery.
En Celery/tareas background: el contexto NO se propaga automáticamente.
Pasar organización explícitamente o usar all_objects con filtro manual.

ANTI-PATTERNS (NO HACER)
-------------------------
  ❌ Model.objects.update(...)
       Bypassa full_clean(), signals y el tenant filter.
       Si necesitas atomicidad: usa all_objects.filter(pk=pk).update() + comenta el motivo.

  ❌ Model.objects.bulk_create([...])
       Bypassa full_clean() en cada instancia.
       Si es necesario: llama obj.full_clean() manualmente antes de cada objeto.

  ❌ Model.objects.raw("SELECT ...")
       Bypassa absolutamente todo — tenant, validaciones, señales.
       Usar solo para reportes de lectura y con all_objects explícito.

  ❌ Model.all_objects fuera de servicios controlados
       all_objects existe para migrations, admin y servicios internos específicos.
       No usarlo en views, serializers ni lógica de negocio general.

  ❌ Acceder a DB sin que TenantMiddleware haya corrido
       En scripts o tareas async: setear contexto manualmente con set_current_org()
       o usar all_objects con filter(organization=org) explícito.
"""
import logging
import threading

from django.db import models

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thread-local context
# NOTE: MVP usa threading.local(). Migrar a contextvars cuando haya ASGI/Celery.
# ---------------------------------------------------------------------------
_current_org  = threading.local()
_current_user = threading.local()


def get_current_org():
    return getattr(_current_org, 'value', None)


def get_current_user():
    return getattr(_current_user, 'value', None)


def set_current_org(org):
    _current_org.value = org


def set_current_user(user):
    _current_user.value = user


def clear_tenant_context():
    _current_org.value  = None
    _current_user.value = None


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------
class TenantQuerySet(models.QuerySet):
    """
    QuerySet seguro para modelos multitenant.

    - delete() bloqueado por defecto: usa soft delete (is_active=False).
    - hard_delete() para borrado físico explícito e intencional.

    ADVERTENCIA: update() y _raw_delete() bypasean este QuerySet.
    No usar update() directo en modelos multitenant.
    """

    def delete(self):
        if not getattr(self, '_allow_delete', False):
            raise Exception(
                "Hard delete bloqueado. Usa soft delete (is_active=False) "
                "o llama hard_delete() si el borrado físico es intencional."
            )
        return super().delete()

    def hard_delete(self):
        self._allow_delete = True
        return self.delete()


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class TenantManager(models.Manager):
    """
    Manager automático que filtra por tenant activo y registros activos.

    Filtros aplicados en cada query:
      - organization == contexto actual (thread-local)
      - is_active == True

    Bypass para scripts/migraciones/tests:
      Model.objects._bypass_tenant = True
    O usar Model.all_objects (sin ningún filtro).
    """

    def get_queryset(self):
        org = get_current_org()

        if org is None:
            if getattr(self, '_bypass_tenant', False):
                # Scripts / migraciones / tests que necesitan acceso sin contexto
                return TenantQuerySet(self.model, using=self._db).filter(is_active=True)
            # Sin contexto de tenant: devuelve queryset vacío (seguro).
            # Esto cubre evaluaciones en tiempo de importación (DRF class-level queryset).
            # En requests reales el middleware siempre setea el contexto antes de este punto.
            logger.debug(
                "TenantManager: sin contexto para %s — devolviendo queryset vacío",
                self.model.__name__,
            )
            return TenantQuerySet(self.model, using=self._db).none()

        return TenantQuerySet(self.model, using=self._db).filter(
            organization=org,
            is_active=True,
        )


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------
class OrganizationalModel(models.Model):
    """
    Modelo base para todas las entidades tenant-aware.

    Provee automáticamente:
      - Aislamiento multitenant (organization)
      - Auditoría (created_at, updated_at, created_by, updated_by)
      - Soft delete (is_active)
      - Manager seguro (objects) + manager sin filtros (all_objects)

    IMPORTANTE:
      - organization usa PROTECT: las organizaciones nunca se borran, se desactivan.
      - save() llama full_clean() centralizado. Para omitir: obj.save(validate=False).
        Usar validate=False solo en bulk operations o imports masivos.
      - update() directo bypasea el manager — no usar en código de negocio.
    """

    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        related_name='%(class)s_set',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    updated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    is_active = models.BooleanField(default=True)

    objects     = TenantManager()
    all_objects = models.Manager()

    def save(self, *args, validate=True, **kwargs):
        # 1. Auditoría primero — para que clean() pueda validar created_by si lo necesita
        user = get_current_user()
        if user:
            if not self.pk:
                self.created_by = user
            self.updated_by = user

        # 2. Validaciones centralizadas (clean + field validation)
        if validate:
            try:
                self.full_clean()
            except Exception as exc:
                org_id = getattr(self, 'organization_id', None)
                user_id = getattr(get_current_user(), 'pk', None)
                logger.warning(
                    "Validación fallida | model=%s pk=%s organization_id=%s user_id=%s | %s",
                    self.__class__.__name__, self.pk, org_id, user_id, exc,
                )
                raise

        super().save(*args, **kwargs)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]


# ---------------------------------------------------------------------------
# Fase 2 — Modelos para RBAC dinámico
# ---------------------------------------------------------------------------

class Permission(models.Model):
    """
    Permiso atómico en formato "resource.action".
    Fuente de verdad: PERMISSION_CODES en permissions_codes.py.
    El seed garantiza que ambos estén sincronizados.
    """
    code = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        return self.code


class Role(models.Model):
    """
    Rol con permisos configurables por organización.
    is_system_role=True: el seed lo crea y gestiona; no editable por usuarios.
    """
    name = models.CharField(max_length=100)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="roles",
    )
    permissions = models.ManyToManyField(Permission, blank=True)
    is_system_role = models.BooleanField(default=False)

    class Meta:
        unique_together = [["name", "organization"]]
        ordering = ["name"]
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return f"{self.name} ({self.organization})"


class UserRole(models.Model):
    """
    Asignación de un rol a un usuario dentro de una organización.
    Un usuario puede tener múltiples roles.
    """
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="user_roles",
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_assigned",
    )

    class Meta:
        unique_together = [["user", "role"]]
        verbose_name = "UserRole"
        verbose_name_plural = "UserRoles"

    def __str__(self):
        return f"{self.user} → {self.role}"
