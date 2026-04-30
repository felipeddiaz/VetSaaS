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
- `subtotal`, `tax_amount`, `total` — calculados automaticamente

### InvoiceItem

Un item es un servicio o una presentacion de inventario (nunca ambos — constraint XOR).

Campos:
- `service` — FK a Service (nullable, SET_NULL)
- `presentation` — FK a Presentation (nullable, PROTECT)
- `quantity` — decimal > 0
- `unit_price` — copiado al crear desde `service.base_price` o `presentation.sale_price`; NO se recalcula al editar el precio del producto
- `discount_type` — `percentage` o `fixed` (nullable)
- `discount_value` — decimal (default 0)
- `subtotal` — calculado en `save()`

## Creacion automatica de facturas

La factura se puede crear de dos formas:

1. **Via signal al completar cita**: cuando una cita pasa a `done`, se crea una factura `draft` vinculada a la cita. Controlado por el toggle `auto_create_invoice_on_done` en `OrganizationSettings`.

2. **Via signal al crear consulta sin cita**: cuando se crea una `MedicalRecord` sin cita asociada, se crea una factura `draft`. Controlado por el toggle `auto_create_medical_record` en `OrganizationSettings`.

Ambas creaciones son idempotentes (`get_or_create`).

## Ventas directas sin cliente registrado

Para ventas a personas sin mascota registrada se usa el propietario generico.

Ver ADR `2026-04-28-generic-client-direct-sale.md`.

Flujo en frontend:
1. Boton "Venta a publico general" pre-selecciona al propietario generico
2. El selector de mascota se deshabilita
3. El tipo de factura se fija a `direct_sale`
4. Se puede agregar cualquier producto o servicio normalmente

## Concurrencia en descuento de stock

Al agregar un `InvoiceItem` con presentacion de inventario, la vista hace:

```python
with transaction.atomic():
    locked_pres = Presentation.objects.select_for_update().get(pk=presentation.pk)
    if locked_pres.stock < quantity:
        raise ValidationError("Stock insuficiente")
```

El `unit_price` se copia en este mismo momento desde `locked_pres.sale_price`.
Cambios posteriores de precio no afectan facturas existentes.

## Estados de la factura

```
draft → confirmed → paid
  ↓
cancelled
```

Reglas:
- solo se pueden agregar o quitar items en estado `draft`
- una factura `paid` es inmutable
- el campo `tax_rate` se hereda de la organizacion al crear y no cambia aunque la organizacion cambie su tasa

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

## Endpoints

| Metodo   | URL                                      | Descripcion                     |
|----------|------------------------------------------|---------------------------------|
| `GET`    | `/api/billing/invoices/`                 | Listar facturas                 |
| `POST`   | `/api/billing/invoices/`                 | Crear factura                   |
| `GET`    | `/api/billing/invoices/<id>/`            | Detalle con items               |
| `PATCH`  | `/api/billing/invoices/<id>/`            | Editar (solo draft)             |
| `POST`   | `/api/billing/invoices/<id>/confirm/`    | Confirmar borrador              |
| `POST`   | `/api/billing/invoices/<id>/pay/`        | Registrar pago                  |
| `POST`   | `/api/billing/invoices/<id>/items/`      | Agregar item                    |
| `DELETE` | `/api/billing/invoices/<id>/items/<i>/`  | Eliminar item (solo draft)      |
| `GET`    | `/api/billing/services/`                 | Listar servicios                |
| `POST`   | `/api/billing/services/`                 | Crear servicio                  |
| `PUT`    | `/api/billing/services/<id>/`            | Editar servicio                 |
| `DELETE` | `/api/billing/services/<id>/`            | Eliminar servicio               |
| `GET`    | `/api/organizations/settings/`           | Ver configuracion de flujo      |
| `PATCH`  | `/api/organizations/settings/`           | Editar toggles de flujo (ADMIN) |

## Filtros disponibles (GET /api/billing/invoices/)

- `owner=<id>` — por propietario
- `pet=<id>` — por mascota
- `status=<estado>` — por estado
- `paid_on=YYYY-MM-DD` — facturas pagadas ese dia
- `created_on=YYYY-MM-DD` — facturas creadas ese dia
