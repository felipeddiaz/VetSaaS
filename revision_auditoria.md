# Auditoría de Seguridad y Concurrencia — VeterinariaSaaS

**Estado:** Pre-Beta | **Prioridad:** P0 (bloqueantes) → P1 (alta) → P2 (hardening)

---

## P0 — Beta-blockers (data corruption, leak o crash garantizado)

### Concurrencia / pérdida de datos

---

#### #1 — `get_or_create_invoice_for_medical_record` sin lock ni atomic

- **Ubicación:** `billing/services.py:246-281`
- **Problema:** La función no usa `@transaction.atomic` ni `select_for_update()`. Dos llamadas simultáneas a `_sync_invoice_item` generan una colisión en la relación OneToOne con `medical_record`.
- **Consecuencia:** `IntegrityError` → 500 sin capturar. La invoice no se crea y el usuario ve error en pantalla.
- **Repro:** 2 POST simultáneos a `/medical-records/<pk>/products/` y `/medical-records/<pk>/services/` sobre un MR sin invoice.
- **Fix:**
  ```python
  @transaction.atomic
  def get_or_create_invoice_for_medical_record(...):
      with transaction.atomic():
          MedicalRecord.objects.select_for_update().get(pk=mr.pk)
          # lookup y creación de invoice
  ```

---

#### #2 — `apply_stock_movement` confía en lock externo, `cancel_invoice` no lo provee

- **Ubicación:** `inventory/services.py:34-48` + `billing/services.py:140-157`
- **Problema:** `apply_stock_movement` asume que el caller ya tiene `select_for_update()` sobre la `Presentation`. `cancel_invoice` itera items y revierte stock sin lockear las presentations.
- **Consecuencia:** Race condition en stock. Dos cancels simultáneos pueden duplicar stock revertido o perder unidades.
- **Fix:** Mover el `select_for_update()` dentro de `apply_stock_movement` o bloquear presentations en `cancel_invoice` igual que `_confirm_locked_invoice`.

---

#### #3 — `MedicalRecordProduct.save()` decrementa stock antes de `super().save()`

- **Ubicación:** `inventory/models.py:151-186`
- **Problema:** El stock se decrementa con `apply_stock_movement()` **antes** de llamar a `super().save()`. Si el UNIQUE `(medical_record, presentation)` falla, el stock ya bajó.
- **Consecuencia:** Stock perdido. Solo `transaction.atomic()` externo lo salva. Admin/shell/migración sin atomic = corrupción garantizada.
- **Fix:** Llamar `super().save()` primero dentro del atomic, después `apply_stock_movement()`.

---

#### #4 — Lost update en `MedicalRecordProduct.quantity += quantity`

- **Ubicación:** `inventory/views.py:322-345`
- **Problema:** Lectura del MRP sin `select_for_update()`. Dos adds del mismo `(MR, presentation)` leen la misma cantidad base y pierden un incremento.
- **Consecuencia:** Cantidad subestimada en la factura y stock inconsistente.
- **Fix:**
  ```python
  with transaction.atomic():
      mrp = MedicalRecordProduct.objects.select_for_update().filter(...).first()
      if mrp:
          mrp.quantity += quantity
          mrp.save()
  ```

---

#### #5 — `_sync_invoice_item` sin lock sobre Invoice

- **Ubicación:** `medical_records/views.py:189-200` + `inventory/views.py:354-365`
- **Problema:** `get_or_create(invoice=, service=, ...)` racea con el UNIQUE de InvoiceItem.
- **Consecuencia:** `IntegrityError` → 500 sin handler. El item no se agrega a la factura.
- **Fix:** Lockear invoice antes del get_or_create:
  ```python
  with transaction.atomic():
      Invoice.objects.select_for_update().get(pk=invoice.pk)
      InvoiceItem.objects.get_or_create(...)
  ```

---

#### #6 — `InvoiceDetailView.update` TOCTOU

- **Ubicación:** `billing/views.py:120-127`
- **Problema:** Lee status sin lock. Entre el check y el PATCH, otra request puede confirmar la invoice.
- **Consecuencia:** PATCH sobrescribe invoice ya confirmada. Corrupción de estado.
- **Fix:** Re-fetch con `select_for_update()` antes del check:
  ```python
  invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
  if invoice.status != 'draft':
      return Response(..., status=400)
  ```

---

#### #7 — Walk-in dedup ignora pet

- **Ubicación:** `appointments/views.py:387-415`
- **Problema:** Filtro `created_at__gte=now-10s + status='in_progress'` sin filtrar `walk_in=True` ni `pet=pet`.
- **Consecuencia:** Recepcionista crea walk-in para mascota B en los 10s tras otra appointment moviéndose a in_progress → confunde pacientes.
- **Fix:** Agregar `walk_in=True, pet=pet` al filtro:
  ```python
  existing = Appointment.objects.filter(
      pet=pet,
      walk_in=True,
      status='in_progress',
      created_at__gte=now - timedelta(seconds=10)
  ).first()
  ```

---

### Cross-org / privilege escalation

---

#### #8 — `InvoiceSerializer` no valida tenant en pet/owner/appointment/medical_record

- **Ubicación:** `billing/serializers.py:140-181`
- **Problema:** Viola regla 2 de CLAUDE.md (validación de FKs con tenant). Defensa solo en `Invoice.clean()` que devuelve 500 (DRF no traduce `ValidationError`).
- **Consecuencia:** PATCH con `pet=<foreign_pk>` se persiste; `pet_name` luego se lee de otra org → leak de datos cross-tenant.
- **Fix:** Agregar 4 `validate_<fk>` con check de organización:
  ```python
  def validate_pet(self, pet):
      if pet and pet.organization != self.context['request'].user.organization:
          raise ValidationError('Acceso inválido.')
      return pet
  ```

---

#### #9 — `PrescriptionItemSerializer` / `WriteSerializer` no validan tenant en product

- **Ubicación:** `prescriptions/serializers.py:6-36, 106-128`
- **Problema:** POST `/prescriptions/` con `items: [{product: <orgB_product_pk>}]` persiste FK cross-org.
- **Consecuencia:** Leak en PDF — receta muestra producto de otra clínica.
- **Fix:** `validate_product` con check de organización.

---

#### #10 — `OrganizationViewSet` es ModelViewSet completo

- **Ubicación:** `organizations/views.py:8-14`
- **Problema:** ADMIN puede hacer POST `/api/organizations/` y crear tenants nuevos (signal seeds roles), y DELETE `/api/organizations/<own>/` que CASCADE borra todo (User org=CASCADE).
- **Consecuencia:** Creación accidental de orgs fantasma o borrado total de datos.
- **Fix:** Cambiar a `RetrieveUpdateAPIView`, quitar `organization.create` de `PERMISSION_CODES`.

---

#### #11 — CASCADE en FKs críticas — pérdida total irreversible

- **Ubicación:**
  - `users/models.py:14` `User.organization=CASCADE`
  - `patients/models.py:41` `Pet.owner=CASCADE`
  - `medical_records/models.py:20,126` `MR.pet=CASCADE`, `VaccineRecord.pet=CASCADE`
- **Problema:** Un DELETE accidental (admin Django, shell, futuro endpoint) borra historia clínica legalmente requerida.
- **Consecuencia:** Pérdida irreversible de datos legales (historias clínicas, vacunas, dueños).
- **Fix:** Cambiar todas a `PROTECT`; soft-delete only.

---

#### #12 — `_create_default_superuser` colisiona username

- **Ubicación:** `users/apps.py:14-44`
- **Problema:** Si clinic A tiene VET username `admin` y operator deploya con `DJANGO_SUPERUSER_USERNAME=admin`, el VET se vuelve superuser platform-wide.
- **Consecuencia:** Privilege escalation — un VET de una clínica obtiene acceso global a todas las orgs.
- **Fix:** Verificar `created=True`; nunca elevar usuario existente.

---

#### #13 — DRF sin `DEFAULT_PERMISSION_CLASSES`

- **Ubicación:** `config/settings.py:99-115`
- **Problema:** Default es `AllowAny`. Cualquier view nueva sin `permission_classes` explícito = open.
- **Consecuencia:** Endpoints nuevos expuestos públicamente sin autenticación.
- **Fix:**
  ```python
  'DEFAULT_PERMISSION_CLASSES': (
      'rest_framework.permissions.IsAuthenticated',
  ),
  ```

---

### Analytics / numbers wrong

---

#### #14 — `compute_daily_metrics` usa `Model.objects` (TenantManager filtra `is_active=True`)

- **Ubicación:** `analytics/services.py:117,138,164,186`
- **Problema:** Cualquier soft-delete futuro de invoice (void) hace desaparecer revenue del snapshot silenciosamente.
- **Consecuencia:** Revenue subestimado en dashboard.
- **Fix:** Usar `.all_objects.filter(organization=org, ...)` en todo analytics computation.

---

#### #15 — `org_timezone_at_snapshot` solo en INSERT

- **Ubicación:** `analytics/services.py:311`
- **Problema:** Rebuild usa TZ actual via `local_day_bounds_utc` pero deja el `_source` apuntando a TZ vieja. Org cambia TZ → todos los rebuilds re-bucketean con TZ nueva mientras el audit dice la vieja.
- **Consecuencia:** Métricas con timezone inconsistente.
- **Fix:** Refrescar en cada rebuild + incluir en `_diff_existing`.

---

#### #16 — Invoice no invalida cache de dashboard

- **Ubicación:** `dashboard/signals.py` solo registra `Appointment/MR/Presentation/StockMovement/MRP`
- **Problema:** `pay/confirm/cancel_invoice` no invalida `dash:summary:<org>`.
- **Consecuencia:** Owner cobra → ve revenue stale por TTL completo.
- **Fix:**
  ```python
  @receiver(post_save, sender=Invoice)
  def invalidate_invoice_cache(sender, instance, **kwargs):
      cache.delete_many([f'dash:summary:{instance.organization_id}'])
  ```

---

#### #17 — `tax_rate=0` en invoices creadas lazy

- **Ubicación:** `billing/services.py:271-280` + `billing/signals.py:37-50`
- **Problema:** Defaults no incluyen `tax_rate=org.tax_rate`. Toda invoice creada via signal / fallback nace con tax=0.
- **Consecuencia:** IVA perdido en facturas automáticas.
- **Fix:** Agregar `'tax_rate': org.tax_rate` a defaults.

---

### Frontend systemic

---

#### #18 — PK enteros en URLs frontend, dependientes de `ALLOW_LEGACY_ID_LOOKUP=True`

- **Ubicación:**
  - `frontend/src/api/{appointments,medicalRecords,prescriptions,inventory,billing}.js`
  - `petDetail.jsx:62`
  - `prescriptions.jsx:212,303,315,328`
  - `medicalRecords/index.jsx:197`
- **Problema:** CLAUDE.md exige flag OFF en beta. Día que se apague: 404 en confirmar/iniciar/cancelar cita, ver MR, editar receta.
- **Consecuencia:** App entera 404 al apagar flag.
- **Fix:** Cambiar todos call sites a `public_id` ANTES de apagar flag.

---

#### #19 — 401 interceptor sin retry de refresh

- **Ubicación:** `frontend/src/api/client.js:22-33`
- **Problema:** Cualquier 401 wipea tokens y redirige a `/login` antes que firme el refresh timer.
- **Consecuencia:** VET mid-consulta pierde draft.
- **Fix:** En 401 intentar refresh + replay; logout solo si refresh falla.

---

#### #20 — Stepper consulta fetch('/api/billing/services/') directo

- **Ubicación:** `medicalRecords/ConsultationStepperV2.jsx:207-215`
- **Problema:** Bypasea `client.js`, depende de Vite proxy. En prod (frontend distinto origin) → 404.
- **Consecuencia:** Dropdown "Servicios" vacío en cada consulta.
- **Fix:** Usar `getServices()` de `billing.js`.

---

#### #21 — `setActiveRecordId` no declarado

- **Ubicación:** `medicalRecords/index.jsx:384`
- **Problema:** `ReferenceError` crashea timeline al click "Editar".
- **Consecuencia:** Crash en producción al editar historial.
- **Fix:** Borrar línea o declarar state.

---

#### #22 — Stepper envía `availableServices.find(s => s.id === serviceLine.service)` mal

- **Ubicación:** `ConsultationStepperV2.jsx:464`
- **Problema:** Compara contra objeto, no id → undefined → "Agregar Servicio" silent no-op.
- **Consecuencia:** Servicios no se agregan silenciosamente.
- **Fix:** Verificar shape; comparar IDs.

---

#### #23 — SIMPLE_JWT sin rotation/blacklist

- **Ubicación:** `config/settings.py:117-120`
- **Problema:** Refresh token robado vale 7 días sin revocación.
- **Consecuencia:** Session hijacking por 7 días.
- **Fix:**
  ```python
  'ROTATE_REFRESH_TOKENS': True,
  'BLACKLIST_AFTER_ROTATION': True,
  ```
  Instalar `token_blacklist` app, throttle en `/api/token/refresh/`.

---

#### #24 — Sin pagination global; sin length cap en `?search=`

- **Ubicación:** `config/settings.py:99`
- **Problema:** Endpoints retornan unbounded; tenant con 50k invoices crashea. `name__icontains` con string 10MB → CPU/RAM DoS.
- **Consecuencia:** DoS por query grande.
- **Fix:** `PAGE_SIZE=50` global + cap `search[:64]` en todos los list endpoints.

---

#### #25 — `appointments/views.py:210` viola ADR-10

- **Ubicación:** `appointments/views.py:210`
- **Problema:** `Appointment.objects.select_related('pet').for_organization(...)` — `for_organization` no está en QuerySet → `AttributeError` en runtime cada `assign_patient`.
- **Consecuencia:** Crash en asignación de pacientes.
- **Fix:** Reordenar a `for_organization(...).select_related('pet')`.

---

## P1 — Bugs de severity alta, no necesariamente bloqueante v1

| # | Problema | Ubicación | Fix |
|---|----------|-----------|-----|
| 26 | `UserRole` no scopeado por org en `_get_cached_permissions` | `core/permissions.py:216` | `.filter(role__organization=user.organization)` |
| 27 | `create_draft_invoice_on_done` re-fires en cada save sin `update_fields` | `billing/signals.py:9-59` | Short-circuit si `Invoice.objects.filter(appointment=instance).exists()` |
| 28 | `MedicalRecord.close` escribe `closed_at` directo en view, no en service | `medical_records/views.py:418-425` | Crear `medical_records/services.py::close_medical_record` |
| 29 | `pay/confirm/cancel_invoice` re-fetch sin `for_organization` | `billing/services.py:182` | `.for_organization(invoice.organization).select_for_update().get(pk=pk)` |
| 30 | `apply_snapshot` no propaga `now` desde mgmt command | `analytics/services.py:251` + `build_daily_metrics.py:157` | Capturar `now=timezone.now()` en `Command.handle` y threadear |
| 31 | `apply_snapshot` no audita no-change runs | `analytics/services.py:343` | Emit audit row con `diff={}` |
| 32 | Walk-in cancel sin reason en UI | `frontend/src/api/appointments.js:20-22` | Prompt + enviar `cancellation_reason` |
| 33 | `InvoiceItem.recalculate_totals` bypasea `updated_at` | `billing/models.py:147-156` | Incluir `updated_at=timezone.now()` en update |
| 34 | `InvoiceAuditLog` no es `OrganizationalModel` | `billing/models.py:299` | Agregar FK + index + backfill |
| 35 | Stock alerts hardcap 5 con texto "+más" falso | `dashboard/views.py:635-644` ↔ `StockAlerts.jsx:30-50` | Backend retornar count total separado |
| 36 | `dashboard/views.py:35,480,579` checkean `user.role` directo | `dashboard/views.py` | `make_permission('dashboard.financial.view')` |
| 37 | `create_with_patient` no sanitiza `owner_name/pet_name` | `appointments/views.py:258-331, 311, 316` | `sanitize_text` + `_validate_name` antes de persistir |
| 38 | `StaffDeactivateView` con `<int:pk>` + sin throttle | `config/urls.py:77` | User → `PublicIdMixin`, URL → `<str:pk>`, throttle scoped |
| 39 | `/me/` retorna `organization.id` PK crudo | `users/views.py:31` | Organization → `PublicIdMixin` |
| 40 | `CreateEmployeeSerializer` acepta `organization_id` writable | `users/serializers.py:25-41` | Borrar field; siempre derivar de `request.user.organization` |
| 41 | Permission UI vs server drift (10+ pages) | `inventory.jsx:154, staff.jsx:36,140,184, appointments.jsx:996-997` | Hook `can("perm.code")` consumiendo `/me/permissions/` |
| 42 | `MedicalRecordProductDeleteView.perform_destroy` sin lock sobre `InvoiceItem` | `inventory/views.py:384-392` | `select_for_update()` en `_sync_invoice_item_delete` |

---

## P2 — Hygiene / hardening (post-beta)

| # | Problema | Ubicación |
|---|----------|-----------|
| 43 | Service modelo: `unique_together=('product','name')` no incluye org | DB Finding 20 |
| 44 | `_get_last_weight(pet)` sin `for_organization()` | DB Finding 12 |
| 45 | `InvoiceAdmin.readonly_fields` lista `paid_at` pero omite `confirmed_at/cancelled_at/*_source` | DB Finding 13 |
| 46 | `User.username` global UNIQUE — dos clínicas no pueden compartir username "admin" | DB Finding 21 |
| 47 | Currency client-side `parseFloat` drift en `billing.jsx:517` (solo display, backend recomputa) | Frontend |
| 48 | `auth/authContext.jsx:78-117` cae a stale `storedUser` sin re-fetch on focus | Frontend |
| 49 | Date formatting frontend sin TZ del org → boundary midnight UTC ≠ local | Frontend |
| 50 | `LOGIN_FAILED` log trustea `X-Forwarded-For` raw | API Finding 10 |

---

## Plan recomendado pre-beta (1 sprint)

### Checklist por día

| Día | Tareas | Issues | Status |
|:---:|--------|:------:|:------:|
| **1-2** | Concurrencia core | #1, #2, #3, #4, #5, #6, #7 | ☐ |
| **3** | Tenant validators | #8, #9 | ☐ |
| **4** | Cascade + lockdown | #10, #11, #12, #13 | ☐ |
| **5** | Analytics correctness | #14, #15, #16, #17 | ☐ |
| **6** | Frontend systemic | #18 (todos los call sites), #19, #20, #21, #22 | ☐ |
| **7** | Perimeter | #23, #24, #25 | ☐ |

**Total nuevo work:** ~7 dev-days. P1+P2 quedan para semana de hardening 2.

---

## Notas operacionales

- **Razón triángulo billing/MR/inventory tiene 9 P0:** ADR-01 dijo "no refactor en v1, fixes quirúrgicos" — correcto, pero el chequeo de invariantes concurrentes nunca se hizo. Tests existentes (`test_invoice_state_machine`, `test_anchor_completeness`) cubren máquina de estados secuencial, **no concurrency**.

- **Hay carpeta `backend/` con ?? (untracked) en git status** — verificar qué quedó sin commit, posible work-in-progress crítico (`test_invoice_pdf.py` también untracked).

- **Frontend depende de flag legacy:** Hasta migrar todo a `public_id`, **no apagues `ALLOW_LEGACY_ID_LOOKUP`**. Si lo apagas hoy → app entera 404.

---

## Resumen de criticidad

| Prioridad | Cantidad | Estado | Acción requerida |
|-----------|----------|--------|------------------|
| **P0** | 25 | 🔴 Bloqueante | Fix antes de beta |
| **P1** | 17 | 🟠 Alta severidad | Fix en sprint 2 |
| **P2** | 8 | 🟡 Hardening | Post-beta |

**Total issues:** 50
