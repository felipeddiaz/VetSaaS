# Plan Día 5 — Analytics Correctness (Remediación Arquitectónica)

**Versión:** 3 (post-revisión, incorpora 9 + 4 feedback points)
**Status:** Plan aprobado para revisión final. Sin ejecución de código.
**Owner principal:** Backend arquitectura
**Owner semántico del contrato analítico:** Backend lead + Product Owner (joint)
**Pre-beta** | **Issues cubiertos:** #14, #15, #16, #17 (`revision_auditoria.md`)
**Fuentes de verdad:** `revision_auditoria.md`, ADR p9 (anchor authority), ADR p10 (snapshots), `docs/dashboard-metrics-contract.md` v0.4, `docs/modules/analytics.md`, ADR-10, ADR-12.
**Out of scope deliberado:** hard reject `LateAnchorError`, `MetricAdjustments`, KPI `done_to_invoice_conversion`, bump `METRICS_SCHEMA_VERSION`, rebuild masivo histórico sin auditoría previa, `close_medical_record` service migration (ADR p9).

---

## Tabla de contenido

1. Resumen ejecutivo
2. Riesgos arquitectónicos
3. Soluciones peligrosas (qué NO hacer)
4. Diseño recomendado
5. Mapeo capa → issue
6. Estrategia live vs snapshot
7. Estrategia temporal
8. Riesgos de deuda técnica
9. Blast radius
10. Rollback strategy
11. Tests requeridos
12. Verificaciones manuales / staging
13. Out of scope explícito
14. Apéndice — Secuencia recomendada de PRs
15. Apéndice — Historial de revisiones del plan

---

## 1. Resumen ejecutivo

Cuatro problemas estructurales distintos, no cuatro variantes del mismo. Cada uno con fix puntual y boundary propio.

| # | Problema | Raíz arquitectónica | Severidad latente |
|---|---|---|---|
| 14 | `compute_daily_metrics` consume vía `Model.objects` (TenantManager filtra `is_active=True`) | Ausencia de política explícita y owner-ed sobre cómo analytics razona sobre tablas operacionales soft-deletable | Latente hoy. Bomba el día que `Invoice.voided_at` / `MedicalRecord.deleted_by_user` / archived semantics aparezcan. |
| 15 | `apply_snapshot` no provee aislamiento temporal punto-a-punto + writers de anchor pueden producir late-arrivals sin observabilidad | Mezcla de "transacción de escritura" con "ventana de lectura" + falta de WARN-only observability en writers de anchor | Drift silencioso. Snapshots históricos invalidables por admin manual corrections sin trail. |
| 16 | Dashboard usa tres rutas distintas para "métrica de hoy" sin contrato explícito de qué métrica vive dónde | Falta declaración explícita: `dashboard_summary` es operacional, NO analytics API | Drift de definición entre superficies. Frontend usa summary como fuente financiera por inercia. |
| 17 | `timezone.now()` se relee dentro de cada helper (3-5 sitios por cadena de build) | Comando no captura `now` y lo threadea como parámetro inmutable | Boundary-bug pre-medianoche, replays no deterministas, tests dependientes del reloj. |

**Lo que sí funciona y no se toca pre-beta:**
- Anchor authority (ADR p9) — billing OK. **MedicalRecord pendiente** (ver §13 deuda explícita).
- Provenance tracking + lifecycle state + idempotencia bajo no-concurrencia.
- Hard cap 365 días, today-rejected, advisory lock per-org.

**Lo que cambia respecto a la versión inicial del plan (v1):**
1. `ANALYTICS_VISIBILITY` registry estático con **ownership semántico explícito + gobernanza dura**.
2. Observabilidad WARNING-only de late-arrivals en Día 5 (no se posterga a Día 7).
3. `dashboard_summary` declarada explícitamente NO analytics API (docstring + contract).
4. Source/version tagging del summary a **nivel response**, no per-KPI.
5. Tests obligatorios nuevos: "historical replay parity" (extendido a version/lifecycle/provenance) + "late-arrival observability" robusto.
6. ADR p9 violation de `close_medical_record` reconocida explícitamente como deuda activa.

---

## 2. Riesgos arquitectónicos

### 2.1 Drift analytics

**Definicional**
- `dashboard_summary.kpis` (in_progress_now, pending_today, patients_today) no tienen entrada en `dashboard-metrics-contract.md` §3. Métricas no contractadas → consumidor frontend las usa → cualquier cambio rompe sin gate.
- Series histórica usa `compute_daily_metrics(today)` para today; summary usa queries propias para today. Cualquier cambio en una sin la otra crea drift entre paneles del mismo dashboard.

**Manager**
- Cuatro call-sites con decisión implícita sobre `Model.objects` vs `all_objects`. Soft-delete futuro las afecta a todas en silencio. La solución NO es hardcodear `all_objects` everywhere; es introducir policy registry semánticamente owner-ed.

### 2.2 Coupling

- `dashboard/views.py` es a la vez consumidor de analytics y replicador de queries operacionales. Cualquier feature que cruce dashboard expande este coupling.
- `analytics/services.py` y `dashboard/views.py` tienen helpers paralelos (`_provenance_breakdown` vs `_provenance_dist`). Dos source-of-truth implícitos.

### 2.3 Duplicación

- `compute_daily_metrics` y `analytics_health` listan los anchors (paid_at, confirmed_at, cancelled_at, closed_at) en arrays paralelos. La consolidación de `ANCHOR_REGISTRY` (constante estática) resuelve esto.

### 2.4 Lifecycle inconsistency

- `is_active` está en `OrganizationalModel` y por tanto en todas las tablas. `Pet` ya soft-deletea. Cuando un módulo agregue void/archived, las queries analytics dejarán de contar esas filas **sin warning**.
- **Riesgo serio futuro**: `Invoice.voided_at` (cuando exista) no es lo mismo que `Invoice.is_active=False`. Mezclar "existencia histórica" con "validez financiera" es bug semántico. Por eso el registry es **semánticamente owner-ed**, no técnico.

### 2.5 Temporal inconsistency

- `now` se relee dentro de cada helper. Build de 100 orgs que cruza midnight tiene `today_local` distinto para org N que para org 1.
- `_dates_for` resuelve `today - 1` por org localmente, lo cual deja de ser correcto cuando el reloj del comando cruza medianoche durante la corrida.
- `compute_daily_metrics` no recibe `now`. Dos llamadas al mismo `(org, bucket_date)` a 100ms de diferencia con un commit intermedio retornan distintos. Sin test que cubra esto.

### 2.6 Hidden state

- `cache.set('dash:summary:<org>', payload, 30)`. Invalidación por signal en Appointment/MR/Presentation/StockMovement/MRP. **No hay invalidación en Invoice** (audit #16). Owner que cobra ve revenue stale por 30 segundos.
- Cualquier futura métrica que entre al payload del summary y dependa de un modelo cuyas signals no están listadas hereda este bug.

### 2.7 Late-arrival anchors (riesgo nuevo, elevado por feedback)

- Admin Django o data-correction scripts pueden escribir `Invoice.paid_at` con timestamp 5 días atrás → bucket frozen → snapshot histórico invalidado en silencio.
- Sin observabilidad WARNING en writers de anchor, este escenario es invisible hasta que alguien compara con auditoría externa.
- **Severidad:** alta. Día 5 cierra el blindspot con WARN-only; Día 7 introduce hard reject + override command.

### 2.8 Scaling risks

- `_build_series` carga hasta 365 filas/org/request. Bien para v1.
- Granularidad hora en v2: 8760 filas — cap actual lo permite. Documentar límite; sin optimización prematura.

---

## 3. Soluciones peligrosas pre-beta (qué NO hacer)

### 3.1 NO introducir un `AnalyticsManager` mágico

Tres managers por modelo (`objects`, `all_objects`, `all_for_analytics`) = explosión de superficie + drift entre cómo cada módulo decide cuál usar + tests existentes regenerados.

### 3.2 NO recomputar today en cada request del summary sin cache

30 a 50 ms × polling × 20 usuarios concurrentes = saturación DB. Cache 30s correcto. Falta UNA receiver para Invoice; tapar el hueco, no remover el cache.

### 3.3 NO mover `compute_daily_metrics` a `SERIALIZABLE` o `REPEATABLE READ`

Costo en false-positive serialization errors y bloqueo de conexión compartida. Snapshots corren para días pasados; el problema no es isolation level — es `now` capture + late-arrival policy.

### 3.4 NO crear `apps/analytics/utils.py` genérico

Helper-creep. Cada helper privado va como `_<nombre>` dentro de `services.py`.

### 3.5 NO crear fact-table event-sourced

Dual write + reconciliation + complexity. ADR-01 rechazó refactor de módulos en v1; mismo principio aplica.

### 3.6 NO usar cache para "resolver" #16

Convierte problema de **contrato** en problema de **TTL/invalidation** (estrictamente más difícil). Resolver contrato primero.

### 3.7 NO introducir `MetricAdjustments` ahora

Contrato §2.8 lo prevé. v1 no soporta cancel-paid (state machine lo prohíbe). T+2 freeze window es suficiente para los reversals que sí soporta v1. Documentar como deuda.

### 3.8 NO permitir que `ANALYTICS_VISIBILITY` crezca como DSL/policy engine

**Crítico:** `historical_excluding_voided` puede degenerar rápidamente hacia `archived`, `refunded`, `merged`, `transferred`, `reversed`, `synthetic_corrections`, etc. Cada nueva enum es decisión de negocio camuflada como ajuste técnico. Gobernanza dura (§4.2) lo impide.

### 3.9 NO acoplar tests de observabilidad al texto literal del log

`assertLogs(logger_name, level='WARNING')` que verifica `'ANCHOR_LATE_ARRIVAL' in message.getMessage()` rompe si cambias formatter/logger structure. Tests robustos validan **structured fields** del `extra` dict, no el rendering.

---

## 4. Diseño recomendado

### 4.1 Capas y responsabilidades (binding desde el PR de Día 5)

```
┌────────────────────────────────────────────────────────────────────┐
│  L1 — Modelos operacionales (billing/MR/appointments/inventory)    │
│       Source of truth de eventos. Anchors escritos solo por        │
│       services.py del módulo dueño (ADR p9).                       │
│       NOTA: close_medical_record actualmente está en views.py      │
│       (violación parcial ADR p9). Ver §13 deuda activa.            │
└────────────────────────────────────────────────────────────────────┘
                              ▲ leen vía policy registry
                              │
┌─────────────────────────────┴──────────────────────────────────────┐
│  L2 — apps.analytics (capa de agregación)                          │
│       compute_daily_metrics(org, day, *, now)  ← pura, no muta     │
│       apply_snapshot(org, day, *, now, force, user)                │
│       is_bucket_frozen(...)                                        │
│       ANALYTICS_VISIBILITY (policy registry, ownership semántico)  │
│       ANCHOR_REGISTRY (metadata estática de anchors temporales)    │
│       UNICA fuente de verdad para "qué cuenta como métrica".       │
└────────────────────────────────────────────────────────────────────┘
                              ▲ consumido por
                              │
┌─────────────────────────────┴──────────────────────────────────────┐
│  L3 — apps.dashboard (capa de presentación)                        │
│       NO calcula KPIs definidos en contract §3.                    │
│       Solo:                                                        │
│         (a) lee snapshots vía DailyOrgMetrics.for_organization     │
│         (b) delega "today" a compute_daily_metrics(...)            │
│         (c) provee métricas LIVE-ONLY (in_progress_now,            │
│             waiting_room, AR_outstanding, low_stock, mr_open)      │
│             declaradas en contract §3                              │
│       dashboard_summary NO es analytics API (docstring + contract) │
└────────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────┴──────────────────────────────────────┐
│  L4 — Jobs (build_daily_metrics, audit_anchor_integrity)           │
│       Cron-driven. Capturan `now` UNA VEZ y lo threadean.          │
│       Ningún job recomputa lo que un endpoint puede leer.          │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 Reglas de boundary + Gobernanza de `ANALYTICS_VISIBILITY`

**Regla 1.** Cualquier KPI listado en `dashboard-metrics-contract.md` §3 SOLO vive en `apps.analytics`. Si el dashboard quiere mostrarlo, consume vía `compute_daily_metrics(today)` o lee `DailyOrgMetrics`. Prohibido reimplementar `Sum('total') filter=status='paid'` en `dashboard/views.py`.

**Regla 2.** Métricas live-only que el dashboard calcula directamente DEBEN listarse explícitamente en una constante. Hoy: `in_progress_now`, `pending_today`, `patients_today`, `waiting_room_count`, `low_stock_count`, `ar_outstanding`, `medical_records_open_*`. El contract §3 ya cataloga parte; alinear el resto.

**Regla 3 — Policy registry `ANALYTICS_VISIBILITY`.**

```
# apps/analytics/services.py

ANALYTICS_VISIBILITY = {
    'billing.Invoice':                'historical',
    'medical_records.MedicalRecord':  'historical',
    'appointments.Appointment':       'historical',
    'medical_records.VaccineRecord':  'historical',
}

def _analytics_queryset(model_cls):
    """
    Resolves the manager for an analytics-side read per ANALYTICS_VISIBILITY.

    Policies (v1 enum — NO additions without ADR + PO sign-off):
      'historical' → model_cls.all_objects (count all rows, active or inactive)

    Future policies (DO NOT add without going through governance §4.2):
      'historical_excluding_voided' → planned when voided_at column exists
      'historical_excluding_archived' → planned when archived_at column exists
    """
    policy = ANALYTICS_VISIBILITY[_dotted(model_cls)]
    if policy == 'historical':
        return model_cls.all_objects
    raise NotImplementedError(f"Policy {policy!r} requires ADR.")
```

**Gobernanza del registry (BINDING):**

> Modificaciones a `ANALYTICS_VISIBILITY` requieren TODOS los siguientes:
>
> 1. **ADR formal** en `docs/decisions/<fecha>-pXX-analytics-visibility-<modelo>.md`. Sin ADR, el PR se rechaza.
> 2. **Snapshot impact analysis**: query diagnóstica que reporte cuántas filas existentes serían incluidas/excluidas bajo la nueva política, por org, por mes de los últimos 12 meses. El reporte se anexa al ADR.
> 3. **Replay parity validation**: ejecución de `test_historical_replay_parity` con fixture que cubra el caso "fila marcada bajo la nueva política", verificando que snapshot reconstruido = live recomputed bajo la nueva política.
> 4. **Product Owner sign-off** si la política cambia métricas financieras históricas (revenue, AR, invoices_paid_count). Sin firma del PO, el PR no se mergea — los números históricos son contrato de auditoría, no decisión de ingeniería.
> 5. **Coordinación de rebuild** post-merge si la política cambia números ya snapshotteados. Ventana de mantenimiento documentada; `--force` con `--reason='<ADR_id>'` en el run.

**Constraints duras del registry (también binding):**
- Solo metadata estática: strings, enums, ints.
- **Prohibido**: lambdas, callables, query-builder objects, dynamic imports, plugin hooks, decoradores que registren entradas en runtime.
- Lógica condicional compleja → función nombrada `_compute_<X>_visibility(...)` en `services.py`. Sin abstracción genérica.
- Cada entrada nueva del enum requiere ADR (regla 1 arriba). No agregar `historical_excluding_X` sin pasar por el proceso.

**Razón de la gobernanza dura.** El registry parece técnico pero su contenido es **semántica de negocio camuflada**. "¿La factura voided cuenta en el revenue histórico del mes pasado?" es pregunta para el PO y el contador, no para el desarrollador. Documentar este gate ahora evita que en 2 meses un PR de 10 líneas modifique silenciosamente los KPIs del trimestre.

**Regla 4 — `ANCHOR_REGISTRY` (constante separada).**

```
# apps/analytics/services.py

@dataclass(frozen=True)
class AnchorSpec:
    model: str               # 'billing.Invoice'
    anchor_field: str        # 'paid_at'
    source_field: str        # 'paid_at_source'
    status_filter: dict      # {'status': 'paid'}
    metric_class: str        # 'financial_cash'

ANCHOR_REGISTRY = (
    AnchorSpec(model='billing.Invoice',
               anchor_field='paid_at',
               source_field='paid_at_source',
               status_filter={'status': 'paid'},
               metric_class='financial_cash'),
    # ... etc
)
```

`compute_daily_metrics`, `analytics_health`, `audit_anchor_integrity` derivan sus listas de aquí. Reemplaza los dos arrays paralelos actuales.

Constraints duras (idénticas al `ANALYTICS_VISIBILITY`):
- Metadata estática. Sin callables. Sin runtime registration.
- Agregar entrada nueva: ADR + análisis de impacto.
- `ANCHOR_REGISTRY` y `ANALYTICS_VISIBILITY` son **dos constantes distintas** que comparten principio (metadata estática) pero NO se fusionan. Una habla de anchors temporales; otra de visibilidad de filas. Mezclar es invitación a DSL creep.

**Regla 5 — `now` es argumento, no side-effect.**

`timezone.now()` se llama UNA vez en el entry point (mgmt command o HTTP view). Helpers internos lo reciben como parámetro. `analytics/services.py` docstring lo enuncia explícitamente.

### 4.3 Source-of-truth por métrica

| Métrica | SoT (capa) | Fuente cálculo | TTL/freeze |
|---|---|---|---|
| `revenue_paid` (historia) | `DailyOrgMetrics.revenue_paid` | snapshot nightly | T+2 frozen |
| `revenue_paid` (today) | `analytics.compute_daily_metrics` | live, sin cache propio | per-request |
| `revenue_accrual` (historia/today) | idem | idem | idem |
| `invoices_paid_count` | idem | idem | idem |
| `appointments_total/done/no_show` (historia) | `DailyOrgMetrics.*` | snapshot | T+1 frozen |
| `appointments_total/done/no_show` (today) | `compute_daily_metrics` | live | per-request |
| `medical_records_closed` (historia) | `DailyOrgMetrics.medical_records_closed` | snapshot | T+2 frozen |
| `medical_records_closed` (today) | `compute_daily_metrics` | live | per-request |
| `appointments_in_progress_now` | `dashboard.views._dashboard_summary` | live, cache 30s | invalidate on Appointment write |
| `waiting_room` | idem | live, cache 30s | idem |
| `ar_outstanding` | idem | live, cache 30s | **invalidate on Invoice write (post-commit)** ← agregar en Día 5 |
| `low_stock_count` | idem | live, cache 30s | invalidate on Presentation/StockMovement write |
| `medical_records_open` / `_stale_24h` / `_without_diagnosis` | idem | live, cache 30s | invalidate on MR write |

---

## 5. Mapeo capa → issue

### Issue #14 — Visibility policy

| Acción | Capa | Owner |
|---|---|---|
| Definir `ANALYTICS_VISIBILITY` registry estático con gobernanza dura (§4.2) | `apps.analytics.services` | Backend lead + PO (joint semantic owner) |
| Helper `_analytics_queryset(model_cls)` | `apps.analytics.services` | Backend |
| `compute_daily_metrics` consume `_analytics_queryset(Invoice).filter(...)` en vez de `Invoice.objects.filter(...)` | `apps.analytics.services` | Backend |
| `analytics_health._provenance_dist` delega a `analytics.services._provenance_breakdown` | `apps.dashboard.views` | Backend |
| Test: row con `is_active=False` que califica para `revenue_paid` cuenta hoy bajo `historical` | `analytics.tests.test_snapshot_v1` | Backend |
| Test parametrizado con policy `historical_excluding_voided` skipped hoy (marker `# v2 future`) — placeholder para el día que se agregue la policy | idem | Backend |

### Issue #15 — Snapshot consistency + late-arrival observability

| Acción | Capa | Owner |
|---|---|---|
| `build_daily_metrics.handle` captura `now=timezone.now()` una vez, threadea | comando | Backend |
| `apply_snapshot(org, d, now=now)` — el comando pasa `now` (firma ya lo acepta) | comando | Backend |
| `compute_daily_metrics` acepta `*, now=None` para simetría (cálculo no depende de `now`, contrato uniforme) | `apps.analytics.services` | Backend |
| **Observabilidad late-arrival WARN-only.** En writers de anchor: `pay_invoice`, `confirm_invoice`, `cancel_invoice` (todos en `billing/services.py`), evaluar `is_bucket_frozen(metric_class, anchor_date_local, org)` post-write y emitir `logger.warning('ANCHOR_LATE_ARRIVAL', extra={...})` con campos estructurados | `billing.services` | Backend |
| Para `MedicalRecord.closed_at`: emitir el mismo log desde `medical_records/views.py::close_medical_record`. **Marcar explícitamente como temporal**: la observabilidad migra a `medical_records/services.py::close_medical_record_service()` cuando ese service exista (ADR p9 compliance). Ver §13. | `medical_records.views` | Backend (con disclaimer ADR p9) |
| Estructura del log obligatoria: `{event: 'ANCHOR_LATE_ARRIVAL', anchor_field, anchor_value_iso, bucket_date_local_iso, frozen_threshold_days, age_days, organization_id, writer, metric_class}` — **`event` field es contrato operacional**, parte del payload estable que monitoring stack consume | logger `analytics.events` | Backend + DevOps |
| Hard reject (`LateAnchorError`) queda fuera Día 5. Día 7 lo introduce con override command. | (Día 7) | (futuro) |
| Test boundary: `pay_invoice` con `paid_at` 5 días atrás emite el log con todos los campos del `extra` correctos | `billing.tests` o `analytics.tests` (preferir el último para ownership) | Backend |
| Documentar en `analytics.md` + `contract §2.9` que Día 5 = warn-only; hard reject = Día 7+ | docs | Backend |

### Issue #16 — Dashboard live + snapshot

| Acción | Capa | Owner |
|---|---|---|
| Auditar `dashboard_summary` y catalogar cada campo del payload: live-only, snapshot-backed, o híbrido | Backend + contrato | Backend lead |
| Para métricas snapshot-backed que el summary expone live (revenue, etc.): cambiar a `compute_daily_metrics(today)`, eliminar queries inline duplicadas | `apps.dashboard.views` | Backend |
| Agregar `invalidate_on_invoice_change` receiver con `transaction.on_commit(...)` (post-commit, no `post_save` directo) | `apps.dashboard.signals` | Backend |
| Documentar `/dashboard/summary/` en docstring + contract como **NO analytics API** (§6.4) | docs + código | Backend lead |
| Response-level tagging: `{metrics_schema_version: 1, source: 'live_summary', kpis: {...}, ...}` — no per-KPI source field | `apps.dashboard.views` + frontend nota | Backend |
| Test consistency: `/operations/series/?include_today=true` y `dashboard_summary` reportan el mismo `revenue_paid` para today | `dashboard.tests.test_consistency` (nuevo) | Backend |

### Issue #17 — `timezone.now()` múltiple

| Acción | Capa | Owner |
|---|---|---|
| Comando captura `now` una vez | `build_daily_metrics.handle` | Backend |
| `_dates_for(org, opts, *, now)` acepta y usa `now` | comando | Backend |
| `apply_snapshot(org, d, *, now, force, user)` propaga `now` a `is_bucket_frozen` y `org_today_local` | `apps.analytics.services` | Backend |
| `compute_daily_metrics` acepta `now=None` por simetría (cálculo no lo usa) | servicio | Backend |
| Endpoints que llaman `compute_daily_metrics(today)` capturan `now` en la view y pasan `now=now` para `today_local = org_today_local(org, now=now)` consistente con el response | `dashboard/views.py` | Backend |
| Test boundary midnight: `--mock-now=2026-05-15T23:59:50Z` y `--mock-now=2026-05-16T00:00:10Z` rebuildean idéntico. Hook `--mock-now` activable solo bajo `DEBUG=True` o `pytest`. | `analytics.tests.test_cron_safety` (extender) | Backend |

---

## 6. Estrategia live vs snapshot

### 6.1 Política

| Categoría | Política | Razón |
|---|---|---|
| Temporal-bucketed (revenue, appointments_done/total, mr_closed) | Snapshot para días cerrados; live (`compute_daily_metrics`) para today | Histórico inmutable + today fluido. Contract §4.2. |
| Point-in-time (in_progress_now, AR_outstanding, low_stock, mr_open, vaccines_due_window) | Live siempre. Sin snapshot. Cache 30s con invalidación por signal. | "El AR del 14 de mayo" no tiene sentido — AR es ahora. |
| Composed/conversion (done_to_invoice_conversion) | Snapshot mutable 14 días, frozen después. Today via live. | Lazy invoice tail. **Out of scope Día 5.** |

### 6.2 Anti-drift rules

1. **Una métrica = una función.** Cada KPI del contract §3 tiene exactamente una función pura en `analytics.services` que la calcula.
2. **Dashboard prohibido reimplementar.** Si `dashboard/views.py` contiene `Sum('total')`, `.filter(status='paid'|'confirmed'|'closed')` con anchor temporal, code review rechaza salvo justificación documentada (point-in-time live, listada en §4.3).
3. **`live` y `snapshot` siempre tagged.** Ya está en series. Summary lo lleva a nivel response (§6.5).
4. **Schema version visible.** `metrics_schema_version` en cada datapoint de series y a nivel response del summary.

### 6.3 Política híbrida

Híbrida = "snapshot histórico + cómputo live para today". Patrón aceptable porque el código que produce el live (`compute_daily_metrics`) **es el mismo** que produjo los snapshots históricos. Garantía matemática: la curva no salta cuando today se vuelve ayer (el live se promueve a snapshot).

**Regla:** un endpoint híbrido SIEMPRE usa `compute_daily_metrics` para today, jamás una query inline distinta.

### 6.4 `dashboard_summary` NO es analytics API

Docstring obligatorio del endpoint:

```
/dashboard/summary/ is the operational dashboard payload. It mixes
temporal KPIs (delegated to apps.analytics.compute_daily_metrics(today))
with point-in-time live aggregates (AR_outstanding, low_stock, mr_open).

This endpoint is NOT a source of truth for financial reporting or
analytical queries. For audited or historical financial data, use:
  - /dashboard/financial/series/    (snapshots + today via analytics)
  - /dashboard/operations/series/   (idem)

Drift between /dashboard/summary/ and the series endpoints for the
temporal KPIs IS A BUG — the temporal KPIs in summary MUST come from
compute_daily_metrics.

Adding new KPIs to this endpoint that are NOT pre-declared as
live-only in dashboard-metrics-contract.md §3 requires an ADR.
```

Y en `dashboard-metrics-contract.md`, nueva nota en §3:

> `/dashboard/summary/` es payload operacional. Las métricas temporales que expone son **derivadas** de `compute_daily_metrics`. Cualquier frontend que necesite reportería financiera consulta `/dashboard/financial/series/`. Modificaciones al summary que rompan esta política requieren ADR.

### 6.5 Source consistency en summary

**Decisión:** NO agregar `source` por KPI al summary. Agregar a **nivel response**:

```json
{
  "metrics_schema_version": 1,
  "source": "live_summary",
  "kpis": { ... },
  "timeline": [...],
  "waiting_room": [...],
  "backlog": {...},
  "stock_alerts": [...],
  "effective_timezone": "America/Mexico_City",
  "local_today": "2026-05-17"
}
```

Frontend lee `metrics_schema_version` y `source` una vez por response. Si en el futuro un KPI del summary se vuelve snapshot-backed, se introduce `source` específico solo para ese campo (cambio aditivo, no breaking).

**Razón:** agregar `{value, source}` por cada KPI infla el JSON y rompe el shape mental ("AR_outstanding es un número"). Response-level tag es honesto y barato.

---

## 7. Estrategia temporal

### 7.1 Política de `now`

- Captura una vez por boundary (mgmt command o HTTP request).
- Propagación explícita: parámetro `now` a través de toda la cadena.
- Helpers internos jamás llaman `timezone.now()`.
- Documentado en `analytics/services.py` module docstring.
- Tests inyectan `now` — sin `now=` los tests son flaky cerca de medianoche.

### 7.2 TZ frozen en snapshots

Ya implementado (`org_timezone_at_snapshot` en INSERT). Lo que falta:

- Documentar explícitamente: **cambio de TZ en `Organization` no reescribe snapshots existentes**.
- Rebucketing por TZ change: mgmt command separado `rebucket_snapshots --org=X --new-tz=Y --reason=...`. **Out of scope Día 5.**

### 7.3 Snapshot windows

- v1 freeze window = T+2 days. Inmutable salvo `--force`.
- Today: nunca snapshotteado, siempre live.
- Yesterday: snapshot al ejecutar cron nightly.

### 7.4 Determinismo de replays

Definición: "tres corridas consecutivas de `build_daily_metrics` con el mismo `--mock-now` producen state idéntico (mismos `built_at`, mismas filas, 0 audit rows nuevos en 2do y 3er run)."

Test: `test_cron_safety.py` extendido con caso mock-now-near-midnight.

---

## 8. Riesgos de deuda técnica

### Riesgos que este plan PUEDE introducir si se ejecuta mal

1. **Helper creep en `analytics/services.py`** — al consolidar `ANCHOR_REGISTRY`, tentación de meter `audit_anchor_integrity` ahí. Mantenerlo separado.
2. **Doble fuente live para today** — si por error se mantiene `dashboard_summary` con queries propias Y se agrega cómputo via `compute_daily_metrics`, drift garantizado. PR debe **eliminar** queries inline, no agregar las correctas en paralelo.
3. **Abstracción prematura: `MetricRegistry`** — para 7 KPIs es overkill. Constante `ANCHOR_REGISTRY` simple basta.
4. **Coupling con frontend** — `source` y `lifecycle_state` ya están en series. Antes de tocar summary shape, confirmar back-compat. El cambio aditivo (`metrics_schema_version`, `source: 'live_summary'` a nivel response) NO es breaking.
5. **Hidden invalidation rules con `post_save` directo** — `post_save` puede disparar antes del commit visible bajo `select_for_update + atomic`. **Obligatorio**: `transaction.on_commit(lambda: cache.delete(...))`. Sin esto, otro request puede recachear datos viejos justo antes del commit.
6. **`ANALYTICS_VISIBILITY` creciendo a DSL** — gobernanza dura §4.2 lo impide. Code review automático: cualquier PR que agregue policy enum sin ADR linkeado se rechaza.
7. **Tests frágiles a cambios de logging infra** — usar helper `assert_late_arrival_logged(captured_logs, *, anchor_field, age_days_min, organization_id)` que valide los **campos estructurados** del `extra` dict, no el rendering del mensaje.

### Lo que este plan EVITA introducir

- Nuevo framework de analytics. Confirmado.
- Event-sourced metric facts. Confirmado.
- Materialized views. Confirmado.
- Singleton MetricsService class. Confirmado.
- Background workers / queues. Confirmado.
- Redis layer dedicado. Confirmado.
- `analytics_utils.py` genérico. Confirmado.

---

## 9. Blast radius

| Módulo | Cambios | Riesgo |
|---|---|---|
| `apps.analytics.services` | `compute_daily_metrics` cambia a `_analytics_queryset`; firma `apply_snapshot` ya acepta `now`; `ANCHOR_REGISTRY` y `ANALYTICS_VISIBILITY` nuevos | Medio — tests existentes deben pasar; 1 test nuevo cubre soft-delete inclusion |
| `apps.analytics.management.commands.build_daily_metrics` | Captura `now`, threadea | Bajo — cambio mecánico |
| `apps.dashboard.views` | Reemplazar queries inline por `compute_daily_metrics(today)`; eliminar `_provenance_dist` (delegate); agregar `metrics_schema_version` + `source: 'live_summary'` a response | Medio — shape del response cambia aditivamente |
| `apps.dashboard.signals` | Agregar receiver Invoice con `transaction.on_commit` | Bajo |
| `apps.billing.services` | Agregar log `ANCHOR_LATE_ARRIVAL` post-write en `pay_invoice`, `confirm_invoice`, `cancel_invoice` | Bajo |
| `apps.medical_records.views.close_medical_record` | Agregar mismo log. Disclaimer ADR p9 (temporal) | Bajo |
| `docs/dashboard-metrics-contract.md` | Actualizar §2.6 (visibility policy), §2.9 (warn-only Día 5), §3 (live-only del summary), §3 nota /dashboard/summary | Sin riesgo |
| `docs/modules/analytics.md` | Documentar `ANALYTICS_VISIBILITY` + gobernanza + `now` policy + late-arrival observability | Sin riesgo |
| `docs/decisions/` | ADR nuevo `2026-05-XX-p17-analytics-correctness-day5.md` | Sin riesgo |
| `apps.billing`, `apps.medical_records` (modelos), `apps.appointments`, `apps.inventory` | **Sin cambios** | Cero |
| `apps.core.models` (TenantManager) | **Sin cambios** | Cero |
| Migraciones de schema | **Ninguna** | Cero |
| Frontend | Cambio aditivo (nuevos campos response-level). NO breaking. | Bajo |

Confinado a `apps.analytics`, `apps.dashboard`, `apps.billing.services`, `apps.medical_records.views`. Sin migraciones. Sin breaking del frontend.

---

## 10. Rollback strategy

### Reversibilidad por commit

| Commit | Reversible vía | Riesgo de rollback |
|---|---|---|
| `analytics.services`: `ANALYTICS_VISIBILITY` + `_analytics_queryset` | `git revert` | Cero — pure code change. Snapshots ya escritos no se tocan. |
| `build_daily_metrics`: threading de `now` | `git revert` | Cero |
| `analytics.services`: `compute_daily_metrics` consume registry | `git revert` | Cero |
| `dashboard.views`: delegate a `compute_daily_metrics` | `git revert` | Cero (vuelve a queries inline) |
| `dashboard.views`: response-level tagging | `git revert` | Cero (cambio aditivo, frontend no rompe si los campos desaparecen) |
| `dashboard.signals`: receiver Invoice con on_commit | `git revert` | Cero (cache vuelve a estar stale 30s post-cobro — estado actual pre-plan) |
| `billing.services`: log late-arrival | `git revert` | Cero |
| `medical_records.views.close_medical_record`: log late-arrival | `git revert` | Cero |
| `ANCHOR_REGISTRY` | `git revert` | Cero (vuelven los dos arrays paralelos) |
| Docs / ADR | `git revert` | Cero |

### Sin migraciones, sin schema changes

Día 5 = puro código. No hay `0017_alter_*` que revertir. No hay backfill obligatorio. Si la auditoría diagnóstica (§12.7) muestra rows `is_active=False` que cambian los números, el rebuild histórico se decide post-merge con PO.

### Feature flag

No es necesaria. Tests de consistencia + replay parity cubren los cambios antes de merge.

---

## 11. Tests requeridos

### Cobertura mínima para mergear

| Test | Fichero | Cubre |
|---|---|---|
| Snapshot incluye filas `is_active=False` calificadas | `analytics/tests/test_snapshot_v1.py` (extender) | #14 |
| `compute_daily_metrics` idempotente bajo no-writes | `analytics/tests/test_snapshot_v1.py` (extender) | #15 base |
| `compute_daily_metrics` NO es idempotente bajo writes intermedios (contrato explícito de no-isolation) | `analytics/tests/test_snapshot_v1.py` | #15 contrato |
| Tres corridas seguidas de `apply_snapshot(..., now=fixed)` producen mismo `built_at` en run 2 y 3 | `analytics/tests/test_snapshot_v1.py` | #15 + #17 |
| Boundary midnight: `--mock-now=23:59:50` y `--mock-now=00:00:10` rebuildean idéntico | `analytics/tests/test_cron_safety.py` (extender) | #17 |
| `dashboard_summary.ar_outstanding` se invalida tras `pay_invoice` (Invoice signal con `on_commit`) | `dashboard/tests/test_summary_endpoint.py` (extender) | #16 |
| `/operations/series/?include_today` y `dashboard_summary` reportan mismo `revenue_paid` para today | `dashboard/tests/test_consistency.py` (NUEVO) | #16 |
| Soft-delete de un MR cerrado: snapshot mantiene `medical_records_closed` correcto | `analytics/tests/test_snapshot_v1.py` | #14 |
| Rebuild post-cambio TZ: filas existentes conservan `org_timezone_at_snapshot` original | `analytics/tests/test_snapshot_v1.py` (verificar; agregar si falta) | #15 TZ frozen |
| **(NUEVO obligatorio) Historical replay parity** (especificación abajo) | `analytics/tests/test_snapshot_v1.py` | contrato híbrido core |
| **(NUEVO obligatorio) Late-arrival observability** robusto (especificación abajo) | `analytics/tests/test_late_arrival_observability.py` (nuevo file) | #15 observabilidad |
| **(NUEVO opcional, recomendado) Visibility policy future-proof** — fixture con `historical_excluding_voided` skipped hoy, placeholder | `analytics/tests/test_snapshot_v1.py` | #14 future-proofing |

### Test "historical replay parity" — especificación completa

```python
def test_snapshot_matches_live_compute_for_same_bucket():
    """
    Para un bucket frozen, los valores persistidos en DailyOrgMetrics
    deben ser BIT-EXACT iguales a compute_daily_metrics(org, bucket_date)
    invocado a posteriori, asumiendo que ningún write tocó las tablas
    operacionales entre el snapshot y la reverificación.

    Este test es el GATE DE CORRECTNESS del sistema híbrido:
      today=live, ayer=snapshot, transición today→ayer sin discontinuidad.

    Si falla en cualquier momento futuro: bug crítico — un cambio rompió
    la equivalencia snapshot/live.

    Campos verificados (TODOS deben coincidir):
      - revenue_paid, revenue_accrual, invoices_paid_count
      - appointments_total, appointments_done, appointments_no_show
      - medical_records_closed
      - excluded_anchor_missing
      - provenance_mix (dict completo)
      - metrics_schema_version (snapshot row vs constant)
      - lifecycle_state (debe ser 'frozen' o 'provisional' según
        is_bucket_frozen — coherente con la lectura live)
    """
    # 1. Fixture: invoices paid hace 3 días (bucket que será frozen
    #    bajo v1_table threshold T+2)
    org = OrganizationFactory()
    bucket_date = org_today_local(org, now=fixed_now) - timedelta(days=3)
    InvoiceFactory.create_batch(5, organization=org, status='paid',
                                 paid_at=local_to_utc(org, bucket_date, time(12, 0)))

    # 2. Snapshot
    snap = apply_snapshot(org, bucket_date, now=fixed_now)
    assert snap.lifecycle_state == LIFECYCLE_FROZEN

    # 3. Live recompute
    live = compute_daily_metrics(org, bucket_date)

    # 4. Comparación bit-exact sobre TODOS los campos del contrato
    for field in SNAPSHOT_VALUE_FIELDS:
        assert getattr(snap, field) == live[field], (
            f"Drift detected on {field}: snapshot={getattr(snap, field)} "
            f"vs live={live[field]}"
        )

    # 5. Provenance mix coincide (dict-equal)
    assert snap.provenance_mix == live['provenance_mix']

    # 6. Schema version persistido = constante actual
    assert snap.metrics_schema_version == METRICS_SCHEMA_VERSION

    # 7. Lifecycle state coherente con is_bucket_frozen para mismo (org, date, now)
    expected_frozen = is_bucket_frozen('v1_table', bucket_date, org, now=fixed_now)
    if expected_frozen:
        assert snap.lifecycle_state in (LIFECYCLE_FROZEN, LIFECYCLE_REBUILT)
    else:
        assert snap.lifecycle_state == LIFECYCLE_PROVISIONAL
```

### Test "late-arrival observability" — especificación completa

```python
# apps/analytics/tests/test_late_arrival_observability.py

def assert_late_arrival_logged(
    captured, *,
    anchor_field,
    organization_id,
    age_days_min,
    writer_substring=None,
):
    """
    Helper de validación robusto a cambios de logging infra.
    Valida campos estructurados del extra dict, no el rendering.
    """
    matching = [
        r for r in captured.records
        if getattr(r, 'event', None) == 'ANCHOR_LATE_ARRIVAL'
        and getattr(r, 'anchor_field', None) == anchor_field
        and getattr(r, 'organization_id', None) == organization_id
        and getattr(r, 'age_days', 0) >= age_days_min
    ]
    assert matching, (
        f"Expected ANCHOR_LATE_ARRIVAL log for anchor={anchor_field} "
        f"org={organization_id} age>={age_days_min}, got: "
        f"{[getattr(r, 'event', '<no_event>') for r in captured.records]}"
    )
    if writer_substring:
        assert any(
            writer_substring in getattr(r, 'writer', '')
            for r in matching
        ), f"writer field missing or doesn't contain {writer_substring!r}"


def test_pay_invoice_with_backdated_paid_at_emits_structured_warning():
    """
    pay_invoice con paid_at dentro de un bucket frozen NO bloquea en v1
    (warn-only Día 5) pero emite log estructurado consumible por
    monitoring stack.
    """
    org = OrganizationFactory()
    invoice = InvoiceFactory(organization=org, status='confirmed')
    backdated_paid_at = timezone.now() - timedelta(days=6)  # frozen (T+2)

    with self.assertLogs('analytics.events', level='WARNING') as captured:
        pay_invoice(invoice, payment_method='cash', paid_at=backdated_paid_at,
                    user=user)

    assert_late_arrival_logged(
        captured,
        anchor_field='paid_at',
        organization_id=org.pk,
        age_days_min=4,  # 6 - 2 threshold = 4 días en frozen
        writer_substring='pay_invoice',
    )


def test_close_medical_record_with_backdated_closed_at_emits_warning():
    """
    Mismo contrato para MR.closed_at. Disclaimer: hoy desde views.py,
    migrará a services.py cuando ADR p9 se complete (Día 7+).
    """
    # ... (mismo patrón)


def test_late_arrival_log_includes_all_required_extra_fields():
    """
    Contrato operacional: el log DEBE incluir estos campos en extra,
    son consumidos por monitoring. Romper esto rompe alerting.
    """
    required = {
        'event', 'anchor_field', 'anchor_value_iso',
        'bucket_date_local_iso', 'frozen_threshold_days',
        'age_days', 'organization_id', 'writer', 'metric_class',
    }
    # ... (trigger + assert que cada campo esté presente)
```

### Test "visibility policy future-proof" — placeholder

```python
@pytest.mark.skip(reason="Future policy 'historical_excluding_voided' "
                          "requires ADR + voided_at column. Placeholder "
                          "to ensure registry expansion path is testable.")
def test_visibility_excludes_voided_when_policy_is_excluding_voided():
    # Cuando exista Invoice.voided_at + policy registry:
    #   ANALYTICS_VISIBILITY['billing.Invoice'] = 'historical_excluding_voided'
    # este test debe cubrir el caso "factura voided excluida del snapshot".
    pass
```

### Tests que NO se agregan en Día 5

- Hard reject `LateAnchorError` — Día 7.
- `MetricAdjustments` — v2.
- Concurrent build runs sobre misma org — cubierto por `advisory_lock` existente.
- Frontend rendering de `lifecycle_state='missing'` y `corrupt` — Día 6 frontend.

---

## 12. Verificaciones manuales / staging pre-merge

### Procedimiento

1. **Snapshot replay determinístico**
   - `build_daily_metrics --from=<7d_atras> --to=<ayer>` en staging.
   - Verificar `DASH_BUILD_RUN_COMPLETED` log con `snapshots_built > 0`.
   - Ejecutar nuevamente la misma línea.
   - Verificar `DASH_SNAPSHOT_NO_CHANGE` para cada (org, day). Ningún `DASH_SNAPSHOT_BUILT` salvo cambios reales.

2. **Boundary midnight**
   - Setear cron job a una hora específica en staging.
   - Forzar comando a durar 60+ segundos (`--from=<7d>` para inflar workload).
   - Verificar que el `org_today_local` en logs es idéntico para todas las orgs de la misma TZ aunque el reloj wall-clock haya avanzado.

3. **Dashboard cross-check**
   - Como ADMIN, abrir `/operations/series/?include_today=true&from=<hoy>&to=<hoy>`.
   - En otra pestaña, abrir `/dashboard/summary/`.
   - Confirmar `series[today].metrics.revenue_paid == summary.kpis.revenue_paid_today` (campo equivalente).
   - Si no coinciden: blocker.

4. **Soft-delete inclusion**
   - Marcar un `Pet` con paid invoice como `is_active=False` (Pet permite soft-delete).
   - Ejecutar `build_daily_metrics --date=<dia_del_pago>`.
   - Verificar `DailyOrgMetrics.revenue_paid` del día NO baja.

5. **Cache invalidation Invoice (post-commit)**
   - Como ADMIN, leer `/dashboard/summary/` → notar `ar_outstanding`.
   - En otra pestaña, ejecutar `confirm_invoice` sobre invoice draft del mismo org.
   - Releer `/dashboard/summary/` inmediatamente.
   - Verificar `ar_outstanding` actualizado (no esperar 30s).

6. **Repeated runs idempotency**
   - `build_daily_metrics --from=<7d> --to=<ayer>` tres veces seguidas.
   - Verificar que `DashboardSnapshotAudit` solo registra eventos en la 1ra corrida.

7. **Auditoría diagnóstica `is_active=False` rows** (decisión rebuild histórico)
   - Por org, ejecutar:
     ```sql
     SELECT organization_id, COUNT(*)
     FROM billing_invoice
     WHERE is_active = FALSE AND status IN ('paid', 'confirmed')
     GROUP BY organization_id;
     ```
   - Si retorna 0 todas: fix forward sin rebuild.
   - Si retorna > 0: coordinar rebuild con Product Owner. Ventana de mantenimiento + `build_daily_metrics --force --org=X --from=Y --to=Z --reason='ADR p17 visibility correction'`.

8. **TZ-changed org**
   - Cambiar TZ de una org de staging.
   - `build_daily_metrics --force --org=X --date=<dia_de_un_snapshot_viejo>`.
   - Verificar `org_timezone_at_snapshot` de la fila histórica **no cambia**.
   - Verificar fila nueva del cron de mañana sí usa nueva TZ.

9. **Late-arrival warning visible**
   - En staging, manipular paid_at de una invoice para que caiga en bucket frozen.
   - Verificar log `ANCHOR_LATE_ARRIVAL` con todos los campos `extra` presentes.
   - Verificar que aparece en el monitoring stack (Sentry / Railway logs).

### Criterio "listo para mergear"

Los 9 puntos pasan + suite completa (294 tests + nuevos) pasa + ADR linkeado.

---

## 13. Out of scope explícito (Día 5)

1. **Hard reject `LateAnchorError`**. Día 7 o Sprint 2. Día 5 entrega warn-only.
2. **`MetricAdjustments` table**. v2.
3. **KPI `done_to_invoice_conversion`**. Feature, no fix.
4. **Bump `METRICS_SCHEMA_VERSION`**. La semántica de los 7 KPIs no cambia. Confirmado con esta revisión: no bump.
5. **Cron rebucketing por TZ change**. Deuda documentada.
6. **Snapshot a granularidad hora**. v2.
7. **OrgScopedThrottle dedicada analytics**. Día 7 perimeter.
8. **Frontend rendering de `lifecycle_state='missing'` y `corrupt`**. Día 6.
9. **Refactor de `dashboard_stats` legacy**. Si no se usa, deprecated; si se usa, no tocar.
10. **Rebuild masivo histórico**. Decisión coordinada con PO post-auditoría diagnóstica (§12.7).
11. **Migración de `ANALYTICS_VISIBILITY` a `historical_excluding_voided`**. Requiere campo `voided_at` + ADR formal + PO sign-off (§4.2 gobernanza). Deuda documentada.

### 13.A Deuda activa reconocida (mantener visible)

**ADR p9 violation parcial: `close_medical_record` en views.py.**

Día 5 agrega observabilidad late-arrival para `MR.closed_at` desde `medical_records/views.py::close_medical_record`. Esto es **temporal** y **NO cierra la deuda de ADR p9**.

Estado correcto futuro: existirá `apps/medical_records/services.py::close_medical_record_service()` que sea el writer autoritativo, idéntico al patrón de `billing/services.py`. Cuando exista:
- El log `ANCHOR_LATE_ARRIVAL` migra al service.
- La view delega al service.
- `close_medical_record` desaparece como writer directo de `closed_at`.

**Owner del item:** medical_records team. **Fecha objetivo:** Día 7 perimeter o Sprint 2.

Documentar en `analytics.md` + `dashboard-metrics-contract.md` §2.7 con marcador "⚠️ writer migration pending — ADR p9".

### 13.B Decisión pendiente con PO

Antes de mergear PR-2 (visibility policy):
1. Ejecutar auditoría diagnóstica §12.7.
2. Si hay rows `is_active=False` que cambiarían números históricos: presentar al PO el delta esperado por org/mes.
3. PO decide: fix forward / rebuild coordinado / mantener números actuales con ADR explicativo.

**Sin esta decisión, PR-2 no se mergea.**

---

## 14. Apéndice — Secuencia recomendada de PRs

Para minimizar riesgo de regresión, 5 PRs (incremento sobre v1 — el ADR formal se separa):

**PR-0 (ADR)** — `docs/decisions/2026-05-XX-p17-analytics-correctness-day5.md`. ADR formal que linkea este plan, describe gobernanza de `ANALYTICS_VISIBILITY`, define warn-only late-arrival como puente hacia hard reject. Sin código. Mergeable solo.

**PR-1 (docs)** — Actualizar `dashboard-metrics-contract.md` §2.6 (visibility policy explícita), §2.9 (warn-only Día 5), §3 (live-only del summary + nota /dashboard/summary no analytics API). Actualizar `docs/modules/analytics.md` con `ANALYTICS_VISIBILITY` + `now` policy + late-arrival. Sin código.

**PR-2 (analytics visibility #14)** — `ANALYTICS_VISIBILITY` registry + `_analytics_queryset` helper + `compute_daily_metrics` y `analytics_health` consumiéndolo. `ANCHOR_REGISTRY` introducido. Test extendido + test future-proof skipped. **Requiere auditoría §12.7 + decisión PO previo a merge.**

**PR-3 (`now` threading + late-arrival warn #15, #17)** — `build_daily_metrics` captura `now`. `apply_snapshot`, `is_bucket_frozen`, `org_today_local` reciben `now` consistente. Logs `ANCHOR_LATE_ARRIVAL` en writers de anchor (billing.services + medical_records.views con disclaimer ADR p9). Test boundary midnight + test late-arrival observability robusto (con helper).

**PR-4 (dashboard live consistency #16)** — `dashboard_summary` delega revenue/appointments a `compute_daily_metrics(today)`. Receiver Invoice con `transaction.on_commit`. Response-level `metrics_schema_version` + `source: 'live_summary'`. Test consistency nuevo + test parity nuevo. Docstring `/dashboard/summary/` declara NO analytics API.

PRs revisados por persona distinta a la que los escribió. Cada PR pasa suite completa de tests.

---

## 15. Apéndice — Historial de revisiones del plan

| Versión | Fecha | Cambios principales |
|---|---|---|
| v1 | 2026-05-17 | Plan inicial. 13 secciones. Propone hardcode `all_objects` en analytics. |
| v2 | 2026-05-17 | Incorpora 9-point feedback: `ANALYTICS_VISIBILITY` registry; late-arrival warn-only en Día 5; `dashboard_summary` no analytics API; source/version response-level; tests obligatorios extendidos. |
| v3 | 2026-05-17 | Incorpora 4-point feedback adicional: **gobernanza dura del registry** (ADR + impact analysis + PO sign-off); **ADR p9 violation reconocida como deuda activa**; **assertLogs reemplazado por helper estructurado**; **constraint anti-DSL** sobre policy enums; **test parity extendido** a `metrics_schema_version`, `lifecycle_state`, `provenance_mix`. |

---

## Cierre

Plan v3 no requiere migraciones, no introduce frameworks, mantiene contratos externos, y respeta los ADRs vigentes (01: no refactor en v1; 09-13: anchor authority intacta; 11-12: snapshot rules intactas). Cada issue tiene un único punto de cambio, una capa propietaria, un test que lo cubre, y un owner semántico explícito.

Rollback es `git revert` por PR. Blast radius confinado a `apps.analytics`, `apps.dashboard`, `apps.billing.services`, `apps.medical_records.views`.

**Decisiones pendientes pre-merge:**

1. PR-2: auditoría diagnóstica §12.7 + decisión PO sobre rebuild histórico.
2. PR-0: ADR formal firmado y mergeado antes de cualquier PR de código.
3. Confirmación con PO de que `ANALYTICS_VISIBILITY` queda como contrato semántico co-owned Backend + Product (no solo técnico).

Esperando luz verde para PR-0 (ADR).
