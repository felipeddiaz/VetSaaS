# Modulo: Analytics

App: `apps/analytics/`. Construye y sirve snapshots agregados nightly.
Capa 4 + Capa 5 del sprint analítico (ADR `2026-05-09-p10`).

## Objetivo

Almacenar agregados diarios pre-computados por (organizacion, fecha local
de la organizacion) para soportar dashboards historicos sin escanear las
tablas operativas. Today es siempre live; ayer y atras son snapshots.

## Modelos

### `DailyOrgMetrics`

Una fila por (organization, date). UniqueConstraint `(organization, date)`.

KPIs minimal v1 (7):
- `revenue_paid` (Decimal, cash basis, anchor `Invoice.paid_at`)
- `revenue_accrual` (Decimal, anchor `Invoice.confirmed_at`)
- `invoices_paid_count` (PositiveInt)
- `appointments_total` / `appointments_done` / `appointments_no_show`
  (PositiveInt, anchor `Appointment.start_datetime`)
- `medical_records_closed` (PositiveInt, anchor `MedicalRecord.closed_at`)

Metadata por fila:
- `org_timezone_at_snapshot` — TZ de la org al momento del build. NO se
  reescribe en rebuild — cambios futuros de TZ no rebucketean historia.
- `metrics_schema_version` (default 1) — bump cuando cambia definicion
  semantica de un KPI. Requiere dual-write protocol (contract §4.7).
- `lifecycle_state` ∈ `provisional` / `frozen` / `rebuilt` / `corrupt`
- `built_at` (auto_now) — avanza solo cuando hay diff real
- `excluded_anchor_missing` — defensive instrumentation; deberia ser 0
  post-Capa 1 CHECKs. Si > 0 → row marcada `corrupt`.
- `build_warnings_count`
- `provenance_mix` (JSON) — `{"paid_at": {"service": 921, "fallback": 2}}`

### `DashboardSnapshotAudit`

Append-only. Una fila por cada lifecycle event:
- `kind` ∈ `build` / `skip_frozen` / `rebuild` / `freeze` /
  `corruption_detected` / `late_arrival_rebuild`
- `from_state`, `to_state`, `diff` (JSON), `reason`
- `triggered_by` (User FK) + `triggered_by_system` flag

## Servicios

`apps/analytics/services.py`. **Solo importar de aqui** desde fuera del
modulo.

### `is_bucket_frozen(metric_class, bucket_date, organization, *, now=None)`

Unica fuente de verdad sobre congelamiento. Uses `METRIC_CLASS_FREEZE_DAYS`.
v1 usa `'v1_table'` clase con T+2 conservador. `now=` injectable para tests.

Nunca duplicar esta logica en otro lugar — DST, rebuilds, late imports
y TZ changes deben pasar por una sola funcion.

### `compute_daily_metrics(organization, bucket_date)`

**Pure**. No writes. Retorna dict con los 7 KPIs + `excluded_anchor_missing`
+ `provenance_mix`. Usado tanto por el snapshot job como por el read endpoint
para computar today (consistencia matematica).

### `apply_snapshot(organization, bucket_date, *, force=False, user=None, now=None)`

**Idempotente**. Reglas:

1. Today/future raise `TodayRejected`. Snapshots NO existen para today.
2. Si fila existe y esta `frozen` y no `force` → audit `skip_frozen`,
   retorna existing sin tocar.
3. Computa metrics. Si `excluded_anchor_missing > 0` → lifecycle `corrupt`
   + audit `corruption_detected` + log ERROR. Numbers se persisten para
   inspeccion (NO silently dropped).
4. Si fila existe y diff vacio (mismas values + mismo lifecycle) → no save
   → `built_at` NO avanza → no audit row. **Verificable corriendo el job
   3x: produce mismos numeros, mismo `built_at`.**
5. Si fila existe y diff no vacio → save + audit row con diff JSON.
6. Si fila no existe → create + audit `build`.

## Mgmt command: `build_daily_metrics`

```
python manage.py build_daily_metrics                       # yesterday por org
python manage.py build_daily_metrics --date=2026-05-08
python manage.py build_daily_metrics --from=2026-05-01 --to=2026-05-07
python manage.py build_daily_metrics --org=12 --force
```

**Production safety**:
- Per-org PG advisory lock (`build_daily_metrics:org:{id}`) via
  `apps.core.db_locks`. Railway double-fire safe. Lock contendido →
  org saltada con `DASH_BUILD_LOCK_BUSY` warn.
- Per-org `try/except` con stacktrace. Un org fallido NO aborta otros.
- `sys.exit(2)` si cualquier org fallo → cron alerting wireable.
- Run summary estructurado: `orgs_processed`, `orgs_locked_busy`,
  `orgs_failed`, `snapshots_built`, `snapshots_skipped_today`,
  `duration_seconds`.
- Logs structured (todos a `analytics.events` logger):
  `DASH_BUILD_RUN_STARTED/COMPLETED`, `DASH_BUILD_ORG_STARTED/COMPLETED/FAILED`,
  `DASH_BUILD_LOCK_BUSY`, `DASH_SNAPSHOT_BUILT/CORRUPT/NO_CHANGE`.

Idempotencia + advisory lock + per-org isolation = safe para correr nightly
sin coordinator externo.

## Mgmt command: `audit_anchor_integrity`

Vive en `apps/core/management/commands/`. Valida que:
- `Invoice.status='paid' ⇒ paid_at IS NOT NULL`
- `Invoice.status IN ('confirmed','paid') ⇒ confirmed_at IS NOT NULL`
- `Invoice.status='cancelled' ⇒ cancelled_at IS NOT NULL`
- `MedicalRecord.status='closed' ⇒ closed_at IS NOT NULL`

Reporta provenance distribution + unresolved + walk-in suspects.

Exit codes: 0 clean, 1 unresolved warn, 2 invariant violation.
Wireable a cron + alerting.

```
python manage.py audit_anchor_integrity
python manage.py audit_anchor_integrity --org=12 --verbose
python manage.py audit_anchor_integrity --json
```

## Read endpoints (Capa 5)

```
GET /api/v1/dashboard/operations/series/   → ASSISTANT, VET, ADMIN
GET /api/v1/dashboard/financial/series/    → ADMIN only
GET /api/internal/analytics-health/        → ADMIN_SAAS only
```

### Query params (series endpoints)

- `from`, `to` (default 30d ending today)
- `include_today` (default true)
- Hard cap **365 dias**. Excede → 400 + `meta.max_range_days`.

### Response contract

Cada datapoint tagged `source` + `lifecycle_state`:

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
    }
  ],
  "today": {
    "bucket_date": "2026-05-09",
    "source": "live",
    "lifecycle_state": null,
    "metrics_schema_version": null,
    "metrics": {...}
  },
  "notes": [...]
}
```

Garantias del contract:
- `source` ∈ `snapshot` | `live`. NUNCA mezcla sin marcar.
- Today siempre `source='live'` con `lifecycle_state=null`. Computado via
  mismo `compute_daily_metrics` del snapshot job.
- `lifecycle_state='corrupt'` rows filtradas en view layer. NO se sirven.
  Aparecen como `'missing'` y se reportan via `/analytics-health/`.
- Dias sin snapshot → `lifecycle_state='missing'` con zeros + `notes`
  entry. NUNCA silenciosamente omitidos.
- Decimals como strings (no float drift). Missing financial = `'0.00'`.

### `/analytics-health/` payload

```json
{
  "anchors": {"invoice.paid_at": {"service": 921, "legacy": 17}, ...},
  "invariant_violations": {...},  // todos deben ser 0
  "unresolved_provenance": 0,
  "walk_in_suspect_count": 0,
  "legacy_decay_alerts": [...],   // legacy > 90d → critical
  "fallback_warnings": [...],     // fallback% > 5% → warning
  "trust_score_per_anchor": {...},
  "checked_at": "2026-05-09T..."
}
```

## Procfile

```
nightly_snapshots: python manage.py build_daily_metrics
nightly_anchor_audit: python manage.py audit_anchor_integrity --json
```

Schedule via Railway Cron service. Recomendacion: 06:00 UTC daily
(cubre Mexico GMT-6/-7/-8 yesterday end-of-day).

## Reglas para extender

Agregar un KPI al snapshot row:
1. Agregar columna a `DailyOrgMetrics` (migration).
2. Agregar a `SNAPSHOT_VALUE_FIELDS` en `services.py`.
3. Calcular en `compute_daily_metrics`.
4. Exponer via serializer + `OPERATIONAL_FIELDS` o `FINANCIAL_FIELDS` en
   `dashboard/views.py`.
5. Default en `MISSING_DAY_DEFAULTS`.
6. Test de idempotency cubre el campo automaticamente.
7. Si la **definicion** cambia (no solo agregar) → bump
   `METRICS_SCHEMA_VERSION` + ADR + dual-write 30 dias (contract §4.7).

Agregar un anchor temporal nuevo:
1. Migration con columna + provenance source field + CHECK constraint.
2. Authoritative writer en `services.py` del modulo dueño.
3. Test bulk-bypass resistance.
4. Actualizar `audit_anchor_integrity` y `/analytics-health/`.
5. Ver ADR `2026-05-09-p9` para el patron completo.

## Prohibido

- `cache.clear()` masivo en signals (rompe tenants vecinos).
- Snapshot computation en signals — toda computacion va via mgmt command
  o on-demand via `apply_snapshot`.
- `today` snapshots — today es siempre live.
- `Invoice.objects.update(status=...)` — bypassa CHECK constraints solo
  si la migration creo el constraint con `NOT VALID` (no es nuestro caso).
  Aunque la CHECK protege, el patron sigue prohibido en codigo de negocio.
- Frontend que ignore `source` o `lifecycle_state` en la respuesta.
