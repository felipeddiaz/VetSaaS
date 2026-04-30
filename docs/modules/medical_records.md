# Modulo: Historial clinico

## Objetivo

El modulo de historial clinico registra el acto medico realizado sobre una mascota y conserva la trazabilidad minima necesaria para auditoria clinica.

Una consulta medica puede incluir:
- mascota
- veterinario responsable
- cita asociada (opcional)
- diagnostico
- tratamiento
- notas
- peso
- productos usados
- servicios usados
- receta medica asociada (opcional)

## Flujo general

### 1. Creacion de consulta

La consulta se crea en estado `open`.

Al crear una consulta sin cita asociada, se genera automaticamente una factura en estado `draft` vinculada a ella via signal.
Si existe cita asociada, la factura ya fue creada al marcar la cita como completada.

Reglas:
- pertenece a una sola organizacion
- el veterinario asignado debe pertenecer a la misma organizacion
- la mascota debe pertenecer a la misma organizacion
- si existe cita asociada, debe pertenecer a la misma organizacion

### 2. Modificaciones mientras esta abierta

Mientras `status = open`, la consulta puede:
- editarse
- agregar o quitar productos usados
- agregar o quitar servicios usados
- crear receta medica asociada

Reglas de acceso:
- `ADMIN`: permitido
- `VET`: solo si es el veterinario asignado a la consulta
- siempre se valida tenant explicito

## Recetas medicas

La receta medica es un documento clinico independiente de la factura.

Reglas de negocio:
- la receta contiene los medicamentos que el veterinario indica clinicamente
- la factura contiene lo que el cliente decide llevar y pagar
- los productos de la receta NO se agregan automaticamente a la factura
- la factura expone `prescription_suggestions`: lista de productos recetados disponibles para que recepcion agregue individualmente segun lo que el cliente confirme
- una consulta `closed` no admite receta nueva ni modificacion de receta existente

Flujo en cobros:
- la factura en draft muestra los servicios e insumos de la consulta como items automaticos
- los productos recetados aparecen como sugerencias opcionales con boton "Agregar" individual
- recepcion agrega solo los que el cliente decide llevar

Regla de frontend:
- la creacion de receta se inicia desde `Historial clinico`
- la consulta y la mascota llegan preseleccionadas y bloqueadas en el modal
- si la creacion falla, el modal permanece abierto y conserva los datos capturados
- al guardar correctamente, el `prescription_id` se actualiza tanto en el detalle abierto como en la lista local de consultas
- el historial muestra el detalle de la receta asociada directamente en la consulta

Validaciones backend:
- `dose` es obligatorio y no puede estar vacio
- `quantity` debe ser mayor a 0
- la receta debe tener al menos un medicamento
- solo se permite una receta por consulta (OneToOneField)
- los productos agregados a una receta deben tener `requires_prescription = true`

La ruta `/prescriptions` se conserva como visor secundario para consulta, reimpresion y mantenimiento historico, pero el flujo principal de prescripcion es desde historial clinico.

Distincion funcional importante:
- receta medica: medicamentos prescritos para administracion posterior o entrega al cliente
- productos consumidos en consulta: stock interno usado durante la atencion clinica

## Seleccion de mascota en el frontend

El modal Nueva Consulta usa `SearchSelect` para la mascota:
- filtra client-side sobre el array `pets` ya cargado para el sidebar (sin llamada extra)
- el campo se deshabilita con placeholder "Cargando mascotas..." mientras `getPets()` no ha resuelto
- el estado `isLoadingPets` controla esto

## Filtros disponibles (GET /api/billing/services/)

- `search=<texto>` — busqueda por nombre (icontains)
- `active=true` — solo servicios activos
- Combinables: `?search=vacu&active=true`

## Productos usados en consulta

Los productos agregados desde consulta son parte del contexto clinico y tambien del financiero.

Reglas actuales:
- se guardan como `MedicalRecordProduct`
- ajustan stock con `select_for_update` para evitar race conditions
- sincronizan un `InvoiceItem` asociado a la factura draft vinculada a la consulta
- si se elimina el producto, se revierte stock y se ajusta o elimina el `InvoiceItem` correspondiente
- productos con `requires_prescription = true` requieren que exista una receta activa para la consulta antes de poderse agregar
- toda la operacion esta envuelta en `transaction.atomic()`: si falla el sync de factura, se revierte el producto

Permiso usado:
- lectura: `medicalrecord.retrieve`
- mutacion: `medicalrecord.update`

No se usa `inventory.create` para este flujo porque el acto que se protege es clinico, no de alta general de inventario.

## Servicios usados en consulta

Los servicios agregados desde consulta forman parte del contexto clinico y financiero de la atencion.

Reglas actuales:
- se guardan como `MedicalRecordService`
- sincronizan un `InvoiceItem` (con FK a `service`, no a `presentation`) en la factura draft
- si se elimina el servicio, se ajusta o elimina el `InvoiceItem` correspondiente
- toda la operacion esta envuelta en `transaction.atomic()`

Permiso usado:
- lectura: `medicalrecord.retrieve`
- mutacion: `medicalrecord.update`

Endpoints:
- `GET /api/medical-records/<id>/services/`
- `POST /api/medical-records/<id>/services/`
- `DELETE /api/medical-records/<id>/services/<service_id>/`

## Cierre de consulta

El cierre de consulta es explicito.

Endpoint:
- `POST /api/medical-records/<id>/close/`

Comportamiento:
- si esta abierta, se cierra
- si ya estaba cerrada, responde `200` sin cambios (idempotente)

Auditoria:
- `status = closed`
- `closed_at`
- `closed_by`

## Reglas de negocio principales

### Consulta cerrada es inmutable

En `closed` solo se permite lectura.

No se permite para ningun rol, incluido `ADMIN`:
- editar consulta
- eliminar consulta
- agregar productos
- quitar productos
- agregar servicios
- quitar servicios

### Consulta con factura no puede eliminarse

Si existe una factura vinculada a la consulta, la eliminacion retorna `403`:

```
Invoice.objects.filter(medical_record=instance).exists()
```

Esto previene que el historial financiero quede huerfano.
La consulta puede cerrarse pero no eliminarse.

Si se necesita eliminar, primero se debe cancelar o eliminar la factura manualmente.

## Validacion de peso

El campo `weight` tiene las siguientes validaciones en el serializer:

- Minimo: `0.01 kg` — no se permiten pesos negativos ni cero
- Cambio brusco (solo en actualizaciones): si el peso nuevo difiere mas del 150% respecto al ultimo registro para esa mascota, el sistema retorna error con mensaje:

  ```
  Cambio brusco de peso: último registro 5.00 kg → nuevo 80.00 kg (1500%). Envía force_weight=true para confirmar.
  ```

- Se puede forzar el cambio enviando `force_weight: true` en el body
- La validacion de cambio brusco solo aplica en `PATCH`/`PUT` (cuando existe `self.instance`), no en `POST`

## Registro de vacunas

El modulo incluye el modelo `VaccineRecord` para registrar el historial de vacunacion de una mascota.

Ver seccion completa abajo.

## Relacion con facturacion

La consulta y la factura son dominios distintos.

La factura puede:
- generarse despues
- cobrarse despues
- cancelarse segun sus reglas propias

Nada de eso define por si mismo el estado clinico de la consulta.

El cierre de consulta no depende del pago de factura.

La relacion modelo es `Invoice.medical_record = OneToOneField` — una sola factura por consulta, constraint en DB.

## Seguridad y control de acceso

El modulo usa dos capas:

### 1. Aislamiento multitenant

Toda operacion se limita a `request.user.organization`.

### 2. RBAC + policy de dominio

RBAC determina si el usuario tiene permiso sobre el recurso.
La policy de dominio (`apps/medical_records/policies.py`) agrega reglas no expresables solo con permisos atomicos:
- ownership del veterinario
- bloqueo por estado `closed`

Funciones de policy:
- `can_modify_medical_record_charges(user, medical_record)`: ADMIN siempre, VET solo si es el asignado
- `can_close_medical_record(user, medical_record)`: ADMIN siempre, VET solo si es el asignado
- `assert_can_modify_charges(user, medical_record, request)`: lanza `PermissionDenied` + emite log, usado en todos los endpoints de cargos

## Vacunas (VaccineRecord)

El estado de vacunacion de una mascota era anteriormente hardcodeado en el frontend mediante una expresion regular sobre el texto del diagnostico (`/vacun/i`). Esto fue eliminado.

Ahora existe el modelo `VaccineRecord` con datos reales.

### Modelo

Campos:
- `pet` — FK a Pet (CASCADE)
- `vaccine_name` — nombre de la vacuna (requerido, no puede estar vacio)
- `application_date` — fecha de aplicacion (no puede ser futura)
- `next_due_date` — fecha de proximo refuerzo (opcional; si se envia, debe ser posterior a `application_date`)
- `applied_by` — FK a User (SET_NULL, opcional)
- `notes` — texto libre
- `medical_record` — FK opcional a la consulta donde se aplico (SET_NULL)

### Estado derivado

El estado no se almacena en DB. Se calcula como propiedad:

| Estado          | Condicion                               |
|-----------------|-----------------------------------------|
| `current`       | `next_due_date` existe y es fecha futura |
| `overdue`       | `next_due_date` existe y ya paso        |
| `no_scheduled`  | sin `next_due_date` (puede ser intencional o no capturado) |

### Validaciones

- `vaccine_name` no puede ser vacio o solo espacios
- `application_date` no puede ser en el futuro
- `next_due_date` debe ser posterior a `application_date` si se envia

### Endpoints

| Metodo   | URL                          | Descripcion                              |
|----------|------------------------------|------------------------------------------|
| `GET`    | `/api/vaccines/`             | Listar vacunas (filtrar por `?pet=<id>`) |
| `POST`   | `/api/vaccines/`             | Registrar vacuna                         |
| `GET`    | `/api/vaccines/<id>/`        | Detalle                                  |
| `PATCH`  | `/api/vaccines/<id>/`        | Editar                                   |
| `DELETE` | `/api/vaccines/<id>/`        | Eliminar                                 |

### Indice

Se usa `Index(fields=['pet', 'vaccine_name'])` para optimizar queries frecuentes de historial de vacunacion por mascota.
El ordenamiento es `-application_date, -id` para desambiguar registros con la misma fecha.

## Observabilidad

Eventos relevantes en logs (`medical_records.events`):
- `MEDICAL_RECORD_CLOSED`
- `MEDICAL_RECORD_CLOSE_IDEMPOTENT`
- `MEDICAL_RECORD_OWNERSHIP_DENIED`
- `MEDICAL_RECORD_CLOSED_DENIED`

Estos eventos permiten auditar intentos de mutacion sobre consultas fuera de policy.
