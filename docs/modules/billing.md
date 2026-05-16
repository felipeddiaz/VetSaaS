# Modulo: Cobros

## Objetivo

El modulo de cobros gestiona las facturas generadas por consultas y ventas directas.
Es el dominio financiero del sistema. Opera de forma independiente del dominio clinico.

## Modelos

### Invoice

Campos clave:
- `invoice_type` — `consultation` o `direct_sale`
- `owner` — FK a Owner (PROTECT, obligatorio)
- `pet` — FK a Pet (PROTECT, nullable si `owner.is_generic = True`)
- `status` — `draft`, `confirmed`, `paid`, `cancelled`
- `medical_record` — OneToOneField SET_NULL (opcional)
- `appointment` — OneToOneField SET_NULL (opcional)
- `tax_rate` — heredado de la organizacion al crear, no editable despues
- `payment_method` — `cash`, `card`, `transfer`, `other`
- `subtotal`, `tax_amount`, `total` — calculados automaticamente en backend; `read_only` en el serializer; el cliente nunca puede sobreescribirlos

### Analytics anchors (event authority)

Tres timestamps `editable=False` cuyo unico writer autoritativo vive en
`billing/services.py` (ver ADR `2026-05-09-p9`):

- `paid_at` — set por `pay_invoice()` y `pay_direct_sale()`
- `confirmed_at` — set por `confirm_invoice()` y `pay_direct_sale()`
- `cancelled_at` — set por `cancel_invoice()`

Cada uno tiene su `*_source` (CharField con choices `service|audit_log|fallback|unresolved|legacy`) para auditar provenance.

CHECK constraints DB:
- `invoice_paid_status_requires_paid_at`
- `invoice_confirmed_status_requires_confirmed_at`
- `invoice_cancelled_status_requires_cancelled_at`

Los CHECK bloquean `queryset.update()`, `bulk_update()`, raw SQL y admin
que dejarian status='X' con anchor NULL (corromperia analytics).

Reglas duras:
- NUNCA setear `status` directamente fuera de `services.py`.
- `InvoiceAdmin.readonly_fields` incluye `status`, `payment_method`, todos
  los anchors, totales y `created_at/updated_at`. Admin no puede mutar
  estado — debe usar la API.

### InvoiceItem

Un item es un servicio o una presentacion de inventario (nunca ambos — constraint XOR en DB).

Campos:
- `service` — FK a Service (nullable, SET_NULL)
- `presentation` — FK a Presentation (nullable, PROTECT)
- `quantity` — decimal > 0
- `unit_price` — copiado al crear desde `service.base_price` o `presentation.sale_price`; NO se recalcula al editar el precio del producto
- `discount_type` — `percentage` o `fixed` (nullable)
- `discount_value` — decimal (default 0)
- `subtotal` — calculado en `save()`

Restricciones de unicidad en DB:
- `unique_together = [('invoice', 'presentation')]` — sin presentaciones duplicadas por factura
- `UniqueConstraint(invoice, service, WHERE service IS NOT NULL)` — sin servicios duplicados por factura

## Creacion automatica de facturas

La factura se puede crear de dos formas:

1. **Via signal al completar cita**: cuando una cita pasa a `done`, se puede crear una factura `draft` vinculada a la cita **y** a la consulta médica (si existe). Controlado por el toggle `auto_create_invoice_on_done` en `OrganizationSettings`. El default actual es `False`.

2. **Creación lazy al agregar cargos**: cuando se agrega el primer servicio o producto a una consulta walk-in (sin cita) o a una consulta creada manualmente desde una cita ya completada, se crea una factura `draft` vinculada a la consulta vía `get_or_create_invoice_for_medical_record()`. **No hay señal ni toggle** — es creación automática por demanda.

**Nota**: La creación automática via señal para consultas walk-in fue eliminada (ADR `2026-05-05-p7-lazy-invoice-creation.md`) para evitar facturas vacías acumuladas. Para citas normales, la señal sigue existiendo pero queda desactivada por default a nivel de organización.

Ambas creaciones son idempotentes (`get_or_create`).

## Default operativo actual

Configuracion recomendada y aplicada por defecto:
- `auto_create_invoice_on_done = False`
- la factura nace cuando realmente aparece el primer cargo clinico

Razon:
- evitar facturas `draft` vacias en `/billing`
- separar con mas claridad el cierre operativo de la cita del inicio del flujo de cobro
- permitir que el veterinario complete la atencion y luego cree la consulta si realmente se necesitara documentar

## Ventas directas sin cliente registrado

Para ventas a personas sin mascota registrada se usa el propietario generico.

Ver ADR `2026-04-28-generic-client-direct-sale.md`.

Flujo en frontend:
1. Boton "+ Cobro" abre el modal de venta directa (tambien via atajo **F11** o **Shift+F11**)
2. El propietario generico se asigna automaticamente (no se muestra al usuario)
3. El tipo de factura se fija a `direct_sale` via backend (serializer)
4. Se agregan productos y/o servicios en estado local (sin backend hasta cobrar)
5. Boton "Cobrar" ejecuta: `createInvoice → addItem × N → direct-pay` en una secuencia atómica
6. Si el cobro falla, el modal permanece abierto y permite reintentar
7. Si el usuario cierra sin cobrar, los items se descartan (sin facturas draft huerfanas)

**Control de acceso**: el boton "+ Cobro" y el atajo F11 usan `can("invoice.create")` —
verifica el permiso real del usuario via la lista de permisos retornada por `/api/me/`,
no compara `user.role`. Esto soporta roles dinamicos donde dos usuarios con el mismo
nombre de rol pueden tener distintos permisos.

## Estados de la factura

```
              ┌─ direct_sale: pay_direct_sale() ─────────────────────────────┐
              │  (internamente: _confirm_locked + _pay_locked, un solo lock) │
              │                                                               │
draft ────────┼── confirm_invoice() ──→ confirmed ── pay_invoice() ──→ paid  │
  │           │                                                               │
  ├── cancel_invoice() ──────────────────────────────────→ cancelled          │
  └── cancel_invoice() ──────────────────────────────────→ cancelled          │
              (confirmed también puede cancelarse)                            │
```

**Dos caminos para llegar a `paid`:**

| Camino | Tipo de factura | UX | Interno |
|--------|----------------|----|---------|
| `confirm → pay` (2 pasos) | `consultation` | Vet define cargos → Recepción cobra | `confirm_invoice()` + `pay_invoice()` (2 locks) |
| `direct-pay` (1 paso) | `direct_sale` | Cajero agrega items → Cobrar | `pay_direct_sale()`: un solo lock, llama `_confirm_locked_invoice()` + `_pay_locked_invoice()` atómicamente |

Reglas:
- Solo facturas en `draft` son editables (PATCH sobre cualquier otro estado retorna 400)
- Solo se pueden agregar o quitar items en estado `draft`
- Confirmar requiere al menos un item activo — factura vacia retorna 400
- Pagar requiere estado `confirmed` y `payment_method` en el body — no se puede saltar a `paid` desde `draft` en consultation
- Direct-pay requiere `invoice_type='direct_sale'`, estado `draft`, y `payment_method` — aplica solo a ventas directas
- El `tax_rate` se hereda de la organizacion al crear y no cambia aunque la organizacion cambie su tasa
- Ambos anchors (`confirmed_at`, `paid_at`) se escriben con `_source='service'` y se generan ambos audit logs incluso en direct-pay

**Implicacion analytics**: para `direct_sale`, `confirmed_at` y `paid_at` tienen valores casi identicos
(diferencia de milisegundos). Las curvas de accrual y cash coinciden para este tipo de factura —
comportamiento esperado y distinto al de `consultation` donde puede haber horas/dias entre confirmacion y pago.
Ver ADR `2026-05-15-p11-pay-direct-sale.md`.

### Arquitectura interna de services

Para evitar double-lock en `pay_direct_sale`, los services se estructuran en dos capas:

```python
# Funciones internas — asumen invoice YA lockeada con select_for_update()
_confirm_locked_invoice(invoice, user)   # sin @transaction.atomic
_pay_locked_invoice(invoice, user, pm)   # sin @transaction.atomic

# Wrappers públicos — lockean + delegan a internals
confirm_invoice(invoice, user)           # @transaction.atomic + select_for_update
pay_invoice(invoice, user, pm)           # @transaction.atomic + select_for_update
cancel_invoice(invoice, user, notes)     # @transaction.atomic (sin cambios)

# Direct sale atómico — lockea UNA vez, llama ambos internals
pay_direct_sale(invoice, user, pm)       # @transaction.atomic + select_for_update
```

Esto reduce 3 locks (wrapper confirm + wrapper pay + cada uno internamente)
a 1 solo lock, eliminando riesgo de deadlocks y queries innecesarias.

## Calculo de totales

El total se calcula siempre en backend. El flujo es:

```
InvoiceItem.save() → self.invoice.recalculate_totals()
```

`recalculate_totals()` usa `all_objects` (bypass de tenant filter) porque puede correr desde signals.
Los campos `subtotal`, `tax_amount` y `total` son `read_only` en el serializer — el cliente no puede enviar estos valores.

## Concurrencia y atomicidad

Al agregar un `InvoiceItem` con presentacion de inventario:

```python
with transaction.atomic():
    locked_pres = Presentation.objects.select_for_update().get(pk=presentation.pk)
    if locked_pres.stock < quantity:
        raise ValidationError("Stock insuficiente")
    serializer.save(...)  # InvoiceItem.save() → recalculate_totals() dentro del mismo atomic
```

El `unit_price` se copia en este mismo momento desde `locked_pres.sale_price`.

Al agregar un item de servicio, tambien corre dentro de `transaction.atomic()` para garantizar que `recalculate_totals()` no quede desincronizado si falla.

`pay_invoice`, `confirm_invoice`, `cancel_invoice` y `pay_direct_sale` viven en
`billing/services.py` y usan `select_for_update()` + `@transaction.atomic`
para evitar transiciones concurrentes. La view `pay_invoice` y `direct_pay_invoice`
son solo wrappers delgados al service respectivo (single authoritative writer
del anchor `paid_at`, ver ADR p9 y ADR p11).

### Orden global de locks (ADR p12)

Para prevenir deadlocks en operaciones que tocan múltiples tablas, se estableció un orden estricto:

```
MedicalRecord → Invoice → Presentation → InvoiceItem → MedicalRecordProduct
```

Reglas:
- Si un flujo no toca alguno, empieza en el primero que sí necesita.
- No se permiten inversiones de orden bajo ninguna circunstancia.
- Los locks se mantienen hasta el commit/rollback de la transacción.

**Implementación en `cancel_invoice()`:**

```python
@transaction.atomic
def cancel_invoice(invoice, user, notes=''):
    # Re-fetch con lock para evitar doble cancelación
    invoice = Invoice.objects.for_organization(
        invoice.organization
    ).select_for_update().get(pk=invoice.pk)
    
    if invoice.status == 'paid':
        raise ValidationError(...)
    
    # Lockear Presentations en orden estable por pk antes de reversar stock
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

**Implementación en `get_or_create_invoice_for_medical_record()`:**

```python
@transaction.atomic
def get_or_create_invoice_for_medical_record(medical_record):
    # Re-fetch MR con lock — este helper es ahora la autoridad central
    medical_record = MedicalRecord.objects.for_organization(
        medical_record.organization
    ).select_for_update().get(pk=medical_record.pk)
    
    # ... lógica de get_or_create ...
    
    # Retornar invoice ya lockeada
    return Invoice.objects.for_organization(org).select_for_update().get(pk=invoice.pk)
```

Ver ADR `2026-05-16-p12-concurrency-lock-order-hardening.md` para detalles completos.

### Convención de mutación de `InvoiceItem.quantity` (ADR p13)

**Regla:** TODA mutación numérica contable de `InvoiceItem` (actualmente `quantity`) DEBE usar `F('field') ± delta` vía `update()`, **incluso cuando el caller posee `select_for_update()` sobre el item**. Está prohibido `item.quantity += delta; item.save()`.

Razones:
- Consistencia con `apply_stock_movement` para `Presentation.stock` (mismo tipo de campo numérico contable).
- Defense-in-depth: si un bug futuro pierde el lock, F() sigue siendo atómico a nivel SQL.
- Single round-trip a la DB para la mutación core (subtotal/total se recomputan después).

**Helper único:** `apps.billing.services.apply_invoice_item_quantity_delta(item, delta)`.

```python
from apps.billing.services import apply_invoice_item_quantity_delta

# Incremento (item ya lockeado con select_for_update())
apply_invoice_item_quantity_delta(item, +quantity)

# Decremento — proyección previa para decidir delete vs update
projected = item.quantity - decrement_amount
if projected <= 0:
    item.delete()
else:
    apply_invoice_item_quantity_delta(item, -decrement_amount)
```

El helper internamente:
1. `InvoiceItem.all_objects.filter(pk=...).update(quantity=F('quantity') + delta)`
2. `refresh_from_db(fields=['quantity'])`
3. Recompute `subtotal` reutilizando `money`, `discount_amount`, `line_subtotal` (mismos helpers que `InvoiceItem.save()` — no diverge del cálculo canónico)
4. `update(subtotal=...)` + `recalculate_totals()` sobre la invoice

Lanza `ValidationError` si la cantidad resultante es `<= 0` (caller debe usar `item.delete()` directamente en ese caso). Ver ADR `2026-05-16-p13-day12-concurrency-remediation.md`.

### Tenant filter en re-fetch de services públicos (ADR p13)

Los 4 services públicos (`confirm_invoice`, `cancel_invoice`, `pay_invoice`, `pay_direct_sale`) re-lockean la invoice al inicio con `for_organization()` aplicado:

```python
invoice = Invoice.objects.for_organization(
    invoice.organization
).select_for_update().get(pk=invoice.pk)
```

Defense-in-depth: incluso si un caller futuro pasa una `Invoice` resuelta sin tenant filter (e.g. mgmt command, webhook), el service aplica el filtro de organización antes de mutar estado/anchors.

## Validacion de stock en serializer

Antes de intentar crear el item se valida en el serializer:
- `presentation.stock <= 0` → error inmediato
- `quantity > presentation.stock` → error inmediato con mensaje descriptivo

Esto evita que el error llegue hasta `confirm_invoice` cuando ya se habian hecho otras operaciones.

## Relacion con historial clinico

La consulta y la factura son dominios distintos.
Ver ADR `2026-04-25-cierre-consulta-explicito.md` y `2026-04-26-receta-no-es-factura.md`.

Regla critica: **una consulta con factura asociada no puede eliminarse**.
`MedicalRecordDetailView.destroy` verifica `Invoice.objects.filter(medical_record=instance).exists()` y retorna `403` si existe.

## Servicios

Los servicios son el catalogo de procedimientos cobrados en consulta (Consulta, Vacuna, Cirugia, etc.).

Reglas:
- gestionados desde `/config` por administradores
- el nombre se normaliza a `title case` al guardar
- un servicio en uso en una `MedicalRecordService` esta protegido con PROTECT (no puede eliminarse)

## Sugerencias de receta

Una factura en `draft` con consulta asociada expone `prescription_suggestions`:
lista de productos recetados disponibles para que recepcion agregue individualmente.

Ver ADR `2026-04-26-receta-no-es-factura.md`.

Importante:
- una receta medica NO descuenta stock por si misma
- una sugerencia de receta NO implica venta automatica
- recepcion decide que agregar a la factura segun lo que el cliente efectivamente lleva

## Frontend — IDs en llamadas a la API

Los endpoints de facturas usan `public_id` (UUID) en las URLs. El frontend debe usar siempre `invoice.public_id`, no `invoice.id` (entero), al construir llamadas a la API:

```javascript
// Correcto
confirmInvoice(invoice.public_id)
addInvoiceItem(invoice.public_id, payload)

// Incorrecto — falla cuando ALLOW_LEGACY_ID_LOOKUP=False
confirmInvoice(invoice.id)
```

El campo `invoice.id` (entero) puede mostrarse en la UI como numero de referencia ("Cobro #123") pero no debe usarse en URLs de API.

## Endpoints

Los IDs de invoice e items usan `<uuid>` (public_id), no el PK entero.

| Metodo   | URL                                          | Descripcion                       |
|----------|----------------------------------------------|-----------------------------------|
| `GET`    | `/api/billing/invoices/`                     | Listar facturas                   |
| `POST`   | `/api/billing/invoices/`                     | Crear factura                     |
| `GET`    | `/api/billing/invoices/<uuid>/`              | Detalle con items                 |
| `PATCH`  | `/api/billing/invoices/<uuid>/`              | Editar (solo draft)               |
| `POST`   | `/api/billing/invoices/<uuid>/confirm/`      | Confirmar borrador                |
| `POST`   | `/api/billing/invoices/<uuid>/pay/`          | Registrar pago (requiere confirmed) |
| `POST`   | `/api/billing/invoices/<uuid>/direct-pay/`   | Cobrar venta directa (draft → paid atómico) |
| `POST`   | `/api/billing/invoices/<uuid>/cancel/`       | Cancelar (no aplica a paid)       |
| `POST`   | `/api/billing/invoices/<uuid>/items/`        | Agregar item                      |
| `PATCH`  | `/api/billing/invoices/<uuid>/items/<id>/`   | Editar item (solo draft)          |
| `DELETE` | `/api/billing/invoices/<uuid>/items/<id>/`   | Eliminar item (solo draft)        |
| `GET`    | `/api/billing/services/`                     | Listar servicios                  |
| `POST`   | `/api/billing/services/`                     | Crear servicio                    |
| `PATCH`  | `/api/billing/services/<uuid>/`              | Editar servicio                   |
| `DELETE` | `/api/billing/services/<uuid>/`              | Eliminar servicio                 |
| `GET`    | `/api/organizations/settings/`               | Ver configuracion de flujo        |
| `PATCH`  | `/api/organizations/settings/`               | Editar toggles de flujo (ADMIN)   |

## Filtros disponibles (GET /api/billing/invoices/)

- `owner=<id>` — por propietario
- `pet=<id>` — por mascota
- `status=<estado>` — por estado
- `paid_on=YYYY-MM-DD` — facturas pagadas ese dia (ajustado a timezone de la org)
- `created_on=YYYY-MM-DD` — facturas creadas ese dia (ajustado a timezone de la org)

## Audit log

Cada cambio de estado genera un `InvoiceAuditLog` con:
- `previous_status` / `new_status`
- `changed_by`
- `notes` — campo opcional sanitizado (max 255 caracteres)

## Atajos de teclado

| Atajo | Acción | Contexto |
|-------|--------|----------|
| `F11` | Abrir modal "+ Cobro" (venta directa) | Sin modales abiertos, si el usuario tiene `invoice.create` |
| `Shift+F11` | Idéntico a F11 | Misma funcionalidad, sin distinción |

Ambos atajos bloquean el comportamiento nativo del navegador (fullscreen) via `preventDefault()`.
El botón "+ Cobro" muestra un badge `F11` como recordatorio visual.
