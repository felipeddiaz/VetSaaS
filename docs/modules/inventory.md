# Modulo: Inventario

## Objetivo

El modulo gestiona el catalogo de productos, sus presentaciones (variantes), el stock y los movimientos de inventario.

## Modelos

### Product

Campos:
- `name` — nombre del producto
- `internal_code` — codigo interno unico por organizacion (auto-generado si no se envia)
- `description` — descripcion opcional
- `category` — choices: `medication`, `food`, `accessory`, `other`
- `requires_prescription` — si `True`, el producto no puede venderse directamente; requiere receta activa
- `is_active` — soft delete

### Presentation

Cada producto puede tener una o mas presentaciones (variantes).
Ver ADR `2026-04-28-presentation-fk-migration.md`.

Campos:
- `product` — FK a Product (CASCADE)
- `name` — etiqueta de la variante (ej: "Bolsa 10kg", "Tableta 500mg")
- `base_unit` — choices: `tablet`, `capsule`, `ml`, `vial`, `ampoule`, `piece`, `bag`, `bottle`, `tube`, `kg`, `g`, `unit`
- `sale_price` — precio de venta (> 0)
- `stock` — existencias actuales (>= 0)
- `min_stock` — umbral de stock minimo para alertas
- `quantity` — factor de escala para Fase 3 (conversion entre variantes); siempre `1` en Fase 1

Constraints:
- `unique_together = [('product', 'name')]` — no puede haber dos variantes con el mismo nombre para el mismo producto
- indices en `product` y `stock` para optimizar queries de alertas y autocomplete

Propiedad derivada:
- `is_low_stock` — `True` si `stock <= min_stock`

### StockMovement

Registro auditado de cada cambio de stock.

- `movement_type` — `in`, `out`, `adjustment`
- `quantity` — cantidad involucrada
- `reason` — texto libre
- FK opcionales a `MedicalRecord`, `Invoice`, `created_by`

## Validaciones de backend

### Nombre de producto

Regex: `^[A-Za-z0-9ÁÉÍÓÚáéíóúñÑ\s\.\-\(\)\/\%\+]+$`

Rechaza caracteres especiales que no tienen sentido en un nombre de producto (signos de interrogacion, exclamacion, corchetes, etc.).
El error se expone con mensaje claro; no cierra el modal del frontend.

### Precio y stock al crear presentacion

- `sale_price >= 0`
- `stock >= 0`
- `min_stock >= 0`

Los `CheckConstraint` del modelo son la ultima linea de defensa; las validaciones del serializer dan mensajes utiles.

## Ajuste de stock y concurrencia

El stock se modifica exclusivamente a traves de `apply_stock_movement()` en `apps/inventory/services.py`.
Nunca se escribe `presentation.stock` directamente fuera de esa funcion.

Para prevenir race conditions en ventas simultaneas, `InvoiceItemCreateView.perform_create` hace:

```python
with transaction.atomic():
    locked_pres = Presentation.objects.select_for_update().get(pk=presentation.pk)
    if locked_pres.stock < quantity:
        raise ValidationError("Stock insuficiente")
```

Esto previene que dos ventas simultaneas pasen el check con el mismo stock disponible.

## Eliminacion de una presentacion

Una presentacion solo puede eliminarse si cumple todas las condiciones:

1. `stock == 0`
2. No existe en `StockMovement`
3. No existe en `InvoiceItem`
4. No existe en `MedicalRecordProduct`

La validacion y el delete se ejecutan dentro de `transaction.atomic()` con `select_for_update()` para evitar que un movimiento concurrente pase despues del check.

## Alertas de stock bajo

`GET /api/inventory/products/low-stock/` retorna productos donde al menos una presentacion tiene `stock <= min_stock`.

El frontend ordena los resultados: primero los agotados (`stock = 0`), luego los que estan por debajo del minimo.

## Autocomplete de medicamentos para recetas

`GET /api/inventory/presentations/?product__category=medication&stock__gt=0&search=<q>`

- filtra por categoria y stock > 0
- usa `select_related('product')` para evitar N+1
- ordenado por `product__name, name`
- limitado a 10 resultados
- debounce 300ms en el frontend

El filtro `stock__gt=0` es UX, no seguridad. El backend valida stock al crear `InvoiceItem` con lock.

## Endpoints

| Metodo   | URL                                             | Descripcion                         |
|----------|-------------------------------------------------|-------------------------------------|
| `GET`    | `/api/inventory/products/`                      | Listar productos                    |
| `POST`   | `/api/inventory/products/`                      | Crear producto (con presentacion inicial) |
| `GET`    | `/api/inventory/products/low-stock/`            | Productos con stock bajo            |
| `GET`    | `/api/inventory/products/<id>/`                 | Detalle de producto                 |
| `PUT`    | `/api/inventory/products/<id>/`                 | Editar producto                     |
| `DELETE` | `/api/inventory/products/<id>/`                 | Desactivar producto (soft delete)   |
| `POST`   | `/api/inventory/products/<id>/adjust/`          | Ajustar stock de primera presentacion (compat) |
| `POST`   | `/api/inventory/products/<id>/presentations/`   | Agregar presentacion variante       |
| `GET`    | `/api/inventory/presentations/`                 | Listar presentaciones con filtros   |
| `PATCH`  | `/api/inventory/presentations/<id>/`            | Editar presentacion                 |
| `DELETE` | `/api/inventory/presentations/<id>/`            | Eliminar presentacion (con checks)  |
| `POST`   | `/api/inventory/presentations/<id>/adjust/`     | Ajustar stock de presentacion especifica |
| `GET`    | `/api/inventory/movements/`                     | Historial de movimientos            |
| `GET`    | `/api/inventory/units/`                         | Catalogo de unidades validas        |

## Filtros disponibles (GET /api/inventory/presentations/)

- `product__category=<categoria>` — filtrar por categoria del producto
- `stock__gt=<n>` — presentaciones con stock mayor a n
- `search=<texto>` — busqueda por nombre del producto (icontains)

## Permisos RBAC

| Accion         | Codigo              |
|----------------|---------------------|
| Listar         | `inventory.list`    |
| Ver detalle    | `inventory.retrieve`|
| Crear          | `inventory.create`  |
| Editar         | `inventory.update`  |
| Ajustar stock  | `inventory.update`  |
