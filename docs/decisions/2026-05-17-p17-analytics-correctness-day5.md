# ADR p17 — Analytics Correctness Remediation (Día 5)

**Date:** 2026-05-17
**Status:** Accepted
**Supersedes:** None (new)
**Related:** ADR 2026-05-09-p9 (analytics anchor authority + provenance),
ADR 2026-05-09-p10 (analytics snapshots and read endpoints)
**Plan reference:** `PLAN_DIA5_ANALYTICS_CORRECTNESS.md` v3

---

## Context

Auditoría pre-beta (`revision_auditoria.md`) identificó cuatro problemas estructurales en la capa analytics:

| # | Problema | Raíz |
|---|----------|------|
| 14 | `compute_daily_metrics` usa `Model.objects` → `TenantManager` filtra `is_active=True` | Ausencia de política explícita sobre visibilidad de filas soft-deleted |
| 15 | `apply_snapshot` sin aislamiento temporal punto-a-punto + writers de anchor sin observabilidad late-arrival | Mezcla de transacción de escritura con ventana de lectura + falta de WARN-only |
| 16 | Dashboard usa tres rutas distintas para métrica de hoy sin contrato explícito | `dashboard_summary` es operacional, no analytics API |
| 17 | `timezone.now()` se relee dentro de cada helper (3-5 sitios por cadena de build) | Comando no captura `now` y lo threadea como parámetro inmutable |

---

## Decision

### 1. ANALYTICS_VISIBILITY — Registry estático con gobernanza dura

Se introduce un registry estático `ANALYTICS_VISIBILITY` en `apps/analytics/services.py` que declara, por modelo, qué política de visibilidad aplica para lecturas analytics.

```python
ANALYTICS_VISIBILITY = {
    'billing.Invoice':                'historical',
    'medical_records.MedicalRecord':  'historical',
    'appointments.Appointment':       'historical',
    'medical_records.VaccineRecord':  'historical',
}
```

**Políticas v1:**
- `'historical'` → `model_cls.all_objects` (cuenta todas las filas, activas o inactivas)

**Gobernanza (BINDING):**

> Modificaciones a `ANALYTICS_VISIBILITY` requieren TODOS los siguientes:
> 1. ADR formal en `docs/decisions/<fecha>-pXX-analytics-visibility-<modelo>.md`.
> 2. Snapshot impact analysis (query diagnóstica, cuántas filas serían incluidas/excluidas, por org, por mes, 12 meses).
> 3. Replay parity validation con fixture que cubra el caso.
> 4. Product Owner sign-off si la política cambia métricas financieras históricas.
> 5. Coordinación de rebuild post-merge si la política cambia números ya snapshotteados.

**Constraints duras del registry:**
- Solo metadata estática: strings, enums, ints.
- Prohibido: lambdas, callables, query-builder objects, dynamic imports, plugin hooks, decoradores.
- Lógica condicional compleja → función nombrada `_compute_<X>_visibility(...)` en `services.py`.
- Cada entrada nueva del enum requiere ADR.

### 2. ANCHOR_REGISTRY — Constante estática separada

Se introduce `ANCHOR_REGISTRY` como `tuple` de `AnchorSpec` dataclasses frozen. `compute_daily_metrics`, `analytics_health`, y `audit_anchor_integrity` derivan sus listas de anchors de aquí. Reemplaza los arrays paralelos duplicados actuales.

Constraints duras idénticas a `ANALYTICS_VISIBILITY`. `ANCHOR_REGISTRY` y `ANALYTICS_VISIBILITY` son dos constantes distintas que NO se fusionan.

### 3. `now` es argumento, no side-effect

`timezone.now()` se llama UNA vez en el entry point (mgmt command o HTTP view). Helpers internos lo reciben como parámetro `now`. `analytics/services.py` module docstring lo enuncia explícitamente.

### 4. Late-arrival observability — WARN-only en Día 5

Cada writer autoritativo de anchor (`pay_invoice`, `confirm_invoice`, `cancel_invoice`, `close_medical_record`) emite `logger.warning('ANCHOR_LATE_ARRIVAL', extra={...})` cuando el anchor cae en un bucket frozen. Hard reject (`LateAnchorError`) queda para Día 7.

Estructura del log (contrato operacional):
```python
extra = {
    'event': 'ANCHOR_LATE_ARRIVAL',
    'anchor_field': 'paid_at',
    'anchor_value_iso': '<iso8601>',
    'bucket_date_local_iso': '<YYYY-MM-DD>',
    'frozen_threshold_days': 2,
    'age_days': <int>,
    'organization_id': <int>,
    'writer': 'pay_invoice',
    'metric_class': 'financial_cash',
}
```

Logger: `analytics.events`. El `event` field es contrato operacional — parte del payload estable que el monitoring stack consume.

**Helper extraction (post-review fix B2):** El bloque de `close_medical_record` se extrajo a un helper module-level `_warn_if_late_closed_at(organization, closed_at)` en `apps/medical_records/views.py`. La view llama el helper inmediatamente después de `medical_record.save(...)`, dentro del mismo `transaction.atomic()`. T8 invoca el helper de producción directamente (sin inline-clone). Deletion-resistance: si el helper se elimina O la llamada se remueve, T8 falla. Ver `apps/analytics/tests/test_late_arrival_observability.py::test_close_mr_backdated_closed_at_emits_warning`.

### 5. `dashboard_summary` NO es analytics API

El endpoint `/api/v1/dashboard/summary/` se declara explícitamente como payload operacional. Las métricas temporales que expone son derivadas de `compute_daily_metrics`. Para reportería financiera auditable se usan los endpoints de series.

El response incluye `metrics_schema_version` y `source: 'live_summary'` a nivel response (no per-KPI).

### 6. Cache invalidation — Invoice signal con `transaction.on_commit`

Se agrega receiver `post_save` para `Invoice` en `dashboard/signals.py` que invalida el cache del summary vía `transaction.on_commit()`. Sin esto, el cache queda stale 30s post-cobro.

---

## Consequences

### Positivas
- Visibilidad de filas soft-deleted es explícita y gobernada, no implícita en el TenantManager.
- Late-arrival tiene observabilidad desde Día 5 (no se posterga).
- `dashboard_summary` tiene contrato claro — no se usa como fuente de reportería financiera.
- Builds son deterministas (mismo `now` → mismo resultado). Tests no son flaky cerca de medianoche.

### Negativas
- `close_medical_record` en `views.py` recibe late-arrival observability temporal — la deuda de ADR p9 (mover a `services.py`) se reconoce pero no se cierra en Día 5.
- Si la auditoría diagnóstica (§12.7 del plan) encuentra rows `is_active=False` que cambian números históricos, se requiere rebuild coordinado con PO.

### Riesgos mitigados
- Sin migraciones de schema.
- Sin nuevos modelos.
- Sin cambios en `apps/core/models.py` (TenantManager intacto).
- Rollback: `git revert` por PR. Blast radius confinado a `apps/analytics`, `apps/dashboard`, `apps/billing/services.py`, `apps/medical_records/views.py`.

---

## Deuda activa reconocida

### ADR p9 violation parcial: `close_medical_record` en views.py

Día 5 agrega observabilidad late-arrival para `MR.closed_at` desde `medical_records/views.py::close_medical_record` vía el helper module-level `_warn_if_late_closed_at`. Esto es **temporal** y **NO cierra la deuda de ADR p9**.

Estado correcto futuro: `apps/medical_records/services.py::close_medical_record_service()` como writer autoritativo. Cuando exista:
- El helper `_warn_if_late_closed_at` migra al service (o se inlina si el writer es uno solo).
- La view delega al service.
- `close_medical_record` desaparece como writer directo de `closed_at`.

**Owner:** medical_records team. **Fecha objetivo:** Día 7 o Sprint 2.
