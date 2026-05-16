# ADR p13: Remediación post-review del sprint de concurrencia (Día 1-2)

**Fecha:** 2026-05-16
**Estado:** Implementado
**Impacto:** `billing`, `inventory`, `medical_records`
**Sigue a:** ADR p12 (`2026-05-16-p12-concurrency-lock-order-hardening.md`)

---

## Contexto

Tras aplicar el sprint de concurrencia (ADR p12), una segunda pasada de revisión paralela con tres agentes especializados (`code-reviewer`, `security-auditor`, `backend-architect`) confirmó que las **7 fixes core están correctas** ✅ pero identificó **7 gaps secundarios** que comprometían la robustez del Día 1-2 antes de pasar al Día 3 (tenant validators P0 #8-9).

Los gaps se clasificaron en:

1. **Convención de mutación de `InvoiceItem.quantity`** — los 4 sites que mutan cantidad usaban `item.quantity += delta; item.save()` en lugar del patrón `F('quantity') ± delta` vía `update()`. Inconsistente con la convención del proyecto establecida en `apply_stock_movement` para `Presentation.stock`.
2. **Lock-order inversion en MRS create** — `MedicalRecordServiceListCreateView.perform_create` ordenaba `MR → MRS.save() → Invoice → InvoiceItem` (la write de MRS antes del lock de Invoice rompía el orden canónico).
3. **Test falso-positivo de rollback** — `test_direct_pay_rolls_back_stock_on_payment_error` usaba `payment_method='bitcoin'` que era rechazado ANTES de `_confirm_locked_invoice`, por lo que el rollback nunca se ejercitaba.
4. **Contrato implícito en `apply_stock_movement`** — la función hace `refresh_from_db()` (sin lock) para el stock-check; todos los callers actuales lockean externamente pero el contrato no estaba documentado.
5. **Defense-in-depth tenant filter** — `confirm_invoice`, `pay_invoice`, `pay_direct_sale` re-lockeaban sin `for_organization()`. `cancel_invoice` sí lo hacía — inconsistente.
6. **Bug silencioso en `MedicalRecordProduct.save()`** — si un caller (admin, mgmt command, signal) invoca `save()` fuera de un bloque atómico, el `select_for_update()` interno no aplica lock real.
7. **Referencia rota en docstring** — `pay_direct_sale.__doc__` apuntaba a `dashboard-metrics-contract.md §4.2` pero la nota sobre `direct_sale` accrual=cash está en §3.1.2.

---

## Decisión

### 1. Helper `apply_invoice_item_quantity_delta` — F() pattern obligatorio

**Convención establecida:** TODA mutación numérica contable de `InvoiceItem` (actualmente solo `quantity`) DEBE usar `F('field') ± delta` vía `update()`, **incluso cuando el caller posee `select_for_update()` sobre el item**. Razones:

1. **Consistencia conceptual** con `apply_stock_movement` para `Presentation.stock` (mismo tipo de campo numérico contable).
2. **Defense-in-depth** — si un bug futuro pierde el lock, F() sigue siendo atómico a nivel SQL.
3. **Single round-trip** a la DB para la mutación core (subtotal/total se recomputan después).

**Helper nuevo en `apps/billing/services.py`:**

```python
def apply_invoice_item_quantity_delta(item, delta):
    """
    Mutación atómica de InvoiceItem.quantity usando F('quantity') + delta.

    ⚠️ CONTRATO:
      - El caller DEBE poseer select_for_update() sobre el item.
      - El caller DEBE estar dentro de transaction.atomic().
      - delta puede ser negativo (decremento), pero el resultado no puede ser <= 0.
        Si el caller necesita borrar el item, debe llamar item.delete() ANTES
        de invocar este helper (proyectar item.quantity + delta primero).
    """
    projected = item.quantity + delta
    if projected <= 0:
        raise ValidationError(
            f"La cantidad resultante ({projected}) no es positiva. "
            f"Llama item.delete() antes de invocar apply_invoice_item_quantity_delta."
        )

    InvoiceItem.all_objects.filter(pk=item.pk).update(quantity=F('quantity') + delta)
    item.refresh_from_db(fields=['quantity'])

    gross = money(item.quantity * item.unit_price)
    disc = discount_amount(gross, item.discount_type, item.discount_value)
    new_subtotal = line_subtotal(item.quantity, item.unit_price, disc)
    InvoiceItem.all_objects.filter(pk=item.pk).update(subtotal=new_subtotal)

    item.invoice.recalculate_totals()
    item.refresh_from_db(fields=['subtotal'])
    return item.quantity
```

Reutiliza los mismos helpers que `InvoiceItem.save()` (`money`, `discount_amount`, `line_subtotal`) para no divergir del cálculo canónico.

**Sites refactorizados (4):**

| Site | Patrón anterior | Patrón nuevo |
|------|-----------------|--------------|
| `medical_records/views.py::MedicalRecordServiceListCreateView.perform_create` (increment) | `item.quantity += quantity; item.save()` | `apply_invoice_item_quantity_delta(item, quantity)` |
| `medical_records/views.py::MedicalRecordServiceDeleteView.perform_destroy` (decrement) | `item.quantity = new_qty; item.save()` | `apply_invoice_item_quantity_delta(item, -fresh_instance.quantity)` (con proyección previa) |
| `inventory/views.py::MedicalRecordProductListCreateView.perform_create` (increment) | `item.quantity += quantity; item.save()` | `apply_invoice_item_quantity_delta(item, quantity)` |
| `inventory/views.py::MedicalRecordProductDeleteView.perform_destroy` (decrement) | `item.quantity = new_quantity; item.save()` | `apply_invoice_item_quantity_delta(item, -fresh_instance.quantity)` (con proyección previa) |

**Patrón canónico para decrement (delete paths):**

```python
projected = item.quantity - fresh_instance.quantity
if projected <= 0:
    item.delete()
else:
    apply_invoice_item_quantity_delta(item, -fresh_instance.quantity)
```

### 2. Lock-order canonical en MRS create

En `MedicalRecordServiceListCreateView.perform_create`, se movió `serializer.save(medical_record=mr)` después del bloque de `InvoiceItem`. Los datos del item (`service`, `quantity`) se leen de `serializer.validated_data` antes para no depender de la instancia MRS. Esto alinea el sitio al orden canónico **MR → Invoice → InvoiceItem → MRS**.

### 3. Test de rollback corregido

`test_direct_pay_rolls_back_stock_on_payment_error` ahora usa `unittest.mock.patch` para mockear `_pay_locked_invoice` con `side_effect=ValidationError(...)`. Esto fuerza el fallo **después** de que `_confirm_locked_invoice` ya escribió `confirmed_at`, descontó stock y creó el `InvoiceAuditLog` row de la transición `draft → confirmed`. El test verifica:

1. `paid_at` sigue `None`
2. `confirmed_at` fue revertido a `None`
3. `status` volvió a `'draft'`
4. `presentation.stock` restaurado
5. `InvoiceAuditLog` row de `confirmed` revertida

### 4. Contrato de lock en `apply_stock_movement`

Docstring extendido en `inventory/services.py` con sección "⚠️ CONTRATO DE LOCK (CRÍTICO)" enumerando explícitamente:

- Caller DEBE poseer `select_for_update()` sobre `presentation`.
- Razón: `refresh_from_db()` sin lock no es atómico contra writes concurrentes.
- Lista de callers actuales que cumplen el contrato (auditable en code review).

### 5. Tenant filter defense-in-depth

Los 3 services que faltaban se alinearon al patrón de `cancel_invoice`:

```python
# confirm_invoice (L131)
invoice = Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)

# pay_invoice (L200)
invoice = Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)

# pay_direct_sale (L229)
invoice = Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)
```

### 6. Fail-fast en `MedicalRecordProduct.save()` y `.delete()`

Assert al inicio de `save()` y `delete()`:

```python
assert connection.in_atomic_block, (
    "MedicalRecordProduct.save() debe llamarse dentro de transaction.atomic(); "
    "sin tx el select_for_update() interno no aplica lock real y pierde la "
    "garantía de serialización contra movimientos de stock concurrentes."
)
```

Adicionalmente, warning log si `save()` se invoca sin `locked_presentation`:

```python
if locked_presentation is None:
    logging.getLogger(__name__).warning(
        "MedicalRecordProduct.save() invocado sin locked_presentation — "
        "fallback a lock interno. Llamada fuera de la view oficial. "
        "mr_id=%s pres_id=%s",
        self.medical_record_id, self.presentation_id,
    )
```

El warning surface uses no-canonicos en producción antes de que rompan.

### 7. Referencia docstring corregida

`pay_direct_sale.__doc__`: `§4.2` → `§3.1.2 (revenue_accrual)`.

---

## Tests agregados

Nuevos tests en `backend/apps/billing/tests/test_invoice_concurrency.py`:

| Test | Valida |
|------|--------|
| `test_two_parallel_pay_direct_sale_serialize` | 2 POSTs paralelos a `/direct-pay/` sobre misma invoice draft: exactamente 1 retorna 200 + paid + stock descontado **una sola vez**; el otro retorna 400 |
| `test_two_parallel_invoice_patch_serialize` | 2 PATCHes paralelos: ambos serializados via lock, estado final coherente sin corrupción |
| `test_parallel_pay_direct_sale_and_cancel_keep_consistent_stock` | `pay_direct_sale` + `cancel_invoice` paralelos: solo una operación tiene éxito, stock consistente |

Test corregido en `backend/apps/billing/tests/test_anchor_completeness.py`:

| Test | Cambio |
|------|--------|
| `test_direct_pay_rolls_back_stock_on_payment_error` | Reemplaza payment_method falso (`bitcoin`) por `mock.patch('_pay_locked_invoice', side_effect=ValidationError)` que dispara DESPUÉS de la confirmación. Verifica rollback completo de stock + anchors + audit log |

---

## Consecuencias

### Positivas

1. **Convención uniforme de F()** en todo el subsistema billing (Presentation.stock + InvoiceItem.quantity usan el mismo patrón).
2. **Fail-fast en MRP.save()** detecta callers fuera de tx **en tiempo de test/dev**, no en producción.
3. **Defense-in-depth tenant filter** — incluso si un caller futuro pasa una `Invoice` resuelta sin tenant filter, el service vuelve a aplicar `for_organization()`.
4. **Test de rollback ejercita el path real** (mock dispara después de `_confirm_locked_invoice`, no antes).
5. **Documentación crítica visible en el código** — `apply_stock_movement` docstring lista todos los callers válidos, facilitando code review.

### Negativas

1. **`apply_invoice_item_quantity_delta` añade overhead** — 2 UPDATEs (quantity + subtotal) + 2 `refresh_from_db` + 1 `recalculate_totals` en lugar de 1 `save()`. Aceptable porque el patrón sigue siendo atómico y la consistencia gana.
2. **Tests preexistentes que llamaban `MRP.save()` fuera de atomic** deben envolver en `transaction.atomic()` explícitamente. Migrado: `test_medical_record_product_create_integrity_error_does_not_decrement_stock`.
3. **Caller surface** del helper sigue siendo "obligación del desarrollador no llamarlo fuera de lock". El contrato está documentado pero no enforced en runtime (sería caro chequear lock holder explícitamente).

### Riesgos residuales (de scope futuro)

1. **`closed_at` se escribe desde view, no service** (`medical_records/views.py:432`) — viola ADR-11. Pre-existente. Mover a `medical_records/services.py::close_medical_record_service()` en sprint separado.
2. **`MedicalRecordProduct.delete()` no se invoca en cascada de MR delete** — Django ORM bypasea custom delete en cascade. Stock no se revierte si se borra el MR completo. Pre-existente. Documentar en `docs/modules/inventory.md`.
3. **`InvoiceSerializer.validate()` exige `pet/owner` en PATCH parcial** — bloquea PATCH minimalistas (`{"notes": "x"}`). Bug pre-existente; los tests concurrentes envían `pet` + `owner` explícitamente para sortearlo.

---

## Estado de implementación

| Fix | Estado | Archivo principal |
|-----|--------|-------------------|
| 1 — Helper F() + 4 sites | ✅ | `billing/services.py`, `inventory/views.py`, `medical_records/views.py` |
| 2 — MRS lock-order canonical | ✅ | `medical_records/views.py::MedicalRecordServiceListCreateView` |
| 3 — Test rollback corregido | ✅ | `billing/tests/test_anchor_completeness.py` |
| 4 — Docstring contrato `apply_stock_movement` | ✅ | `inventory/services.py` |
| 5 — Tenant filter en 3 services | ✅ | `billing/services.py` |
| 6 — Assert + warning en MRP.save/.delete | ✅ | `inventory/models.py` |
| 7 — Docstring `pay_direct_sale` | ✅ | `billing/services.py` |

---

## Métricas de validación

- `python manage.py check` → no issues
- 233 tests pasan (suite completa CLAUDE.md + nuevos de concurrencia)
- `audit_anchor_integrity` → `✓ All invariants hold` (exit 0)
- Smoke del assert `MedicalRecordProduct.save()` fuera de atomic → dispara `AssertionError` con mensaje canónico

---

## Referencias

- `docs/decisions/2026-05-16-p12-concurrency-lock-order-hardening.md` — fixes core Día 1-2
- `docs/decisions/2026-05-09-p9-analytics-anchor-authority.md` — anchor authority (writer único en services.py)
- `docs/dashboard-metrics-contract.md §3.1.2` — accrual=cash para `direct_sale`
- `docs/modules/billing.md` — sección "Convención de mutación de InvoiceItem.quantity"
- `docs/modules/inventory.md` — contrato de lock en `apply_stock_movement`
- `docs/modules/medical_records.md` — orden canónico de locks en MRS/MRP
- `CLAUDE.md` — reglas de concurrencia (no negociables)
