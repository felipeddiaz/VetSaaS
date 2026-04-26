# ADR: Cierre explicito de consulta medica

## Contexto

El proyecto ya opera sobre datos clinicos, inventario y facturacion con impacto real. Antes de este cambio, una consulta medica no tenia un estado de cierre explicito y varios flujos permitian seguir modificando informacion asociada aun despues de que la consulta ya debia considerarse terminada.

Tambien existia la posibilidad de usar eventos de facturacion como trigger para cerrar la consulta, por ejemplo marcarla como cerrada al pagar una factura.

Ese enfoque es incorrecto porque mezcla dos dominios distintos:
- dominio clinico: consulta, diagnostico, tratamiento, productos y servicios usados en el acto medico,
- dominio financiero: factura, cobro, cancelacion, pago.

## Decision

Se adopta un cierre explicito de consulta mediante una accion dedicada:

- endpoint: `POST /api/medical-records/<id>/close/`
- semantica: idempotente
- comportamiento:
  - si la consulta esta `open`, pasa a `closed`
  - si la consulta ya esta `closed`, responde `200` sin mutar datos

Se agregan campos de auditoria al modelo `MedicalRecord`:
- `status`
- `closed_at`
- `closed_by`

Regla global del sistema:

- una consulta `closed` es clinicamente inmutable
- en estado `closed` solo se permite lectura

Acciones prohibidas sobre una consulta cerrada:
- editar consulta
- eliminar consulta
- agregar productos
- quitar productos
- agregar servicios
- quitar servicios

El control de acceso se resuelve con RBAC dinamico y policy de dominio:
- `ADMIN` puede cerrar o modificar mientras la consulta este abierta
- `VET` solo puede cerrar o modificar si es el veterinario asignado a la consulta
- no se usa `user.role` como fuente de verdad para esta politica

## Alternativas consideradas

### 1. Cierre automatico por factura pagada

Descartada.

Problemas:
- mezcla dominio clinico con financiero
- impide casos reales como seguimiento sin cobro o cobro diferido
- rompe auditoria: una consulta puede quedar clinicamente cerrada aunque la factura siga abierta o se cancele despues

### 2. Permitir excepciones de admin sobre consultas cerradas

Descartada.

Problemas:
- rompe inmutabilidad clinica
- permite manipulacion de historial cerrado
- genera riesgo legal y operativo
- desalinea historial clinico con factura ya emitida o pagada

### 3. Tratar `close` repetido como error `400`

Descartada.

Problemas:
- rompe reintentos seguros del frontend
- obliga a branching innecesario en cliente
- el estado objetivo ya fue alcanzado, por lo que el comportamiento correcto es idempotente

## Consecuencias

Consecuencias positivas:
- separacion clara entre dominio clinico y financiero
- trazabilidad explicita de cierre (`closed_at`, `closed_by`)
- base solida para auditoria y reglas futuras
- menor ambiguedad operativa para usuarios y para el codigo

Costos y restricciones:
- se requiere mantener policy central para ownership y estado
- se requiere mantener cobertura de tests de idempotencia, ownership, closed-deny y concurrencia
- el frontend debe reflejar visualmente que una consulta cerrada no puede mutarse

Notas de implementacion:
- el endpoint usa `transaction.atomic()` y `select_for_update()` para evitar race conditions al cerrar
- los endpoints de cargos sobre consulta usan permisos del recurso `medicalrecord`, no `inventory.create`
- los logs de seguridad relevantes se emiten en `medical_records.events`
