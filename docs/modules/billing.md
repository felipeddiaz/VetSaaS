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
1. Boton "Venta a publico general" pre-selecciona al propietario generico
2. El selector de mascota se deshabilita
3. El tipo de factura se fija a `direct_sale`
4. Se puede agregar cualquier producto o servicio normalmente

## Estados de la factura

```
draft → confirmed → paid
  ↓
cancelled
```

Reglas:
- Solo facturas en `draft` son editables (PATCH sobre cualquier otro estado retorna 400)
- Solo se pueden agregar o quitar items en estado `draft`
- Confirmar requiere al menos un item activo — factura vacia retorna 400
- Pagar requiere estado `confirmed` y `payment_method` en el body — no se puede saltar a `paid` desde `draft`
- El `tax_rate` se hereda de la organizacion al crear y no cambia aunque la organizacion cambie su tasa

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

`pay_invoice` usa `select_for_update()` + `transaction.atomic()` para evitar doble pago bajo concurrencia.

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
| `POST`   | `/api/billing/invoices/<uuid>/pay/`          | Registrar pago                    |
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
