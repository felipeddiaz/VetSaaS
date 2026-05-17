# ADR p15 — Día 4: Cascade lockdown + perimeter hardening

**Fecha:** 2026-05-17
**Status:** Implementado parcial (PR-4A merged) | PR-4B pendiente
**Sprint:** Pre-beta hardening — Día 4 de 7
**Issues:** P0 #10, #11, #12, #13 de `revision_auditoria.md`
**ADRs relacionados:** p9 (anchors), p11 (anchor authority), p12 (lock ordering), p13 (concurrency), p14 (tenant validators)

---

## 1. Contexto

Día 4 del sprint pre-beta cierra cuatro bugs P0 que la auditoría adjunta clasificó como bloqueantes:

- **Issue #12 — `_create_default_superuser` privilege escalation (CVSS 9.9):** el signal `post_migrate` en `apps/users/apps.py` usaba `User.objects.get_or_create(username=...)`, después seteaba `is_superuser=True` y reseteaba el password sobre el resultado. Si una clínica registraba un usuario interno con username == `DJANGO_SUPERUSER_USERNAME` (típicamente `admin`), el siguiente deploy escalaba ese usuario a superuser de plataforma y reseteaba sus credenciales. Vector remoto, persistente y silencioso. La operación no quedaba reflejada en logs.
- **Issue #13 — `DEFAULT_PERMISSION_CLASSES` faltante:** `REST_FRAMEWORK` en `config/settings.py` no declaraba `DEFAULT_PERMISSION_CLASSES`. DRF cae a `AllowAny` cuando no hay default. Cualquier `APIView` sin `permission_classes` explícito quedaba expuesta sin autenticación. La superficie inmediata estaba contenida (todas las vistas activas declaran `HybridPermission`), pero el invariante "default-deny" no estaba enforced — riesgo alto en cualquier vista nueva o experimental.
- **Issue #10 — `/organizations/` ViewSet sin singleton:** scope de PR-4B.
- **Issue #11 — Cascade huérfanos y `ProtectedError` propagado como 500:** scope de PR-4B.

PR-4A cierra #12 y #13. PR-4B abordará #10 y #11.

---

## 2. Decisiones

### 2.1 Lo que se hizo

- **Fix #12:** reescritura completa de `_create_default_superuser` con guard explícito (`filter().first()` + bifurcación) en lugar de `get_or_create`. Tres branches discretos:
  1. Usuario no existe → `create_user()` con `role='ADMIN_SAAS'` + org `'Vet Care Internal'`.
  2. Usuario existe Y es el platform-superuser legítimo (`is_superuser=True AND role='ADMIN_SAAS' AND email coincide cuando se provee`) → solo refresca `is_active` si estaba inactivo. **No resetea password** (idempotencia de credenciales).
  3. Usuario existe pero NO es platform-superuser → log `CRITICAL` con evento `SUPERUSER_BOOTSTRAP_SKIPPED` + `reason='username_collision_non_platform_user'` + abort sin mutación.
- **Fix #13:** `DEFAULT_PERMISSION_CLASSES = ('rest_framework.permissions.IsAuthenticated',)` añadido a `REST_FRAMEWORK`. `ThrottledTokenObtainPairView` declara `permission_classes = [AllowAny]`. Se introduce `PublicTokenRefreshView(TokenRefreshView)` con `permission_classes = [AllowAny]` (subclassing porque `TokenRefreshView` se usaba directamente vía `.as_view()` y no tiene atributo de clase configurable de otra forma sin colapsar el contrato DRF). Las rutas reciben `name='token_obtain_pair'` y `name='token_refresh'` para soportar `reverse()` en tests.
- Tests nuevos: `apps/users/tests/test_bootstrap.py` (7 tests) y `apps/core/tests/test_default_permissions.py` (3 tests). Cobertura: 7 escenarios del guard anti-escalación + verificación de default + acceso público a token endpoints.

### 2.2 Lo que NO se hizo y por qué

- **NO se promovió la lógica del signal a `apps/users/management/commands/`.** Aunque "mejor práctica" sería un mgmt command explícito (deferido a deuda B5), Día 4 prioriza cerrar el vector sin alterar la superficie de bootstrap actual. Reescribir como command exige cambios en `Procfile` Railway + revisión de orden de boot. Fuera de scope.
- **NO se introdujo `RBAC_BOOTSTRAP_DENIED` como evento separado.** El evento `SUPERUSER_BOOTSTRAP_SKIPPED` con `reason='username_collision_non_platform_user'` es suficientemente descriptivo y no requiere ampliar `apps/core/logging.py`. Se reusa el logger `rbac.events` (mismo handler `rbac_console`).
- **NO se cambió el default de `DEFAULT_AUTHENTICATION_CLASSES`.** El `TenantJWTAuthentication` ya está en su lugar; el cambio es ortogonal.
- **NO se hizo audit sweep de views legacy sin `permission_classes`.** El cambio del default es defensa estructural — si un test legacy rompiera por 401 inesperado, lo detectaríamos. Suite completa pasó sin regresiones, lo que confirma que no había views activas sin permission declarado.

---

## 3. PR-4A — Scope implementado

### 3.1 Flujo bootstrap actualizado (`apps/users/apps.py`)

```
post_migrate
   ↓
env vars DJANGO_SUPERUSER_USERNAME / PASSWORD presentes?
   ├─ no  → return (noop)
   └─ sí
        ↓
   User.objects.filter(username=username).first()
   ├─ None (usuario no existe)
   │     ↓
   │   create org 'Vet Care Internal' (get_or_create)
   │     ↓
   │   create_user(..., is_superuser=True, role='ADMIN_SAAS')
   │     ↓
   │   log INFO SUPERUSER_BOOTSTRAP_CREATED
   │
   └─ existing
        ↓
      is_platform_superuser =
            existing.is_superuser
        AND existing.role == 'ADMIN_SAAS'
        AND (not email OR existing.email == email)
        ├─ False
        │     ↓
        │   log CRITICAL SUPERUSER_BOOTSTRAP_SKIPPED + abort
        │
        └─ True
              ↓
            si NOT is_active → existing.is_active=True (update_fields=['is_active'])
              ↓
            return  # NO resetea password
```

Cambios clave vs. implementación previa:
- `filter().first()` + bifurcación explícita reemplaza `get_or_create`. `get_or_create` no permite distinguir "encontrado vs creado" antes de decidir mutación.
- `set_password()` se elimina del path "usuario existente". Idempotencia de credenciales: re-deploys no rotan password silenciosamente.
- `Organization.get_or_create(name='Vet Care Internal')` se mueve dentro del branch "usuario no existe". Si abortamos por collision no creamos org huérfana.
- Comparación de email como defense-in-depth: si `DJANGO_SUPERUSER_EMAIL` está seteado y no coincide con el email del usuario en DB, lo tratamos como collision. Cierra ataque donde el operator cambió el email env esperando "transferir" el rol — exige flujo manual explícito vía admin.
- Logger `rbac.events` reusado (no se introduce logger nuevo).

### 3.2 Default permission classes (`config/settings.py` + `config/urls.py`)

`REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES = ('rest_framework.permissions.IsAuthenticated',)`.

Endpoints públicos:
- `ThrottledTokenObtainPairView.permission_classes = [AllowAny]`
- `PublicTokenRefreshView(TokenRefreshView)` con `permission_classes = [AllowAny]` (subclass nueva).

Rutas en `urls.py`:
- `path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair')`
- `path('api/token/refresh/', PublicTokenRefreshView.as_view(), name='token_refresh')`

`name=` añadido para soportar `reverse()` en tests de regresión y para introspección de URLs (consistente con resto del archivo cuando aplica).

---

## 4. PR-4B — Scope pendiente

Placeholder para la próxima implementación (no incluida en este merge):

- **Issue #10 — `/organizations/<pk>/` singleton:** colapsar el ViewSet a `/api/organizations/me/` (acción `me` ya canónica). Las URLs ID-based quedan deprecadas con header `Sunset: 2026-12-31` siguiendo RFC 8594.
- **Issue #11 — Cascade huérfanos + `ProtectedError`:**
  - `audit_orphan_fks` mgmt command (read-only, output JSON versionado, exit codes para CI).
  - `ProtectedError` handler bounded en `apps/core/exceptions.py` — solo `isinstance(exc, ProtectedError)` exact, probe slice `[:6]` para detalles, NO captura amplia de `IntegrityError`/`Exception`.
  - Soft-delete real (deuda A5) explícitamente fuera de PR-4B — se difiere a Fase 2 post-beta.

PR-4B referenciará este ADR como predecessor.

---

## 5. API contract — `/organizations/me/` singleton (decisión formal para PR-4B)

Cuando se implemente PR-4B, los compromisos serán:

- **URL stability:** `/api/organizations/me/` es el único endpoint singleton de la org del request. No expone `<pk>` salvo en API v2 con scope explícito de admin SaaS.
- **Schema:** mismo shape que `OrganizationSerializer` actual. Sin campos nuevos en v1.
- **HTTP semantics:**
  - `GET /api/organizations/me/` → 200 con datos de `request.user.organization`.
  - `PATCH /api/organizations/me/` → 200 con campos editables (admin only).
  - `DELETE` → 405 (no eliminar org via API).
- **Sunset path:** `/api/organizations/<pk>/` se mantiene operativo hasta `2026-12-31` con header `Sunset: Tue, 31 Dec 2026 23:59:59 GMT` y `Link: </api/organizations/me/>; rel="successor-version"` (RFC 8594). Tras esa fecha → 410 Gone.

---

## 6. Deprecation policy — `/organizations/<pk>/` (RFC 8594)

Política formal de deprecation cuando PR-4B aterrice:
- Headers en cada respuesta del endpoint legacy: `Sunset` + `Link rel="successor-version"`.
- Log `DEPRECATED_ENDPOINT_HIT` por cada request, con `endpoint`, `user_id`, `org_id`. Monitorea drift de adopción.
- Documentación en `CONTEXTO_ACTUAL_PROYECTO.md` con fecha límite y comunicación a clientes (cuando exista relación contractual).
- 2026-12-31 → response `410 Gone` + body `{"detail": "Endpoint deprecated. Use /api/organizations/me/."}`.

---

## 7. `audit_orphan_fks` como infraestructura operacional (PR-4B)

Cuando se implemente:
- Mgmt command read-only. Recorre FKs declaradas en modelos con tenant, detecta filas con `organization_id` inconsistente vs FK target.
- Output JSON versionado: `{"schema_version": "1", "audit_run_id": ..., "results": [...]}`. Bumpear `schema_version` si cambia el shape.
- Exit codes: `0` clean, `1` orphans detected (CI failure), `2` invariant violation (audit query failed).
- Ownership: ADMIN_SAAS via CLI / Railway shell. No expuesto vía API.
- **Boundary explícito (lo que NO mete):** validación de stock, balance contable, dedup de pacientes, reconciliación de Invoice. El comando audita integridad referencial. Otros invariantes tienen sus propios scripts (`audit_anchor_integrity`).

---

## 8. `ProtectedError` handler bounded (PR-4B)

Cuando se implemente:
- En `apps/core/exceptions.py::custom_exception_handler` añadir branch:
  ```python
  if isinstance(exc, ProtectedError):
      protected = list(exc.protected_objects)[:6]
      return Response({
          "detail": "No se puede eliminar — registros relacionados lo impiden.",
          "protected": [str(p) for p in protected],
          "protected_count": len(exc.protected_objects),
      }, status=409)
  ```
- `isinstance(...)` exact — NO captura `IntegrityError` ni `Exception`. La captura amplia oculta bugs no relacionados con FK protections (constraint failures, deadlocks).
- Probe `[:6]` para limitar tamaño de respuesta. El `protected_count` da el total.
- 409 Conflict (no 400) — el request es semánticamente válido, el conflicto es estado del recurso.

---

## 9. Deuda diferida a Fase 2

PR-4A genera deuda explícita que se documenta en `docs/deuda/`:

- **A5** — Soft-delete real (`is_active` / `deleted_at`) en `Owner` / `Pet` / `Organization`. Razón: hoy un `delete()` cascadea destructivamente; un soft-delete preservaría historial sin riesgo. Estimación 5-7 días. Bloquea PR-4B parcialmente (sin soft-delete, `ProtectedError` será frecuente en flujos legítimos).
- **A6** — `InvoiceAuditLog.invoice` `CASCADE` → `SET_NULL` + snapshot `invoice_public_id_at_delete`. Razón: hoy borrar una Invoice borra el rastro de auditoría que la justificó. Estimación 1-2 días.
- **A7** — `MedicalRecord.veterinarian` snapshot `vet_name_at_close` cuando User borrado. Razón: si un VET se elimina, los MR cerrados pierden la atribución. Estimación 1 día.
- **B5** — Migrar `_create_default_superuser` signal → management command explícito (`bootstrap_superuser`). Razón: signals en `post_migrate` son frágiles para invariantes de seguridad (orden de boot, doble-fire en multi-worker). Estimación 1 día.
- **B6** — `seed_permissions --prune` destructivo de Permission huérfanos. Razón: hoy `seed_permissions` solo añade; permisos eliminados del código quedan en DB. Estimación 1 día.

Detalle completo en `docs/deuda/fase2-prioridad-alta.md` y `docs/deuda/fase3-prioridad-media.md`.

---

## 10. Alternativas descartadas

- **Soft-delete inmediato en Fase 4 (en este PR):** descartado. Requiere migraciones en 4+ modelos + actualización de todas las queries con `for_organization()` para filtrar `deleted_at IS NULL` + impacto en analytics. Blast radius incompatible con PR de hardening pre-beta. Movido a deuda A5.
- **Mixin `TenantBootstrap` promovido a `apps/core/`:** descartado. El signal de bootstrap es one-off; no hay segundo caller que justifique el mixin. Promoción prematura.
- **`HybridPermission` como default global:** descartado. `HybridPermission` resuelve un `required_permission` por acción que las vistas declaran. Como default sin `required_permission` declarado se comporta indefinidamente. `IsAuthenticated` es el invariante mínimo correcto.
- **Mover signal a management command en este PR (cerrar B5 ahora):** descartado. Cambia el contrato de boot Railway; exige actualizar `Procfile` + smoke en staging. Día 4 cierra el vector sin tocar deploy ops.
- **Verificar `email` siempre (sin el branch `not email or ...`):** descartado. La env `DJANGO_SUPERUSER_EMAIL` es opcional. Si no se setea, no podemos exigirla en DB. La comparación se aplica solo cuando se provee — defense-in-depth opcional.
- **Throttle scope `bootstrap` en el endpoint legacy `/organizations/<pk>/`:** descartado para PR-4A. Cuando PR-4B implemente la deprecation, evaluar si el throttle global anon basta o si se requiere scope dedicado.

---

## Resumen ejecutivo

- **PR-4A merged:** Issue #12 (privilege escalation) + Issue #13 (default permission classes).
- **Tests:** 10 nuevos (7 bootstrap + 3 default permissions), 134 regresión OK, 0 fallos.
- **PR-4B pendiente:** Issue #10 (organizations singleton) + Issue #11 (cascade + ProtectedError handler).
- **Deuda generada:** A5-A7 (Fase 2), B5-B6 (Fase 3).
- **Sin cambios en:** modelos, migraciones, endpoints existentes (excepto declaración explícita de `AllowAny` en token endpoints).
