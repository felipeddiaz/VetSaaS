# Modulo: Organizaciones y usuarios

## Objetivo

Gestiona las clinicas (tenants), sus usuarios y la configuracion operativa de cada una.

## Roles del sistema

| Rol          | Alcance            | Descripcion                                    |
|--------------|--------------------|------------------------------------------------|
| `ADMIN_SAAS` | Plataforma entera  | Administrador de Vet Care. No pertenece a ninguna clinica. Accede via Django admin. |
| `ADMIN`      | Una organizacion   | Administrador de la clinica. Gestiona staff, configuracion y tiene acceso completo a todos los modulos. |
| `VET`        | Una organizacion   | Veterinario. Puede crear y cerrar consultas propias. |
| `ASSISTANT`  | Una organizacion   | Asistente. Acceso limitado segun permisos RBAC configurados. |

## Como el ADMIN_SAAS crea una clinica nueva

No existe un endpoint de API para crear organizaciones desde fuera. El flujo es via Django admin.

### En Railway (produccion)

El ADMIN_SAAS se crea automaticamente en cada deploy si las siguientes variables estan en Railway:

```
DJANGO_SUPERUSER_USERNAME=admin_saas
DJANGO_SUPERUSER_PASSWORD=TuClave123!
DJANGO_SUPERUSER_EMAIL=admin@vetcare.example.com   # opcional pero recomendado
```

Esto ejecuta `_create_default_superuser` en el signal `post_migrate` de `apps/users/apps.py`.

**Guard anti-escalación (PR-4A / ADR p15):** El signal usa `filter().first()` + predicado `_is_platform_superuser` (requiere `is_superuser=True AND is_staff=True AND role='ADMIN_SAAS' AND email coincide case-insensitive cuando se provee`). Si una clinica registra un VET con el mismo username que `DJANGO_SUPERUSER_USERNAME`, el deploy ya NO escala al VET ni le resetea password — log CRITICAL `SUPERUSER_BOOTSTRAP_SKIPPED` y abort sin mutacion.

Eventos emitidos por el bootstrap:
- `SUPERUSER_BOOTSTRAP_CREATED` (INFO) — superuser nuevo creado
- `SUPERUSER_BOOTSTRAP_SKIPPED` (CRITICAL) — username collision con usuario non-platform
- `SUPERUSER_BOOTSTRAP_RACE_RESOLVED` (WARNING) — race multi-worker resuelto
- `SUPERUSER_BOOTSTRAP_INCOMPLETE_ENV` (WARNING) — solo `USERNAME` o solo `PASSWORD` seteado

### Flujo para crear una clinica nueva

1. Ir a `https://tu-backend.railway.app/admin/` con las credenciales del ADMIN_SAAS
2. **Organizations** → `+ Add` → completar:
   - `name`: nombre de la clinica
   - `timezone`: zona horaria (default `America/Mexico_City`)
   - `tax_rate`: `0.0000` sin IVA, `0.1600` para IVA 16%
3. **Users** → `+ Add` → completar:
   - `username`, `email`, `password`
   - `organization`: la clinica recien creada
   - `role`: `ADMIN`
4. Ejecutar `seed_permissions` para la nueva org (ver abajo)

### Ejecutar seed_permissions en Railway

Desde la consola de Railway:

```bash
python manage.py seed_permissions
```

O simplemente hacer redeploy — el Procfile lo ejecuta automaticamente antes de iniciar el servidor.

Si `seed_permissions` no se ejecuta, todos los endpoints de la org nueva retornan `403`.

## Como el ADMIN de una clinica gestiona su equipo

Una vez que el ADMIN tiene credenciales, todo lo demas es via API.

### Login

```
POST /api/token/
{ "username": "...", "password": "..." }
→ { "access": "...", "refresh": "..." }
```

### Crear staff

```
POST /api/staff/create/
Authorization: Bearer <token ADMIN>

{
  "username": "dra.garcia",
  "email": "garcia@clinica.com",
  "password": "Clave1234!",
  "first_name": "Laura",
  "last_name": "Garcia",
  "role": "VET",
  "specialty": "Cirugia"
}
```

Validaciones de password: minimo 8 caracteres, al menos una mayuscula, al menos un numero.

La asignacion de `UserRole` RBAC ocurre automaticamente al crear el usuario (requiere que `seed_permissions` haya corrido).

### Listar staff

```
GET /api/staff/
Authorization: Bearer <token ADMIN>
```

### Desactivar usuario

```
DELETE /api/staff/<id>/
Authorization: Bearer <token ADMIN>
```

No elimina el usuario, marca `is_active = False`.

## Endpoints de Organization (PR-4B / ADR p16)

### Singleton — recomendado

```
GET   /api/organizations/me/
PATCH /api/organizations/me/
Authorization: Bearer <token ADMIN>
```

Devuelve/actualiza la organizacion del usuario autenticado sin exponer el PK en la URL. Forma canonica desde PR-4B.

### Legacy — deprecado

```
GET   /api/organizations/<pk>/
PATCH /api/organizations/<pk>/
```

Mantenido por retrocompat hasta **2026-08-17** (RFC 8594 Sunset). Reglas:
- `pk == request.user.organization_id` valida explicitamente — si no calza, **404** (no devuelve silenciosamente "tu org")
- Headers en TODO response: `Deprecation: true`, `Sunset: Mon, 17 Aug 2026 23:59:59 GMT`, `Link: </api/organizations/me/>; rel="successor-version"`
- Cada hit emite log `DEPRECATED_ENDPOINT_HIT` para tracking de adopcion
- **Post-Sunset (>2026-08-17): responde 410 Gone automaticamente** via `_EndpointSunsetException` raised en `initial()`

### Removidos

`list`, `create`, `destroy` ya no existen — router `DefaultRouter.register('organizations', ...)` removido. GET/POST a `/api/organizations/` → 404.

### Admin Django

`OrganizationAdmin.has_delete_permission = False` — la org se desactiva, no se borra (consistencia con `User.organization` PROTECT).

## Configuracion de la clinica

```
GET  /api/organizations/settings/
PATCH /api/organizations/settings/
Authorization: Bearer <token ADMIN>
```

Toggles disponibles:

| Campo                              | Default | Descripcion                                                   |
|------------------------------------|---------|---------------------------------------------------------------|
| `auto_create_medical_record`       | `false` | Crea consulta automaticamente al completar una cita           |
| `auto_create_invoice_on_done`      | `false` | Crea factura draft al marcar cita como completada             |
| `require_confirmation_before_start`| `false` | La cita debe confirmarse antes de iniciar                     |
| `allow_anonymous_walkin`           | `false` | Permite walk-in sin mascota registrada                        |
| `show_status_change_history`       | `true`  | Muestra historial de cambios de estado en citas               |

Ver ADR `2026-04-28-organization-settings-toggles.md` para el racional de cada toggle.

## RBAC — como funciona

El sistema usa `HybridPermission`: primero busca permisos en DB, si no encuentra usa fallback estatico.

```
POST /api/token/ → JWT
→ request llega a endpoint
→ HybridPermission.has_permission()
→ busca UserRole del usuario en DB
→ compara permisos del Role con el permiso requerido por el endpoint
→ permite o deniega
```

Eventos emitidos a stdout (Railway logs):
- `RBAC_ALLOWED_DB` — permiso concedido desde DB
- `RBAC_FALLBACK_ALLOWED` — permiso concedido por fallback (no deberia verse en produccion estable)
- `RBAC_DENIED` — acceso denegado
- `TENANT_MISMATCH_DETECTED` — intento de acceso a datos de otra organizacion
- `DEPRECATED_ENDPOINT_HIT` — uso del legacy `/api/organizations/<pk>/` (logger `core.deprecation`)

Gate para corte del fallback: `RBAC_FALLBACK_ALLOWED` ausente en logs por 7 dias consecutivos → se puede eliminar el campo `User.role`.

**Default DRF (PR-4A / ADR p15):** `REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] = ('rest_framework.permissions.IsAuthenticated',)`. Cualquier vista nueva que olvide declarar `permission_classes` queda cerrada por defecto. Las vistas publicas (`/api/token/`, `/api/token/refresh/`) declaran `AllowAny` explicito.

## Zona horaria por organizacion

Cada organizacion tiene su propia zona horaria. Actualmente solo se soporta Mexico.

Cambiar el timezone:

```
PATCH /api/organizations/me/
Authorization: Bearer <token ADMIN>
{ "timezone": "America/Monterrey" }
```

El cambio queda auditado en `OrganizationTimezoneAudit` con `changed_by` y timestamps del cambio.

Los filtros de fecha en facturas (`paid_on`, `created_on`) respetan la timezone de la organizacion.

## Cascade lockdown (PR-4B / ADR p16)

`User.organization` ahora es `on_delete=PROTECT` (antes CASCADE). Borrar una `Organization` con usuarios asociados lanza `django.db.models.ProtectedError` mapeado a 409 Conflict por el handler global. Justificacion: NOM-024 retencion de datos del prestador + audit trails (`InvoiceAuditLog.changed_by`, `MedicalRecord.closed_by`, etc.).

Para desactivar una organizacion: marcar `is_active=False` (soft-delete real es deuda Fase 2 A5).
