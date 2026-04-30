# ADR: Maquina de estados del modulo de citas

## Contexto

El modulo de citas existia con tres estados (`scheduled`, `canceled`, `done`) sin ninguna validacion
de transicion. Cualquier status podia enviarse al endpoint y el sistema lo aceptaba sin restriccion.

Al disenar el flujo clinico completo se volvio necesario definir reglas explicitas:
cuando puede iniciarse una consulta, cuando puede cancelarse, y como se registran los pacientes
que no se presentaron. Tambien se necesitaba un flujo distinto para pacientes que llegan sin cita
previa (walk-in), que no pasan por el estado inicial agendado.

## Problema de negocio

Sin maquina de estados el sistema permitia casos imposibles en el negocio real:
- marcar como `done` una cita que nunca se inicio
- cancelar una consulta en progreso sin trazabilidad
- registrar que el paciente no se presento en una cita ya completada

Ademas, el flujo de confirmacion es opcional segun la clinica. Algunas clinicas confirman la cita
por telefono antes de la atencion; otras no lo hacen. El sistema no puede asumir que la confirmacion
es un paso obligatorio.

## Decision

Se implementa una maquina de estados explícita con seis estados y transiciones validadas en el backend.

Estados:
- `scheduled` — cita agendada, estado inicial siempre
- `confirmed` — clinica confirmo que el paciente viene (opcional, segun la clinica)
- `in_progress` — paciente en consulta activa
- `done` — consulta finalizada, inmutable
- `canceled` — cancelada antes de atenderse
- `no_show` — el paciente no se presento

Transiciones permitidas:

```
scheduled   → confirmed, in_progress, canceled, no_show
confirmed   → in_progress, canceled, no_show
in_progress → done, canceled
done        → (ninguna)
canceled    → scheduled  (solo si appointment.date >= hoy en timezone de la org)
no_show     → scheduled  (solo si appointment.date >= hoy en timezone de la org)
```

La transicion `canceled → scheduled` y `no_show → scheduled` replica el estado original de la cita.
Si la fecha original ya paso, el sistema rechaza la operacion con un error explicito y se debe crear
una cita nueva.

La transicion `scheduled → in_progress` directa (sin pasar por `confirmed`) es intencional.
Permite que clinicas que no usan confirmacion inicien la consulta directamente desde el estado agendado.

## Walk-in

El walk-in es un flujo distinto al agendamiento normal.

Un paciente walk-in llega sin cita previa. La recepcion registra la llegada y el sistema crea
la cita directamente en estado `in_progress` con la hora actual como hora de inicio.

El endpoint `POST /api/appointments/walk-in/` requiere: mascota, veterinario y motivo.
La duracion por defecto es 30 minutos. No valida conflictos de horario porque es una atencion inmediata.

## Bug de validacion de fecha

Al crear una cita el sistema comparaba el datetime de inicio (convertido a UTC desde timezone de la org)
contra `now()` (UTC). La logica es correcta.

El problema era configuracion: si la organizacion tenia `timezone = 'UTC'` (valor por defecto)
y la clinica estaba en Mexico (UTC-6), la hora `11:00` local se almacenaba como `11:00 UTC`.
A las 10:45 hora local (16:45 UTC), `11:00 UTC < 16:45 UTC` y la cita era rechazada aunque
la hora local fuera futura.

El fix esta en el frontend: el campo `min` del input de fecha usaba `toISOString().split('T')[0]`,
que retorna fecha UTC, no local. Cambiado a construccion manual de fecha local para evitar
el desfase en timezones con offset negativo.

La raiz del problema sigue siendo que la organizacion debe tener su timezone correctamente configurado
en `/config` para que la conversion local→UTC sea correcta en el backend.

## Alternativas consideradas

### 1. Validar transiciones solo en el frontend

Descartada.

El backend debe ser la fuente de verdad. Cualquier cliente (app movil futura, integraciones, tests)
que llame al endpoint directamente podria dejar la cita en un estado invalido.

### 2. Tabla separada de eventos de estado (event sourcing)

Descartada para v1.

Agrega complejidad de lectura sin beneficio inmediato. El estado actual en el modelo es suficiente
para el volumen de uso actual. Puede revisarse si se necesita auditoria detallada de cada transicion.

### 3. `canceled` como estado terminal estricto

Considerada y parcialmente adoptada.

Si la fecha original ya paso, `canceled` es terminal y se debe crear una cita nueva.
Si la fecha aun no paso, se permite la transicion `canceled → scheduled` porque la clinica
puede haber cancelado por error y querer recuperar la misma cita.

## Consecuencias

Positivas:
- el ciclo clinico tiene trazabilidad completa: agendado → consulta → finalizado
- las clinicas que no confirman citas siguen operando sin friccion
- los no-shows quedan registrados para reportes futuros
- el walk-in tiene un flujo propio que no contamina el agendamiento normal

Costos:
- el frontend debe manejar seis estados y sus variantes de UI
- cualquier codigo que llame a `update_status` con una transicion invalida recibe un `400` explicito
- la deteccion de conflictos ahora incluye citas en `confirmed` e `in_progress`, no solo `scheduled`

## Notas de implementacion

- `ALLOWED_TRANSITIONS` esta definido en `backend/apps/appointments/views.py`
- la validacion de fecha en reprogramacion usa `org_today_local(org)` de `core.datetime_utils`
- el endpoint walk-in esta en `POST /api/appointments/walk-in/` registrado en `config/urls.py`
- el conflict check en el serializer usa `status__in=['scheduled', 'confirmed', 'in_progress']`
- la deteccion de conflictos NO aplica al walk-in porque se crea directamente en `in_progress`
- `cancellation_reason` es un campo opcional que se puede enviar junto al status `canceled`
