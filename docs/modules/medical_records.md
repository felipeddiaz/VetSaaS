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

## Flujo general

### 1. Creacion de consulta

La consulta se crea en estado `open`.

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

Reglas de acceso:
- `ADMIN`: permitido
- `VET`: solo si es el veterinario asignado a la consulta
- siempre se valida tenant explicito

## Productos usados en consulta

Los productos agregados desde consulta son parte del contexto clinico y no solo del financiero.

Reglas actuales:
- se guardan como `MedicalRecordProduct`
- ajustan stock
- sincronizan un `InvoiceItem` asociado a la factura draft vinculada a la consulta
- si se elimina el producto, se revierte stock y se ajusta/elimina el `InvoiceItem` correspondiente

Permiso usado:
- lectura: `medicalrecord.retrieve`
- mutacion: `medicalrecord.update`

No se usa `inventory.create` para este flujo porque el acto que se protege es clinico, no de alta general de inventario.

## Servicios usados en consulta

Los servicios agregados desde consulta tambien forman parte del contexto clinico y financiero de la atencion.

Reglas actuales:
- se guardan como `MedicalRecordService`
- sincronizan un `InvoiceItem` asociado a la factura draft vinculada a la consulta
- si se elimina el servicio, se ajusta o elimina el `InvoiceItem` correspondiente

Permiso usado:
- lectura: `medicalrecord.retrieve`
- mutacion: `medicalrecord.update`

El objetivo es mantener trazabilidad clinica del servicio aplicado y no depender solo del modulo de cobros para reconstruir que paso en la consulta.

## Cierre de consulta

El cierre de consulta es explicito.

Endpoint:
- `POST /api/medical-records/<id>/close/`

Comportamiento:
- si esta abierta, se cierra
- si ya estaba cerrada, responde `200` sin cambios

Auditoria:
- `status = closed`
- `closed_at`
- `closed_by`

## Regla de negocio principal

Una consulta cerrada es inmutable.

En `closed` solo se permite lectura.

No se permite:
- editar consulta
- eliminar consulta
- agregar productos
- quitar productos
- agregar servicios
- quitar servicios

Esta regla aplica para todos los roles, incluido `ADMIN`.

## Relacion con facturacion

La consulta y la factura son dominios distintos.

La factura puede:
- generarse despues
- cobrarse despues
- cancelarse segun sus reglas propias

Nada de eso debe definir por si mismo el estado clinico de la consulta.

Por eso el cierre de consulta no depende del pago de factura.

## Seguridad y control de acceso

El modulo usa dos capas:

### 1. Aislamiento multitenant

Toda operacion se limita a `request.user.organization`.

### 2. RBAC + policy de dominio

RBAC determina si el usuario tiene permiso sobre el recurso.
La policy de dominio agrega reglas no expresables solo con permisos atomicos:
- ownership del veterinario
- bloqueo por estado `closed`

Funciones actuales de policy:
- `can_modify_medical_record_charges(...)`
- `can_close_medical_record(...)`

## Observabilidad

Eventos relevantes en logs:
- `MEDICAL_RECORD_CLOSED`
- `MEDICAL_RECORD_CLOSE_IDEMPOTENT`
- `MEDICAL_RECORD_OWNERSHIP_DENIED`
- `MEDICAL_RECORD_CLOSED_DENIED`

Estos eventos permiten auditar intentos de mutacion sobre consultas fuera de policy.

## Pendientes conocidos

- agregar tests realmente concurrentes para ejercer el cierre en paralelo a nivel de DB, no solo idempotencia observable secuencial
- extender la UI del modal para listar y gestionar servicios usados desde historial clinico, igual que hoy ya se hace con productos
