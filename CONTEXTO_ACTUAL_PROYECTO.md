# Contexto actual del proyecto (VeterinariaSaaS)

Fecha de corte: 2026-04-23
Fuente: estado real del repositorio (backend + frontend) y `plan.txt`.

## 1) Punto actual

El proyecto ya esta en una fase funcional avanzada con arquitectura multitenant operativa, autenticacion JWT, modulos clinicos y administrativos conectados, y frontend con rutas privadas para los principales flujos de una clinica veterinaria.

Los commits recientes y el codigo reflejan foco en:
- estabilizar el contexto de organizacion por request,
- reforzar RBAC (modelo hibrido con fallback),
- y cerrar flujos de facturacion/inventario con validaciones de consistencia.

## 2) Estado de la correccion multitenant (tema critico ya diagnosticado)

Segun `plan.txt`, el problema identificado era perdida de contexto de organizacion por uso de estado global.

Estado actual observado en codigo:
- El tenant para queries de negocio se toma de `request.user.organization` en vistas y servicios.
- Existe `TenantQueryMixin` que bloquea acceso cuando el usuario no tiene organizacion.
- `TenantJWTAuthentication` recarga usuario con `select_related('organization')`.
- En `apps/core/models.py` el thread-local se conserva para auditoria (`created_by/updated_by`), no para tenant.

Conclusion: el punto critico de aislamiento por organizacion esta encaminado en el sentido correcto y alineado con la regla de `plan.txt`.

## 3) Modulos backend implementados

Backend: Django + DRF + JWT + Postgres + CORS + WhiteNoise + Sentry.

Apps activas:
- `organizations`
- `users`
- `patients`
- `appointments`
- `medical_records`
- `inventory`
- `billing`
- `prescriptions`
- `dashboard`
- `core`

Capacidades ya presentes:
- Multitenancy por modelo base (`OrganizationalModel`) + managers tenant-aware.
- Soft delete en entidades aplicables (`is_active`) con manager seguro.
- Auditoria de creacion/actualizacion (`created_by`, `updated_by`).
- Agenda de citas con estados y validaciones temporales.
- Historial medico con relacion a cita, mascota y veterinario.
- Inventario con productos, presentaciones, movimientos y alerta de stock bajo.
- Facturacion con servicios, items, estados (`draft/confirmed/paid/cancelled`) y auditoria.
- Reglas de stock transaccionales al confirmar/cancelar factura (solo `direct_sale`).
- Recetas con items y exportacion PDF.
- Endpoint de dashboard con metricas diarias y alertas.

## 4) RBAC y permisos (estado real)

Hay una transicion en curso:
- Existe RBAC dinamico en DB (`Permission`, `Role`, `UserRole`) y comando `seed_permissions`.
- Existe `HybridPermission` (DB + fallback a rol estatico).
- Existe comando `migrate_users_to_roles` para migracion del campo `User.role` al esquema dinamico.

Pero aun conviven ambos enfoques:
- Muchas vistas siguen usando `RolePermission` (estatico).
- Algunas rutas (ej. `make_permission(...)`) ya pasan por `HybridPermission`.

Interpretacion: migracion RBAC en progreso, no cerrada al 100% en todas las vistas.

## 5) Frontend implementado

Stack: React + Vite + React Router + Axios + FullCalendar + Sentry.

Estado funcional:
- Autenticacion con JWT y refresh programado antes de expiracion.
- `AuthProvider` + rutas privadas.
- Vistas operativas para:
  - Dashboard
  - Pacientes
  - Detalle de mascota
  - Equipo (staff)
  - Citas
  - Historial medico
  - Inventario
  - Facturacion
  - Recetas
  - Configuracion
- Cliente API central con interceptor para token y manejo de 401/500.

## 6) Deploy y operaciones

Backend (`Procfile`) ejecuta en arranque:
1. migraciones,
2. `seed_permissions`,
3. `migrate_users_to_roles`,
4. gunicorn.

Esto indica intencion de mantener RBAC sincronizado automaticamente en despliegues.

Frontend incluye `vercel.json` con rewrite SPA a `index.html`.

## 7) Deuda tecnica y pendientes visibles (sin inventar)

Pendientes explicitos en codigo:
- `billing/models.py`: TODO para hacer `presentation` obligatorio en `InvoiceItem` en v2.
- Comentarios por fases en inventario/personalizacion de presentaciones (fase futura).

Pendientes inferidos por arquitectura actual:
- Unificar todas las vistas en `HybridPermission` y retirar `RolePermission` cuando el fallback llegue a cero.
- Cerrar el ciclo final de migracion RBAC (eliminar dependencia del campo `User.role` cuando sea seguro).

## 8) Resumen ejecutivo

El proyecto no esta en etapa inicial: ya tiene base multitenant, seguridad de acceso, dominio clinico y financiero integrado, y UI conectada a API.

El foco actual parece ser "endurecimiento" (hardening):
- consistencia multitenant en todos los flujos,
- cierre definitivo de migracion RBAC,
- y refinamientos de reglas de negocio (facturacion/inventario).
