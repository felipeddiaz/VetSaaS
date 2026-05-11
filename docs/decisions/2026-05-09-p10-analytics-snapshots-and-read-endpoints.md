# ADR p10: Analytics snapshots minimal v1 + read endpoints JSON-first

**Fecha**: 2026-05-09
**Estado**: Implementado (Capa 3 + Capa 4 + Capa 5)
**Documentos relacionados**:
- `docs/dashboard-metrics-contract.md` (v0.3)
- `docs/decisions/2026-05-09-p9-analytics-anchor-authority.md`

## Contexto

Con anchors confiables (p9), el siguiente paso lógico era construir
snapshots agregados nightly + read endpoints. Riesgos a evitar:

1. Snapshots sobre datos no confiables → garbage in/out (resuelto en p9).
2. Snapshots no idempotentes → un retry produce diff fantasma.
3. Cron Railway puede duplicar jobs / overlap por deploys → race conditions.
4. Mezclar `today` (live) con `yesterday+` (snapshot) sin marcar fuente →
   confusión + bugs irreproducibles.
5. Construir frontend bonito antes de validar correctness del JSON.

## Decisión

Sprint dividido en 3 capas estrictas:

### Capa 3 — Indexes (performance only)
11 índices compuestos creados (no afectan correctness, sí escalabilidad):
- `idx_inv_org_status_paid` / `_conf` / `_canc` (cash basis, accrual, AR)
- `idx_mr_org_status_closed_at` / `_appointment` / `_status_created`
- `idx_appt_org_start_status`
- `idx_vacc_org_app_date` / `_next_due`
- `idx_stockmov_org_pres_created`
- `idx_presc_org_created`

EXPLAIN ejecutado con `enable_seqscan=off` para validar que cada índice es
utilizable. Operational rule: correr `ANALYZE <tabla>` después de cada
import y de la primera corrida del nightly job para que el planner
re-precie con stats reales.

### Capa 4 — Snapshots minimal v1

App nueva `apps/analytics/` con dos modelos:

**`DailyOrgMetrics`** — 1 row por (organization, org-local date):
- 7 KPIs minimales: `revenue_paid`, `revenue_accrual`,
  `invoices_paid_count`, `appointments_total`, `appointments_done`,
  `appointments_no_show`, `medical_records_closed`
- `org_timezone_at_snapshot` — frozen al build, NO se reescribe en
  rebuild (cambios de TZ no rebucketean historia)
- `metrics_schema_version` (=1) — bump cuando cambie definición
- `lifecycle_state` ∈ provisional/frozen/rebuilt/corrupt
- `excluded_anchor_missing` (defensive, debería ser 0 post-p9)
- `build_warnings_count`, `provenance_mix` (JSON con `{anchor: {source: count}}`)
- `built_at` auto_now (avanza solo si hay diff real)

**`DashboardSnapshotAudit`** — append-only:
Cada lifecycle transition (build/skip_frozen/rebuild/freeze/corruption_detected/
late_arrival_rebuild) genera 1 row con `from_state`, `to_state`, `diff` JSON,
`triggered_by` user/system.

#### Servicios (`apps/analytics/services.py`)

- `is_bucket_frozen(metric_class, bucket_date, org, *, now=None)` —
  **único helper**. No `timezone.now()` disperso. Tabla
  `METRIC_CLASS_FREEZE_DAYS`. v1 usa T+2 conservador.
- `compute_daily_metrics(org, date)` — **puro**, no writes. Retorna dict.
- `apply_snapshot(org, date, *, force=False, user=None, now=None)` —
  **idempotente**. Diff vs existing; si igual → no save → `built_at` NO
  avanza. Frozen sin force → audit `skip_frozen`. Frozen con force →
  lifecycle `rebuilt`. `excluded_anchor_missing > 0` → lifecycle `corrupt`
  + audit `corruption_detected` + log ERROR.
- `TodayRejected` — today/future raises. Snapshots NO existen para today.

#### Mgmt command `build_daily_metrics`

- `--date | --from --to | --org | --force`
- Default: yesterday por org-local TZ
- **Per-org PG advisory lock** (`build_daily_metrics:org:{id}`) →
  Railway double-fire safe. `on_busy='skip'` salta org y sigue.
- **Per-org try/except** → un org fallido NO aborta otros.
- Run summary estructurado + `sys.exit(2)` si cualquier org falló →
  cron alerting wireable.
- Logs: `DASH_BUILD_RUN_STARTED/COMPLETED`, `DASH_BUILD_ORG_*`,
  `DASH_BUILD_LOCK_BUSY`, `DASH_SNAPSHOT_BUILT/CORRUPT/NO_CHANGE`.

#### Decisiones explícitas (lo que NO se hizo)

- **Sin cache invalidation sofisticado**. Today = live cada request,
  history = snapshot directo. Sin signal fanout, sin reactive rebuilds,
  sin dependency graph.
- **Sin today snapshot parcial mutable**. Today es siempre live-only.
- **Sin MetricAdjustments** (reversal policy del contract §2.8) — minimal
  v1 no la necesita; cancel deja anchor pero v1 no lo usa.
- **Sin rankings / heatmaps / conversion / derived ratios**. Ampliación
  posterior con bump de `metrics_schema_version`.

### Capa 5 — Read endpoints JSON-first

Dos endpoints separados por permission (RBAC limpio, no widget-level filter):

```
GET /api/v1/dashboard/operations/series/   → ASSISTANT, VET, ADMIN
GET /api/v1/dashboard/financial/series/    → ADMIN only
```

Permissions: `dashboard.view` (existente) y `dashboard.financial.view`
(nuevo en `PERMISSION_CODES`). Financial además double-check role layer
contra ADMIN/ADMIN_SAAS.

#### Query params

- `?from=YYYY-MM-DD&to=YYYY-MM-DD` — default 30d ending today
- `?include_today=true|false` — default true
- Hard cap **365 días** (contract §5.1) → 400 + `meta.max_range_days`
- Rango invertido / fecha inválida → 400

#### Response contract

Cada datapoint tagged explícitamente:

```json
{
  "range": {"from": "2026-04-09", "to": "2026-05-09", "tz": "UTC"},
  "series": [
    {
      "bucket_date": "2026-04-09",
      "source": "snapshot",
      "lifecycle_state": "frozen",
      "metrics_schema_version": 1,
      "metrics": {"revenue_paid": "1234.56", ...}
    },
    {
      "bucket_date": "2026-04-10",
      "source": "snapshot",
      "lifecycle_state": "missing",
      "metrics_schema_version": null,
      "metrics": {"revenue_paid": "0.00", ...}
    }
  ],
  "today": {
    "bucket_date": "2026-05-09",
    "source": "live",
    "lifecycle_state": null,
    "metrics_schema_version": null,
    "metrics": {...}
  },
  "notes": ["1 day(s) in range have no snapshot yet — they will populate after the next nightly build."]
}
```

#### Garantías

- `source` + `lifecycle_state` en TODO datapoint. NUNCA mezcla snapshot/live
  sin marcar.
- Today computado vía mismo `compute_daily_metrics` que usa el snapshot job
  → consistencia matemática.
- `lifecycle_state='corrupt'` se filtra en view layer. NO se sirve. Aparece
  como `'missing'` en el series + se reporta vía `/analytics-health/`.
- Días sin snapshot → `lifecycle_state='missing'` con zeros + `notes`. NUNCA
  silenciosamente omitidos.
- Decimals serializados como strings (no float drift). Missing financial
  days = `'0.00'` para shape consistency.

## Procfile

```
nightly_snapshots: python manage.py build_daily_metrics
nightly_anchor_audit: python manage.py audit_anchor_integrity --json
```
Schedulable vía Railway Cron service. Recomendación: 06:00 UTC daily
(cubre Mexico GMT-6/-7/-8 yesterday end-of-day).

## Consecuencias

- Frontend dashboards consumirán `/api/v1/dashboard/*/series/` directamente.
  Cualquier UI que ignore `lifecycle_state` o `source` es bug — debe rendear
  `provisional` distinto de `frozen`, `missing` distinto de `0 reales`.
- Bumpear `METRICS_SCHEMA_VERSION` requiere ADR aparte + dual-write protocol
  (ver contract §4.7).
- Agregar nuevos KPIs al snapshot row es minor (sin bump de version),
  pero requiere actualizar `compute_daily_metrics` + `SNAPSHOT_VALUE_FIELDS`
  + endpoints + tests de idempotency.
- `build_daily_metrics` NUNCA debe llamarse con today. Si necesitas refrescar
  today → pega el read endpoint (que computa live).
