# ADR: Flujo manual post-done con CTA explícito

**Fecha**: 2026-05-06  
**Estado**: Implementado

## Contexto

El flujo de citas tenía dos tensiones:

1. `Appointment.done` ya es un estado terminal por diseño (`'done': set()` en la máquina de estados).
2. La UX cerraba inmediatamente el modal al completar la cita, por lo que el usuario no veía qué hacer después.

Intentar resolver esto haciendo `done -> in_progress` habría degradado la semántica del estado:
- perder auditabilidad de cuándo terminó realmente la atención
- volver ambiguas métricas, reportes y KPIs basados en `done`
- mezclar correcciones de UX con la lógica de dominio

## Decisión

Se mantiene `done` como estado terminal.

La solución se aplica solo en UX y defaults configuracionales:

1. Antes de pasar `in_progress -> done`, el frontend muestra un `ConfirmDialog` explícito.
2. Tras completar la cita, el modal de detalle permanece abierto.
3. Los CTAs post-`done` se recalculan con la respuesta actual del backend (`medical_record_ids`, `invoice_id`).
4. Los defaults de auto-creación (`auto_create_medical_record`, `auto_create_invoice_on_done`) pasan a `False`.

## Flujo resultante

```text
in_progress
  -> ConfirmDialog("Finalizar atención")
  -> done
  -> modal sigue abierto
  -> CTA:
       - Ver Consulta, si medical_record_ids tiene datos
       - + Crear Consulta Médica, si no existe historial
       - Ver Factura, si invoice_id existe
```

## Consecuencias

Positivas:
- `done` conserva su peso semántico como estado terminal
- desaparece la sensación de "no pasó nada" al completar la cita
- se evita la auto-creación silenciosa de documentos por default
- los CTAs no dependen de estado local stale del frontend

Costos:
- el usuario debe confirmar una acción más antes de cerrar la atención
- el flujo clínico posterior queda explícitamente desacoplado del cierre operativo de la cita

## Relación con otros ADRs

- `2026-04-27-maquina-de-estados-citas.md`: se preserva la terminalidad de `done`
- `2026-04-28-organization-settings-toggles.md`: los toggles siguen existiendo, pero con defaults manuales
- `2026-05-05-p7-lazy-invoice-creation.md`: refuerza que la factura no debe nacer automáticamente por default al completar una cita
