# ADR: Cliente generico para ventas directas

## Contexto

El modelo `Invoice` requeria `owner` y `pet` no nulos.
Esto bloqueaba el flujo cuando alguien compra un producto sin tener una mascota registrada en el sistema
(por ejemplo, un cliente que llega a comprar alimento de paso sin consulta).

El sistema actualmente permite crear facturas de tipo `direct_sale` pero aun asi forzaba
seleccionar un propietario y una mascota registrados.

## Problema de negocio

Una clinica veterinaria vende productos ocasionalmente a personas que:
- no son clientes regulares
- no tienen mascota registrada en el sistema
- compran un producto sin ninguna consulta asociada

Obligarlos a registrar un propietario y mascota falsos es mala UX y genera datos basura.

## Decision

Se crea un propietario generico por organizacion con `is_generic = True`.

- `Owner.is_generic = BooleanField(default=False)`
- constraint parcial en DB: `UniqueConstraint(fields=['organization'], condition=Q(is_generic=True), name='unique_generic_owner_per_organization')`
- se crea automaticamente al crear la organizacion via signal `post_save`
- nombre fijo: "Publico General"
- telefono vacio: la validacion de 10 digitos se salta cuando `owner.is_generic = True`

Cambios en `Invoice`:
- `pet` pasa a ser nullable (`null=True, blank=True`)
- en el serializer: si `owner.is_generic = True`, pet puede omitirse y `invoice_type` se fuerza a `direct_sale`

El frontend expone un boton "Venta a publico general" en el modal de nueva factura que:
- pre-selecciona al propietario generico
- oculta el selector de mascota
- fija el tipo a venta directa

## Alternativas consideradas

### 1. Hacer owner opcional (null=True) en Invoice

Descartada.

Rompe reportes de ventas por cliente.
Complica queries que asumen siempre hay owner.
Hace imposible agregar `PROTECT` en el FK sin logica condicional.

### 2. Crear propietario y mascota placeholder manualmente por cada venta

Descartada.

Genera datos basura en el sistema.
Contamina la lista de propietarios y mascotas.
No es escalable.

## Consecuencias

Positivas:
- las ventas directas sin cliente registrado tienen un flujo limpio
- el propietario generico existe exactamente una vez por organizacion (constraint en DB)
- la lista de propietarios en el frontend puede filtrar el generico con `?is_generic=false`
- el generico siempre esta disponible via `GET /api/owners/?is_generic=true`

Costos:
- `Invoice.pet` es ahora nullable, el codigo que asume siempre existe debe usar `invoice.pet_id` con guard
- el frontend de detalle de factura debe manejar pet ausente

## Extension: mascota generica para walk-in anonimo

La misma signal que crea el `Owner` genérico también crea un `Pet` genérico:

- `Pet.is_generic = BooleanField(default=False)`
- nombre fijo: "Paciente Anónimo"
- vinculado al owner genérico de la organización
- se usa cuando `allow_anonymous_walkin=True` y un walk-in llega sin mascota identificada

La mascota genérica puede vincularse a un paciente real después con
`PATCH /api/appointments/<id>/assign-patient/`.

## Notas de implementacion

- migration `0007_...is_generic` en `apps/patients/migrations/` (Owner.is_generic)
- migration posterior: `Pet.is_generic` (mismo módulo)
- migration `0011_alter_invoice_pet` en `apps/billing/migrations/`
- signal en `apps/organizations/signals.py`: `post_save Organization → get_or_create Owner(is_generic=True)`, `get_or_create Pet(is_generic=True)` y `get_or_create OrganizationSettings`
- `OwnerViewSet.get_queryset` soporta `?is_generic=true/false`
- `InvoiceSerializer.validate` aplica la logica de pet opcional cuando owner es generico
- El frontend filtra mascotas genéricas en búsquedas con `.filter(p => !p.is_generic)`
