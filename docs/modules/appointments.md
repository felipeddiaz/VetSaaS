# Modulo: Citas

## Objetivo

El modulo de citas es el punto de entrada al ciclo clinico completo.
Una cita agendada y atendida dispara la creacion del historial clinico y la factura en borrador.

## Estados y transiciones

```
scheduled → confirmed → in_progress → done
    ↓            ↓            ↓
 canceled     canceled     canceled
    ↓            ↓
 no_show     no_show
```

Transiciones validas:

| Desde        | Hacia                                    |
|--------------|------------------------------------------|
| `scheduled`  | `confirmed`, `in_progress`, `canceled`, `no_show` |
| `confirmed`  | `in_progress`, `canceled`, `no_show`     |
| `in_progress`| `done`, `canceled`                       |
| `done`       | (ninguna — terminal)                     |
| `canceled`   | `scheduled` (solo si la fecha no paso)  |
| `no_show`    | `scheduled` (solo si la fecha no paso)  |

Las transiciones invalidas retornan `400` con mensaje explicito.

`confirmed` es opcional. Las clinicas que no confirman citas pasan directamente de `scheduled` a `in_progress`.

## Flujos principales

### Cita normal

1. Recepcion o veterinario crea la cita desde el calendario (`POST /api/appointments/`)
2. La cita nace en `scheduled`
3. Opcionalmente: se confirma (`confirmed`) antes de la atencion
4. Al llegar el paciente: se inicia la consulta (`in_progress`)
5. Al finalizar: se completa (`done`)
6. Desde `done`: el veterinario crea el historial clinico o lo visualiza si ya existe

### Walk-in

El walk-in es para pacientes que llegan sin cita previa.

Endpoint: `POST /api/appointments/walk-in/`

Campos requeridos: `pet`, `veterinarian`, `reason`
Campo opcional: `notes`

Comportamiento:
- la cita se crea directamente en `in_progress` con la hora local actual como hora de inicio
- la duracion es de 30 minutos por defecto
- no valida conflictos de horario (es atencion inmediata)
- el veterinario puede abrir el historial clinico inmediatamente

Si el toggle `allow_anonymous_walkin` está activo, el campo `pet` es opcional. Cuando se omite, el sistema asigna automáticamente la mascota genérica de la organización (`Pet.is_generic=True`). Ver sección "Walk-in anónimo y vinculación de paciente" más abajo.

### Registro rápido + cita (alta de paciente en el momento)

Para pacientes nuevos sin registro previo, el formulario "Nueva cita" ofrece el enlace
**"No encuentro la mascota →"** que expande un panel inline (`QuickPatientForm`).

Endpoint: `POST /api/appointments/create-with-patient/`

Campos requeridos:

| Campo | Descripción |
|-------|-------------|
| `owner_name` | Nombre del dueño |
| `owner_phone` | Teléfono del dueño (exactamente 10 dígitos) |
| `pet_name` | Nombre de la mascota |
| `pet_species` | Especie (valor de `SPECIES_CHOICES`) |
| `veterinarian` | ID del veterinario |
| `date` | Fecha de la cita |
| `start_time` | Hora inicio |
| `end_time` | Hora fin |
| `reason` | Motivo |

Campos opcionales: `pet_sex` (default `unknown`), `pet_birth_date`, `notes`.

Lógica interna con `transaction.atomic()`:

1. `Owner.objects.get_or_create(organization=org, phone=owner_phone)` — si el teléfono ya existe en la organización se reutiliza el owner (cliente que regresa con mascota nueva), de lo contrario se crea con el nombre enviado.
2. `Pet.objects.create(...)` — siempre crea una mascota nueva (incluso si el owner ya existía).
3. `AppointmentSerializer(...).is_valid(raise_exception=True)` — reutiliza toda la validación existente: conflictos de horario, fecha pasada, conversión de timezone.

Si cualquier paso falla (validación, conflicto de horario, teléfono inválido), toda la transacción se revierte. No quedan owners ni mascotas huérfanas.

El frontend valida los campos del formulario antes de llamar al backend (owner_name, owner_phone 10 dígitos, pet_name, species). El botón "Guardar cita" es el mismo que el del flujo normal; el formulario bifurca internamente según si está activo el panel de registro rápido.

### No-show

Cuando el paciente no se presenta y la hora de la cita ya paso, recepcion lo marca manualmente.

Desde `scheduled` o `confirmed` se puede transicionar a `no_show`.

No existe marcado automatico en v1. Es una accion manual confirmada desde el detalle de la cita.

### Walk-in anónimo y vinculación de paciente

Cuando `allow_anonymous_walkin = True` y se omite `pet` en el walk-in, el sistema usa la
mascota genérica de la organización (`Pet.is_generic=True`, propietario `Owner.is_generic=True`).

Ambos registros genéricos se crean automáticamente al crear la organización (signal `post_save`).
Existe exactamente uno por organización.

**Vinculación posterior** — una cita con mascota genérica puede vincularse a un paciente real
mientras no esté en estado `done`:

`PATCH /api/appointments/<id>/assign-patient/` con `{ "pet": <id> }`

Comportamiento:
- Solo aplica cuando `appointment.pet.is_generic = True` (retorna `400` en otro caso).
- No se puede vincular al propio paciente genérico.
- Si existe un `MedicalRecord` abierto vinculado a esa cita, también se actualiza su `pet`.
- El cambio queda registrado en `AppointmentStatusChange` con mensaje descriptivo.

La UI muestra un banner amarillo en el detalle de la cita cuando el paciente es genérico y el
estado no es `done`. El banner desaparece al vincular.

## Cancelacion

Solo se puede cancelar desde `scheduled`, `confirmed` o `in_progress`.

Al cancelar se puede enviar un `cancellation_reason` opcional (texto libre).
El motivo queda almacenado en la cita para reportes.

Reprogramacion:
- si la fecha original no paso: `canceled → scheduled` restaura la cita
- si la fecha ya paso: se debe crear una cita nueva. El sistema retorna `400` con mensaje explicito

## Reglas de creacion

- requiere: mascota, veterinario, fecha, hora inicio, hora fin, motivo
- la mascota y el veterinario deben pertenecer a la misma organizacion
- si el frontend envia `owner_id` en el body, el backend valida que la mascota pertenezca a ese propietario (guardia de integridad, no constraint de modelo)
- la hora de inicio no puede ser en el pasado (comparacion de datetime completo en UTC)
- hora fin debe ser mayor a hora inicio (constraint en DB)
- no puede haber dos citas solapadas para el mismo veterinario en estados `scheduled`, `confirmed` o `in_progress`

## Visibilidad

- `ADMIN`: ve todas las citas de su organizacion
- `VET`: ve todas las citas de su organizacion; la vista por defecto muestra las propias
- `ASSISTANT`: ve todas las citas de su organizacion (lectura)

## Seleccion de mascota en el frontend

La seleccion de mascota en `SidebarForm` y `WalkInModal` usa el componente `SearchSelect`:
- el usuario escribe y se busca contra `GET /api/pets/?search=<texto>` (debounce 300ms)
- el label muestra `<nombre> – <propietario>` cuando el propietario tiene nombre registrado
- no se carga la lista completa de mascotas al montar la pagina

El veterinario sigue siendo un `<select>` nativo (lista pequena, sin problema de escala).

## Auditoria de transiciones (AppointmentStatusChange)

Cada cambio de estado exitoso crea un registro `AppointmentStatusChange`.

Campos:
- `appointment` — FK a Appointment (CASCADE)
- `from_status` / `to_status` — estados antes y después del cambio
- `changed_by` — FK a User (SET_NULL, puede ser null si el cambio fue automático)
- `reason` — texto libre (se usa para `cancellation_reason` y mensajes de vinculación de paciente)
- `created_at` — timestamp automático

El modelo hereda de `OrganizationalModel` (multitenant). Ordenamiento por `-created_at`.

Endpoint: `GET /api/appointments/<id>/history/`

La UI consume este endpoint de forma lazy (solo al expandir el panel "Historial de estados")
y solo lo muestra si `show_status_change_history = True` en `OrganizationSettings`.

## Configuracion de flujo por organizacion

El comportamiento automático al completar citas está controlado por `OrganizationSettings`.
Todos los toggles están implementados en backend y frontend.

Ver ADR `2026-04-28-organization-settings-toggles.md`.

| Toggle | Default | Comportamiento |
|--------|---------|----------------|
| `auto_create_invoice_on_done` | `True` | Al pasar a `done`, crea factura draft automáticamente via signal |
| `auto_create_medical_record` | `True` | Al pasar a `done`, crea `MedicalRecord` vacío en estado `open` (dentro de `update_status`, no via signal) |
| `require_confirmation_before_start` | `False` | Bloquea cualquier transición a `in_progress` si el estado previo no es `confirmed` |
| `allow_anonymous_walkin` | `False` | Permite walk-in sin mascota; usa paciente genérico (`Pet.is_generic=True`) |
| `show_status_change_history` | `True` | Controla visibilidad del panel de historial en la UI de detalle de cita |

Los defaults replican el comportamiento previo para organizaciones existentes.
El fallback cuando no existe registro de settings está en `get_org_setting()` (`apps/organizations/utils.py`).

## Duracion por defecto de slot en el formulario

La duracion por defecto al crear una cita desde el formulario del calendario es **30 minutos**.

- Hora inicio: la hora del slot seleccionado (en punto, ej: 10:00)
- Hora fin: 30 minutos despues (ej: 10:30), salvo en el ultimo slot del dia (20:00) donde se ajusta automaticamente
- El backend acepta cualquier duracion siempre que `end_time > start_time`

El walk-in tambien usa 30 minutos por defecto (comportamiento sin cambio).

## Relacion con otros modulos

- **Historial clinico**: una cita `done` puede tener uno o mas `MedicalRecord` asociados.
  El campo `medical_record_ids` en la respuesta lista los IDs vinculados.
  La consulta clinica se crea desde `/medical-records?pet=<id>&appointment=<id>`.

- **Facturacion**: una cita puede tener una `Invoice` asociada.
  El campo `invoice_id` en la respuesta expone el ID si existe.
  La factura se genera automaticamente segun el toggle `auto_create_invoice_on_done`.

## Endpoints

| Metodo | URL | Descripcion |
|--------|-----|-------------|
| `GET`    | `/api/appointments/` | Listar citas de la organizacion |
| `POST`   | `/api/appointments/` | Crear cita (mascota ya registrada) |
| `POST`   | `/api/appointments/create-with-patient/` | Crear cita + owner + pet en una sola transaccion |
| `POST`   | `/api/appointments/walk-in/` | Registrar walk-in (crea en `in_progress`) |
| `GET`    | `/api/appointments/<id>/` | Detalle de cita |
| `PUT`    | `/api/appointments/<id>/` | Editar cita (campos clinicos) |
| `DELETE` | `/api/appointments/<id>/` | Cancelar cita (soft cancel, solo desde `scheduled` o `confirmed`) |
| `PATCH`  | `/api/appointments/<id>/status/` | Cambiar estado con validacion de transicion |
| `GET`    | `/api/appointments/<id>/history/` | Historial de cambios de estado |
| `PATCH`  | `/api/appointments/<id>/assign-patient/` | Vincular paciente real a cita con paciente generico |

### Permisos RBAC de los nuevos endpoints

| Endpoint | Permiso requerido |
|----------|-------------------|
| `POST create-with-patient/` | `appointment.create` |
| `GET <id>/history/` | `appointment.retrieve` |
| `PATCH <id>/assign-patient/` | `appointment.update` |

### Filtros disponibles (GET /api/appointments/)

- `veterinarian=<id>` — filtrar por veterinario
- `date=YYYY-MM-DD` — filtrar por dia (usa timezone de la organizacion)
- `pet=<id>` — filtrar por mascota

### Filtros disponibles (GET /api/pets/)

- `search=<texto>` — busqueda por nombre (icontains, limite 20)
- `owner=<id>` — filtrar por propietario
- Ambos son combinables: `?search=luna&owner=3`

### Filtros disponibles (GET /api/owners/)

- `search=<texto>` — busqueda por nombre (icontains, limite 20)
- `is_generic=true/false` — filtrar propietario generico (para ventas directas)

## Campos de respuesta

```json
{
  "id": 1,
  "pet": 12,
  "pet_name": "Max",
  "pet_is_generic": false,
  "owner_id": 5,
  "owner_name": "Juan Perez",
  "veterinarian": 3,
  "veterinarian_name": "Dr. Garcia",
  "date": "2026-04-28",
  "start_time": "10:00:00",
  "end_time": "10:30:00",
  "reason": "Vacunacion",
  "notes": "",
  "status": "scheduled",
  "cancellation_reason": "",
  "medical_record_ids": [],
  "invoice_id": null
}
```

`pet_is_generic` — indica si la mascota asignada es el paciente genérico.
El frontend usa este campo para mostrar el banner de vinculación.

## Permisos RBAC

| Accion                  | Codigo                |
|-------------------------|-----------------------|
| Listar                  | `appointment.list`    |
| Ver detalle             | `appointment.retrieve`|
| Crear                   | `appointment.create`  |
| Editar                  | `appointment.update`  |
| Cancelar (DELETE)       | `appointment.destroy` |
| Cambiar estado          | `appointment.update`  |
| Walk-in                 | `appointment.create`  |
| Registro rapido + cita  | `appointment.create`  |
| Ver historial estados   | `appointment.retrieve`|
| Vincular paciente       | `appointment.update`  |

## Timezone

Las fechas y horas se almacenan en UTC en los campos `start_datetime` y `end_datetime`.
Los campos `date`, `start_time` y `end_time` almacenan los valores locales tal como los envia el cliente.

La conversion local→UTC usa el timezone configurado en la organizacion (`org.timezone`).
Si la organizacion no tiene timezone configurado, usa `UTC` como fallback.

Para que el modulo funcione correctamente en clinicas en Mexico, la organizacion debe tener
`timezone = 'America/Mexico_City'` configurado en `/config`.

## Observabilidad

Los eventos de RBAC (acceso denegado, acceso por fallback) se registran automaticamente
por el sistema de permisos `HybridPermission`.

Las transiciones invalidas retornan `400` con `error` descriptivo que incluye el estado actual
y el estado solicitado.
