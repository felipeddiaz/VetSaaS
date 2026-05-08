# ADR: Hardening de logica de negocio P1

**Fecha**: 2026-05-01  
**Estado**: Implementado

## Contexto

Tras completar P0 (seguridad basica), la auditoria P1 identifico problemas de logica de negocio, consistencia de datos y concurrencia que podian generar dinero incorrecto o datos inconsistentes en produccion.

## Decisiones implementadas

### 1. URLs de items de factura usan public_id (UUID)

**Antes**: `/api/billing/invoices/<int:invoice_pk>/items/`  
**Despues**: `/api/billing/invoices/<str:invoice_pk>/items/`

El `invoice_pk` entero era predecible y permitia enumeracion de tenants por timing de respuesta HTTP. Ahora se usa `resolve_public_id()` en los tres fetch internos de `InvoiceItemCreateView` y `InvoiceItemDetailView`.

### 2. Solo facturas en draft son editables

**Antes**: el PATCH sobre facturas bloqueaba solo estado `paid`.  
**Despues**: cualquier estado distinto de `draft` retorna 400.

Un PATCH sobre una factura `confirmed` o `cancelled` podia cambiar `owner`, `pet`, `invoice_type` con stock ya descontado.

### 3. InvoiceItem de servicio dentro de transaction.atomic()

El flujo de creacion de item de servicio no estaba en transaccion. Si `recalculate_totals()` fallaba tras el `save()`, el item quedaba guardado con totales desactualizados. Ahora todo el bloque esta en `transaction.atomic()`.

### 4. Constraint unico para (invoice, service) en DB

`unique_together = [('invoice', 'presentation')]` no cubria items de servicio porque `presentation IS NULL` hace que el constraint no aplique. Se agrego:

```python
UniqueConstraint(
    fields=['invoice', 'service'],
    condition=Q(service__isnull=False),
    name='invoiceitem_unique_invoice_service',
)
```

Se agrego tambien validacion en serializer (devuelve 400 con mensaje claro antes de llegar a la DB) porque `IntegrityError` no esta capturado por el exception handler global.

### 5. Validacion FK tenant en serializers

`MedicalRecordSerializer` y `VaccineRecordSerializer` no tenian `validate_pet`, `validate_appointment`, `validate_veterinarian`, `validate_medical_record`. Un usuario podia enviar FKs de otra organizacion. Se agregan metodos `validate_*` con el patron:

```python
def validate_pet(self, pet):
    if pet and pet.organization != self.context['request'].user.organization:
        raise serializers.ValidationError('Acceso invalido.')
    return pet
```

El `if pet and ...` es necesario porque los campos opcionales pueden llegar como `None`.

### 6. pay_invoice con select_for_update() y atomic

Dos requests simultaneos de pago podian pasar el check de estado y ejecutar `save()` ambos. Se agrego `select_for_update()` sobre el queryset de la factura dentro de `transaction.atomic()`.

### 7. walk_in: select_for_update() evaluado

El queryset de lock en `walk_in` nunca se evaluaba (Django no ejecuta SQL hasta evaluar el queryset). Se agrego `.first()` para forzar la evaluacion y que el lock llegue a la DB.

### 8. MedicalRecordProduct UPDATE con lock

El path de UPDATE en `MedicalRecordProduct.save()` leia `old.quantity` sin `select_for_update()`. Dos requests concurrentes calculaban el mismo diff y aplicaban el movimiento dos veces. Se envuelve con `transaction.atomic()` y `select_for_update()`.

### 9. Sanitizacion de notes en factura y cancelacion

El campo `notes` de `Invoice` y el parametro `notes` de `cancel_invoice` no pasaban por `sanitize_text()`. Se agrega `validate_notes()` en `InvoiceSerializer` y sanitizacion en la view de cancelacion.

### 10. Hardening de validaciones en serializers

- `InvoiceItemSerializer`: valida `quantity > stock` en serializer (antes solo en `confirm_invoice`)
- `StockAdjustmentSerializer`: `min_value` cambiado de `0` a `0.01` (quantity=0 es una operacion no-op que contamina el historial de auditoria)
- `AppointmentSerializer`: `reason` truncaba a 100 pero el modelo define `max_length=255`

## Tests agregados

- `apps/billing/tests/test_invoice_state_machine.py` — 8 tests de maquina de estados
- `apps/billing/tests/test_invoice_multitenancy.py` — 6 tests de multitenancy FK
- `apps/billing/tests/test_money.py` — 9 tests de aritmetica (migrados de `billing/tests.py`)

Suite total: 82 tests, todos pasando.
