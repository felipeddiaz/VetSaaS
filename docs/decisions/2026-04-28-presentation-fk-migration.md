# ADR: Presentacion como FK en lugar de OneToOne

## Contexto

El modelo original tenia `Presentation.product = OneToOneField(Product)`.
Esto forzaba que cada producto tuviera exactamente una presentacion.

En inventario real una clinica maneja el mismo producto en distintos tamanhos o formatos:
- Royal Canin bolsa 10 kg y bolsa 20 kg son el mismo producto con stock, precio y unidad distintos
- Amoxicilina tableta 250 mg y capsula 500 mg son el mismo principio activo con presentaciones distintas

Con OneToOne esto era imposible sin duplicar el nombre del producto.

Ademas, el campo `quantity` ya existia en el modelo como preparacion para Fase 3 (multiples presentaciones con conversion de unidades), lo que indicaba que la intencion arquitectonica siempre fue escalar hacia esto.

## Decision

Se migra `Presentation.product` de `OneToOneField` a `ForeignKey(Product, CASCADE)`.

Cada producto puede tener una o mas presentaciones.
Cada presentacion tiene nombre propio (etiqueta de variante), unidad, precio y stock propios.

Cambios de modelo:
- `related_name` cambia de `presentation` a `presentations`
- se agrega `unique_together = [('product', 'name')]` para prevenir variantes duplicadas
- se agregan indices en `product` y `stock` para optimizar queries de autocomplete y alertas

Cambio de API:
- `GET /api/inventory/products/` retorna `presentations: [...]` (lista) y `presentation` (primera presentacion, para compatibilidad con frontend existente)
- nuevo endpoint `POST /api/inventory/products/<id>/presentations/` para agregar una variante
- nuevo endpoint `PATCH /api/inventory/presentations/<id>/` para editar una variante
- nuevo endpoint `DELETE /api/inventory/presentations/<id>/` con validaciones de integridad
- nuevo endpoint `POST /api/inventory/presentations/<id>/adjust/` para ajuste de stock por presentacion especifica

Reglas de eliminacion de presentacion:
- stock debe ser 0
- no puede existir en `StockMovement`
- no puede existir en `InvoiceItem`
- no puede existir en `MedicalRecordProduct`
- la validacion y el delete estan dentro de `transaction.atomic()` con `select_for_update()` para evitar race conditions

## Alternativas consideradas

### 1. Mantener OneToOne y crear productos separados por tamanho

Descartada.

Obliga a nombrar los productos con el tamanho incluido en el nombre ("Royal Canin 10kg", "Royal Canin 20kg").
No hay relacion entre variantes del mismo producto.
Precio, stock y reportes por producto compuesto son imposibles sin logica adicional.

### 2. Campo JSON de variantes en Product

Descartada.

Impide queries eficientes por stock.
No permite FK desde `InvoiceItem` o `StockMovement` a una variante especifica.
Rompe integridad referencial.

## Consecuencias

Positivas:
- modela la realidad del inventario de una clinica veterinaria
- precios y stock independientes por presentacion
- la relacion `InvoiceItem.presentation` y `MedicalRecordProduct.presentation` ya apuntaban a `Presentation`, no cambian
- el campo `quantity` en Presentation queda disponible para Fase 3 (conversion de unidades entre variantes)

Costos:
- el codigo que accedia a `product.presentation` (singular) debe migrar a `product.presentations.first()` o consultar la presentacion especifica
- el frontend necesita UI para gestionar multiples presentaciones por producto
- la migracion de datos es aditiva: los registros existentes mantienen su unica presentacion con `name = product.name`

## Notas de implementacion

- migration `0013_alter_presentation_options_and_more` en `apps/inventory/migrations/`
- `ProductSerializer` expone `presentations` (many=True) y un campo computado `presentation` (primera, para compat)
- `PresentationCreateSerializer` se usa en el endpoint de agregar variante
- `PresentationDetailView.perform_destroy` ejecuta todos los checks dentro de `transaction.atomic()`
- el campo `is_low_stock` es una property derivada en el modelo, no un campo almacenado
