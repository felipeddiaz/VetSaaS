# Contexto actual del proyecto (VeterinariaSaaS)

Fecha de corte: 2026-05-16
Fuente: estado real del repositorio (backend + frontend).

---

## 1) Punto actual

El proyecto está en fase de hardening avanzado. La base multitenant, autenticación JWT, módulos clínicos/administrativos y frontend están operativos. Los sprints recientes se centraron en:

- Completar la migración RBAC hacia roles dinámicos en DB.
- Aplicar un sprint de seguridad completo (sanitización, concurrencia, UUIDs en URLs, throttling, exception handler).
- Cerrar bugs de UX en inventario, mascotas y citas.
- Sprint de validación transversal: sanitización en prescripciones, validación de servicios de billing, corrección del patrón `toast.promise` en formularios, navegación de Recetas.
- Rediseño estructural del historial clínico: `consultation_type`, modelo `VitalSigns`, endpoints `vitals` y `summary`, validación de cierre, 3 nuevos permisos RBAC.
- **Sprint 2026-05-05**: separación create/close en stepper (ADR p4), estandarización de PATCH (ADR p5), captura de vitales con hash comparison (ADR p6), lazy invoice creation sin facturas vacías (ADR p7).
- **Sprint 2026-05-06**: toggles de auto-creación a `False` por defecto, modal de citas post-done abierto con CTAs explícitos (ADR p8), `force_weight` por patrón `meta` en exception handler, `FIELD_TO_STEP` en stepper, anti-stale check con `updated_at`, servicios en stepper con endpoints completos, `unit_price` en MedicalRecordProduct.
- **Sprint 2026-05-07**: timeline editorial con Framer Motion (diario clínico agrupado año/mes, animaciones staggered, panel expandido rico), `public_id` en todas las URLs de medical records, `apiError` FIELD_MAP ampliado (30+ campos), RBAC UI usando `can_modify_charges`/`can_close` del backend, errores inline con cleanup onChange en stepper y vitales.
- **Sprint analytics 2026-05-09 (ADR p9 + p10)**: contrato analítico v0.3 + auditoría de schema (catálogo de "analytics lies") + Capa 1 hardening (anchors writers en services, CHECK constraints, admin status readonly, DELETE bypass cerrado, MR save() guard) + Capa 2 anchor completeness (`Invoice.confirmed_at`/`cancelled_at`, `Appointment.walk_in`, provenance fields con 5 sources, backfill no-naive) + Capa 3 indexes (11 índices compuestos + EXPLAIN validation) + Capa 4 snapshots (`apps/analytics/`, `DailyOrgMetrics`, `apply_snapshot` idempotente, `is_bucket_frozen` único helper, advisory lock per-org en cron) + Capa 5 read endpoints JSON-first (`/api/v1/dashboard/operations/series/`, `/financial/series/`, cada datapoint tagged con `source`+`lifecycle_state`). 159 tests pasando, 0 regresiones.
- **Sprint concurrencia 2026-05-16 (ADR p12)**: orden global de locks `MedicalRecord → Invoice → Presentation → InvoiceItem → MedicalRecordProduct` + `cancel_invoice()` con lock de Invoice + Presentations + `get_or_create_invoice_for_medical_record()` atómico + MR lockeado + `InvoiceDetailView.update()` bajo lock + `MedicalRecordProduct.save()` con parámetros `locked_presentation`/`previous_quantity` para evitar re-lock redundante + walk-in dedup con `pet=pet` + `walk_in=True`. Tests de concurrencia: 14 OK. Regresión amplia: 90 OK.

---

## 2) Arquitectura general

**Backend**: Django 6 + DRF + SimpleJWT — deploy en Railway (branch `main`).
**Frontend**: React 19 + Vite (JavaScript, sin TypeScript) — deploy en Vercel.
**DB**: PostgreSQL multitenant por `organization_id` en cada modelo.

Modelo base: `OrganizationalModel` con FK a `Organization`. Todas las queries de negocio van por `for_organization(org)` via `TenantManager`. Las vistas usan `TenantQueryMixin` que bloquea acceso si el usuario no tiene organización.

Autenticación: `TenantJWTAuthentication` recarga usuario con `select_related('organization')` en cada request.

---

## 3) Módulos backend

Apps activas: `organizations`, `users`, `patients`, `appointments`, `medical_records`, `inventory`, `billing`, `prescriptions`, `dashboard`, `analytics`, `core`.

| Módulo | Acoplamiento | Estado |
|--------|-------------|--------|
| `core` | Estable | Infraestructura pura. Permisos, sanitización, throttling, exception handler con soporte `meta` para metadatos (`__`-prefijo), mensajes de campo sin limpieza agresiva. Config `LANGUAGE_CODE = 'es-mx'`. |
| `patients` | Estable | Owner + Pet con aislamiento por org. UniqueConstraint para paciente genérico por org. |
| `prescriptions` | Estable | Items de receta con exportación PDF. FKs por string reference. Serializers con `sanitize_text` en `dose`, `duration`, `instructions`, `notes`. Validación de tenant en `validate_medical_record` y `validate_pet`. Receta NO descuenta stock por sí misma. |
| `users` | Estable | Roles estáticos + RBAC dinámico. Staff se crea vía API `/api/staff/create/`. |
| `dashboard` | Estable | Read endpoints v1 (`/api/v1/dashboard/operations/series/`, `/financial/series/`) que consumen `analytics.DailyOrgMetrics` para historia y `compute_daily_metrics` para today live. Cada datapoint tagged con `source` ∈ `snapshot`/`live` + `lifecycle_state`. `/api/internal/analytics-health/` para ADMIN_SAAS. |
| `organizations` | Bajo | Settings por org (timezone, tax_rate). `OrganizationSettings` se crea automáticamente. Defaults de toggles migrados a `False` (`auto_create_medical_record`, `auto_create_invoice_on_done`). |
| `appointments` | Moderado | Máquina de estados completa. Walk-in idempotente con lock en fila estable. `done` es estado terminal (`set()`). Modal post-done permanece abierto mostrando CTAs desde datos reales del backend. **`Appointment.walk_in BooleanField(db_index=True, editable=False)`** persistido (ADR p9). DELETE crea `AppointmentStatusChange` (event lineage). |
| `inventory` | Moderado-alto | Productos, presentaciones, movimientos de stock. `MedicalRecordProduct` vive aquí. `for_organization()` siempre antes de `select_for_update()` en queryset (ADR-10 consolidado). URLs de products migradas a `<str:medical_record_pk>`. `MedicalRecordProductSerializer` expone `unit_price` vía `presentation.sale_price`. |
| `medical_records` | Alto | Consultas con diagnóstico, tratamiento, vacunas, productos, servicios. `consultation_type` (general/vaccine/surgery/emergency), modelo `VitalSigns` (append-only, recorded_at), endpoints `vitals` y `summary`. Cierre valida `diagnosis` siempre y `treatment` si tipo cirugía. `MedicalRecordService` URLs migradas a `<str:>`. `updated_at` en fields para anti-stale. **`closed_at` editable=False + `closed_at_source` provenance + CHECK constraint + `save()` guard** (ADR p9). |
| `billing` | Alto | Máquina de estados `draft→confirmed→paid / cancelled`. Stock transaccional. `auto_create_invoice_on_done` default `False`; creación lazy via `get_or_create_invoice_for_medical_record()`. `Service` con `CheckConstraint(base_price__gt=0)`. **`paid_at`/`confirmed_at`/`cancelled_at` editable=False + `*_source` provenance + 3 CHECK constraints; `pay_invoice` movido a `services.py`** (ADR p9). |
| `analytics` | Lectura-derivada | App nueva (ADR p10). `DailyOrgMetrics` (1 row por org+día, 7 KPIs minimal v1, lifecycle_state, provenance_mix JSON, org_timezone_at_snapshot frozen). `DashboardSnapshotAudit` (append-only). Servicios: `is_bucket_frozen()` único, `compute_daily_metrics()` puro, `apply_snapshot()` idempotente. Mgmt commands: `build_daily_metrics` (per-org PG advisory lock + per-org failure isolation), `audit_anchor_integrity` (CI-ready). Today nunca snapshotteado. |

### Modelos con `public_id` (UUID en URLs)

`Pet`, `Owner`, `Appointment`, `MedicalRecord`, `Invoice`, `Prescription`, `Product`, `Presentation`, `Service`.

Modelos **sin** `public_id` (internos, nunca expuestos por UUID): `InvoiceItem`, `StockMovement`, `MedicalRecordProduct`, `MedicalRecordService`, `VitalSigns`, `InvoiceAuditLog`, `Permission`, `Role`, `UserRole`, `DailyOrgMetrics`, `DashboardSnapshotAudit`, `OrganizationTimezoneAudit`, `AppointmentStatusChange`.

URLs que referencian modelos con `public_id` usan `<str:pk>` (nunca `<int:`). La resolución va por `resolve_public_id()` con fallback controlado por `ALLOW_LEGACY_ID_LOOKUP`.

---

## 4) RBAC — estado actual

**Migración completada en fases:**

| Fase | Estado |
|------|--------|
| Fase 1 — Observabilidad | ✅ Completa |
| Fase 2 — Seguridad base (tests) | ✅ Completa |
| Fase 3 — Migración de vistas a HybridPermission | ✅ Completa |
| Fase 4 — Corte de `User.role` | ⏳ Pendiente (gate: 7 días sin `RBAC_FALLBACK_ALLOWED` en logs) |

**Fase 3 detail**: Todas las vistas usan `HybridPermission` o `make_permission()`. No queda ningún `RolePermission` directo en views. Se corrigió `organizations/views.py` que tenía una clase local `IsAdminUser` que verificaba `user.role == 'ADMIN'` directamente, bypaseando el RBAC.

**Eventos de observabilidad** (logger `rbac.events` → stdout Railway):
- `RBAC_ALLOWED_DB` (INFO) — permiso concedido por DB
- `RBAC_FALLBACK_ALLOWED` (WARNING) — concedido por rol estático (fallback)
- `RBAC_DENIED` (WARNING) — denegado
- `TENANT_MISMATCH_DETECTED` (ERROR) — acceso cross-tenant detectado

**Gate Fase 4**: `RBAC_FALLBACK_ALLOWED` ausente en stdout Railway por 7 días con tráfico real + `tenant_mismatch=0`. Al cumplirse: eliminar fallback en `HybridPermission` y retirar `User.role`.

**`seed_permissions`**: debe ejecutarse en cada deploy que agregue nuevos códigos a `PERMISSION_CODES`. Los 4 códigos `organization.*` agregados en la Fase 3 y los 3 nuevos de vitales/summary (`medicalrecord.vitals.create`, `medicalrecord.vitals.list`, `medicalrecord.summary.retrieve`) necesitan `seed_permissions` en el próximo deploy para persistirse en DB (ADMIN tiene wildcard `"*.*"` por lo que ya funciona sin ellos).

---

## 5) Seguridad y hardening

### Sanitización de inputs

Todos los campos de texto libre pasan por `apps/core/sanitize.py:sanitize_text()`:
- Proceso: truncar → normalizar unicode NFKC → bleach.clean (sin tags) → strip
- Límites por campo: `diagnosis/treatment → 400 chars`, `notes → 5000`, `vaccine_name/reason → 255`, `motivo/batch_number → 100`, `dose/duration → 255`, `instructions → 5000`
- FBVs que reciben texto libre sanitizan directamente (no delegan al serializer)

**Patrón obligatorio para campos obligatorios** (sanitizar antes de validar vacío):
```python
def validate_dose(self, value):
    clean = sanitize_text(value or '', max_length=255)
    if not clean.strip():
        raise serializers.ValidationError("La dosis es obligatoria.")
    return clean
```

**Cobertura por módulo:**

| Módulo | Campos sanitizados |
|--------|-------------------|
| `medical_records` | `diagnosis`, `treatment`, `notes`, `vaccine_name` |
| `appointments` | `reason`, `notes`, `cancellation_reason` |
| `billing` | `notes` (Invoice), `name`/`description` (Service) |
| `prescriptions` | `dose`, `duration`, `instructions`, `notes` |
| `inventory` | Regex restrictivo en `name` (no `sanitize_text`, bajo riesgo) |

### Throttling

`apps/core/throttling.py`:
- `LoginRateThrottle`: límite por IP (scope `login`)
- `LoginUserRateThrottle`: límite por IP+username normalizado (scope `login_by_user`).
- `vitals` scope: `60/hour` en `VitalSignsListCreateView` (usa `ScopedRateThrottle` por clase, no global).

### Exception handler global

`apps/core/exceptions.py:custom_exception_handler()`: formato unificado, mensajes en español, errores 500 incluyen `request_id`.

**Mejoras 2026-05-06:**
- **Contrato `meta`**: las claves que comienzan con `__` en el dict de errores se mueven a `response.data.meta`. Se usa en `_validate_weight_change` para señalar `force_weight_required` sin depender de texto del mensaje.
- **Errores de campo sin limpieza**: `_clean_message()` ya NO se aplica a errores de validación por campo (solo a `detail` global). Los mensajes del serializer preservan su contexto técnico completo. Combinado con `LANGUAGE_CODE = 'es-mx'`, DRF entrega mensajes en español directamente.

### Operaciones críticas en transacciones

- `select_for_update()` + `transaction.atomic()` en todas las operaciones de stock.
- **ADR-10 consolidado**: `for_organization()` siempre primero en la cadena de queryset. `select_for_update()` devuelve `QuerySet` estándar sin `for_organization()`. La cadena correcta es `Model.objects.for_organization(org).select_for_update()`.
- `bulk_create` asigna `organization=` explícitamente.
- Services con `@transaction.atomic` re-fetchean el objeto con lock al inicio.
- `delete()` overrides en modelos que mueven stock: envueltos en `atomic()` + lock previo.
- Walk-in / get_or_create idempotente: lockea fila estable (User/vet), no queryset vacío.

### Validación de FKs en serializers

Todo serializer que reciba FK de otro módulo valida el tenant:
```python
def validate_pet(self, pet):
    if pet and pet.organization != self.context['request'].user.organization:
        raise ValidationError('Acceso inválido.')
    return pet
```
**Cobertura completa 2026-05-06**: `PrescriptionSerializer` ahora incluye `validate_medical_record` y `validate_pet`.

### Validación de dominio en campos numéricos

- Precios (`base_price`, `sale_price`): `> 0` obligatorio. Validado en serializer + `CheckConstraint` en DB.
- Stock/cantidad: `>= 0` en stock, `> 0` en cantidades de venta.
- `Service.base_price__gt=0`: `CheckConstraint` en `Service.Meta` (migración `billing 0014`).

### Headers y configuración de producción

- `ENVIRONMENT=production`, `CORS_ALLOWED_ORIGINS`, `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`
- `ALLOW_LEGACY_ID_LOOKUP=False` — fijar cuando el frontend use `public_id` en todas las URLs (medical_records ya migrado).
- `LANGUAGE_CODE = 'es-mx'` — mensajes de validación DRF en español.

---

## 6) Máquinas de estado

### Appointment

```
scheduled → confirmed → in_progress → done (terminal)
    ↓            ↓            ↓
 canceled     canceled     canceled
    ↓            ↓
 no_show     no_show
```

`done` es estado terminal — no tiene transiciones salientes por diseño. El modal de citas permanece abierto tras completar la cita para mostrar CTAs contextuales (`+ Crear Consulta Médica`, `Ver Consulta`, `Ver Factura`) basados en `medical_record_ids` e `invoice_id` de la respuesta del backend.

### Invoice

Estados válidos: `draft → confirmed → paid` y `draft/confirmed → cancelled`.
- Solo `draft` puede editarse.
- `confirm_invoice`: requiere ≥1 ítem activo; re-fetch con `select_for_update()` al inicio.
- `pay_invoice`: requiere estado `confirmed` + `payment_method`.
- `total/subtotal/tax_amount/tax_rate` siempre calculados en backend (read-only en serializer).
- Factura ya no se auto-crea al marcar cita como `done` por defecto (`auto_create_invoice_on_done = False`).
- Creación lazy: la factura nace al agregar el primer cargo (producto/servicio) vía `get_or_create_invoice_for_medical_record()`.
- Nota ortográfica: billing usa `'cancelled'` (doble L), appointments usa `'canceled'` (una L).

---

## 7) Tests

Suite completa: **159 tests** en `backend/apps/`.

```bash
python manage.py test \
  apps.core.tests.test_security \
  apps.core.tests.test_sanitize \
  apps.core.tests.test_throttling \
  apps.core.tests.test_invoices \
  apps.medical_records.tests.test_close \
  apps.medical_records.tests.test_vitals \
  apps.billing.tests.test_money \
  apps.billing.tests.test_invoice_state_machine \
  apps.billing.tests.test_invoice_multitenancy \
  apps.billing.tests.test_event_authority \
  apps.billing.tests.test_anchor_completeness \
  apps.billing.tests.test_invoice_concurrency \
  apps.appointments.tests.test_walkin \
  apps.dashboard.tests.test_analytics_health \
  apps.dashboard.tests.test_series_endpoints \
  apps.analytics.tests.test_snapshot_v1 \
  apps.analytics.tests.test_build_command \
  apps.analytics.tests.test_cron_safety
```

`test_e2e.py` en la raíz de `backend/` requiere servidor corriendo — no se incluye en la suite normal.

**Suites analytics (29 tests, ADR p9 + p10)**:
- `test_event_authority` (7) — bloqueo de bypass paths a anchors
- `test_anchor_completeness` (14) — confirmed_at/cancelled_at writers + bulk-bypass + walk_in field + audit cmd
- `test_snapshot_v1` (18) — idempotency, today rejection, freeze transitions, TZ freeze, multi-tenant isolation, corruption visibility, provenance mix
- `test_build_command` (6) — CLI args, today skip, defaults
- `test_cron_safety` (7) — advisory lock, hash determinism, busy-org skip, failure isolation
- `test_series_endpoints` (17) — RBAC, source/lifecycle tagging, corrupt filtering, missing days, cardinality, tenant isolation, decimal-as-string
- `test_analytics_health` (4) — `/api/internal/analytics-health/` para ADMIN_SAAS

---

## 8) Frontend

Stack: React 19 + Vite + React Router 7 + Axios + FullCalendar + Sonner + react-day-picker 9 + Framer Motion + Sentry.

### Vistas operativas

Dashboard, Pacientes (con panel lateral de detalle), Equipo, Citas, Historial médico, Inventario, Facturación, Recetas (visor), Configuración.

### Patrones clave

- JWT con refresh automático antes de expiración.
- `AuthProvider` + rutas privadas.
- Cliente Axios central con interceptor para token y manejo de 401/500.
- **Formularios críticos**: usar `await api()` directo + `toast.success/error` manual + `saving` state.
- **ConfirmDialog**: `useConfirm` en todas las acciones destructivas y transiciones terminales (`in_progress → done`).
- `apiError(err, fallback)` — helper centralizado con `FIELD_MAP` ampliado a 30+ campos y fallback inteligente `field.replace(/_/g, ' ')`.
- **Errores inline**: `formErrors` state + cleanup onChange + `FIELD_TO_STEP` para navegación automática al paso con error.
- **`public_id`** en todas las URLs de API para modelos con UUID. `id` entero reservado para FK payloads en body de serializers.
- **Refetch obligatorio** tras mutaciones — no confiar en estado local.

### Timeline — Diario Clínico Editorial

Rediseño completo 2026-05-07:
- Agrupación jerárquica por año → mes con rail vertical + badge de count.
- Cards con bloque de fecha tipo mini-calendario (día grande, mes abreviado, hora).
- Track vertical con indicador de pulso animado (abierta) o check sólido (cerrada).
- Cápsula de tipo con icono y paleta por consulta (slate-blue, jade, mulberry, amber-rust).
- Diagnóstico como elemento primario tipográfico. Tratamiento como sublínea. Vitales como pills con iconos.
- Panel expandido con grid editorial: impresión clínica + plan terapéutico lado a lado. Productos como chips con icono. Receta como tarjetas con dosis y duración visibles.
- Animaciones: staggered entrance con Framer Motion, hover lift, `AnimatePresence` en expandir/colapsar.
- Métricas compactas (insumos / meds) en el costado derecho de cada card.
- Tipografía con `var(--font-display)` ('Outfit') para elementos editoriales. Sin cambios de fuente respecto al sistema.

### Recetas — visor clínico

`/prescriptions` es un visor histórico de recetas:
- **No tiene** botón "Nueva Receta" ni "Editar" por fila.
- Banner informativo: "Las recetas se crean desde el historial clínico de cada consulta."
- Funciones disponibles: Ver detalle, descargar PDF, eliminar.
- El flujo de creación desde URL params (`?medical_record=X&pet=Y`) se preserva para el link desde historial clínico.
- Una receta médica NO descuenta stock. Los productos recetados son sugerencias que el cliente decide llevar o no en caja.

### Fechas — BirthDatePicker

`pets.jsx` usa un componente `BirthDatePicker` custom que envuelve `react-day-picker v9`:
- Toggle al hacer click, cierra con click fuera (mousedown listener).
- `disabled={{ after: today }}` previene fechas futuras en el picker.
- Locale español (`es` de `react-day-picker/locale`).
- CSS override en `frontend/src/styles/day-picker.css` con los tokens del design system.

### Permisos en frontend

- `ASSISTANT`: solo lectura. No puede crear citas, no puede editar historial.
- `VET`: puede crear/editar en su ámbito. TimelineCard usa `can_modify_charges` y `can_close` del backend — no infiere permisos desde `user.role`.
- `ADMIN`: acceso completo.
- Selector de veterinario en citas solo muestra roles `VET` y `ADMIN`.

---

## 9) Deploy y operaciones

**Procfile** (Railway):
```
web: python manage.py collectstatic --noinput && python manage.py migrate --no-input && python manage.py seed_permissions && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
nightly_snapshots: python manage.py build_daily_metrics
nightly_anchor_audit: python manage.py audit_anchor_integrity --json
```

Process types `nightly_snapshots` y `nightly_anchor_audit` se schedulen vía Railway Cron service. Recomendación: 06:00 UTC daily (cubre Mexico GMT-6/-7/-8 yesterday end-of-day). Ambos commands son seguros para correr múltiples veces (advisory lock + idempotency en snapshots; mgmt audit es read-only). Wire alerting al exit code (snapshots exit 2 = al menos un org falló; audit exit 1 = unresolved provenance, exit 2 = invariant violation).

**Frontend**: `vercel.json` con rewrite SPA a `index.html`.

---

## 10) Deuda técnica y pendientes

> **Índice formal en [`docs/deuda/`](docs/deuda/README.md)** — items de hardening arquitectónico agrupados por fase (Fase 2 alta / Fase 3 media / Fase 4 baja). Esta tabla mantiene items operativos (deploy, config, frontend) que no encajan en hardening estructural.

| Item | Prioridad | Tracking |
|------|-----------|----------|
| ~~Día 3 — Multitenant FK validation (Errores 8-9)~~ | ✅ Cerrado | ADR p14 |
| **Fase 2 — Extracción `TenantScopedSerializerMixin` + migración 9 sitios** | Alta | [deuda A1](docs/deuda/fase2-prioridad-alta.md#a1) |
| **Fase 2 — `Invoice.clean()` → service + DB CHECK** | Alta | [deuda A2](docs/deuda/fase2-prioridad-alta.md#a2) |
| **Fase 2 — `closed_at` writer fuera de service (ADR p9 violation)** | Alta | [deuda A3](docs/deuda/fase2-prioridad-alta.md#a3) |
| **Fase 2 — `MRP.delete()` no se invoca en cascade** | Alta | [deuda A4](docs/deuda/fase2-prioridad-alta.md#a4) |
| **Fase 2 — Soft-delete real en `Owner`/`Pet`/`Organization`** | Alta | [deuda A5](docs/deuda/fase2-prioridad-alta.md#a5) |
| **Fase 2 — `InvoiceAuditLog.invoice` `CASCADE→SET_NULL` + snapshot `invoice_public_id_at_delete`** | Alta | [deuda A6](docs/deuda/fase2-prioridad-alta.md#a6) |
| **Fase 2 — `MedicalRecord.vet_name_at_close` snapshot cuando User borrado** | Alta | [deuda A7](docs/deuda/fase2-prioridad-alta.md#a7) |
| **Fase 3 — `_create_default_superuser` signal → mgmt command `bootstrap_superuser`** | Media | [deuda B5](docs/deuda/fase3-prioridad-media.md#b5) |
| **Fase 3 — `seed_permissions --prune` destructivo de Permission huérfanos** | Media | [deuda B6](docs/deuda/fase3-prioridad-media.md#b6) |
| Gate Fase 4 RBAC: 7 días sin `RBAC_FALLBACK_ALLOWED` en Railway para poder cortar `User.role` | Alta | [deuda B3](docs/deuda/fase3-prioridad-media.md#b3) |
| `seed_permissions` en próximo deploy: persistir `dashboard.financial.view` (nuevo) + códigos preexistentes (vitales/summary + organizations) | Alta |
| Wire Railway Cron a `nightly_snapshots` + `nightly_anchor_audit` con alerting on non-zero exit | Alta |
| `ALLOW_LEGACY_ID_LOOKUP=False` en Railway: medical_records ya migrado a `public_id`; restan billing, prescriptions, inventory, pets | Alta |
| Stock gap en venta de recetados: `prescription_suggestions` en billing no crea `MedicalRecordProduct` → stock nunca se descuenta al vender un producto recetado | Alta |
| Frontend dashboards consumiendo `/api/v1/dashboard/*/series/` — backend listo, UI pendiente | Media |
| `MetricAdjustments` table (contract §2.8) — necesaria si v1 va a soportar cancellations en charts post-freeze window | Media |
| Migrar `MedicalRecord.weight` a `VitalSigns` (data migration + eliminar campo heredado) — v2 | Media |
| `policies.py` — fallback a `PERMISSIONS` dict no emite `RBAC_FALLBACK_ALLOWED` (invisible al gate Fase 4) | Media |
| `ProductSerializer.update()` siempre actualiza la primera presentación (`first()`) sin validar identidad — correcto para v1 pero fragilidad si hay múltiples presentaciones | Media |
| `inventory/serializers.py` y `patients/serializers.py` — usan regex pero no `sanitize_text()`. Bajo riesgo (regex filtra HTML), aceptable en v1 | Baja |
| Inconsistencia ortográfica: `billing='cancelled'` vs `appointments='canceled'` requeriría migración de datos para unificar | Baja |
| `billing/models.py` TODO: hacer `presentation` obligatorio en `InvoiceItem` en v2 | Baja |
| Señal de creación de `Owner` genérico falla si el teléfono está vacío (visible en logs de test, no afecta producción) | Baja |
| Throttling per-scope para dashboard endpoints (contract §5.4) — diferido al ramp-up de uso real | Baja |
| Cache layer para today live aggregates — diferido (compute es barato a escala v1) | Baja |

### Fixes aplicados 2026-05-03 (sprint 1 — hardening RBAC/seguridad)

- **ADR-02**: `_get_cached_permissions(user)` extraída como función standalone en `core/permissions.py`.
- **ADR-03**: Constantes `SETTING_AUTO_MEDICAL_RECORD` / `SETTING_AUTO_INVOICE_ON_DONE` en `organizations/utils.py`.
- **ADR-04**: `pay_invoice` en `billing/views.py` ahora llama `_log_status_change()` dentro del bloque atómico capturando `previous_status` antes de la mutación.

### Fixes aplicados 2026-05-03 (sprint 2 — UX + validación transversal)

- **ADR-05**: `prescriptions/serializers.py` — sanitización completa en `dose` (obligatorio: sanitize → check vacío), `duration`, `instructions`, `notes`.
- **ADR-06**: `billing/serializers.py` — `SERVICE_NAME_REGEX` + `validate_name`, `validate_description`, `validate_base_price` (>0). `billing/models.py` — `CheckConstraint(base_price__gt=0)`.
- **ADR-07**: `prescriptions.jsx` convertido a visor clínico (sin creación/edición standalone). Sidebar con "Recetas".

### Fixes aplicados 2026-05-04 (sprint 3 — rediseño historial clínico)

- **ADR-08**: `medical_records/policies.py` — `assert_can_modify_medical_record()` separado de `assert_can_modify_charges()`.
- **ADR-09**: `VitalSignsListCreateView` — `initial()` fija `required_permission` explícito según HTTP.
- **ADR-10**: `for_organization()` siempre primero en la cadena de queryset.
- Nuevos modelos: `MedicalRecord.consultation_type`, `VitalSigns` (append-only). Migraciones `0012` y `0013`.
- `_get_last_weight(pet)`, `_validate_weight_change()` (compartida por ambos serializers).
- Validación de cierre: `close_medical_record` exige `diagnosis` siempre y `treatment` si `consultation_type=surgery`.
- 3 nuevos permisos RBAC: `medicalrecord.vitals.create/list`, `medicalrecord.summary.retrieve`.

### Fixes aplicados 2026-05-05 (sprint 4 — stepper + lazy invoice)

- **ADR-p4**: Separación create/close. Stepper crea en paso 1 y cierra en paso 4. `FIELD_TO_STEP` para mapeo de errores.
- **ADR-p5**: Estandarización de PATCH en todos los API helpers del frontend.
- **ADR-p6**: Captura de vitales con hash comparison normalizado. No duplica `VitalSigns` en cada avance de paso.
- **ADR-p7**: Creación lazy de facturas. Signal A eliminada (consultas walk-in). Signal B corregida (recupera invoice huérfana). `get_or_create_invoice_for_medical_record` con lógica appointment-first. `auto_create_invoice_on_done` default `False`.

### Fixes aplicados 2026-05-06 (sprint 5 — defaults + UX post-done)

- **ADR-p8**: Flujo manual post-done con CTA explícito. `done` se preserva como estado terminal. ConfirmDialog antes de completar. Modal permanece abierto con CTAs desde datos reales del backend. Defaults `auto_create_medical_record` y `auto_create_invoice_on_done` a `False`.
- Exception handler: soporte `meta` para `__`-prefijo. `_validate_weight_change` usa `__force_weight_required`. `_clean_message` retirado de errores de campo.
- `LANGUAGE_CODE = 'es-mx'` en settings.
- `force_weight` en frontend detectado por `meta.force_weight_required`. Reset en errores ajenos.
- `apiError.js`: FIELD_MAP ampliado a 30+ campos. Fallback con `replace(/_/g, ' ')`.
- `ConsultationStepperV2`: `recordRef` centralizado, `public_id` en URLs, `id` para FK payloads. Anti-stale check con `updated_at`. `formErrors` inline + cleanup onChange. Servicios con selector, normalización, constraint de unicidad y rollback.
- `inventory/serializers.py`: `unit_price` en `MedicalRecordProductSerializer` vía `presentation.sale_price`.
- `inventory/urls.py` y `medical_records/urls.py`: `<int:>` → `<str:>` para products y services.
- `prescriptions/serializers.py`: `validate_medical_record` y `validate_pet` para tenant.
- Todas las views de inventory y medical_records: `for_organization().select_for_update()` en orden correcto (ADR-10).

### Fixes aplicados 2026-05-07 (sprint 6 — timeline editorial + RBAC UI + clean exception handler)

- Timeline editorial completo: `Timeline.jsx` y `TimelineCard.jsx` rediseñados con Framer Motion. Agrupación año/mes, rail vertical, pulso animado, panel expandido editorial.
- `TimelineCard`: RBAC desde `can_modify_charges` / `can_close` del backend. Eliminada inferencia desde `user.role`.
- `medicalRecords.module.css`: sistema visual nuevo para todo el timeline. Sin cambios de fuente.
- `appointments.jsx`: `useConfirm` antes de `in_progress → done`. Modal permanece abierto. CTAs desde respuesta real del backend.
- Documentación: `CONTEXTO_ACTUAL_PROYECTO.md`, módulos (`appointments`, `billing`, `medical_records`, `frontend`), decisiones (p8, toggles).

### Fixes aplicados 2026-05-09 (sprint analytics — ADR p9 + p10)

**Capa 0 — Contrato + audit**
- `docs/dashboard-metrics-contract.md` v0.3 (event authority, reversal/cancellation policy, late-arriving data, snapshot lifecycle, schema versioning, throttling).
- `docs/analytics-readiness-checklist.md` (anchor matrix 5-D + index requirements + auth services + isolation tests).
- `docs/analytics-schema-audit.md` (trust matrix A/B/C/D/F, 18 analytics lies catalogados, 16 migraciones + 8 fixes ordenados, EXPLAIN findings, decay alerts).

**Capa 1 — Authority hardening**
- `pay_invoice` movido de `billing/views.py` a `billing/services.py` (single writer del anchor).
- `MedicalRecord.save()` invariant: `status='closed' AND closed_at is None` raise.
- `AppointmentDetailView.destroy()` crea `AppointmentStatusChange` (event lineage restaurado).
- `InvoiceAdmin.readonly_fields` incluye `status`, `payment_method`, anchors. Admin no muta estado.
- `create_draft_invoice_on_done` signal short-circuit cuando `update_fields` no toca status.
- CHECK constraints DB:
  - `invoice_paid_status_requires_paid_at` (billing/0015)
  - `medicalrecord_closed_status_requires_closed_at` (medical_records/0014)

**Capa 2 — Anchor completeness + provenance**
- Nuevos campos `Invoice.confirmed_at`, `Invoice.cancelled_at` (editable=False) + `Appointment.walk_in BooleanField(db_index=True, editable=False)` (migrations billing/0016, billing/0017, medical_records/0015, appointments/0010).
- Provenance fields con choices `service|audit_log|fallback|unresolved|legacy`: `Invoice.paid_at_source`, `confirmed_at_source`, `cancelled_at_source`, `MedicalRecord.closed_at_source`.
- Backfill no-naive desde `InvoiceAuditLog`. Política estricta: jamás inventar timestamps; `unresolved` antes que falso.
- 2 CHECK constraints adicionales: `invoice_confirmed_status_requires_confirmed_at`, `invoice_cancelled_status_requires_cancelled_at`.
- Mgmt command `audit_anchor_integrity` (validation + provenance distribution + decay alerts; exit 0/1/2 para CI).

**Capa 3 — Indexes**
- 11 índices compuestos: `idx_inv_org_status_paid`/`_conf`/`_canc`, `idx_mr_org_status_closed_at`/`_appointment`/`_status_created`, `idx_appt_org_start_status`, `idx_vacc_org_app_date`/`_next_due`, `idx_stockmov_org_pres_created`, `idx_presc_org_created`.
- EXPLAIN ejecutado con `enable_seqscan=off` para verificar utilizabilidad.
- Operational rule: `ANALYZE <tabla>` después de cada import / primera corrida del nightly job.

**Capa 4 — Snapshots minimal v1 (`apps/analytics/`)**
- `DailyOrgMetrics` (1 row por org+día, 7 KPIs minimales, `lifecycle_state`, `metrics_schema_version`, `provenance_mix`, `org_timezone_at_snapshot`).
- `DashboardSnapshotAudit` (append-only, lifecycle transitions + diff JSON).
- `apps/analytics/services.py`: `is_bucket_frozen()` único helper, `compute_daily_metrics()` puro, `apply_snapshot()` idempotente.
- `apps/core/db_locks.py`: `try_advisory_lock`, `advisory_lock` context manager, `hash_lock_key`.
- Mgmt command `build_daily_metrics`: per-org PG advisory lock (Railway double-fire safe), per-org failure isolation, structured logs, exit 2 si algún org falló.

**Capa 5 — Read endpoints JSON-first**
- `/api/v1/dashboard/operations/series/` (VET/ASSISTANT/ADMIN).
- `/api/v1/dashboard/financial/series/` (ADMIN only, permission code `dashboard.financial.view` nuevo).
- `/api/internal/analytics-health/` (ADMIN_SAAS only) — anchor distribution, invariant violations, decay alerts, trust score per anchor.
- Cada datapoint tagged con `source` ∈ `snapshot|live` y `lifecycle_state`. Today siempre `live`. Corrupt rows filtradas.
- Hard cap 365 días, `?include_today=true|false`, `notes` para missing days.

**Tests**: 159 totales. 24 nuevos en analytics, 17 en dashboard endpoints, 21 en billing event-authority + anchor-completeness, 4 en analytics health.

**Documentación nueva**:
- `docs/decisions/2026-05-09-p9-analytics-anchor-authority.md`
- `docs/decisions/2026-05-09-p10-analytics-snapshots-and-read-endpoints.md`
- `docs/modules/analytics.md`
- Updates en `docs/modules/billing.md`, `medical_records.md`, `appointments.md`, `CLAUDE.md`.

### Fixes aplicados 2026-05-16 (sprint concurrencia — ADR p12)

**Orden global de locks** (no negociable):
```
MedicalRecord → Invoice → Presentation → InvoiceItem → MedicalRecordProduct
```

**Services — `billing/services.py`:**
- `cancel_invoice()`: re-fetch con `select_for_update()` de Invoice + lock de Presentations en orden estable por pk antes de reversar stock.
- `get_or_create_invoice_for_medical_record()`: `@transaction.atomic`, lock de `MedicalRecord`, retorna Invoice lockeada.
- Helper `_lock_presentations(presentation_ids)`: lockea múltiples Presentations en orden determinista.

**Views — `billing/views.py`:**
- `InvoiceDetailView.update()`: `transaction.atomic()` + lock de Invoice antes del check de `draft`.
- `InvoiceItemDetailView.update()/destroy()`: `transaction.atomic()` + lock de Invoice para proteger `recalculate_totals()`.

**Views — `inventory/views.py`:**
- `MedicalRecordProductListCreateView.perform_create()`: lock de MR → Invoice (via helper) → Presentation → InvoiceItem → MRP.
- `MedicalRecordProductDeleteView.perform_destroy()`: re-fetch de instancia con lock antes de delete, sync de InvoiceItem bajo lock de Invoice.

**Models — `inventory/models.py`:**
- `MedicalRecordProduct.save()`: parámetros opcionales `locked_presentation` y `previous_quantity` para evitar re-lock redundante cuando la view ya lockeó.
- `MedicalRecordProduct.delete()`: acepta `locked_presentation` para reutilizar lock del caller.

**Views — `medical_records/views.py`:**
- `MedicalRecordServiceListCreateView.perform_create()`: lock de MR → Invoice → sync de InvoiceItem bajo lock.
- `MedicalRecordServiceDeleteView.perform_destroy()`: re-fetch de instancia con lock, sync de InvoiceItem bajo lock de Invoice.

**Views — `appointments/views.py`:**
- `walk_in()`: dedup ahora exige `walk_in=True` y `pet=pet` — no reutiliza cita de otra mascota.

**Tests nuevos** (`apps/billing/tests/test_invoice_concurrency.py`):
- `test_parallel_product_and_service_create_single_invoice`
- `test_medical_record_product_create_integrity_error_does_not_decrement_stock`
- `test_cancel_invoice_parallel_pay_and_cancel_keeps_single_final_state`
- `test_parallel_add_and_delete_same_product_keeps_correct_stock`

**Tests extendidos** (`apps/appointments/tests/test_walkin.py`):
- `test_walkin_dedup_does_not_reuse_different_pet`
- `test_walkin_dedup_does_not_reuse_non_walkin_appointment`

**Resultados**: 14 tests de concurrencia OK + 90 tests de regresión OK (0 fallos).

**Documentación nueva**:
- `docs/decisions/2026-05-16-p12-concurrency-lock-order-hardening.md`
- Updates en `docs/modules/billing.md`, `inventory.md`, `medical_records.md`, `appointments.md`.

### Fixes aplicados 2026-05-16 (remediación post-review Día 1-2 — ADR p13)

Tras p12, una segunda pasada de revisión paralela (`code-reviewer`, `security-auditor`, `backend-architect`) confirmó las 7 fixes core correctas pero detectó 7 gaps secundarios. Todos resueltos:

**Convención de mutación de `InvoiceItem.quantity` (regla no negociable):**
- Toda mutación de `InvoiceItem.quantity` DEBE usar `F('quantity') ± delta` vía `update()`, **incluso con `select_for_update()`**. Prohibido `item.quantity += delta; item.save()`.
- Helper único: `apps.billing.services.apply_invoice_item_quantity_delta(item, delta)`.
- Razón: consistencia con `apply_stock_movement` para `Presentation.stock` + defense-in-depth + single round-trip.

**Sites refactorizados (4) con el helper:**
- `medical_records/views.py::MedicalRecordServiceListCreateView.perform_create` (increment) — además **orden corregido**: `mrs = serializer.save(...)` ahora se ejecuta DESPUÉS del sync de InvoiceItem para respetar el orden canónico `MR → Invoice → InvoiceItem → MRS`.
- `medical_records/views.py::MedicalRecordServiceDeleteView.perform_destroy` (decrement con proyección previa).
- `inventory/views.py::MedicalRecordProductListCreateView.perform_create` (increment).
- `inventory/views.py::MedicalRecordProductDeleteView.perform_destroy` (decrement con proyección previa).

**Patrón canónico decrement (delete paths):**
```python
projected = item.quantity - fresh_instance.quantity
if projected <= 0:
    item.delete()
else:
    apply_invoice_item_quantity_delta(item, -fresh_instance.quantity)
```

**Defense-in-depth tenant filter** (`billing/services.py`):
- `confirm_invoice`, `pay_invoice`, `pay_direct_sale` re-lockean con `Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)` — consistente con `cancel_invoice` que ya lo hacía.

**Contrato de lock documentado** (`inventory/services.py`):
- Docstring de `apply_stock_movement` ahora enumera explícitamente "⚠️ CONTRATO DE LOCK (CRÍTICO)" + lista los 5 callers válidos. Próximo contribuidor no puede romperlo por desconocimiento.

**Fail-fast en `MedicalRecordProduct.save()` y `.delete()`** (`inventory/models.py`):
- `assert connection.in_atomic_block` al inicio de ambos métodos. Si el caller no abrió `transaction.atomic()`, levanta `AssertionError` con mensaje canónico.
- Warning log si `save()` se invoca sin `locked_presentation` (visibilidad de callers no-canónicos en prod).
- Smoke verificado: invocar `MRP.save()` fuera de atomic dispara el assert.

**Test rollback corregido** (`billing/tests/test_anchor_completeness.py`):
- `test_direct_pay_rolls_back_stock_on_payment_error` reemplaza el falso-positivo (`payment_method='bitcoin'` rechazado ANTES de `_confirm_locked_invoice`) por `unittest.mock.patch` que dispara `ValidationError` DESPUÉS de la confirmación. Verifica rollback completo de stock + `confirmed_at` + `paid_at` + `InvoiceAuditLog`.

**Tests de concurrencia nuevos** (`billing/tests/test_invoice_concurrency.py`):
- `test_two_parallel_pay_direct_sale_serialize` — 2 POSTs paralelos a `/direct-pay/` sobre misma invoice; solo 1 retorna 200, stock descontado una vez.
- `test_two_parallel_invoice_patch_serialize` — 2 PATCHes paralelos serializados via lock, estado final coherente.
- `test_parallel_pay_direct_sale_and_cancel_keep_consistent_stock` — `pay_direct_sale` + `cancel_invoice` paralelos, solo una operación gana, stock consistente.

**Doc reference corregida**:
- `pay_direct_sale.__doc__`: `§4.2` → `§3.1.2 (revenue_accrual)`.

**Resultados**: 233 tests pasan (suite completa CLAUDE.md + 3 nuevos concurrentes). `audit_anchor_integrity` → `✓ All invariants hold`. Smoke del assert OK.

**Deuda conocida flagged (fuera de scope, documentar para sprint separado):**
- `medical_records/views.py:432` escribe `closed_at` desde view en lugar de `services.py` (viola ADR p9 / ADR-11). Extraer a `medical_records/services.py::close_medical_record_service()`.
- `MedicalRecordProduct.delete()` no se invoca en cascada de `MedicalRecord.delete()` (Django ORM bypasea custom delete). Stock no se revierte si se borra el MR completo. No exponer endpoint de cascade-delete sin antes iterar productos.
- `InvoiceSerializer.validate()` exige `pet/owner` incluso en PATCH parcial. Bloquea PATCH minimalistas como `{"notes": "x"}`. Los tests envían `pet` + `owner` explícitamente para sortearlo.

**Documentación nueva**:
- `docs/decisions/2026-05-16-p13-day12-concurrency-remediation.md`
- Updates en `docs/modules/billing.md` (sección F() helper + tenant filter), `inventory.md` (contrato `apply_stock_movement` + assert + deuda cascade), `medical_records.md` (orden MRS create + helper en MRP/MRS), `CLAUDE.md` (regla F() obligatoria).

**Próximo**: Día 3 — tenant validators P0 #8-9 (`InvoiceSerializer` + `PrescriptionItemSerializer`).

### Fixes aplicados 2026-05-16 (Día 3 — tenant validators serializers — ADR p14)

**P0 #8 + #9 cerrados.** Última pieza pre-beta. Approach hotfix-conservador (no se promueve abstracción a `apps/core/` hasta battle-testing post-beta — ver ADR p14).

**Serializers — `billing/serializers.py`:**
- `InvoiceSerializer`: 4 `validate_<fk>` (owner, pet, appointment, medical_record) usando helper local `_validate_same_org`. Cross-org FK ahora retorna **400 'Acceso inválido.'** (antes: 500 crudo porque `Invoice.clean()` levantaba `django.core.exceptions.ValidationError` no mapeada por DRF).
- Patrón canónico `_get_request()`: `self.context.get('request') + assert is not None`. Loud failure si se invoca fuera de view DRF, sin romper introspectivos (schema generation, swagger).
- Fix 4 PATCH partial: `data.get('field', getattr(self.instance, 'field', None))` permite PATCH minimalistas como `{"notes": "x"}` sin re-enviar pet/owner. Bug pre-existente que afectaba UX real.

**Serializers — `prescriptions/serializers.py`:**
- `PrescriptionItemSerializer` (nested en `PrescriptionSerializer.items`): nuevo `validate_product` con tenant check. Cierra el leak de productos cross-org en el PDF de receta.
- `PrescriptionItemWriteSerializer.validate_product`: tenant check añadido **antes** del existente `requires_prescription` check (no revelar atributo de producto cross-org).
- Helper `_validate_same_org` duplicado (idéntico al de billing) — se elimina en Fase 2 cuando se extraiga el mixin.

**Observabilidad — nuevo evento `TENANT_VALIDATION_REJECTED`:**
- Logger `apps.tenant_validation` → handler `rbac_console` (JSON estructurado, Railway-ready).
- Severidad **WARNING** (no ERROR). Separado intencionalmente de `TENANT_MISMATCH_DETECTED` (ERROR, `HybridPermission.has_object_permission`) para no saturar la señal operacional con typos de UI / IDs stale / replays.
- Campos: `source='serializer'`, `serializer`, `field`, `user_id`, `user_org_id`, `resource_org_id`, `resource_pk`, `endpoint`, `method`.

**Tests:**
- `billing/tests/test_invoice_multitenancy.py`: 14 nuevos (6 P0 + 8 PATCH partial). Total billing multitenancy: 20/20 OK.
- `prescriptions/tests/test_multitenancy.py`: **archivo nuevo** (dir tampoco existía). 7 tests cubren: nested PrescriptionItem cross-org, WriteSerializer cross-org, orden tenant-first / requires_prescription-second, observabilidad assertLogs, PATCH nested replace items, PATCH notes-only sin tocar items.
- Suite completa: **254/254 OK**, `audit_anchor_integrity` → `✓ All invariants hold`.

**Decisiones rechazadas (documentadas en ADR p14):**
- ❌ `TenantScopedSerializerMixin` + `TenantScopedPrimaryKeyRelatedField` promovidos a `apps/core/` ahora. Razones: cambio silencioso de contrato API (mensajes inglés vs español), cambio de filosofía semántica (400 "Acceso inválido" vs 404 "Not found"), side effects en `validate()` legacy, DRF caching/nested edge cases, blast radius transversal pre-beta. La abstracción es correcta arquitectónicamente — diferida a Fase 2 post-beta.
- ❌ Copia-pega de 5+ validators más (consolidaría deuda existente de 7 sitios duplicados).
- ❌ `@expectedFailure` para PATCH partial bug (cerca de release degrada disciplina QA).

**Decisiones aceptadas como deuda visible (ver `docs/deuda/`):**
- 🔴 **Fase 2 (post-beta inmediato)**: extracción de mixin centralizado + migración 9 sitios; `Invoice.clean()` → service + DB CHECK; `closed_at` writer fuera de service (ADR p9 violation); `MRP.delete()` cascade.
- 🟠 **Fase 3 (sprint dedicado)**: `apply_stock_movement` lock-internal o assert; PrescriptionItemSerializer dedup; RBAC Fase 4 (cortar `User.role` legacy); eliminar `_validate_same_org` duplicados.
- 🟡 **Fase 4 (mejoras arquitectónicas)**: decisión 400 vs 404 cross-tenant; `InvoiceSerializer.validate()` side effects (`generic owner → direct_sale` mutación).

**Resultados pre-beta:** 9/9 P0 cerrados (#1-7 concurrencia Días 1-2 + #8-9 tenant Día 3). Listo para staging.

**Documentación nueva**:
- `docs/decisions/2026-05-16-p14-tenant-validators-day3.md` — ADR completo
- `docs/deuda/README.md` — índice de deuda
- `docs/deuda/fase2-prioridad-alta.md` — A1-A4 (post-beta inmediato)
- `docs/deuda/fase3-prioridad-media.md` — B1-B4 (sprint dedicado)
- `docs/deuda/fase4-prioridad-baja.md` — C1-C2 (arquitectónicas)
- Updates en `docs/modules/billing.md` (tenant validators + PATCH fix), `medical_records.md` (receta tenant + closed_at deuda link), `inventory.md` (cascade deuda link), `CLAUDE.md` (regla `.get() + assert`).

**Próximo**: staging deploy + monitoreo Railway 7+ días → si métricas estables, beta launch. En paralelo: Fase 2 sprint planning.

### Fixes aplicados 2026-05-17 (Día 4 PR-4A — perimeter hardening — ADR p15)

**P0 #12 + #13 cerrados.** PR-4A del sprint pre-beta. PR-4B (#10 + #11) pendiente.

**Fix #12 — `_create_default_superuser` privilege escalation (CVSS 9.9) — `apps/users/apps.py`:**
- Reescritura completa del signal `post_migrate`. Se reemplaza `User.objects.get_or_create(username=...)` por `filter(username).first()` + bifurcación explícita en 3 branches:
  - Usuario no existe → `create_user(..., is_superuser=True, role='ADMIN_SAAS')` + log INFO `SUPERUSER_BOOTSTRAP_CREATED`. La org `'Vet Care Internal'` solo se crea aquí (no quedan orgs huérfanas si abortamos).
  - Usuario existe Y es el platform-superuser legítimo (`is_superuser=True AND role='ADMIN_SAAS' AND email coincide cuando se provee`) → solo refresca `is_active` si estaba inactivo. **NO resetea password** (idempotencia de credenciales).
  - Usuario existe pero NO es el platform-superuser esperado → log CRITICAL `SUPERUSER_BOOTSTRAP_SKIPPED` con `reason='username_collision_non_platform_user'` + abort sin mutación.
- Vector cerrado: una clínica registra VET con username `admin`, env Railway tiene `DJANGO_SUPERUSER_USERNAME=admin`, el siguiente deploy ya NO escala al VET ni le resetea password.

**Fix #13 — `DEFAULT_PERMISSION_CLASSES` faltante — `config/settings.py` + `config/urls.py`:**
- `REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] = ('rest_framework.permissions.IsAuthenticated',)` añadido. Cualquier vista nueva que olvide declarar `permission_classes` queda cerrada por defecto.
- `ThrottledTokenObtainPairView.permission_classes = [AllowAny]` añadido para preservar acceso público al login.
- `PublicTokenRefreshView(TokenRefreshView)` con `permission_classes = [AllowAny]` (subclass nueva — `TokenRefreshView` se usaba directamente).
- Rutas reciben `name='token_obtain_pair'` y `name='token_refresh'` para soportar `reverse()` en tests.

**Tests nuevos:**
- `apps/users/tests/test_bootstrap.py` — 7 tests (creación, collision skip, idempotencia password, refresh is_active, no-org-leak en collision, email mismatch, env vars ausentes).
- `apps/core/tests/test_default_permissions.py` — 3 tests (settings default, token endpoint público, refresh endpoint público).
- **Resultados**: 10/10 nuevos OK + 134/134 regresión OK (suite security/sanitize/throttling/invoices/state-machine/multitenancy/prescriptions/close/walkin).

**Decisiones rechazadas (documentadas en ADR p15):**
- ❌ Soft-delete real (deuda A5) en este PR — blast radius transversal, exige migraciones en 3 modelos + filtrado en `TenantManager` + actualización de endpoints.
- ❌ Mover signal a management command ahora (deuda B5) — exige cambios en `Procfile` Railway + revisión de orden de boot.
- ❌ `HybridPermission` como default global — sin `required_permission` declarado se comporta indefinidamente. `IsAuthenticated` es el invariante mínimo correcto.

**Deuda generada (visible en `docs/deuda/`):**
- 🔴 **Fase 2 (post-beta inmediato)**: A5 (soft-delete real), A6 (`InvoiceAuditLog.invoice` `CASCADE→SET_NULL`), A7 (`MR.vet_name_at_close` snapshot).
- 🟠 **Fase 3 (sprint dedicado)**: B5 (signal → mgmt command `bootstrap_superuser`), B6 (`seed_permissions --prune`).

**Documentación nueva**:
- `docs/decisions/2026-05-17-p15-day4-cascade-lockdown.md` — ADR completo
- `docs/deuda/fase2-prioridad-alta.md` — A5-A7 añadidos
- `docs/deuda/fase3-prioridad-media.md` — B5-B6 añadidos

**Próximo**: PR-4B (Issue #10 organizations singleton + Issue #11 cascade + `ProtectedError` handler bounded).

---

## 11) Índice de ADRs (decisiones de arquitectura)

| ADR | Fecha | Título | Estado |
|-----|-------|--------|--------|
| `2026-04-25-cierre-consulta-explicito.md` | 04-25 | Cierre de consulta explícito | Implementado |
| `2026-04-26-receta-no-es-factura.md` | 04-26 | Receta no es factura | Implementado |
| `2026-04-27-maquina-de-estados-citas.md` | 04-27 | Máquina de estados de citas | Implementado |
| `2026-04-28-organization-settings-toggles.md` | 04-28 | Toggles de flujo por organización | Implementado |
| `2026-04-28-generic-client-direct-sale.md` | 04-28 | Venta directa con cliente genérico | Implementado |
| `2026-04-28-registro-rapido-cita.md` | 04-28 | Registro rápido + cita | Implementado |
| `2026-05-01-p1-business-logic-hardening.md` | 05-01 | Hardening de lógica de negocio | Implementado |
| `2026-05-02-p2-frontend-ux-hardening.md` | 05-02 | Hardening UX frontend | Implementado |
| `2026-05-04-p3-historial-clinico-vitalsigns.md` | 05-04 | VitalSigns en historial clínico | Implementado |
| `2026-05-05-p4-create-close-separation.md` | 05-05 | Separación create/close en stepper | Implementado |
| `2026-05-05-p5-patch-vs-put.md` | 05-05 | PATCH en lugar de PUT | Implementado |
| `2026-05-05-p6-stepper-vitals-capture.md` | 05-05 | Captura de vitales en stepper | Implementado |
| `2026-05-05-p7-lazy-invoice-creation.md` | 05-05 | Creación lazy de facturas | Implementado |
| `2026-05-06-p8-post-done-manual-flow.md` | 05-06 | Flujo manual post-done con CTA explícito | Implementado |
| `2026-05-09-p9-analytics-anchor-authority.md` | 05-09 | Analytics anchor authority + provenance (Capa 1+2) | Implementado |
| `2026-05-09-p10-analytics-snapshots-and-read-endpoints.md` | 05-09 | Snapshots minimal v1 + read endpoints JSON-first (Capa 3+4+5) | Implementado |
| `2026-05-16-p12-concurrency-lock-order-hardening.md` | 05-16 | Orden global de locks + hardening concurrencia Día 1-2 | Implementado |
| `2026-05-16-p13-day12-concurrency-remediation.md` | 05-16 | Remediación post-review Día 1-2 (helper F() + asserts + tenant filter + docstring) | Implementado |
| `2026-05-16-p14-tenant-validators-day3.md` | 05-16 | Día 3 — tenant validators P0 #8-9 + Fix 4 PATCH partial + plan Fase 2 mixin | Implementado |
| `2026-05-17-p15-day4-cascade-lockdown.md` | 05-17 | Día 4 — PR-4A: privilege escalation guard + default IsAuthenticated. PR-4B (cascade + ProtectedError handler) pendiente | Parcial (PR-4A) |
