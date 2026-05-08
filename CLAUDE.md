# VeterinariaSaaS — Reglas para Claude Code

## Stack
- Backend: Django 6 + DRF + SimpleJWT — deploy en Railway (branch `main`)
- Frontend: React 19 + Vite (JavaScript, no TypeScript)
- DB: PostgreSQL multitenant
- Branch activa de desarrollo: `develop`

## Setup inicial (DB vacía)

### 1. Migraciones y permisos
```bash
python manage.py migrate
python manage.py seed_permissions   # crea Permission + Roles por org (idempotente)
```

### 2. Primera organización + ADMIN
No hay endpoint de registro público. El primer admin se crea vía Django admin:
1. `python manage.py createsuperuser` → usuario ADMIN_SAAS de la plataforma
2. Ir a `/admin/` → crear **Organization** (`name`, `timezone`, `tax_rate`)
3. Crear **User** vinculado a esa org con `role=ADMIN`
4. `python manage.py seed_permissions` nuevamente → genera Roles RBAC para la org

### 3. El ADMIN crea staff vía API
```
POST /api/staff/create/
Authorization: Bearer <token ADMIN>

{
  "username": "dra.garcia",
  "email": "garcia@clinica.com",
  "password": "Clave1234!",
  "first_name": "Laura",
  "last_name": "García",
  "role": "VET",       # VET | ASSISTANT | ADMIN
  "specialty": "Cirugía"
}
```
`StaffCreateView` asigna `UserRole` RBAC automáticamente al crear el usuario.

### Mínimo requerido por organización
| Campo | Obligatorio | Notas |
|-------|-------------|-------|
| `Organization.name` | ✅ | |
| `Organization.timezone` | ✅ | default `America/Mexico_City` |
| `Organization.tax_rate` | ✅ | `0.0000` sin IVA, `0.1600` para 16% |
| Un usuario con `role=ADMIN` | ✅ | |
| `seed_permissions` ejecutado | ✅ | Sin esto todos los endpoints retornan 403 |
| `OrganizationSettings` | ❌ | Se crea automáticamente con defaults |

---

## Reglas de seguridad (no negociables)

### Sanitización de inputs
Todos los campos de texto libre pasan por `sanitize_text()` de `apps/core/sanitize.py`:
```python
from apps.core.sanitize import sanitize_text
data['diagnosis'] = sanitize_text(data.get('diagnosis') or '', max_length=400)
```
Siempre usar `value or ''` — nunca pasar `None` directamente a `sanitize_text`.

Límites por campo:
- `diagnosis`, `treatment` → `max_length=400`
- `notes` → `max_length=5000`
- `vaccine_name`, `reason` → `max_length=255`
- `motivo`, `cancellation_reason`, `batch_number` → `max_length=100`

FBVs que reciben campos de texto libre deben sanitizar directamente (no delegan al serializer):
```python
# update_status → cancellation_reason se sanitiza en la FBV, no en AppointmentSerializer
cancellation_reason = sanitize_text(request.data.get('cancellation_reason') or '', max_length=100)
```

### Aislamiento multitenant
Todas las queries de negocio DEBEN usar `for_organization()`:
```python
obj = Model.objects.for_organization(request.user.organization)
```
Nunca usar `Model.objects.filter(pk=pk)` sin filtro de organización.

### Validación de FKs en serializers
Todo serializer que reciba una FK de otro modelo debe validar el tenant:
```python
def validate_pet(self, pet):
    if pet and pet.organization != self.context['request'].user.organization:
        raise ValidationError('Acceso inválido.')
    return pet
```
Notar el `if pet and ...` — los campos opcionales pueden llegar como `None`.
Aplica en: `AppointmentSerializer`, `MedicalRecordSerializer`, `InvoiceSerializer`,
`PrescriptionSerializer`, `VaccineRecordSerializer`, `MedicalRecordProductSerializer`.

Validaciones de stock en serializers sin lock son **no-autoritativas** — son pre-checks de UX.
La validación autoritativa siempre va en la view con `select_for_update()`. No duplicar la
misma validación con lock y sin lock para el mismo campo numérico (produce doble error en race).

### Operaciones críticas en transacciones
Toda operación que involucre stock + factura debe estar en `transaction.atomic()`.
Reglas de concurrencia:
- `select_for_update()` requiere `.first()` / `.exists()` / iteración para que el lock llegue a la DB — un queryset sin evaluar no genera SQL
- Envolver TODA la cadena dentro del `with transaction.atomic()`, incluyendo el `save()` que internamente llama otros métodos
- `@transaction.atomic` en services recibe objetos ya cargados — siempre re-fetch con lock al inicio del service

```python
with transaction.atomic():
    locked = Model.objects.select_for_update().filter(...).first()  # evalúa el lock
    # operación dependiente del lock
```

**Patrón correcto para services que reciben objeto pre-cargado:**
```python
@transaction.atomic
def confirm_invoice(invoice, user):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)  # re-fetch con lock
    if invoice.status != 'draft':
        raise ValidationError(...)
```

**bulk_create siempre debe asignar `organization` explícitamente:**
`bulk_create` bypasea `save()` y el TenantManager — la organización nunca se asigna automáticamente.
```python
# INCORRECTO — organization queda NULL
presentations.append(Presentation(product=product, **item))
# CORRECTO
presentations.append(Presentation(product=product, organization=organization, **item))
```

**Override de `delete()` en modelos que mueven stock:**
Envolver en `atomic()` + lock previo, incluyendo el `super().delete()`. Sin esto, el cascade
puede revertir stock en múltiples llamadas no atómicas.
```python
def delete(self, *args, **kwargs):
    with transaction.atomic():
        fresh = Presentation.objects.select_for_update().get(pk=self.presentation_id)
        apply_stock_movement(presentation=fresh, movement_type='in', ...)
        super().delete(*args, **kwargs)
```

**Lock en walk-in / operaciones de creación idempotente:**
Lockear una fila que SIEMPRE existe (ej. el User veterinario), no un queryset que puede estar vacío.
Un queryset vacío no genera ningún lock en la DB.
```python
with transaction.atomic():
    User.objects.select_for_update().get(pk=vet.pk)  # fila estable, siempre existe
    existing = Appointment.objects.filter(...).first()
```

### IDs en URLs
Los modelos expuestos públicamente usan `public_id` (UUID) en URLs, NO el PK entero.
Modelos con `public_id`: `Pet`, `Owner`, `Appointment`, `MedicalRecord`, `Invoice`, `Prescription`, `Product`, `Presentation`, `Service`.
Modelos SIN `public_id` (internos): `InvoiceItem`, `StockMovement`, `MedicalRecordProduct`, `MedicalRecordService`, `InvoiceAuditLog`, `Permission`, `Role`, `UserRole`.

Cuando un ViewSet tiene sub-recursos anidados (ej. `/invoices/<invoice_pk>/items/`), el `invoice_pk` debe ser `<str:>` y resolverse con `resolve_public_id()`, no con `get_object_or_404(..., pk=...)`.

**Regla**: todos los parámetros de URL que referencian modelos con `public_id` deben ser `<str:>`, nunca `<int:>`. Usar `<int:>` expone el PK secuencial interno y rompe la resolución UUID.

### Máquina de estados — Invoice
Los estados válidos son: `draft → confirmed → paid` y `draft/confirmed → cancelled`.
- Solo facturas en `draft` pueden editarse (PATCH sobre cualquier otro estado → 400)
- `confirm_invoice`: requiere al menos un ítem activo
- `pay_invoice`: requiere estado `confirmed` + `payment_method`
- El `total` siempre se recalcula en backend — `total`, `subtotal`, `tax_amount`, `tax_rate` son `read_only` en el serializer

### Manejo de errores
El exception handler global `apps/core/exceptions.py` mapea todos los errores a mensajes en español.
Nunca exponer mensajes del ORM directamente al frontend.
Los errores 500 incluyen `request_id` para correlación en Railway logs.
`IntegrityError` de la DB NO está capturado por el handler — validar duplicados en el serializer antes de llegar a la DB.

### Checklist obligatorio por serializer

Todo serializer nuevo debe cumplir estas reglas antes de merge:

- `CharField` / `TextField` libre → `sanitize_text()` con `max_length` explícito
- Campo obligatorio → validar no vacío **después** de `sanitize_text` (puede colapsar HTML a `""`)
- `DecimalField` de precio → `validate > 0`
- `DecimalField` de stock/cantidad → `validate >= 0` (o `> 0` según dominio)
- FK de otro módulo → validación de tenant (`if obj.organization != request.user.organization`)

```python
# Patrón correcto para campo de texto obligatorio:
def validate_name(self, value):
    clean = sanitize_text(value or '', max_length=255)
    if not clean.strip():
        raise serializers.ValidationError("El campo es obligatorio.")
    return clean
```

---

## RBAC
- Todos los endpoints usan `HybridPermission` o `make_permission()`
- Nunca usar `RolePermission` directamente en views
- Nunca verificar `user.role == 'ADMIN'` directamente en views ni permission classes locales
- Gate Fase 4: `RBAC_FALLBACK_ALLOWED` ausente en logs por 7 días → listo para cortar `User.role`
- Al agregar nuevos códigos a `PERMISSION_CODES`, ejecutar `seed_permissions` en el siguiente deploy para persistirlos en DB
- Naming: billing usa `'cancelled'` (doble L), appointments usa `'canceled'` (una L) — no mezclar al filtrar por status entre módulos
- Nuevos códigos (2026-05-04): `medicalrecord.vitals.create`, `medicalrecord.vitals.list`, `medicalrecord.summary.retrieve` — VET recibe los 3, ASSISTANT solo `vitals.list` + `summary.retrieve`

---

## Arquitectura de módulos

### Mapa de dependencias

| Módulo | Acoplamiento | Dependencias salientes |
|--------|-------------|----------------------|
| `core` | Estable | 0 — infraestructura pura |
| `patients` | Estable | core |
| `prescriptions` | Estable | core (`sanitize_text`, string FKs) |
| `users` | Estable | core, organizations |
| `dashboard` | Estable | core (late imports, solo lectura) |
| `organizations` | Bajo | core, patients (signal bootstrap, ocurre 1 vez) |
| `appointments` | Moderado | core, organizations, users, patients, medical_records (late) |
| `inventory` | Moderado-alto | core, medical_records, prescriptions |
| `medical_records` | Alto | core, users, patients, appointments, inventory, prescriptions, billing. Incluye `VitalSigns` (append-only, historial de signos vitales). |
| `billing` | Alto | core, organizations, users, patients, appointments, medical_records, inventory |

**Triángulo de alto riesgo**: `medical_records ↔ billing ↔ inventory`. Cualquier feature que expanda la consulta clínica (labs, vitales) o el ciclo de facturación (descuentos, reembolsos) aterriza aquí.

### Flujo de sincronización Invoice (3 puntos, no duplicados)

1. **`billing.signals.create_draft_invoice_on_done`** — crea la Invoice `draft` cuando una cita pasa a `'done'` o cuando se crea un `MedicalRecord` sin cita. Controlado por toggle `SETTING_AUTO_INVOICE_ON_DONE`.
2. **`medical_records.views._sync_invoice_item`** — crea/actualiza `InvoiceItem` de servicio al agregar un `MedicalRecordService`.
3. **`inventory.views._sync_invoice_item`** — crea/actualiza `InvoiceItem` de producto al agregar un `MedicalRecordProduct`.

El punto 1 debe ejecutarse antes que 2 y 3. Si la Invoice aún no existe, `get_or_create_invoice_for_medical_record()` (`billing/services.py`) la crea on-demand.

### Acoplamiento oculto (no visible en imports)

| Contrato implícito | Riesgo si falla |
|-------------------|-----------------|
| `organizations.signals` garantiza `Owner` genérico por org con teléfono válido → `billing.services` lo accede sin guard | `create_invoice` walk-in rompe |
| `MedicalRecord.Status.CLOSED` es gate de autorización en `inventory.views`, `medical_records.policies` y `medical_records.views` | Los 3 usan la constante enum — riesgo bajo; un cambio de nombre falla en import, no silenciosamente |
| Toggles de `OrganizationSettings` definidos como constantes en `organizations/utils.py` | Siempre importar `SETTING_AUTO_MEDICAL_RECORD` / `SETTING_AUTO_INVOICE_ON_DONE` — nunca string literals |
| `MedicalRecord.ConsultationType.SURGERY` es el gate de la validación de `treatment` obligatorio en `close_medical_record` | Si se renombra el choice, la validación deja de aplicarse silenciosamente |
| `_get_last_weight(pet)` busca en `VitalSigns` primero y en `MedicalRecord` segundo — ambas fuentes deben coexistir hasta migración v2 | Si se elimina `MedicalRecord.weight` antes de migrar, el fallback queda huérfano |

### Decisiones de arquitectura

**ADR-01 — No refactor de módulos en v1 (2026-05-03)**
El acoplamiento moderado-alto concentrado en el triángulo es sostenible para v1. Los flujos críticos, las transacciones y los locks están correctamente implementados. Mover modelos o rediseñar flujos en este punto introduce más riesgo que el que elimina. Los fixes se aplican quirúrgicamente.

**ADR-02 — `_get_cached_permissions` como función standalone en core (2026-05-03)**
`HybridPermission._get_db_permissions()` y `medical_records/policies._permission_codes()` duplicaban la misma consulta DB y clave de cache (`user._cached_permissions`). Se extrajo a `_get_cached_permissions(user)` module-level en `core/permissions.py`. Ambas delegan a ella. Si la lógica de cache evoluciona, lo hace en un único lugar.

**ADR-03 — Constantes para claves de OrganizationSettings (2026-05-03)**
Los string literals `'auto_create_medical_record'` y `'auto_create_invoice_on_done'` estaban dispersos en 3 archivos (`organizations/utils.py`, `appointments/views.py`, `billing/signals.py`). Un typo causa que el toggle se ignore silenciosamente. Constantes: `SETTING_AUTO_MEDICAL_RECORD` y `SETTING_AUTO_INVOICE_ON_DONE` en `organizations/utils.py`.

**ADR-04 — Audit log completo en pay_invoice (2026-05-03)**
`confirm_invoice` y `cancel_invoice` escriben a `InvoiceAuditLog` vía `_log_status_change()`. `pay_invoice` no lo hacía. Se añadió capturando `previous_status = invoice.status` antes de la mutación — no hardcodeado `'confirmed'` — para ser correcto frente a flujos futuros donde el estado previo pueda variar.

**ADR-05 — Sanitización en serializers de prescripciones (2026-05-03)**
`PrescriptionItemSerializer.validate_dose` verificaba vacío pero no sanitizaba. El bug silencioso: `sanitize_text("<script>alert(1)</script>")` colapsa a `""`, que pasaba la validación anterior y devolvía 200 con string vacío en DB. Patrón correcto: sanitizar primero, luego verificar vacío. Se aplicó en `dose` (obligatorio), `duration`, `instructions` (opcionales) y `notes` de `PrescriptionSerializer`. Mismos validators replicados en `PrescriptionItemWriteSerializer`.

**ADR-06 — Validación robusta en ServiceSerializer (2026-05-03)**
`ServiceSerializer.validate_name` solo hacía `.strip().title()` sin sanitización ni regex. `base_price` aceptaba 0 y negativos sin validación. Se reemplazó con `sanitize_text()` + `SERVICE_NAME_REGEX` (equivalente al de inventory para consistencia entre módulos — caracteres explícitos, no `re.UNICODE`). Se agregaron `validate_base_price` (`> 0`, alineado con `Presentation.sale_price__gt=0`) y `validate_description`. Se añadió `CheckConstraint(base_price__gt=0, name='service_base_price_positive')` en `Service.Meta` como defensa final a nivel DB (migración `0014`).

**ADR-07 — Recetas como visor clínico, no punto de creación (2026-05-03)**
La página `/prescriptions` tenía botones "Nueva Receta" y "Editar" que contradecían el flujo clínico: las recetas son documentos que emergen de una consulta, no se crean de forma standalone. Se eliminaron ambos botones. La página es ahora un visor histórico (listado + PDF). Se agregó banner informativo con link al historial clínico. El flujo legítimo desde historial (URL params `?medical_record=X&pet=Y`) se preserva. Se agregó "Recetas" al sidebar (`Icon.Pill`) después de "Historial Clínico".

**ADR-08 — Dos gates de autorización en medical_records (2026-05-04)**
`assert_can_modify_charges` es para operaciones de facturación (productos/servicios): valida org + status + ownership del VET. `assert_can_modify_medical_record` es para datos clínicos puros (vitales): valida org + status. Semánticamente distintos — no mezclar. Los vitales no son cargos de factura; no deben pasar por el gate de billing.

**ADR-09 — `HybridPermission._method_to_action` infiere `retrieve` cuando hay `pk` en kwargs (2026-05-04)**
Para vistas de lista anidadas bajo una URL con `<pk>` (ej. `/medical-records/<pk>/vitals/`), `HybridPermission` ve el `pk` del padre y mapea GET a `retrieve` en lugar de `list`. Solución: declarar `required_permission` explícitamente en `initial()` según el método HTTP. No confiar en la inferencia automática para sub-recursos anidados.

**ADR-10 — `for_organization()` siempre primero en la cadena de queryset (2026-05-04)**
`select_related()` y `prefetch_related()` devuelven un `QuerySet` estándar de Django que no tiene el método `for_organization()` del `TenantManager`. La cadena correcta siempre es `Model.objects.for_organization(org).select_related(...).prefetch_related(...)`. Orden inverso genera `AttributeError` en runtime.

---

## Tests
Suite completa: 87 tests en `backend/apps/`
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
El `test_e2e.py` en la raíz de `backend/` requiere servidor corriendo — no se incluye en la suite normal.

---

## Variables de entorno clave (Railway)
- `ENVIRONMENT=production` — activa fail-fast de CORS y otros guards
- `CORS_ALLOWED_ORIGINS=https://tu-frontend.railway.app`
- `SECURE_SSL_REDIRECT=True`
- `SECURE_HSTS_SECONDS=31536000`
- `ALLOW_LEGACY_ID_LOOKUP=False` — desactivar cuando frontend use `public_id`
- `SENTRY_DSN` — error tracking
