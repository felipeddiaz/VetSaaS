# Modulo: Logs y eventos del sistema

## Descripcion general

El sistema emite eventos estructurados en formato JSON al stdout (visible en Railway como logs del servidor).
Cada evento tiene un campo `event` con el nombre del evento y campos adicionales con contexto.

Hay dos grupos de eventos segun su origen:

- `rbac.events` — acceso y permisos (quien puede hacer que)
- `medical_records.events` — ciclo de vida de consultas medicas

---

## Eventos de acceso y permisos (`rbac.events`)

### `RBAC_ALLOWED_DB` · INFO

El usuario hizo una accion y el sistema verifico en la base de datos que tiene permiso para hacerla. Todo funciono como debe. Este es el estado normal y saludable de la aplicacion.

Campos: `request_id`, `user_id`, `organization_id`, `role`, `endpoint`, `method`, `required_permission`

Accion requerida: ninguna.

---

### `RBAC_FALLBACK_ALLOWED` · WARNING

El usuario hizo una accion y el sistema le dio acceso, pero no porque la base de datos lo diga — sino porque el codigo tiene una lista de respaldo codificada. Ocurre cuando un usuario no tiene rol asignado en la base de datos y el sistema usa la configuracion estatica como plan B.

Por que es un warning: indica que ese usuario aun no esta completamente migrado al sistema nuevo de permisos. Mientras exista este evento, la migracion RBAC no esta terminada.

Campos: `request_id`, `user_id`, `organization_id`, `role`, `endpoint`, `method`, `required_permission`

Accion requerida: verificar que todos los usuarios tienen rol en DB (`python manage.py seed_permissions`). El gate de Fase 4 requiere que este evento desaparezca durante 7 dias consecutivos.

---

### `RBAC_DENIED` · WARNING

El usuario intento hacer algo que su rol no permite. El sistema lo bloqueo y devolvio un error 403. Puede ser algo legitimo (un asistente intentando crear algo que solo el admin puede) o puede indicar un bug en el frontend que esta llamando endpoints que no deberia.

Campos: `request_id`, `user_id`, `organization_id`, `role`, `endpoint`, `method`, `required_permission`

Accion requerida: si aparece frecuentemente para el mismo `endpoint` y `role`, revisar si hay un bug en el frontend o si falta asignar ese permiso al rol.

---

### `TENANT_MISMATCH_DETECTED` · ERROR

Un usuario autenticado intento acceder a un recurso que pertenece a otra clinica. El sistema lo bloqueo. En operacion normal esto nunca deberia ocurrir — si aparece, es un intento de acceso entre organizaciones que puede ser un bug grave o un intento malicioso.

Campos: `request_id`, `user_id`, `organization_id`, `role`, `endpoint`, `method`, `required_permission`, `resource_org` (organizacion del recurso al que se intento acceder)

Accion requerida: investigar de inmediato. Identificar el `user_id`, el `endpoint`, y el `organization_id` de ambos lados.

---

## Eventos de consultas medicas (`medical_records.events`)

### `MEDICAL_RECORD_CLOSED` · INFO

Una consulta medica fue finalizada correctamente por un usuario autorizado. A partir de este momento queda bloqueada y ya no puede modificarse.

Campos: `user_id`, `organization_id`, `medical_record_id`, `endpoint`, `method`

Accion requerida: ninguna.

---

### `MEDICAL_RECORD_CLOSE_IDEMPOTENT` · INFO

Alguien intento finalizar una consulta que ya estaba cerrada. El sistema lo detecto, no hizo ningun cambio, y respondio con exito igual. Es el comportamiento esperado cuando el frontend llama el endpoint mas de una vez por error.

Campos: `user_id`, `organization_id`, `medical_record_id`, `endpoint`, `method`

Accion requerida: ninguna. Si aparece muy seguido para el mismo registro, revisar si hay un loop en el frontend.

---

### `MEDICAL_RECORD_OWNERSHIP_DENIED` · WARNING

Un veterinario intento agregar o quitar productos/servicios de una consulta que no le pertenece — fue creada por otro veterinario. El sistema lo bloqueo. Los administradores nunca generan este evento porque pueden modificar cualquier consulta.

Campos: `user_id`, `organization_id`, `medical_record_id`, `veterinarian_id` (el vet dueno de la consulta), `endpoint`, `method`

Accion requerida: si aparece seguido para el mismo veterinario, puede indicar un bug en el frontend que no esta filtrando correctamente que consultas puede editar ese vet.

---

### `MEDICAL_RECORD_CLOSED_DENIED` · WARNING

Alguien intento modificar una consulta que ya estaba cerrada. El sistema lo bloqueo. Puede ser que el frontend no actualizo el estado de la consulta en pantalla y el usuario intento editar algo que ya no era editable.

Campos: `user_id`, `organization_id`, `medical_record_id`, `veterinarian_id`, `endpoint`, `method`

Accion requerida: si aparece seguido, revisar si hay una condicion en el frontend que no refleja correctamente el estado `closed` de la consulta.

---

## Regla practica para monitorear en Railway

Filtrar el stdout por nombre de evento:

| Que buscar | Frecuencia esperada | Que significa si aparece |
|---|---|---|
| `TENANT_MISMATCH_DETECTED` | Nunca | Prioridad inmediata — posible incidente de seguridad |
| `RBAC_FALLBACK_ALLOWED` | Decrece hasta cero | Usuarios sin rol en DB — correr `seed_permissions` |
| `RBAC_DENIED` | Bajo, ocasional | Permisos mal configurados o bug en frontend |
| `RBAC_ALLOWED_DB` | La mayoria de requests | Estado normal |

El `request_id` presente en todos los eventos de `rbac.events` permite agrupar multiples eventos del mismo request HTTP para reconstruir que paso exactamente en una solicitud especifica.
