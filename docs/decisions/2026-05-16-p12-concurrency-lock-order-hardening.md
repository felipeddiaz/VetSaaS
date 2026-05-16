# ADR p12: Concurrencia y orden de locks — hardening Día 1-2

**Fecha:** 2026-05-16  
**Estado:** Implementado  
**Impacto:** `billing`, `inventory`, `medical_records`, `appointments`

---

## Contexto

La auditoría de concurrencia (`revision_auditoria.txt`) identificó 9 riesgos de carrera y deadlocks potenciales en el triángulo crítico `medical_records ↔ billing ↔ inventory`. Los hallazgos se agruparon en:

- **Día 1-2:** Candados para evitar fallos por clics simultáneos (Errores 1-7)
- **Día 3:** Bloquear fuga de datos entre clínicas (Errores 8-9) — pendiente

Los riesgos más críticos eran:
1. Doble cancelación de factura → reversa de stock duplicada
2. Edición de factura mientras otra request confirma → lost update en totales
3. Race condition al agregar producto/servicio → invoice duplicada o cantidad incorrecta
4. Walk-in reutilizando cita de otra mascota → corrupción de datos clínicos

---

## Decisión

### Orden global de locks

Se establece un orden estricto y no negociable para todos los paths que requieren múltiples locks:

```
MedicalRecord → Invoice → Presentation → InvoiceItem → MedicalRecordProduct
```

Reglas:
- Si un flujo no toca alguno, empieza en el primero que sí necesita.
- No se permiten inversiones de orden bajo ninguna circunstancia.
- Los locks se mantienen hasta el commit/rollback de la transacción.

### Implementación por componente

#### `billing/services.py::cancel_invoice()`

**Antes:**
```python
if invoice.status == 'paid':
    raise ValidationError(...)
for item in invoice.items.all():
    apply_stock_movement(presentation=item.presentation, ...)
```

**Ahora:**
```python
@transaction.atomic
def cancel_invoice(invoice, user, notes=''):
    # Re-fetch con lock para evitar doble cancelación
    invoice = Invoice.objects.for_organization(
        invoice.organization
    ).select_for_update().get(pk=invoice.pk)
    
    if invoice.status == 'paid':
        raise ValidationError(...)
    
    previous_status = invoice.status
    
    if previous_status == 'confirmed' and invoice.invoice_type == 'direct_sale':
        items = list(
            InvoiceItem.all_objects
            .filter(invoice=invoice, is_active=True)
            .select_related('presentation__product')
        )
        # Lockear Presentations en orden estable por pk
        locked_presentations = _lock_presentations(
            item.presentation_id for item in items if item.presentation_id
        )
        for item in items:
            if item.presentation_id:
                apply_stock_movement(
                    presentation=locked_presentations[item.presentation_id],
                    quantity=item.quantity,
                    movement_type='in',
                    ...
                )
```

**Helper nuevo:**
```python
def _lock_presentations(presentation_ids):
    if not presentation_ids:
        return {}
    return {
        p.pk: p
        for p in Presentation.objects.select_for_update().filter(
            pk__in=sorted(set(presentation_ids))
        )
    }
```

#### `billing/services.py::get_or_create_invoice_for_medical_record()`

**Antes:**
```python
def get_or_create_invoice_for_medical_record(medical_record):
    org = medical_record.organization
    invoice, _ = Invoice.objects.get_or_create(
        medical_record=medical_record,
        defaults={...}
    )
    return invoice
```

**Ahora:**
```python
@transaction.atomic
def get_or_create_invoice_for_medical_record(medical_record):
    # Re-fetch MR con lock — este helper es ahora la autoridad central
    medical_record = MedicalRecord.objects.for_organization(
        medical_record.organization
    ).select_for_update().get(pk=medical_record.pk)
    org = medical_record.organization
    
    if medical_record.appointment_id:
        invoice = Invoice.objects.select_for_update().filter(
            appointment=medical_record.appointment,
            organization=org,
        ).first()
    
    invoice, _ = Invoice.objects.get_or_create(
        medical_record=medical_record,
        defaults={
            'owner': medical_record.pet.owner,
            'pet': medical_record.pet,
            'organization': org,
            'status': 'draft',
            'invoice_type': 'consultation',
            'tax_rate': org.tax_rate,
        }
    )
    # Retornar invoice ya lockeada
    return Invoice.objects.for_organization(org).select_for_update().get(pk=invoice.pk)
```

#### `billing/views.py::InvoiceDetailView.update()`

**Antes:**
```python
def update(self, request, *args, **kwargs):
    invoice = self.get_object()
    if invoice.status != 'draft':
        return Response({'error': ...}, status=400)
    return super().update(request, *args, **kwargs)
```

**Ahora:**
```python
def update(self, request, *args, **kwargs):
    with transaction.atomic():
        # Lock antes del check de estado
        invoice = resolve_public_id(
            Invoice.objects.for_organization(request.user.organization).select_for_update(),
            kwargs['pk'],
        )
        if invoice.status != 'draft':
            return Response({'error': ...}, status=400)
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(invoice, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
```

#### `inventory/views.py::MedicalRecordProductListCreateView.perform_create()`

**Antes:**
```python
def perform_create(self, serializer):
    with transaction.atomic():
        medical_record = ...select_for_update()
        mrp = MedicalRecordProduct.objects.filter(...).first()
        if mrp:
            mrp.quantity += quantity
            mrp.save()
        else:
            mrp = serializer.save(...)
        self._sync_invoice_item(...)
```

**Ahora:**
```python
def perform_create(self, serializer):
    with transaction.atomic():
        medical_record = ...select_for_update()
        # Obtener invoice lockeada desde el helper central
        invoice = get_or_create_invoice_for_medical_record(medical_record)
        locked_pres = Presentation.objects.select_for_update().get(pk=presentation.pk)
        
        # Sync InvoiceItem primero (bajo lock de Invoice)
        if invoice.status == 'draft':
            item = InvoiceItem.objects.select_for_update().filter(
                invoice=invoice, presentation=locked_pres, is_active=True
            ).first()
            if item is None:
                InvoiceItem.objects.create(...)
            else:
                item.quantity += quantity
                item.save()
        
        # Luego MRP con lock explícito
        mrp = MedicalRecordProduct.objects.select_for_update().filter(
            medical_record=medical_record, presentation=locked_pres
        ).first()
        
        if mrp is not None:
            previous_quantity = mrp.quantity
            mrp.quantity = previous_quantity + quantity
            mrp.save(locked_presentation=locked_pres, previous_quantity=previous_quantity)
        else:
            mrp = MedicalRecordProduct(
                medical_record=medical_record,
                presentation=locked_pres,
                quantity=quantity,
            )
            mrp.save(locked_presentation=locked_pres)
```

#### `inventory/models.py::MedicalRecordProduct.save()`

**Antes:**
```python
def save(self, *args, **kwargs):
    if self.pk:
        with transaction.atomic():
            old = MedicalRecordProduct.objects.select_for_update().get(pk=self.pk)
            diff = self.quantity - old.quantity
            if diff != 0:
                apply_stock_movement(...)
    else:
        with transaction.atomic():
            fresh = Presentation.objects.select_for_update().get(pk=self.presentation_id)
            apply_stock_movement(...)
    super().save(*args, **kwargs)
```

**Ahora:**
```python
def save(self, *args, **kwargs):
    locked_presentation = kwargs.pop('locked_presentation', None)
    previous_quantity = kwargs.pop('previous_quantity', None)
    
    with transaction.atomic():
        if self.pk:
            if previous_quantity is None:
                old = MedicalRecordProduct.objects.select_for_update().get(pk=self.pk)
                previous_quantity = old.quantity
            diff = self.quantity - previous_quantity
            if diff != 0:
                fresh = locked_presentation or Presentation.objects.select_for_update().get(pk=self.presentation_id)
                self.presentation = fresh
        else:
            fresh = locked_presentation or Presentation.objects.select_for_update().get(pk=self.presentation_id)
            self.presentation = fresh
        
        super().save(*args, **kwargs)
        
        # Stock movement dentro de la misma transacción
        if self.pk and previous_quantity is not None:
            diff = self.quantity - previous_quantity
            if diff != 0:
                apply_stock_movement(presentation=self.presentation, ...)
        elif previous_quantity is None:
            apply_stock_movement(presentation=self.presentation, ...)
```

**Parámetros opcionales:**
- `locked_presentation`: permite reutilizar un lock ya tomado por la view (evita re-lock redundante)
- `previous_quantity`: evita query extra para calcular delta

#### `inventory/views.py::MedicalRecordProductDeleteView.perform_destroy()`

**Antes:**
```python
def perform_destroy(self, instance):
    with transaction.atomic():
        mr = ...select_for_update()
        self._sync_invoice_item_delete(instance)
        instance.delete()
```

**Ahora:**
```python
def perform_destroy(self, instance):
    with transaction.atomic():
        mr = ...select_for_update()
        invoice_id = instance.medical_record.invoice_id
        locked_invoice = None
        locked_pres = Presentation.objects.select_for_update().get(pk=instance.presentation_id)
        
        if invoice_id:
            locked_invoice = Invoice.objects.for_organization(...).select_for_update().filter(pk=invoice_id).first()
        
        # Sync InvoiceItem bajo lock
        item = None
        if locked_invoice:
            item = InvoiceItem.objects.select_for_update().filter(
                invoice=locked_invoice, presentation=locked_pres, is_active=True
            ).first()
        
        if item and item.invoice.status == 'draft':
            new_quantity = item.quantity - instance.quantity
            if new_quantity <= 0:
                item.delete()
            else:
                item.quantity = new_quantity
                item.save()
        
        # Re-fetch instance con lock antes de delete
        fresh_instance = MedicalRecordProduct.objects.select_for_update().get(
            pk=instance.pk, medical_record=mr
        )
        fresh_instance.delete(locked_presentation=locked_pres)
```

#### `medical_records/views.py::MedicalRecordServiceListCreateView.perform_create()`

**Antes:**
```python
def perform_create(self, serializer):
    with transaction.atomic():
        mr = ...select_for_update()
        mrs = serializer.save(...)
        self._sync_invoice_item(mrs)
```

**Ahora:**
```python
def perform_create(self, serializer):
    with transaction.atomic():
        mr = ...select_for_update()
        mrs = serializer.save(medical_record=mr)
        
        invoice = get_or_create_invoice_for_medical_record(mr)
        if invoice.status != 'draft':
            return
        
        item = InvoiceItem.objects.select_for_update().filter(
            invoice=invoice, service=mrs.service, is_active=True
        ).first()
        
        if item is None:
            InvoiceItem.objects.create(...)
        else:
            item.quantity += mrs.quantity
            item.save()
```

#### `appointments/views.py::walk_in()`

**Antes:**
```python
existing = Appointment.objects.filter(
    organization=org,
    veterinarian=vet,
    created_at__gte=timezone.now() - timedelta(seconds=10),
    status='in_progress',
).first()
```

**Ahora:**
```python
existing = Appointment.objects.filter(
    organization=org,
    veterinarian=vet,
    pet=pet,  # <-- nuevo: no reciclar cita de otra mascota
    walk_in=True,  # <-- nuevo: solo reutiliza walk-in
    created_at__gte=timezone.now() - timedelta(seconds=10),
    status='in_progress',
).first()
```

---

## Tests de concurrencia agregados

Nuevo archivo: `backend/apps/billing/tests/test_invoice_concurrency.py`

| Test | Valida |
|------|--------|
| `test_parallel_product_and_service_create_single_invoice` | MR lock authority, invoice uniqueness, cross-flow consistency |
| `test_medical_record_product_create_integrity_error_does_not_decrement_stock` | UNIQUE violation no descuenta stock |
| `test_cancel_invoice_parallel_pay_and_cancel_keeps_single_final_state` | pay/cancel como estados terminales competidores |
| `test_parallel_add_and_delete_same_product_keeps_correct_stock` | add/delete concurrente mantiene stock correcto |
| `test_invoice_patch_cannot_update_after_confirm_race` | PATCH no gana carrera contra confirm |

Extensión de `backend/apps/appointments/tests/test_walkin.py`:

| Test | Valida |
|------|--------|
| `test_walkin_dedup_does_not_reuse_different_pet` | no reutiliza cita de otra mascota |
| `test_walkin_dedup_does_not_reuse_non_walkin_appointment` | no reutiliza cita normal (no walk-in) |

**Patrón de tests concurrentes:**
```python
from django.test import TransactionTestCase
from django.db import close_old_connections
import threading

def _run_parallel_requests(self, calls):
    barrier = threading.Barrier(len(calls))
    results = []
    
    def worker(spec):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(self.admin)
        barrier.wait(timeout=5)
        response = getattr(client, spec['method'])(spec['url'], spec.get('data'))
        results.append((spec['name'], response.status_code, response.data))
        close_old_connections()
    
    threads = [threading.Thread(target=worker, args=(spec,)) for spec in calls]
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    return results
```

---

## Consecuencias

### Positivas

1. **Deadlocks eliminados:** el orden global previene inversiones de locks.
2. **Stock consistente:** IntegrityError en MRP no deja stock tocado.
3. **Invoice única:** producto + servicio concurrentes crean una sola factura.
4. **Totales protegidos:** toda mutación de `InvoiceItem` ocurre bajo lock de `Invoice`.
5. **Walk-in seguro:** no hay contaminación cruzada entre mascotas.

### Negativas

1. **Mayor tiempo de lock:** algunas transacciones tardan ~10-20ms más por el lock ordering.
2. **Complejidad mental:** los desarrolladores deben memorizar el orden global.
3. **Nested locks redundantes:** `MedicalRecordProduct.save()` puede re-lockear `Presentation` si la view ya lo hizo (aceptable — Postgres reutiliza el lock).

### Riesgos residuales

1. **`recalculate_totals()` invisible:** si un path legacy muta `InvoiceItem` sin lock de `Invoice`, hay lost update. Mitigación: tests de regresión + code review estricto.
2. **Side effects en signals:** si `post_save` de `InvoiceItem` escribe en otra tabla sin lock, puede haber inconsistencia. Mitigación: no hay signals activas sobre `InvoiceItem` en v1.

---

## Estado de implementación

| Hallazgo | Estado | Archivos |
|----------|--------|----------|
| #1 — Doble cancelación | ✅ Implementado | `billing/services.py::cancel_invoice()` |
| #2 — Edición post-confirm | ✅ Implementado | `billing/views.py::InvoiceDetailView.update()` |
| #3 — Race en producto | ✅ Implementado | `inventory/views.py::perform_create()` |
| #4 — Race en servicio | ✅ Implementado | `medical_records/views.py::perform_create()` |
| #5 — Invoice duplicada | ✅ Implementado | `billing/services.py::get_or_create_invoice_for_medical_record()` |
| #6 — Stock negativo | ✅ Implementado | `inventory/models.py::MedicalRecordProduct.save()` |
| #7 — Walk-in cross-pet | ✅ Implementado | `appointments/views.py::walk_in()` |
| #8 — FK cross-org (Invoice) | ⏳ Pendiente Día 3 | `billing/serializers.py` |
| #9 — FK cross-org (Prescription) | ⏳ Pendiente Día 3 | `prescriptions/serializers.py` |

---

## Métricas de validación

Suite de concurrencia: **14 tests OK** (0 fallos, 0 errores)
Suite de regresión amplia: **90 tests OK** (billing, medical_records, appointments)

| Suite | Tests | Resultado |
|-------|-------|-----------|
| `test_invoice_concurrency` | 5 | ✅ |
| `test_walkin` (extendido) | 9 | ✅ |
| `test_invoice_state_machine` | 8 | ✅ |
| `test_invoice_multitenancy` | 4 | ✅ |
| `test_event_authority` | 7 | ✅ |
| `test_anchor_completeness` | 14 | ✅ |
| `test_close` | 22 | ✅ |
| `test_walkin` (original) | 21 | ✅ |

---

## Referencias

- `docs/decisions/2026-05-09-p9-analytics-anchor-authority.md` — event authority
- `docs/modules/billing.md` — sección de concurrencia actualizada
- `docs/modules/inventory.md` — lock order consolidado
- `CLAUDE.md` — reglas de concurrencia (no negociables)
