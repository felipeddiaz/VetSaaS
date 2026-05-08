# Contexto actual del proyecto (VeterinariaSaaS)

Fecha de corte: 2026-05-07
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

---

## 2) Arquitectura general

**Backend**: Django 6 + DRF + SimpleJWT — deploy en Railway (branch `main`).
**Frontend**: React 19 + Vite (JavaScript, sin TypeScript) — deploy en Vercel.
**DB**: PostgreSQL multitenant por `organization_id` en cada modelo.

Modelo base: `OrganizationalModel` con FK a `Organization`. Todas las queries de negocio van por `for_organization(org)` via `TenantManager`. Las vistas usan `TenantQueryMixin` que bloquea acceso si el usuario no tiene organización.

Autenticación: `TenantJWTAuthentication` recarga usuario con `select_related('organization')` en cada request.

---

## 3) Módulos backend

Apps activas: `organizations`, `users`, `patients`, `appointments`, `medical_records`, `inventory`, `billing`, `prescriptions`, `dashboard`, `core`.

| Módulo | Acoplamiento | Estado |
|--------|-------------|--------|
| `core` | Estable | Infraestructura pura. Permisos, sanitización, throttling, exception handler con soporte `meta` para metadatos (`__`-prefijo), mensajes de campo sin limpieza agresiva. Config `LANGUAGE_CODE = 'es-mx'`. |
| `patients` | Estable | Owner + Pet con aislamiento por org. UniqueConstraint para paciente genérico por org. |
| `prescriptions` | Estable | Items de receta con exportación PDF. FKs por string reference. Serializers con `sanitize_text` en `dose`, `duration`, `instructions`, `notes`. Validación de tenant en `validate_medical_record` y `validate_pet`. Receta NO descuenta stock por sí misma. |
| `users` | Estable | Roles estáticos + RBAC dinámico. Staff se crea vía API `/api/staff/create/`. |
| `dashboard` | Estable | Métricas diarias y alertas. Solo lectura vía late imports. Sin joins que asuman MedicalRecord para cada cita. |
| `organizations` | Bajo | Settings por org (timezone, tax_rate). `OrganizationSettings` se crea automáticamente. Defaults de toggles migrados a `False` (`auto_create_medical_record`, `auto_create_invoice_on_done`). |
| `appointments` | Moderado | Máquina de estados completa. Walk-in idempotente con lock en fila estable. `done` es estado terminal (`set()`). Modal post-done permanece abierto mostrando CTAs desde datos reales del backend. |
| `inventory` | Moderado-alto | Productos, presentaciones, movimientos de stock. `MedicalRecordProduct` vive aquí. `for_organization()` siempre antes de `select_for_update()` en queryset (ADR-10 consolidado). URLs de products migradas a `<str:medical_record_pk>`. `MedicalRecordProductSerializer` expone `unit_price` vía `presentation.sale_price`. |
| `medical_records` | Alto | Consultas con diagnóstico, tratamiento, vacunas, productos, servicios. `consultation_type` (general/vaccine/surgery/emergency), modelo `VitalSigns` (append-only, recorded_at), endpoints `vitals` y `summary`. Cierre valida `diagnosis` siempre y `treatment` si tipo cirugía. `MedicalRecordService` URLs migradas a `<str:>`. `updated_at` en fields para anti-stale. |
| `billing` | Alto | Máquina de estados `draft→confirmed→paid / cancelled`. Stock transaccional. `auto_create_invoice_on_done` default `False`; creación lazy via `get_or_create_invoice_for_medical_record()`. `Service` con `CheckConstraint(base_price__gt=0)`. |

### Modelos con `public_id` (UUID en URLs)

`Pet`, `Owner`, `Appointment`, `MedicalRecord`, `Invoice`, `Prescription`, `Product`, `Presentation`, `Service`.

Modelos **sin** `public_id` (internos, nunca expuestos por UUID): `InvoiceItem`, `StockMovement`, `MedicalRecordProduct`, `MedicalRecordService`, `VitalSigns`, `InvoiceAuditLog`, `Permission`, `Role`, `UserRole`.

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

Suite completa: **87 tests** en `backend/apps/`.

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
  apps.billing.tests.test_invoice_multitenancy
```

`test_e2e.py` en la raíz de `backend/` requiere servidor corriendo — no se incluye en la suite normal.

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
web: python manage.py migrate --no-input && python manage.py seed_permissions && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

**Frontend**: `vercel.json` con rewrite SPA a `index.html`.

---

## 10) Deuda técnica y pendientes

| Item | Prioridad |
|------|-----------|
| Gate Fase 4 RBAC: 7 días sin `RBAC_FALLBACK_ALLOWED` en Railway para poder cortar `User.role` | Alta |
| `seed_permissions` en próximo deploy: persistir nuevos códigos RBAC en DB (vitales/summary + organizations) | Alta |
| `ALLOW_LEGACY_ID_LOOKUP=False` en Railway: medical_records ya migrado a `public_id`; restan billing, prescriptions, inventory, pets | Alta |
| Stock gap en venta de recetados: `prescription_suggestions` en billing no crea `MedicalRecordProduct` → stock nunca se descuenta al vender un producto recetado | Alta |
| Migrar `MedicalRecord.weight` a `VitalSigns` (data migration + eliminar campo heredado) — v2 | Media |
| `policies.py` — fallback a `PERMISSIONS` dict no emite `RBAC_FALLBACK_ALLOWED` (invisible al gate Fase 4) | Media |
| `inventory/serializers.py` y `patients/serializers.py` — usan regex pero no `sanitize_text()`. Bajo riesgo (regex filtra HTML), aceptable en v1 | Baja |
| `ProductSerializer.update()` siempre actualiza la primera presentación (`first()`) sin validar identidad — correcto para v1 pero fragilidad si hay múltiples presentaciones | Media |
| Inconsistencia ortográfica: `billing='cancelled'` vs `appointments='canceled'` requeriría migración de datos para unificar | Baja |
| `billing/models.py` TODO: hacer `presentation` obligatorio en `InvoiceItem` en v2 | Baja |
| Señal de creación de `Owner` genérico falla si el teléfono está vacío (visible en logs de test, no afecta producción) | Baja |

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
