# Modulo: Historial clinico

## Objetivo

El modulo de historial clinico registra el acto medico realizado sobre una mascota y conserva la trazabilidad minima necesaria para auditoria clinica.

Una consulta medica puede incluir:
- mascota
- veterinario responsable
- cita asociada (opcional)
- tipo de consulta (`consultation_type`)
- diagnostico
- tratamiento
- notas
- peso (campo heredado; historial detallado en `VitalSigns`)
- signos vitales (modelo `VitalSigns`, append-only)
- productos usados
- servicios usados
- receta medica asociada (opcional)

## Flujo general

### 1. Creacion de consulta

La consulta se crea en estado `open` con `consultation_type = general` por defecto.

**Facturación lazy**: La factura NO se crea automáticamente al crear la consulta. Se crea de forma lazy al agregar el primer cargo (servicio o producto) vía `_sync_invoice_item` → `get_or_create_invoice_for_medical_record()`.

Si la consulta tiene cita asociada y la clínica activa explícitamente el toggle `auto_create_invoice_on_done`, la factura se puede crear al marcar la cita como `done` (ver `docs/modules/appointments.md`). El default actual es `False`.

Reglas:
- pertenece a una sola organizacion
- el veterinario asignado debe pertenecer a la misma organizacion (validado en serializer)
- la mascota debe pertenecer a la misma organizacion (validado en serializer)
- si existe cita asociada, debe pertenecer a la misma organizacion (validado en serializer)

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

### Cierre y analytics anchor (`closed_at`)

Al cerrar via `close_medical_record` view (POST `/api/medical-records/<uuid>/close/`):
- `status` pasa a `closed`
- `closed_at` se setea con `timezone.now()` en el mismo `transaction.atomic()`
- `closed_at_source = 'service'` (provenance — ver ADR `2026-05-09-p9`)
- `closed_by` registra al user

`closed_at` es `editable=False`. Defenses:
1. **Model `save()` guard**: si `status='closed' AND closed_at is None` →
   raise `ValidationError`. Bloquea bypasses tipo `mr.status='closed'; mr.save()`.
2. **CHECK constraint DB** `medicalrecord_closed_status_requires_closed_at`:
   bloquea `queryset.update()`, `bulk_update`, raw SQL.

`closed_at_source` choices:
- `service` — escrito por close view (default para nuevos)
- `fallback` — backfilled desde `updated_at` (migration 0014)
- `legacy` — preexistente al provenance tracking (mark via migration 0015)

> **Deuda técnica:** `close_medical_record` actualmente escribe `closed_at` desde la **view**, no desde un service. Viola ADR p9 (single authoritative writer en `services.py`). El `_source='service'` es técnicamente falso. Migración planificada — ver [deuda A3](../deuda/fase2-prioridad-alta.md#a3---closed_at-writer-fuera-de-service-medical_recordsviewspy432).

### Late-arrival observability (ADR p17 — Día 5)

Después de setear `closed_at`, la view invoca el helper module-level
`_warn_if_late_closed_at(organization, closed_at)` (en el mismo `transaction.atomic()`).

El helper emite `ANCHOR_LATE_ARRIVAL` (WARNING) en el logger `analytics.events`
si `closed_at` cae en un bucket ya frozen para el metric_class `clinical`
(threshold T+2 días). Side-effect free si el bucket está abierto.

Estructura del log (contrato operacional — ver `docs/modules/analytics.md`):

```python
extra = {
    'event': 'ANCHOR_LATE_ARRIVAL',
    'anchor_field': 'closed_at',
    'anchor_value_iso': '<iso8601>',
    'bucket_date_local_iso': '<YYYY-MM-DD>',
    'frozen_threshold_days': 2,
    'age_days': <int>,
    'organization_id': <int>,
    'writer': 'close_medical_record',
    'metric_class': 'clinical',
}
```

Día 5 = warn-only. Hard reject (`LateAnchorError`) queda para Día 7+.

El helper vive temporalmente en `views.py` por consistencia con la deuda A3
(no existe `services.py::close_medical_record_service` todavía). Migrará junto
con el writer cuando esa deuda se cierre.

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
- la receta por si sola NO descuenta stock ni crea items financieros

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
- **tenant validation (ADR p14 — Día 3):** `PrescriptionItemSerializer.validate_product` y `PrescriptionItemWriteSerializer.validate_product` rechazan productos de otra organización con `400 'Acceso inválido.'`. El endpoint `/items/` además exige `requires_prescription=True` **después** del tenant check (no revelar atributos de productos cross-org). Antes de Día 3 no había tenant check → leak en el PDF de receta. Helper local `_validate_same_org` emite `TENANT_VALIDATION_REJECTED` (WARNING). Migración a mixin centralizado planificada — ver [deuda A1](../deuda/fase2-prioridad-alta.md#a1).

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

### Orden de locks (ADR p12)

Para operaciones concurrentes de productos en consulta, se respeta el orden global:

```
MedicalRecord → Invoice → Presentation → InvoiceItem → MedicalRecordProduct
```

**En `MedicalRecordProductListCreateView.perform_create()`:**
1. Lock de `MedicalRecord`
2. Lock de `Invoice` via `get_or_create_invoice_for_medical_record()`
3. Lock de `Presentation`
4. Sync de `InvoiceItem` bajo lock de `Invoice` — usa `apply_invoice_item_quantity_delta(item, +qty)` para incrementos (ADR p13, patrón F())
5. Create/update de `MedicalRecordProduct` con `locked_presentation` y `previous_quantity`

**En `MedicalRecordProductDeleteView.perform_destroy()`:**
1. Lock de `MedicalRecord`
2. Lock de `Invoice` (si existe)
3. Lock de `Presentation`
4. Sync de `InvoiceItem` bajo lock — proyectar `item.quantity - fresh.quantity`; si `<= 0` llamar `item.delete()`, sino `apply_invoice_item_quantity_delta(item, -fresh.quantity)`
5. Re-fetch de instancia con lock antes de `delete()`

Ver ADRs `2026-05-16-p12-concurrency-lock-order-hardening.md` (orden global) y `2026-05-16-p13-day12-concurrency-remediation.md` (helper F() + asserts).

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

### Orden de locks (ADR p12)

Para operaciones concurrentes de servicios en consulta, se respeta el orden global:

```
MedicalRecord → Invoice → InvoiceItem
```

**En `MedicalRecordServiceListCreateView.perform_create()` (ADR p13 — orden corregido):**
1. Lock de `MedicalRecord` con `select_for_update()`
2. Validar tenant del `service` (`serializer.validated_data`)
3. Lock de `Invoice` via `get_or_create_invoice_for_medical_record()`
4. Sync de `InvoiceItem` bajo lock — `apply_invoice_item_quantity_delta(item, +qty)` para incrementos
5. **Por último:** `serializer.save(medical_record=mr)` crea el MRS

El orden importa: el MRS se crea **después** del sync de InvoiceItem para respetar el orden canónico `MR → Invoice → InvoiceItem → MRS`. Antes de ADR p13, MRS se guardaba antes que el lock de Invoice (deviation del orden).

**En `MedicalRecordServiceDeleteView.perform_destroy()`:**
1. Lock de `MedicalRecord`
2. Lock de `Invoice` (si existe)
3. Sync de `InvoiceItem` bajo lock — proyectar `item.quantity - fresh.quantity`; si `<= 0` llamar `item.delete()`, sino `apply_invoice_item_quantity_delta(item, -fresh.quantity)`
4. Re-fetch de instancia con lock antes de `delete()`

Ver ADRs `2026-05-16-p12-concurrency-lock-order-hardening.md` (orden global) y `2026-05-16-p13-day12-concurrency-remediation.md` (MRS create reorder + helper F()).

Endpoints:
- `GET /api/medical-records/<id>/services/`
- `POST /api/medical-records/<id>/services/`
- `DELETE /api/medical-records/<id>/services/<service_id>/`

## Tipo de consulta

El campo `consultation_type` clasifica el acto medico para facilitar el flujo clinico y las validaciones en cierre.

Valores validos:
- `general` — consulta de rutina (default)
- `vaccine` — vacunacion
- `surgery` — cirugia
- `emergency` — emergencia

Reglas:
- editable mientras la consulta esta en `open`
- `surgery` activa validacion adicional en el cierre: requiere `treatment` no vacio

## Signos vitales (VitalSigns)

Los signos vitales se registran como un historial append-only vinculado a la consulta.

Campos:
- `weight` — peso en kg (0.01–200)
- `temperature` — temperatura en °C (30.0–45.0)
- `heart_rate` — frecuencia cardiaca en bpm (20–300)
- `respiratory_rate` — frecuencia respiratoria en rpm (5–120)
- `recorded_by` — usuario que registro los vitales
- `recorded_at` — momento clinico real (editable, no el de ingreso al sistema)

Reglas:
- al menos un campo debe estar presente
- temperatura >= 42.0 °C con FC < 40 bpm es inconsistente clinicamente (error de validacion)
- no hay PATCH ni DELETE: cada registro es inmutable
- bloqueado si la consulta esta `closed`
- la `organization` se asigna automaticamente desde el `medical_record` (incluso si se llama directamente a `.create()`)
- `recorded_at` no puede ser futuro ni mayor a 10 anos en el pasado

El campo `weight` de `MedicalRecord` se mantiene por compatibilidad. Los helpers centrales priorizan `VitalSigns`:
- `_get_last_weight(pet)`: busca el ultimo peso del paciente en `VitalSigns` primero, luego en `MedicalRecord`. Usado para detectar cambios bruscos de peso.
- `get_current_weight(record)`: peso a mostrar en el panel lateral de una consulta. Usa el ultimo vital con `weight != None`, sino cae al campo del registro.

Endpoints:

| Metodo | URL | Descripcion |
|--------|-----|-------------|
| `GET`  | `/api/medical-records/<pk>/vitals/` | Listar vitales de la consulta (paginado) |
| `POST` | `/api/medical-records/<pk>/vitals/` | Registrar nuevos vitales |

Permisos:
- lectura: `medicalrecord.vitals.list` (VET + ASSISTANT)
- creacion: `medicalrecord.vitals.create` (VET solo)

## Panel lateral — Summary

Endpoint de lectura que agrega todos los datos relevantes de una consulta para el panel lateral de la UI. Evita multiples requests independientes.

Endpoint:
- `GET /api/medical-records/<pk>/summary/`

Respuesta:

```json
{
  "patient": { "name", "species", "breed", "birth_date" },
  "last_vitals": {
    "weight", "temperature", "heart_rate", "respiratory_rate",
    "recorded_at", "has_vitals"
  },
  "diagnosis": "...",
  "consultation_type": "general",
  "status": "open",
  "totals": { "subtotal", "tax_amount", "total", "status" },
  "next_vaccine_date": "2026-08-01"
}
```

Notas:
- `last_vitals.weight`: usa `get_current_weight(record)` — prioriza `VitalSigns.weight`, sino cae a `MedicalRecord.weight`
- `totals`: `null` si no existe factura vinculada
- `next_vaccine_date`: proxima vacuna futura de la mascota (de cualquier consulta, no solo esta)
- el endpoint hace una sola query por entidad con `select_related`/`prefetch_related`

Permiso: `medicalrecord.summary.retrieve` (VET + ASSISTANT)

## Cierre de consulta

El cierre de consulta es explícito.

Endpoint:
- `POST /api/medical-records/<id>/close/`

Comportamiento:
- si está abierta, se valida y se cierra
- si ya estaba cerrada, responde `200` sin cambios (idempotente — no re-valida campos)

Validaciones en cierre (solo para consultas que no están ya cerradas):
- `diagnosis` no puede estar vacío (todos los tipos)
- `treatment` no puede estar vacío **excepto** si `consultation_type = vaccine`

**Excepción para vacunación**: Las consultas de tipo `vaccine` pueden cerrarse sin tratamiento documentado, ya que en muchos flujos reales una vacunación no requiere tratamiento adicional.

Si la validación falla, retorna `400` con el campo afectado en formato estandarizado:

```json
{
  "code": "validation_error",
  "errors": {
    "treatment": ["El tratamiento es obligatorio."]
  }
}
```

El frontend mapea estos errores a steps específicos mediante `FIELD_TO_STEP`:

```javascript
const FIELD_TO_STEP = {
  consultation_type: 1,
  diagnosis: 1,
  notes: 1,
  treatment: 2,
  weight: 2
};
```

Auditoría:
- `status = closed`
- `closed_at`
- `closed_by`

Logging:
- `MEDICAL_RECORD_CLOSE_VALIDATION_FAILED` (WARNING) — emitido cuando falla validación de `diagnosis` o `treatment`. Incluye `record_id`, `field`, `user_id`, `organization_id` para auditoría.

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
- registrar nuevos signos vitales

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

- Minimo: `0.01 kg`, maximo: `200.00 kg`
- Cambio brusco: si el peso nuevo difiere mas del 150% respecto al ultimo peso registrado para esa mascota, el sistema retorna error. El ultimo peso se busca con `_get_last_weight(pet)`, que prioriza `VitalSigns` sobre `MedicalRecord`.

  ```
  Cambio brusco de peso: último registro 5.00 kg → nuevo 80.00 kg. Envía force_weight=true para confirmar.
  ```

- Se puede forzar enviando `force_weight: true` en el body (campo declarado explicitamente en el serializer — aparece en el schema OpenAPI)
- La validacion de cambio brusco aplica tanto en actualizaciones de `MedicalRecord` como al registrar nuevos `VitalSigns`
- La funcion `_validate_weight_change(pet, new_weight, force)` es compartida entre `MedicalRecordSerializer` y `VitalSignsSerializer`

**Helper de conversion segura** (frontend): El stepper usa `toNumberOrNull(v)` para convertir valores de input:

```javascript
const toNumberOrNull = (v) => {
    if (v === "" || v == null) return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
};
```

Esto maneja casos edge como `" "` (espacios) → `null`, `"0"` → `0` (válido).

## Captura de signos vitales en el stepper

Los signos vitales viven en el sidebar derecho del stepper y pueden editarse durante todo el flujo visual. Operativamente, el frontend los intenta persistir junto con el avance del stepper cuando detecta cambios.

```
Paso 1: Diagnóstico → POST /medical-records/ → recordId creado
Paso 2: Tratamiento + Receta
  • Los vitales siguen visibles en el sidebar
  • Si cambiaron respecto al ultimo snapshot enviado:
      - PATCH /medical-records/{id}/ (sin weight — peso vive en VitalSigns)
      - POST /medical-records/{id}/vitals/ (si hay campos llenos)
Paso 3: Productos → ...
Paso 4: Facturación → Cerrar
```

**Orden de escritura**:
1. Primero se actualiza el `MedicalRecord`
2. Luego se crean los `VitalSigns` si hay cambios y al menos un campo no-vacio

Si el paso 1 falla, los vitales no se guardan (consistencia atómica por orden, no por transacción DB).

El frontend usa un hash normalizado para no duplicar registros identicos de vitales al avanzar entre pasos.

**Doble fuente de peso**:
- `MedicalRecord.weight` — campo legacy, se mantiene por compatibilidad con datos históricos
- `VitalSigns.weight` — fuente de verdad para signos vitales
- En step 2, solo se envía `weight` a `createVitals()`, no a `updateMedicalRecord()`

**Edición de consulta existente**: Al editar una consulta, el stepper precarga los vitales desde `initialRecord.latest_vitals`, con fallback a `initialRecord.weight` si no hay vitales registrados.

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
- `assert_can_modify_charges(user, medical_record, request)`: gate **billing** — productos y servicios. Lanza `PermissionDenied` + emite log.
- `assert_can_modify_medical_record(user, medical_record, request)`: gate **clinico** — signos vitales y datos no-factura. Valida org + estado `closed`. Semanticamente distinto del anterior.

Importante: no usar `assert_can_modify_charges` para vitales. Son dominios distintos aunque comparten el bloqueo por `closed`.

## Vacunas (VaccineRecord)

El estado de vacunacion de una mascota era anteriormente hardcodeado en el frontend mediante una expresion regular sobre el texto del diagnostico (`/vacun/i`). Esto fue eliminado.

Ahora existe el modelo `VaccineRecord` con datos reales.

### Modelo

Campos:
- `pet` — FK a Pet (**PROTECT** desde PR-4B / ADR p16 — antes CASCADE; justificacion NOM-007/046 retencion vacunal)
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
- `pet` debe pertenecer a la misma organizacion del usuario autenticado (validado en serializer)
- `medical_record` si se envia, debe pertenecer a la misma organizacion (validado en serializer)

### Endpoints

| Metodo   | URL                          | Descripcion                              |
|----------|------------------------------|------------------------------------------|
| `GET`    | `/api/vaccines/`             | Listar vacunas (filtrar por `?pet=<id>`) |
| `POST`   | `/api/vaccines/`             | Registrar vacuna                         |
| `GET`    | `/api/vaccines/<id>/`        | Detalle                                  |
| `PATCH`  | `/api/vaccines/<id>/`        | Editar                                   |

**DELETE removido en PR-4B / ADR p16**: el registro vacunal es documento legal (NOM-007/046) — bloquear borrado directo es consistente con la motivacion del flip `VaccineRecord.pet` → PROTECT. `DELETE /api/vaccines/<id>/` ahora responde **405**. Para anular un registro creado por error, usar `PATCH` (campo `notes`); soft-delete real es deuda Fase 2 A5.

### Indice

Se usa `Index(fields=['pet', 'vaccine_name'])` para optimizar queries frecuentes de historial de vacunacion por mascota.
El ordenamiento es `-application_date, -id` para desambiguar registros con la misma fecha.

## Cascade lockdown (PR-4B / ADR p16)

| FK | Estado | Motivo |
|----|--------|--------|
| `MedicalRecord.pet` | **PROTECT** (era CASCADE) | NOM-046 retencion 5 anos de expediente clinico |
| `VaccineRecord.pet` | **PROTECT** (era CASCADE) | NOM-007/046 retencion vacunal |
| `MedicalRecord.veterinarian` | SET_NULL (sin cambio) | Permite borrado de usuarios; snapshot `vet_name_at_close` es deuda Fase 2 A7 |
| `MedicalRecord.appointment` | SET_NULL (sin cambio) | Cita puede purgarse; expediente sobrevive |
| `MedicalRecordProduct.medical_record` | CASCADE (sin cambio) | Producto consumido pertenece a la consulta — sin MR pierde semantica |
| `MedicalRecordService.medical_record` | CASCADE (sin cambio) | Igual que producto |
| `VitalSigns.medical_record` | CASCADE (sin cambio) | Subrecurso del MR — append-only pero vida atada al padre |

Comportamiento DELETE actual:
- `DELETE /api/medical-records/<uuid>/` con prescriptions/invoices/vitales asociadas → bloqueado por guard `medical_record_has_clinical_content` (403 antes de tocar PROTECT) o **409 Conflict** del handler global si PROTECT dispara.
- `DELETE /api/vaccines/<id>/` → **405 Method Not Allowed** (removido en PR-4B).

## Frontend — patron de submit

El formulario de nueva/editar consulta usa `saving` state para bloquear el boton durante la operacion. Ver ADR `2026-05-02-p2-frontend-ux-hardening.md` para el patron estandar.

## Observabilidad

Eventos relevantes en logs (`medical_records.events`):
- `MEDICAL_RECORD_CLOSED`
- `MEDICAL_RECORD_CLOSE_IDEMPOTENT`
- `MEDICAL_RECORD_OWNERSHIP_DENIED`
- `MEDICAL_RECORD_CLOSED_DENIED`
- `VITAL_SIGNS_CREATED` (INFO) — emitido por `VitalSignsListCreateView.perform_create`

Eventos analytics (logger separado `analytics.events`):
- `ANCHOR_LATE_ARRIVAL` (WARNING) — emitido por `_warn_if_late_closed_at` cuando `closed_at` cae en un bucket frozen (ADR p17 — Día 5)

Estos eventos permiten auditar intentos de mutacion sobre consultas fuera de policy y el registro de vitales.
