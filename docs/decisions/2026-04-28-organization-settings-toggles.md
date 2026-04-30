# ADR: Configuracion de flujo clinico por organizacion

## Contexto

Distintas clinicas tienen comportamientos operativos distintos.
El codigo tenia comportamientos hardcodeados que no se adaptaban a cada clinica:
- la factura siempre se creaba al completar la cita
- el historial siempre se creaba al crear la consulta sin cita
- no habia forma de requerir confirmacion antes de iniciar una consulta

Estos toggles estaban documentados en `flujo_citas.txt` como requerimiento pendiente.

## Decision

Se introduce el modelo `OrganizationSettings` con un registro por organizacion.

Campos:
- `auto_create_medical_record` (default `True`) — al crear consulta sin cita, genera factura draft automaticamente
- `auto_create_invoice_on_done` (default `True`) — al marcar cita como `done`, genera factura draft automaticamente
- `require_confirmation_before_start` (default `False`) — obliga pasar por `confirmed` antes de `in_progress`
- `allow_anonymous_walkin` (default `False`) — permite walk-in sin propietario registrado
- `show_status_change_history` (default `True`) — expone el historial de cambios de estado en cada cita

Los valores por defecto replican el comportamiento anterior para que organizaciones existentes no noten cambio.

El registro se crea automaticamente al crear la organizacion via signal.
Si no existe (caso de datos anteriores a la migracion), el sistema usa los defaults definidos en `DEFAULT_ORG_SETTINGS`.

El patron de acceso seguro:

```python
def get_org_setting(org, key):
    settings = getattr(org, 'settings', None)
    if settings and hasattr(settings, key):
        return getattr(settings, key)
    return DEFAULT_ORG_SETTINGS[key]
```

Endpoint de configuracion:
- `GET /api/organizations/settings/` — obtener configuracion actual
- `PATCH /api/organizations/settings/` — actualizar uno o varios toggles (solo `ADMIN`)

## Alternativas consideradas

### 1. Campos JSON en el modelo Organization

Considerada pero descartada.

`getattr(org, key)` podria ocultar errores si se agrega un toggle y se olvida el default.
Un modelo separado es mas explicito y permite validacion campo por campo en el serializer.

### 2. Variables de entorno por instalacion

Descartada.

No permite configuracion por organizacion en un sistema multitenant.
Requiere re-deploy para cambiar un toggle.

## Consecuencias

Positivas:
- cada clinica puede ajustar su flujo sin deploy
- los defaults mantienen el comportamiento conocido
- el modelo es extensible: agregar un toggle nuevo es una migracion aditiva

Costos:
- las signals de billing deben consultar settings antes de crear facturas automaticas
- el sistema tiene una dependencia mas en cada accion de alto nivel del flujo clinico
- los tests deben cubrir el fallback cuando no existe registro de settings

## Estado de implementacion por toggle (actualizado 2026-04-28)

| Toggle | Backend | Frontend |
|--------|---------|----------|
| `auto_create_invoice_on_done` | ✅ Signal en `billing/signals.py` | ✅ Toggle en `/config` |
| `auto_create_medical_record` | ✅ Lógica en `update_status` al pasar a `done` | ✅ Toggle en `/config` |
| `require_confirmation_before_start` | ✅ Validación en `update_status` antes de `in_progress` | ✅ Toggle en `/config` |
| `allow_anonymous_walkin` | ✅ Walk-in usa `Pet.is_generic=True` si no se envía `pet` | ✅ Toggle en `/config` |
| `show_status_change_history` | ✅ Modelo `AppointmentStatusChange` + endpoint `GET <id>/history/` | ✅ Toggle en `/config` + panel en detalle de cita |

Ver historial de brechas resueltas en `2026-04-28-toggles-backlog.md`.

## Notas de implementacion

- modelo en `apps/organizations/models.py`
- migration `0005_organizationsettings`
- signal combinada en `apps/organizations/signals.py`: crea `OrganizationSettings`, `Owner(is_generic=True)` y `Pet(is_generic=True, name="Paciente Anónimo")` en `post_save Organization`
- `DEFAULT_ORG_SETTINGS` y `get_org_setting` definidos en `apps/organizations/utils.py` (no en `billing/signals.py` — movido para evitar imports circulares)
- `OrganizationSettingsView` en `apps/organizations/views.py`: solo accesible por `ADMIN`
- `apps/organizations/apps.py` registra la signal via `ready()`
- La UI de toggles está en `config.jsx` sección "Flujo Clínico" (solo visible para `ADMIN`)
