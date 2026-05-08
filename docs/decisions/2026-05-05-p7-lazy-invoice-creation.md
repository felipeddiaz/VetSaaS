# ADR: Creación Lazy de Facturas

**Fecha**: 2026-05-05  
**Estado**: Implementado

## Contexto

El sistema creaba automáticamente una factura `draft` cada vez que se creaba una consulta médica, mediante dos señales:

1. **Signal A** (`create_draft_invoice_on_medical_record`): Se disparaba al crear `MedicalRecord` sin cita asociada (walk-in)
2. **Signal B** (`create_draft_invoice_on_done`): Se disparaba al marcar una cita como `done`

## Problemas identificados

### Problema A: Facturas vacías en walk-in

Cada vez que se abría una consulta walk-in desde el frontend, se creaba inmediatamente una factura `draft` vacía (sin items). Si el usuario nunca agregaba servicios o productos, o si abandonaba la consulta sin cerrarla, la factura huérfana permanecía en el sistema acumulándose silenciosamente.

### Problema B: Facturas duplicadas/huérfanas en flujo con cita

Cuando una cita se marcaba como `done`:

```
1. Appointment.status = 'done'
2. Signal B → Invoice A { appointment=cita, medical_record=NULL }  ← HUÉRFANA
3. MedicalRecord.get_or_create(appointment=cita)  ← auto-creado por view
4. Signal A → retorna temprano (appointment_id SET)
5. Usuario agrega servicio → _sync_invoice_item
6. get_or_create_invoice_for_medical_record()
7. Invoice B { appointment=NULL, medical_record=consulta }  ← CON ITEMS
```

**Resultado**: Dos facturas para la misma consulta. Invoice A nunca recibía items porque `_sync_invoice_item` busca por `medical_record`, no por `appointment`.

### Problema C: Dashboard no afectado

El dashboard (`dashboard/views.py`) no consulta `Invoice` actualmente, así que las facturas vacías no polutan la UI principal. Pero si en el futuro se agrega un widget de "facturas pendientes" o "ingresos", estas facturas vacías aparecerían incorrectamente.

## Decisión

### 1. Eliminar Signal A

Se elimina completamente `create_draft_invoice_on_medical_record` de `billing/signals.py`.

**Consecuencia**: Las consultas walk-in ya no crean factura automáticamente. La factura se crea de forma **lazy** al agregar el primer cargo (servicio o producto) vía `_sync_invoice_item` → `get_or_create_invoice_for_medical_record()`.

### 2. Mantener Signal B pero desacoplada del default

La señal `create_draft_invoice_on_done` ahora:

1. Busca el `MedicalRecord` vinculado a la cita (si existe)
2. Crea la factura con `medical_record` en los `defaults`
3. Maneja `IntegrityError` por race conditions (dos procesos concurrentes)
4. Si la factura ya existía sin `medical_record`, la linkea correctamente

```python
@receiver(post_save, sender='appointments.Appointment')
def create_draft_invoice_on_done(sender, instance, **kwargs):
    if instance.status != 'done':
        return
    if not get_org_setting(instance.organization, SETTING_AUTO_INVOICE_ON_DONE):
        return

    medical_record = (
        MedicalRecord.objects
        .filter(appointment=instance)
        .order_by('-created_at')
        .first()
    )

    defaults = {
        'owner': instance.pet.owner,
        'pet': instance.pet,
        'organization': instance.organization,
        'status': 'draft',
        'invoice_type': 'consultation',
        'medical_record': medical_record,
    }

    try:
        invoice, created = Invoice.objects.get_or_create(
            appointment=instance,
            defaults=defaults,
        )
    except IntegrityError:
        # Race condition: dos procesos concurrentes → re-fetch
        invoice = Invoice.objects.get(appointment=instance)
        created = False

    # Recovery: si la invoice ya existía sin medical_record, linkearla
    if not created and invoice.medical_record_id is None and medical_record:
        invoice.medical_record = medical_record
        invoice.save(update_fields=['medical_record'])
```

Adicionalmente, el default organizacional de `auto_create_invoice_on_done` pasa a `False`. La señal sigue existiendo para clínicas que explícitamente quieran ese comportamiento, pero el flujo recomendado es lazy.

### 3. `get_or_create_invoice_for_medical_record` con lógica appointment-first

La función ahora:

1. **Si hay cita**: Busca factura por `appointment` (con filtro multi-tenant explícito)
2. **Si existe**: La linkea al `medical_record` si no estaba vinculada
3. **Fallback**: Crea factura nueva vinculada al `medical_record`

```python
def get_or_create_invoice_for_medical_record(medical_record):
    org = medical_record.organization

    # 1) Si hay cita, buscar factura vinculada a la cita
    if medical_record.appointment_id:
        invoice = Invoice.objects.filter(
            appointment=medical_record.appointment,
            organization=org,
        ).first()
        if invoice:
            if invoice.medical_record_id is None:
                invoice.medical_record = medical_record
                invoice.save(update_fields=['medical_record'])
            return invoice

    # 2) Fallback: factura nueva vinculada al medical_record
    invoice, _ = Invoice.objects.get_or_create(
        medical_record=medical_record,
        defaults={...}
    )
    return invoice
```

**Filtro multi-tenant explícito**: `organization=org` previene que una consulta de una organización pueda linkearse accidentalmente a una factura de otra organización.

### 4. Manejo de race conditions

El `try/except IntegrityError` en Signal B maneja el caso donde dos procesos concurrentes intentan crear la misma factura (ej. Signal B + `_sync_invoice_item` corriendo simultáneamente).

### 5. Impacto UX — SidePanel

El SidePanel del historial clínico ya maneja `totals: null` correctamente:

```jsx
{totals ? (
    <TotalesDeFactura />
) : (
    <p className={styles.panelEmpty}>Sin factura</p>
)}
```

El endpoint `summary` retorna `"totals": null` cuando no existe factura:

```python
"totals": {
    "subtotal": invoice.subtotal,
    ...
} if invoice else None,
```

**No se requiere cambio en frontend.**

## Flujos resultantes

### Walk-in (sin cita)

```
POST /api/medical-records/
  → MedicalRecord creado
  → NO se crea Invoice (Signal A eliminada)

Usuario agrega producto/servicio
  → _sync_invoice_item()
  → get_or_create_invoice_for_medical_record()
  → Invoice creada lazy { medical_record=consulta, status=draft }
```

### Con cita con toggle ON

```
PATCH /api/appointments/{id}/status/ { status: 'done' }
  → MedicalRecord.get_or_create(appointment=cita)  [view]
  → Signal B → Invoice { appointment=cita, medical_record=consulta }

Usuario agrega producto/servicio
  → _sync_invoice_item()
  → get_or_create_invoice_for_medical_record()
  → Encuentra Invoice por appointment → la reutiliza
  → NO crea segunda factura
```

## Alternativas consideradas

### A: Mantener Signal A con flag `is_empty`
**Rechazado**: Complejidad innecesaria. Mejor no crear hasta que haya algo que cobrar.

### B: Cambiar toggle default a `False`
**Adoptado**: El toggle `SETTING_AUTO_INVOICE_ON_DONE` sigue existiendo para Signal B, pero queda apagado por default. Signal A se elimina completamente (sin toggle).

### C: Job cron que limpie facturas vacías
**Rechazado**: Parche, no solución de raíz. Mejor no crear basura.

## Tests agregados

| Test | Propósito |
|------|-----------|
| `test_walk_in_no_auto_invoice` | Walk-in → NO Invoice inmediata |
| `test_product_sync_creates_invoice_lazy` | Agregar producto → Invoice lazy |
| `test_appointment_done_creates_invoice_with_link` | Cita done → Invoice linkeada a cita Y consulta |
| `test_orphan_invoice_recovery_on_sync` | Invoice huérfana → agregar servicio → linkeada |

## Deuda técnica

La señal de `done` sigue existiendo por compatibilidad configuracional, pero ya no es el camino recomendado. El patrón objetivo es: solo crear un documento financiero cuando hay algo que facturar.

## Relación con otros ADRs

- **ADR-01** (No refactor de módulos en v1): Fix quirúrgico en señales, sin mover modelos.
- **ADR-04** (Audit log en pay_invoice): Ídem — seguridad por capas.
- **ADR-05** (Sanitización en serializers): No aplica — este ADR es de flujo, no de validación de datos.
