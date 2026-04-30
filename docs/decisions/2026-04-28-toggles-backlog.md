# Backlog: Toggles de flujo clínico — estado real vs requerimiento

Fecha de auditoría: 2026-04-28

Este documento registra la brecha entre los 5 toggles definidos en `flujo_citas.txt`
y lo que está implementado actualmente.

---

## Matriz de estado (actualizada — todos implementados)

| Toggle | Campo en OrganizationSettings | Estado | Implementación |
|--------|-------------------------------|--------|----------------|
| Al completar cita, crear historial automáticamente | `auto_create_medical_record` | ✅ Implementado | Lógica en `update_status` (no signal): al pasar a `done`, `MedicalRecord.objects.get_or_create(appointment=...)` dentro del mismo `transaction.atomic()`. |
| Al completar cita, crear factura en borrador automáticamente | `auto_create_invoice_on_done` | ✅ Implementado | Signal `create_draft_invoice_on_done` en `billing/signals.py`. |
| Requerir confirmación antes de iniciar consulta | `require_confirmation_before_start` | ✅ Implementado | En `update_status`: si `to_status == 'in_progress'` y `from_status != 'confirmed'`, lanza `ValidationError`. Aplica a cualquier transición hacia `in_progress`, no solo desde `scheduled`. |
| Permitir citas sin dueño registrado (walk-in anónimo) | `allow_anonymous_walkin` | ✅ Implementado | El endpoint `walk_in` acepta `pet` opcional. Si se omite y el toggle está activo, usa `Pet.objects.get(owner=generic_owner, is_generic=True)`. |
| Mostrar historial de cambios de estado en cada cita | `show_status_change_history` | ✅ Implementado | Modelo `AppointmentStatusChange`. Endpoint `GET /api/appointments/<id>/history/`. UI: panel colapsable en `DetailModal`, carga lazy. |

---

## Bug corregido (2026-04-28)

**Signal `create_draft_invoice_on_medical_record`** (`billing/signals.py:32`) chequeaba
`auto_create_medical_record` en lugar de `auto_create_invoice_on_done`.

El toggle `auto_create_medical_record` controla la *creación automática de historial clínico*,
que no está implementada. La factura al crear un historial sin cita debe respetar
`auto_create_invoice_on_done` porque es el mismo tipo de acción (creación automática de factura).

Corregido: `get_org_setting(org, 'auto_create_invoice_on_done')`.

---

## Frontend: pantalla de configuración

La sección "Flujo Clínico" en `config.jsx` está implementada. Consume `GET /api/organizations/settings/`
al montar y hace `PATCH` individual por toggle al cambiar cada switch. Solo visible para `ADMIN`.

---

## Notas de implementación finales

### auto_create_medical_record
Se implementó dentro de `update_status` (no como signal) porque en ese punto la transición
es un hecho conocido y atómico. Una signal post_save habría reaccionado a cualquier save,
incluyendo ediciones que no cambian el estado.

### require_confirmation_before_start
La condición correcta es `to_status == 'in_progress' and from_status != 'confirmed'`, no
`from_status == 'scheduled'`. Esto bloquea también la transición `no_show → in_progress`
(si alguna vez se habilita) sin necesidad de ajustar la condición.

### allow_anonymous_walkin
El paciente genérico se obtiene con `Pet.objects.get(owner=generic_owner, is_generic=True)`.
No se busca por nombre ("Paciente Anónimo") para evitar acoplamiento al string.
Una cita anónima puede vincularse a un paciente real después con `PATCH <id>/assign-patient/`.

### show_status_change_history
El historial se carga de forma lazy en el frontend (solo al expandir el panel). Si el toggle
está `False`, el panel no se renderiza y el endpoint nunca se llama.
