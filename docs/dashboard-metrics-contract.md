# Dashboard Metrics Contract

Version: 0.4 (draft)
Owner: Backend
Status: Draft — event authority table updated for p11 (pay_direct_sale)
Last updated: 2026-05-15

Changelog:
- 0.4: Updated event authority table (§2.7) — all billing anchors now exist and have authoritative writers in `services.py`. Added `pay_direct_sale` as second writer for `confirmed_at` + `paid_at` (atomic single-step for direct_sale). Added note in §3.1.2 about `direct_sale` accrual=cash behavior.
- 0.3: minimal alignment with `analytics-schema-audit.md` findings. Marked anchors with explicit trust levels (A/B/C/D/F). Locked `Invoice.cancelled_at` decision to "ADD column, do not rely on audit log". Documented `AppointmentDetailView.destroy()` bypass as a known event-authority violation pending fix C3. Renamed vaccine fields to match real model (`application_date`, `next_due_date`). Removed `priority` from `next_appointments` payload. Annotated `pay_invoice` writer as "currently in views, fix C1 in progress". No metric definitions changed.
- 0.2: incorporated v0.1 review feedback. Added §2.7 (Event Authority), §2.8 (Reversal/Cancellation Policy), §2.9 (Late-arriving Data Policy), §4.6 (Snapshot Lifecycle State), §4.7 (Metrics Schema Versioning), §5.4 (Analytics Throttling). Conversion mutation window extended T+7 → T+14. Appendix A documents resolutions per review item.
- 0.1: initial draft.

This document is the single source of truth for every metric exposed by the dashboard
endpoints. Any disagreement between this document and the implementation MUST be
resolved by changing the implementation, never by changing this document silently.
Edits to this document require an ADR.

---

## 0. Scope

This contract covers:
- Definition of every dashboard KPI.
- Source-of-truth table and column.
- Status filters, inclusions, exclusions.
- Timezone policy at event time and at query time.
- Snapshot mutation policy (when a snapshot is allowed to change after first write).
- Cardinality limits and downsampling rules.
- Recomputation policy when underlying data is corrected.

Not in scope: UI rendering, polling cadence, RBAC mapping (those live in the dashboard
design doc and in `core/permissions.py`).

---

## 1. Glossary (terms used everywhere)

| Term | Definition |
|------|------------|
| Event time | Wall-clock instant when the underlying domain event occurred. Stored as UTC. |
| Org-local date | Calendar date in `Organization.timezone` at event time. |
| Snapshot | Row in an aggregated table representing one bucket (e.g. one org-day). |
| Snapshot key | The (organization, bucket) tuple that identifies a snapshot row. |
| Bucket | The temporal granularity of a snapshot row (day, week, month). |
| Cash basis | Revenue counted on the org-local date the invoice was paid. |
| Accrual basis | Revenue counted on the org-local date the invoice was confirmed (services rendered, billable). |
| Built-at | Timestamp at which a snapshot row was last written. |

---

## 2. Universal rules

These apply to every metric without exception.

### 2.1 Tenant scoping
Every aggregation begins with `Model.objects.for_organization(org)`. No exception.
Cache keys are prefixed with `org_id` (`dash:{org_id}:...`). No exception.

### 2.2 Timezone at event time
Org-local date is computed using the organization's timezone **as it was at the moment
the event was recorded**. This timezone is frozen into snapshots (see §4.2). The current
`Organization.timezone` is only used for events that have not yet been bucketed.

### 2.3 Timezone at query time
Query parameters `from` and `to` are interpreted as org-local dates (calendar dates,
not instants). They are converted to UTC bounds via `local_day_bounds_utc(org, date)`
and only then passed to the ORM. The frontend never sends UTC.

### 2.4 Status names — beware
- `Invoice.status` uses `cancelled` (double L).
- `Appointment.status` uses `canceled` (single L).
This contract spells each one in its native module. Do not normalize across modules.

### 2.5 Currency
All monetary fields are `DECIMAL(12, 2)` MXN. No multi-currency in v1. Sums use
`Coalesce(Sum(...), Decimal('0'))` so empty result sets return `0.00`, never `None`.

### 2.6 Visibility policy (analytics-side reads)

v1 defines an explicit `ANALYTICS_VISIBILITY` registry in `apps/analytics/services.py`
that governs which rows analytics computations see (Issue #14, ADR p17 Día 5).

The registry maps model → policy enum:

| Model | Policy | Manager used | Rationale |
|-------|--------|-------------|-----------|
| `billing.Invoice` | `historical` | `all_objects` | Revenue/AR metrics must count all invoices including soft-deleted. A voided invoice (future) should not silently disappear from historical revenue. |
| `medical_records.MedicalRecord` | `historical` | `all_objects` | Clinical activity counts must include all records. |
| `appointments.Appointment` | `historical` | `all_objects` | Appointment counts must include all appointments. |
| `medical_records.VaccineRecord` | `historical` | `all_objects` | Vaccine records are permanent clinical data. |

Future policies require ADR + impact analysis + PO sign-off (§4.2 gobernanza).
`historical_excluding_voided` is planned when `Invoice.voided_at` exists — it will
NOT be silently added without governance.

**Constraint:** `Model.objects` (TenantManager, filters `is_active=True`) is NEVER
used for analytics reads. Always resolve via `_analytics_queryset(model_cls)`.

### 2.7 Event authority

Every temporal anchor used by an analytics metric (`paid_at`, `confirmed_at`,
`cancelled_at`, `closed_at`, `done_at`, `applied_at`) MUST be written by exactly one
authoritative code path. Direct ORM writes (`Model.objects.filter(...).update(status='X')`)
that bypass the service are forbidden for any model whose status feeds an analytics anchor.

Authoritative writers (current state — annotated against real schema):

| Anchor field | Authoritative writer | Module | Status (2026-05-15) |
|--------------|---------------------|--------|---------------------|
| `Invoice.confirmed_at` | `billing/services.py::confirm_invoice`, `pay_direct_sale` | billing | ✅ Column exists. Two writers, both in `services.py`. |
| `Invoice.paid_at` | `billing/services.py::pay_invoice`, `pay_direct_sale` | billing | ✅ Column exists. Two writers, both in `services.py`. `pay_direct_sale` escribe `confirmed_at` + `paid_at` atomicamente. |
| `Invoice.cancelled_at` | `billing/services.py::cancel_invoice` | billing | ✅ Column exists. Writer in `services.py`. |
| `MedicalRecord.closed_at` | `medical_records/views.py::close_medical_record` | medical_records | ⚠️ Writer is in views.py, not services.py (ADR p9 violation). CHECK constraint active (M16). Late-arrival observability added in Día 5 as temporary bridge. Migration to `medical_records/services.py::close_medical_record_service()` pending (Día 7+). |
| `Appointment.done_at` | not stored — derived from `AppointmentStatusChange.created_at` | appointments | ✅ Acceptable per §3.2.2 (anchor on `start_datetime` instead). |
| `VaccineRecord.application_date` | model write at create | medical_records | ✅ DateField, daily granularity. |
| `Appointment` cancel transition | `appointments/views.py::update_status` | appointments | ⚠️ `destroy()` bypasses `update_status`. Pending fix C3. |
| `Appointment.walk_in` | walk-in creation view | appointments | ✅ Column exists. |

Enforcement:
- Each authoritative writer MUST set the timestamp inside the same `transaction.atomic()`
  block that mutates the status. Tests assert that bypassing the writer (raw queryset
  update) leaves the timestamp `NULL`, which the `build_daily_metrics` job will then
  reject and log as `DASH_ANCHOR_MISSING`.
- The `dashboard.events` logger emits `DASH_ANCHOR_MISSING` whenever a row matches a
  status filter but its anchor column is `NULL`. The row is excluded from snapshots and
  the count of excluded rows is recorded in `DailyOrgMetrics.excluded_anchor_missing`.
- A non-zero `excluded_anchor_missing` value in any production snapshot is a P1 alert.

### 2.8 Reversal and cancellation policy (dual-window)

When a status transition reverses an earlier billable event (e.g. `confirmed → cancelled`,
`paid → cancelled` if ever supported, `closed → reopened` for medical records), the
treatment depends on whether the original event's snapshot day is still inside its
mutation window.

| Scenario | Treatment | Storage |
|----------|-----------|---------|
| Reversal happens within the original day's mutation window | Mutate the original snapshot in place. Re-run `build_daily_metrics` for that single day. | Original snapshot row updated; `built_at` advances. |
| Reversal happens AFTER the original day's mutation window has closed (frozen) | Do not touch the frozen snapshot. Record a negative adjustment on the day of the reversal. | New row in `MetricAdjustments` table (org, date, metric_name, delta, reason, source_invoice_id, created_at). |

Read-time computation:
```
revenue_paid_net(day)     = revenue_paid(day)     + sum(adjustments where date=day and metric='revenue_paid')
revenue_accrual_net(day)  = revenue_accrual(day)  + sum(adjustments where date=day and metric='revenue_accrual')
```

Charts always plot the `_net` value. The `_gross` value remains queryable for audit.
A negative-adjusted day is rendered with a small marker in the UI ("contains adjustments")
linking to the audit row.

Rationale: this preserves snapshot immutability (historical days do not silently change
under your feet), while keeping the running total accurate for cash and accrual reporting.
Accountants get a clean audit trail.

Specific rules:
- Cancellation of a `confirmed` invoice: subtract the invoice total from `revenue_accrual` only.
- Cancellation of a `paid` invoice (if v2 ever allows it): subtract from both
  `revenue_paid` and `revenue_accrual`. Currently disallowed by the state machine.
- Reopen of a closed `MedicalRecord`: subtract 1 from `medical_records_closed` for the
  reversal day. If reopened and re-closed on the same day, no adjustment.
- Reassignment of an `Appointment` to a different vet/day: not a reversal — the original
  day's count stands (the appointment was scheduled there at the time).

### 2.9 Late-arriving data policy

A "late-arriving event" is any write whose authoritative anchor (e.g. `confirmed_at`,
`paid_at`) carries a timestamp that, when converted to org-local date, falls in a frozen
bucket. This happens during:
- Bulk import / migration from another system.
- Admin manual correction of a timestamp.
- Backdated data entry.

**Día 5 (current): WARN-only.** Every anchor writer emits a structured
`ANCHOR_LATE_ARRIVAL` warning log (logger `analytics.events`, level `WARNING`)
with fields: `event`, `anchor_field`, `anchor_value_iso`, `bucket_date_local_iso`,
`frozen_threshold_days`, `age_days`, `organization_id`, `writer`, `metric_class`.
The write is NOT blocked. The `event` field is an operational contract — the
monitoring stack consumes it.

**Día 7+ (planned): Hard reject.** The authoritative service will refuse to set an
anchor in a frozen bucket, raising `LateAnchorError` which the API layer maps
to HTTP 400 with `meta.frozen_bucket_date` populated.

Override: a management command `import_with_backdated_anchors --org=X --allow-frozen
--reason="<text>"` accepts late anchors. After the import:
1. All affected frozen snapshots are recomputed via `build_daily_metrics --force`.
2. Each recomputed snapshot creates a `DashboardSnapshotAudit` row with `kind='late_arrival_rebuild'`.
3. UI surfaces an "amended" badge on affected days for 30 days after the rebuild.

Imports that introduce events in OPEN buckets (current mutation window) follow the
normal flow — no override needed.

---

## 3. Metric catalog

> **Note on `/dashboard/summary/` (ADR p17 Día 5):** The `/api/v1/dashboard/summary/`
> endpoint is an operational dashboard payload, NOT an analytics API. Metrics marked
> "live-only" below are computed directly by the summary endpoint. Temporal KPIs that
> the summary exposes (revenue, appointments, medical_records_closed for today) are
> **derived** from `apps.analytics.services.compute_daily_metrics(today)`. For audited
> or historical financial data, use `/dashboard/financial/series/` and
> `/dashboard/operations/series/`. Any frontend consuming the summary for financial
> reporting does so at its own risk — the summary contract may evolve independently.
> Modifications to the summary that break this policy require an ADR.

Each metric block follows the same shape:

```
Name              <stable id used in API field names>
Audience          <roles that may see it>
Definition        <one-line plain English>
Source of truth   <table.column>
Filter            <SQL-ish expression>
Excludes          <statuses or rows explicitly removed>
Time anchor       <which column drives the org-local date>
Bucket            <day | hour-of-day | etc>
Mutation policy   <see §4.2>
Notes             <edge cases, gotchas>
```

---

### 3.1 Financial metrics (ADMIN only)

#### 3.1.1 `revenue_paid`
- Audience: ADMIN
- Definition: total cash received from paid invoices on a given org-local day. Cash basis.
- Source of truth: `billing_invoice.total`
- Filter: `status = 'paid' AND paid_at IS NOT NULL`
- Excludes: `draft`, `confirmed`, `cancelled`
- Time anchor: `paid_at` (UTC) → org-local date via stored snapshot timezone
- Bucket: day
- Mutation policy: **immutable after T+2** (see §4.2). Late-paid old invoices land on the day they were paid, never on the day they were confirmed or issued.
- Notes:
  - If `Invoice.paid_at` is missing on existing rows, backfill from latest `InvoiceAuditLog` row with `new_status='paid'` before snapshots run. Rows where neither exists are excluded with a logger warning (`DASH_PAID_AT_MISSING`).
  - Refunds are NOT supported in v1. If added later, this metric must be re-defined as net of refunds.

#### 3.1.2 `revenue_accrual`
- Audience: ADMIN
- Definition: billable revenue earned on a given org-local day. Accrual basis.
- Source of truth: `billing_invoice.total`
- Filter: `status IN ('confirmed', 'paid') AND confirmed_at IS NOT NULL`
- Excludes: `draft`, `cancelled`
- Time anchor: `confirmed_at`
- Bucket: day
- Mutation policy: immutable after T+2.
- Notes:
  - Accrual ≥ paid for any historical day. If the chart shows accrual < paid for a day, the snapshot is corrupt — alert.
  - **Direct sale behavior**: para facturas `direct_sale`, `confirmed_at ≈ paid_at` (diferencia de milisegundos, escritos en la misma transaccion por `pay_direct_sale`). Las curvas de accrual y cash coinciden para este tipo de factura. Esto es comportamiento esperado — distinto al de `consultation` donde puede haber horas/dias entre confirmacion y pago. Ver ADR `2026-05-15-p11-pay-direct-sale.md`.
  - This is the metric to use for "service productivity" of a clinic, not `revenue_paid`. UX label should make this distinction visible to ADMIN.

#### 3.1.3 `accounts_receivable_outstanding`
- Audience: ADMIN
- Definition: unpaid amount on confirmed invoices, as of NOW.
- Source of truth: `billing_invoice.total`
- Filter: `status = 'confirmed'` (i.e. confirmed but not yet paid, not cancelled)
- Excludes: `draft`, `paid`, `cancelled`
- Time anchor: not bucketed (point-in-time snapshot).
- Bucket: live read, no snapshot.
- Mutation policy: N/A (read-through cache, TTL 60s).
- Notes:
  - For aging buckets see §3.1.4.
  - "AR" is reported in MXN, never as a count of invoices.

#### 3.1.4 `ar_aging_buckets`
- Audience: ADMIN
- Definition: outstanding AR sliced by age, as of NOW.
- Source of truth: `billing_invoice`
- Filter: `status = 'confirmed'`
- Buckets:
  - `0-7`: `confirmed_at >= NOW - 7d`
  - `8-15`: `NOW - 15d <= confirmed_at < NOW - 7d`
  - `16-30`: `NOW - 30d <= confirmed_at < NOW - 15d`
  - `31-60`: `NOW - 60d <= confirmed_at < NOW - 30d`
  - `60+`: `confirmed_at < NOW - 60d`
- Time anchor: `confirmed_at`. Days are calendar days in org timezone.
- Mutation policy: live (read-through cache, TTL 5min).
- Notes:
  - This is the only metric that uses `confirmed_at` as the aging anchor in v1.
  - When `Invoice.due_date` is added (deuda técnica), aging will switch to `due_date - NOW`. This is a breaking semantic change and requires a contract bump.

#### 3.1.5 `invoices_paid_count`
- Audience: ADMIN
- Definition: number of invoices that became `paid` on a given org-local day.
- Source: `billing_invoice`, `status='paid'`, anchor `paid_at`.
- Bucket: day. Mutation: immutable after T+2.

#### 3.1.6 `invoices_cancelled_count`
- Source: `status='cancelled'`. Anchor: latest `InvoiceAuditLog.created_at` where `new_status='cancelled'`. Bucket: day. Mutation: immutable after T+2.
- Reason for using audit log: `Invoice.cancelled_at` does not exist as a field. Either add the column or keep relying on the audit log.

#### 3.1.7 `discount_total`
- Definition: total monetary discount applied on invoices that were paid that day.
- Status: NOT IMPLEMENTED in v1 — `Invoice` has no `discount` column. Placeholder so the contract is forward-compatible. Do not emit this field until the column exists.

#### 3.1.8 `tax_collected`
- Source: `billing_invoice.tax_amount` summed over invoices with `status='paid'` on a given day. Same anchor and mutation rules as `revenue_paid`.

#### 3.1.9 `average_ticket`
- Definition: `revenue_paid / invoices_paid_count`. Computed at read time from snapshot fields. Returns `null` when `invoices_paid_count = 0`. Never division-by-zero.

#### 3.1.10 `done_to_invoice_conversion`
- Audience: ADMIN
- Definition: fraction of `appointments.done` (org-local day) that have at least one Invoice (any non-cancelled status) attached, as of NOW.
- Numerator: `count(distinct appointment_id)` where appointment is `done` on day D AND there exists an `Invoice` for that appointment with `status != 'cancelled'`.
- Denominator: `count(appointments)` with `status='done'` on day D.
- Time anchor: `Appointment.start_datetime` (the scheduled day) — NOT `done_at`. Reason: clinics see "today's appointments" by their scheduled date.
- Bucket: day. Mutation: **mutable for 14 days**, then frozen. Reason: lazy invoice can land days after the appointment under surgery / hospitalization / "client returns later" patterns. T+14 covers the realistic tail without leaving snapshots forever-mutable.
- Notes:
  - This is the metric that detects revenue leakage from `auto_create_invoice_on_done=False`.
  - If conversion < 0.6 sustained, the toggle should probably be flipped or the UX flow reviewed.
  - First 14 days a snapshot row is `provisional`; chart renders a "stabilizing" hint for those buckets so dashboard readers do not over-react to mid-tail values.

---

### 3.2 Operational metrics (ASSISTANT, VET, ADMIN)

#### 3.2.1 `appointments_total`
- Definition: count of appointments scheduled to happen on a given org-local day, regardless of final status.
- Source: `appointments_appointment`
- Filter: none (all statuses included)
- Time anchor: `start_datetime`
- Bucket: day. Mutation: **mutable until day end** (T+0), then frozen.

#### 3.2.2 `appointments_done`
- Status filter: `status='done'`
- Time anchor: `start_datetime` (NOT the moment it transitioned to done)
- Bucket: day. Mutation: mutable until T+1, then frozen.
- Reason for `start_datetime` anchor: a "Tuesday at 4pm" appointment that gets completed Wednesday morning still belongs to Tuesday operationally.

#### 3.2.3 `appointments_no_show`
- Status filter: `status='no_show'` (single L)
- Anchor: `start_datetime`. Bucket: day. Mutation: T+1 frozen.

#### 3.2.4 `appointments_canceled`
- Status filter: `status='canceled'` (single L)
- Anchor: `start_datetime`.
- Excludes: appointments cancelled BEFORE their start_datetime that landed on a different org-local day. (Edge case: cancellation event is logged but bucket is the scheduled day.)
- Bucket: day. Mutation: T+1 frozen.

#### 3.2.5 `walk_ins_total`
- Definition: count of appointments where `walk_in=True`.
- Anchor: `created_at` (when the walk-in was registered, since `start_datetime` is set to the moment of arrival). Bucket: day. Mutation: T+1.

#### 3.2.6 `appointments_in_progress_now`
- Live only. Filter: `status='in_progress'`. No snapshot.

#### 3.2.7 `waiting_room_count`
- Live. Filter: `status='confirmed'` AND `start_datetime` within `[NOW - 1h, NOW + 30min]`. Heuristic — patients arriving early or running late.
- Note: this is a UX approximation. v2 should add an explicit `arrived_at` field.

#### 3.2.8 `next_appointments` (list, not metric)
- Top N (default 5) appointments from `for_organization(org)` ordered by `start_datetime ASC` where `status IN ('scheduled', 'confirmed')` AND `start_datetime >= NOW`.
- Fields: `public_id`, `start_datetime`, `pet_name`, `vet_full_name`, `status`. Nothing else.
- Note: `priority` field was specified in v0.2 and removed in v0.3 — column does not exist in the model. Add it back when the column is added.

#### 3.2.9 `vet_load_today` (group)
- Group by `veterinarian_id`. Fields: `appointments_total`, `appointments_done`, `appointments_remaining`. Filter: `start_datetime` within today's UTC bounds.

---

### 3.3 Clinical metrics (VET, ADMIN)

#### 3.3.1 `medical_records_open`
- Definition: count of `MedicalRecord` rows with `status='open'`, as of NOW.
- Source: `medical_records_medicalrecord`. Live only.

#### 3.3.2 `medical_records_open_stale_24h`
- Definition: subset of 3.3.1 where `created_at < NOW - 24h`. This is THE clinical backlog metric.
- Reason: a record opened 30 minutes ago is normal mid-consultation. Open >24h is a process leak.

#### 3.3.3 `medical_records_open_without_diagnosis`
- Definition: subset of 3.3.1 where `diagnosis IS NULL OR diagnosis = ''`. Cannot be closed in current rules.
- This is a different backlog from 3.3.2 — they may overlap; report independently.

#### 3.3.4 `appointments_done_without_medical_record`
- Definition: count of appointments with `status='done'` where no `MedicalRecord` exists with `appointment_id = X`.
- Time anchor: appointment `start_datetime`. Bucket: day, mutable T+7, frozen T+8.
- This metric exists because of ADR-p7 (lazy invoice and lazy MR creation). It detects the lazy gap.

#### 3.3.5 `medical_records_closed`
- Status filter: `status='closed'`. Time anchor: `closed_at`. Bucket: day. Mutation: immutable after T+2.

#### 3.3.6 `prescriptions_issued`
- Source: `prescriptions_prescription`. Anchor: `created_at`. Bucket: day. Mutation: immutable after T+2.
- Note: a prescription does NOT decrement stock (per ADR-2026-04-26). Do not derive sales from prescriptions.

#### 3.3.7 `vaccines_applied`
- Source: `medical_records_vaccinerecord`. Anchor: `application_date` (DateField). Bucket: day. Mutation: immutable after T+2.
- Note: anchor is a `DateField`, daily granularity is the cap. Sub-day analytics not supported.

#### 3.3.8 `vaccines_due_window`
- Definition: count of `VaccineRecord` rows with `next_due_date` within `[today, today + N days]` where the pet is still active.
- Live read. Default N=7 (parametrizable: 7 / 14 / 30).
- Output: count + paginated drill-down list `(pet, owner_phone, vaccine, next_due_date)`.

#### 3.3.9 `consultations_with_charges`
- Definition: fraction of `medical_records_closed` on day D that have at least one `MedicalRecordProduct` OR `MedicalRecordService`.
- Used to identify vets whose tickets are systematically empty (process gap, training need, or revenue leak).
- Bucket: day. Mutation: immutable after T+7 (charges can be backfilled inside the open window).

---

## 4. Snapshot mechanics

### 4.1 Tables (planned)

| Table | Bucket | Key | Build cadence |
|-------|--------|-----|---------------|
| `DailyOrgMetrics` | (org, day) | unique (org, date) | Nightly cron 02:00 org-local + on-demand backfill |
| `VetDailyPerformance` | (org, vet, day) | unique (org, vet, date) | Nightly |
| `ProductDailyConsumption` | (org, presentation, day) | unique (org, presentation, date) | Nightly |
| `HourOfWeekHeatmap` | (org, dow, hour) | rolling 12-week window | Nightly (full rebuild — small) |

Every table has columns: `id`, `organization_id`, `bucket_key columns`, the metric columns, `org_timezone_at_snapshot` (string, e.g. `America/Mexico_City`), `built_at` (datetime), `frozen` (bool, default False).

### 4.2 Mutation policy by metric class

| Class | Window | Frozen after | Reason |
|-------|--------|--------------|--------|
| Operational counts (appointments, walk-ins) | T+0 to T+1 | T+1 | Operational corrections happen same-day or next morning |
| Clinical activity (records closed, prescriptions, vaccines) | T+0 to T+2 | T+2 | Late documentation is common but rare beyond 48h |
| Charges-on-records (`consultations_with_charges`) | T+0 to T+14 | T+14 | Charges can land days after the consult under lazy invoice; aligned with conversion window |
| Financial cash basis (`revenue_paid`, `invoices_paid_count`) | T+0 to T+2 | T+2 | Once cash is in, it does not move |
| Conversion (`done_to_invoice_conversion`) | T+0 to T+14 | T+14 | Lazy invoice creation tail under surgery / hospitalization |

"Frozen" means the nightly job will not overwrite the row. Manual override requires a
management command `dashboard_resnapshot --org=X --date=Y --force` that logs the override
to `DashboardSnapshotAudit`.

**Critical rule**: a paid-today invoice for a service rendered last month lands in TODAY's
`revenue_paid`, not last month's. The day-of-payment is the anchor, and that day is in its
own (unfrozen) window. Last month's snapshot is NOT touched.

This is cash-basis convention. Anyone asking "but the work was done in March!" needs
`revenue_accrual`, which they can read on the same dashboard.

### 4.3 Frozen timezone

Each snapshot row stores `org_timezone_at_snapshot`. Subsequent timezone changes on the
organization do not retroactively re-bucket history. The dashboard's historical chart
shows what happened in the timezone that was active at the time. A timezone change is
recorded in `Organization` history (audit log) so a chart can render a vertical "TZ changed"
marker if needed (v2).

Rationale: a clinic that moves operations from Mexico City to Tijuana should not see its
March revenue retroactively bucketed by Pacific time. The snapshots are the historical
record.

### 4.4 Backfill and idempotency

`build_daily_metrics --from=YYYY-MM-DD --to=YYYY-MM-DD [--org=ID] [--force]`:
- Iterates orgs (or single org), iterates days in range.
- For each (org, day): computes metrics from source tables, writes/updates row via
  `update_or_create`, sets `built_at = now()`.
- If row exists and `frozen=True` and `--force` not passed: skip with a logged
  `DASH_SNAPSHOT_FROZEN_SKIPPED` event. Continue with next day.
- If `--force` is passed: overwrite, log `DASH_SNAPSHOT_FORCED` with old vs new diff.
- Cron schedule: 02:00 in each org's local timezone. Implementation note: a single global
  cron at 06:00 UTC builds yesterday's snapshot for every org (most Mexican TZs are
  GMT-6/-7/-8; 06:00 UTC = midnight to 22:00 local). Acceptable for v1.

### 4.5 Recompute on data correction

Any data correction that modifies a frozen day requires:
1. Run `build_daily_metrics --org=X --date=Y --force`.
2. Cache invalidation for that org's affected keys.
3. Audit row in `DashboardSnapshotAudit` capturing the diff and the reason.

A regular write to current-day data (e.g. an invoice gets paid) does NOT trigger a snapshot
rebuild — the read-through cache covers today's number. The snapshot will be built the
following night.

### 4.6 Snapshot lifecycle state (persisted)

Every snapshot row carries an explicit `lifecycle_state` enum field:

| State | Meaning | Set by |
|-------|---------|--------|
| `provisional` | Inside mutation window. Subject to overwrites by nightly job. | `build_daily_metrics` first write |
| `frozen` | Past mutation window. Nightly job will skip. | Nightly job when `today - bucket_date > class.freeze_days` |
| `rebuilt` | Was frozen, then forcibly rewritten. | `build_daily_metrics --force` or late-arrival rebuild |
| `corrupt` | Build job detected anchor inconsistency it could not resolve. Excluded from charts. | Nightly job when `excluded_anchor_missing > threshold` |

`lifecycle_state` is the source of truth for "is this number trustworthy". The dashboard
API exposes it per bucket so the frontend can render hints (`provisional` = stabilizing,
`rebuilt` = amended badge, `corrupt` = hidden).

Every transition is logged to `DashboardSnapshotAudit` with `(org, date, from_state,
to_state, reason, user_id_or_system, diff_json)`.

Without this field, no one can tell whether a number is "today's running tally", "a
finalized historic", or "a value that was rebuilt three weeks late". Debugging analytics
without persistent lifecycle is impossible.

### 4.7 Metrics schema versioning

Every snapshot row carries `metrics_schema_version` (integer). Initial value: `1`.

Bump rules:
- Adding a new metric column: no version bump (NULL on historic rows is fine).
- Changing the definition of an existing metric (filter, anchor, formula): mandatory bump.
- Changing only the storage type (e.g. widening a Decimal): no bump.

When a metric definition changes:
1. Bump `metrics_schema_version` constant (e.g. 1 → 2).
2. Add the new column alongside the old one (`revenue_paid_v1`, `revenue_paid_v2`) for
   the dual-write window.
3. Run nightly job in dual-write mode for at least 7 days. Both values produced.
4. Deploy chart code that reads `revenue_paid_v2`.
5. Backfill historic rows: choose to either (a) recompute under v2 if the source data
   still supports it, or (b) leave historic rows on v1 and render a "definition changed
   on YYYY-MM-DD" marker on the chart.
6. After 30 days, drop `revenue_paid_v1`.

Without this, every analytics bug fix breaks all historical comparisons silently. Charts
that mix two definitions are worse than no chart.

This is overhead. Pay it now in the schema, not later in a migration scramble.

---

## 5. Cardinality and downsampling

### 5.1 Hard limits per request

| Endpoint | Default range | Max range | Max bucket count |
|----------|---------------|-----------|------------------|
| `/revenue-series?granularity=day` | 30d | 365d | 365 |
| `/revenue-series?granularity=week` | 13w | 156w (3y) | 156 |
| `/revenue-series?granularity=month` | 12m | 60m (5y) | 60 |
| `/heatmap` | 12w | 52w | fixed 7×24 |
| `/financial/aging` | n/a | n/a | 5 buckets |

Requests outside these limits return HTTP 400 with `meta.max_range_days` set.
`from > to` returns 400. Range overlapping future returns the past portion only.

### 5.2 Auto-bucketing rules

If a client requests `from..to` longer than the max for `granularity=day`, the server
does NOT silently downgrade. It returns 400 with a hint:
```json
{"detail": "Range exceeds limit for daily granularity",
 "meta": {"granularity": "day", "max_days": 365, "requested_days": 730,
          "suggested_granularity": "week"}}
```
Frontend reissues with the suggested granularity.

### 5.3 Series shape

`/revenue-series` always returns a fully-padded series — missing days are filled with
`{revenue_paid: 0, revenue_accrual: 0, invoices_paid_count: 0}`. Frontend never
interpolates; backend pads.

### 5.4 Analytics throttling and abuse controls

Dashboard endpoints are heavier and more sensitive than transactional endpoints.
Throttle separately from the global API throttle.

| Scope | Limit | Applies to |
|-------|-------|-----------|
| `dashboard_operations` | 120/min/user | `/operations`, `/operations/realtime` |
| `dashboard_clinical` | 60/min/user | `/clinical/*` |
| `dashboard_financial` | 30/min/user | `/financial`, `/financial/aging`, `/revenue-series` |
| `dashboard_export` | 5/hour/user, 1 concurrent | `/export/*` (CSV / PDF generation) |
| `dashboard_heatmap` | 10/min/user | `/heatmap` (more expensive scan) |

Per-org caps (defense against compromised single account scraping all data):
- `dashboard_financial_per_org`: 200/min combined across all users in the org.
- `dashboard_export_per_org`: 20/hour combined.

Implementation: `apps/core/throttling.py` adds `OrgScopedThrottle` parallel to
`UserRateThrottle`. The org-scoped variant uses `org_id` as the key.

Audit:
- Every access to a `dashboard_financial` endpoint logs `DASHBOARD_FINANCIAL_VIEWED`
  with `user_id`, `org_id`, `endpoint`, `query_params_hash`. Hash, not raw, so PII
  in params (rare but possible in `?owner=` filters) does not enter logs.
- Every export logs `DASHBOARD_EXPORT_REQUESTED` with row count, byte size, and
  duration. Export over 10MB or longer than 30s triggers a P3 alert.

Anti-scraping:
- A single user pulling `/revenue-series` with `granularity=day` over moving windows
  (e.g. yesterday/today/tomorrow rolling) > 60 times in an hour is flagged. Soft
  enforcement in v1 (alert only); hard enforcement (temporary 429 lockout) in v2 if
  observed.

---

## 6. Definitions to remove from the proposal

These were in the v0 design but should NOT ship until they have a contract:

- "Revenue del día" without cash/accrual disambiguation — REMOVED. Use `revenue_paid` or `revenue_accrual` explicitly.
- "Top vets" without a specific metric — REMOVED. Each ranking widget needs a stated
  ordering metric (e.g. "by `revenue_paid` for invoices linked to their appointments").
- Generic "ticket promedio" — KEPT only as `average_ticket = revenue_paid / invoices_paid_count`. No alternative formulas.

---

## 7. Open questions (block implementation)

1. **`Invoice.paid_at` column**: present? If not, add migration before contract is signed.
2. **`Invoice.confirmed_at` column**: present? Same.
3. **`Invoice.cancelled_at` column**: probably absent. Either add or commit to using audit log as anchor.
4. **`MedicalRecord.closed_at`**: present?
5. **`MedicalRecord.appointment_id`**: confirm FK exists and is indexed for §3.3.4.
6. **Audit log for `Organization.timezone` changes**: exists or accept that v1 cannot draw "TZ changed" markers.
7. **`Appointment.priority`**: exists? Otherwise drop the field from `next_appointments`.

These are answered against schema, not assumed. Check the migrations and confirm in writing
in this doc (v0.2) before any code is written.

---

## 8. Versioning

This contract follows semantic versioning at the metric level:
- Patch (0.1.0 → 0.1.1): clarifications, no semantic change.
- Minor (0.1 → 0.2): new metrics added, existing untouched.
- Major (0.x → 1.0): breaking change to existing metric. Forces a deprecation window
  and a `?contract=v1` query parameter on endpoints.

A breaking change to a financial metric requires an ADR, signoff from the product owner,
and a 30-day overlap in production where both versions are queryable.

---

## 9. Sign-off

This document is in **draft**. Before promotion to v1.0:
- Owner reviews each metric definition.
- All §7 open questions answered.
- Schema gaps closed via migrations or explicit ADR.
- One round of "play the dashboard" — read each KPI back and confirm it does what the
  product owner expects on three real org datasets.


## Appendix A — Resolutions to v0.1 review feedback

This appendix records, item by item, how each piece of v0.1 review feedback was
incorporated into v0.2. It is informational; the binding text lives in the numbered
sections above.

| # | Review item | Resolution | Where in v0.2 |
|---|-------------|------------|---------------|
| A1 | T+7 too short for `done_to_invoice_conversion` (surgery, hospitalization, client returns later) | Extended to T+14. Charges window aligned. Buckets within window flagged `provisional` so UI can warn readers. | §3.1.10, §3.3.9, §4.2 |
| A2 | Missing "event authority" — analytics break silently if anchor written outside the service | Added §2.7. Each anchor has a single authoritative writer. Bypass writes leave anchor `NULL` and trigger `DASH_ANCHOR_MISSING` P1 alert. | §2.7 |
| A3 | Missing reversal/cancellation policy (confirmed → cancelled, etc.) | Added §2.8 (dual-window). In-window reversals mutate the original snapshot. Out-of-window reversals create a row in `MetricAdjustments` and charts plot `_net = _gross + adjustments`. | §2.8 |
| A4 | Missing late-arriving data policy (bulk import, manual correction) | Added §2.9. Default: writer rejects late anchors with `LateAnchorError`. Override only via explicit management command with audit. | §2.9 |
| A5 | Snapshot freezing needs persisted state, not just documentation | Added §4.6. Each snapshot row carries `lifecycle_state ∈ {provisional, frozen, rebuilt, corrupt}`. Every transition logged to `DashboardSnapshotAudit`. | §4.6 |
| A6 | Need rebuild policy and `metrics_schema_version` from day one | Added §4.7. Every snapshot row carries `metrics_schema_version`. Definition changes follow a 7-day dual-write protocol. | §4.7 |
| A7 | Cardinality covered but throttling not | Added §5.4. Per-scope and per-org throttles. Export limits (5/hour, 1 concurrent). Audit of every financial view. Anti-scraping detection (alert in v1, hard in v2). | §5.4 |

### Re-prioritized blockers (review confirmed, restated)

The §7 list is unchanged in content, but the priority is now restated so it is
unambiguous what blocks what:

| # | Schema gap | Blocks | Required action |
|---|-----------|--------|-----------------|
| B1 | `Invoice.paid_at` | All financial cash-basis metrics | Add column + backfill from `InvoiceAuditLog` before any financial snapshot ships |
| B2 | `Invoice.confirmed_at` | All accrual metrics, AR aging | Add column + backfill |
| B3 | `MedicalRecord.closed_at` | `medical_records_closed`, `consultations_with_charges` | Add column + backfill |
| B4 | `Invoice.cancelled_at` (optional) | Cancellation metrics; can fall back to audit log if not added | Decide: add column or commit to audit-log anchor |
| B5 | `Organization.timezone` change audit | "TZ changed" UI marker (cosmetic in v1) | Defer; document the gap |
| B6 | `Appointment.priority` | One field of `next_appointments` payload | Drop the field if absent — not a blocker |

Implementation order is therefore strict: B1, B2, B3 must land before any snapshot
table is created. B4/B5/B6 can ship in parallel or be deferred.

### Implementation sequence (replaces the v0.1 roadmap)

1. **Analytics readiness checklist** — produced as separate doc
   `docs/analytics-readiness-checklist.md`. Catalog of every required column, index,
   authoritative service, and backfill needed. Audited against the actual schema.
2. **Schema audit + migrations** — close blockers B1–B3 (and B4 if added). Add indexes
   §8.1 of design doc. Backfill anchors from audit logs where possible.
3. **`MetricAdjustments` table** — supports §2.8 reversal policy. Required even before
   the first snapshot table because reversal events that happen now must be captured.
4. **`DailyOrgMetrics` + `build_daily_metrics` job** — lifecycle state, schema version,
   anchor validation. Tested with multi-tenant fixtures including one TZ-changed org.
5. **Operations endpoints only** — `/operations`, `/operations/realtime`. No financial.
6. **Operations frontend** — narrowest scope, lowest blast radius.
7. **Financial endpoints + snapshots** — only after operations is stable in production.
8. **Financial frontend** — last.

No code is written before step 1 is reviewed and signed off.