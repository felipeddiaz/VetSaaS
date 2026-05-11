# Analytics Readiness Checklist

Version: 0.1 (draft)
Owner: Backend
Status: Draft — must be fully verified against schema before any analytics code is written
Last updated: 2026-05-09
Companion to: `docs/dashboard-metrics-contract.md`

This checklist is the gate between "we have a contract" and "we can build snapshots".
Every item must be either ✅ verified in the current schema, or ⛔ converted into a
migration ticket and a hard blocker.

The checklist is mechanical. It is meant to be filled in by reading the actual code,
not by guessing. When an item is unverified, write `?` and stop.

---

## 1. Required timestamp columns (anchors)

The contract uses these timestamps as the source of truth for bucketing events into days.
Each must (a) exist as a non-nullable-going-forward column, (b) be set by an authoritative
writer in the same transaction as the status mutation, (c) be present on all relevant
historical rows or backfilled.

| # | Anchor | Used by | Status | Authoritative writer | Backfill source if missing |
|---|--------|---------|--------|---------------------|----------------------------|
| T1 | `Invoice.paid_at` | `revenue_paid`, `invoices_paid_count`, `tax_collected` | ? | `billing/services.py::pay_invoice` | latest `InvoiceAuditLog` row with `new_status='paid'` |
| T2 | `Invoice.confirmed_at` | `revenue_accrual`, `accounts_receivable_outstanding`, `ar_aging_buckets` | ? | `billing/services.py::confirm_invoice` | latest `InvoiceAuditLog` row with `new_status='confirmed'` |
| T3 | `Invoice.cancelled_at` (optional) | `invoices_cancelled_count`, reversals | ? | `billing/services.py::cancel_invoice` | latest `InvoiceAuditLog` row with `new_status='cancelled'` |
| T4 | `MedicalRecord.closed_at` | `medical_records_closed`, `consultations_with_charges` | ? | `medical_records/views.py::close_medical_record` | best-effort from `updated_at` on rows where `status='closed'`; flag uncertain rows |
| T5 | `Appointment.done_at` | optional finer-grained ops metrics | ? | `appointments/views.py::update_status` (transition to `done`) | none — without this, `appointments_done` keeps using `start_datetime` as anchor (acceptable per contract §3.2.2) |
| T6 | `VaccineRecord.applied_at` | `vaccines_applied` | ? | model `save()` if status flips to applied | `created_at` (acceptable; vaccines are recorded at the moment of application) |

### Verification protocol

For each row above:
1. Read the model file in the cited module.
2. Confirm the column exists with the expected name and type (`DateTimeField`, nullable
   only if backfill is incomplete).
3. Read the cited authoritative writer. Confirm it sets the timestamp inside
   `transaction.atomic()` adjacent to the status mutation.
4. Run a query against staging: `SELECT count(*) FROM <table> WHERE <status_filter> AND <anchor> IS NULL`. Record the count. Anything >0 is a backfill blocker.
5. Mark ✅ or convert to a migration ticket.

---

## 2. Required FK relationships

| # | Relationship | Used by | Status | Notes |
|---|-------------|---------|--------|-------|
| F1 | `MedicalRecord.appointment_id` | `appointments_done_without_medical_record` | ? | Must be FK with index. Verify nullable (lazy MR creation may leave it NULL for walk-ins not yet linked). |
| F2 | `Invoice.appointment_id` | `done_to_invoice_conversion` | ? | Same. |
| F3 | `Invoice.medical_record_id` | conversion fallback path | ? | Required because lazy invoice attaches to MR, not appointment, in the no-appointment walk-in flow. |
| F4 | `MedicalRecordProduct.medical_record_id` | `consultations_with_charges` | ? | Trivially exists; verify index. |
| F5 | `MedicalRecordService.medical_record_id` | `consultations_with_charges` | ? | Same. |

---

## 3. Required indexes (compound)

These indexes are mandatory before snapshot jobs run on any non-trivial dataset.
Without them, the nightly job time scales linearly with table size and will eventually
exceed its window.

| # | Table | Index | Used by | Status |
|---|-------|-------|---------|--------|
| I1 | `appointments_appointment` | `(organization_id, start_datetime DESC)` | every operational query | ? |
| I2 | `appointments_appointment` | `(organization_id, status, start_datetime)` | per-status counts | ? |
| I3 | `appointments_appointment` | `(organization_id, veterinarian_id, start_datetime)` | `vet_load_today`, `VetDailyPerformance` | ? |
| I4 | `billing_invoice` | `(organization_id, status, paid_at)` | cash-basis snapshots | ? |
| I5 | `billing_invoice` | `(organization_id, status, confirmed_at)` | accrual snapshots, AR aging | ? |
| I6 | `billing_invoice` | `(organization_id, appointment_id)` | conversion metric | ? |
| I7 | `billing_invoice` | `(organization_id, medical_record_id)` | conversion (walk-in path) | ? |
| I8 | `medical_records_medicalrecord` | `(organization_id, status, created_at DESC)` | `medical_records_open*` | ? |
| I9 | `medical_records_medicalrecord` | `(organization_id, status, closed_at)` | `medical_records_closed` | ? |
| I10 | `medical_records_medicalrecord` | `(organization_id, appointment_id)` | conversion | ? |
| I11 | `inventory_stockmovement` | `(organization_id, presentation_id, created_at DESC)` | `ProductDailyConsumption` | ? |
| I12 | `prescriptions_prescription` | `(organization_id, created_at DESC)` | `prescriptions_issued` | ? |
| I13 | `medical_records_vaccinerecord` | `(organization_id, applied_at)` | `vaccines_applied` | ? |
| I14 | `medical_records_vaccinerecord` | `(organization_id, next_due)` | `vaccines_due_window` | ? |

### Verification protocol

For each index:
1. `python manage.py dbshell` and run `\d+ <table>` (PG) to list current indexes.
2. Confirm presence by column tuple. Order matters — `(org_id, status, paid_at)` is not
   the same as `(org_id, paid_at, status)` for our query patterns.
3. If absent, ticket a migration. Use `Meta.indexes = [Index(fields=[...])]` not raw SQL,
   so the ORM tracks it.

---

## 4. Authoritative services (anchor enforcement)

Each anchor must be written in exactly one place. This section enumerates the call sites
that exist today and identifies any direct-write paths that bypass the service layer.

| # | Anchor | Authoritative service | Bypass paths to remove | Status |
|---|--------|----------------------|----------------------|--------|
| S1 | `Invoice.paid_at` | `pay_invoice` | grep for `Invoice.objects.*update.*status='paid'`, `invoice.status = 'paid'` outside the service | ? |
| S2 | `Invoice.confirmed_at` | `confirm_invoice` | same pattern for `'confirmed'` | ? |
| S3 | `Invoice.cancelled_at` | `cancel_invoice` (TBD) | same for `'cancelled'` | ? |
| S4 | `MedicalRecord.closed_at` | `close_medical_record` view | search for any `mr.status = 'closed'` outside the view; check management commands | ? |
| S5 | `Appointment.done_at` (if added) | `appointments/views.py::update_status` | search for `appointment.status = 'done'` direct writes | ? |

### Verification protocol

```
grep -rn "status\s*=\s*['\"]paid['\"]" backend/apps/ | grep -v tests/
grep -rn "status\s*=\s*['\"]confirmed['\"]" backend/apps/ | grep -v tests/
grep -rn "status\s*=\s*['\"]closed['\"]" backend/apps/ | grep -v tests/
grep -rn "\.update(.*status" backend/apps/ | grep -v tests/
```

Any hit outside the authoritative service is a finding. Either route the write through
the service or document an exception with rationale.

---

## 5. Tables to create before snapshots

| # | Table | Purpose | Migration |
|---|-------|---------|-----------|
| C1 | `MetricAdjustments` | Negative adjustments for out-of-window reversals (§2.8 of contract) | Required before T1/T2 columns are useful for accrual |
| C2 | `DashboardSnapshotAudit` | Lifecycle state transitions (§4.6) | Required before any snapshot row is written |
| C3 | `DailyOrgMetrics` | First aggregated table (§4.1) | After C1 + C2 |
| C4 | `VetDailyPerformance` | Per-vet daily aggregates | After C3 |
| C5 | `ProductDailyConsumption` | Per-presentation daily consumption + closing stock | After C3 |
| C6 | `HourOfWeekHeatmap` | Heatmap source | After C3 |

Required columns on every snapshot table:
- `id`, `organization_id`, bucket key columns, metric columns
- `org_timezone_at_snapshot` (CharField, e.g. `America/Mexico_City`)
- `built_at` (DateTimeField, auto_now)
- `lifecycle_state` (CharField, choices `provisional`/`frozen`/`rebuilt`/`corrupt`, default `provisional`)
- `metrics_schema_version` (PositiveIntegerField, default = current `METRICS_SCHEMA_VERSION` constant)
- `excluded_anchor_missing` (PositiveIntegerField, default 0) — number of rows excluded due to NULL anchors

---

## 6. Late-arriving data preconditions

For §2.9 of the contract to be enforceable, the following must exist:

| # | Item | Status |
|---|------|--------|
| L1 | `LateAnchorError` exception class in `apps/core/exceptions.py` | ? (likely missing) |
| L2 | Each authoritative writer (S1–S5) raises `LateAnchorError` if the supplied anchor falls in a frozen bucket | ? |
| L3 | API exception handler maps `LateAnchorError` to HTTP 400 with `meta.frozen_bucket_date` | ? |
| L4 | Management command `import_with_backdated_anchors --org=X --allow-frozen --reason="..."` exists with `--reason` mandatory and audit-logged | not built |

If L1–L4 are not present, the late-arriving policy is documented but not enforced.
That is acceptable for v1 ONLY if there is no current ingest path that produces backdated
anchors. Verify by listing all writers of T1–T5 and confirming none accept a user-supplied
timestamp.

---

## 7. Cancellation / reversal preconditions

For §2.8 to function:

| # | Item | Status |
|---|------|--------|
| R1 | `MetricAdjustments` table exists (C1) | not built |
| R2 | `cancel_invoice` service writes a `MetricAdjustments` row when invoice is cancelled outside its mutation window | not built |
| R3 | `reopen_medical_record` service exists OR a clear policy that MRs cannot be reopened in v1 | ? |
| R4 | Read-time computation of `_net = _gross + sum(adjustments)` implemented in the dashboard serializer layer | not built |

---

## 8. Throttling and audit preconditions (§5.4)

| # | Item | Status |
|---|------|--------|
| H1 | `apps/core/throttling.py` has `OrgScopedThrottle` parallel to `UserRateThrottle` | ? — only `LoginRateThrottle` and `LoginUserRateThrottle` confirmed today |
| H2 | Throttle scopes `dashboard_operations`, `dashboard_clinical`, `dashboard_financial`, `dashboard_export`, `dashboard_heatmap` registered in `DEFAULT_THROTTLE_RATES` | not built |
| H3 | `DASHBOARD_FINANCIAL_VIEWED` event emitted on every financial endpoint hit | not built |
| H4 | `DASHBOARD_EXPORT_REQUESTED` event with size + duration | not built (no export endpoint yet) |
| H5 | Anti-scraping detection: counter of distinct `(user, endpoint, range_offset)` triples per hour | not built — defer to v2 per contract |

---

## 9. Multi-tenant isolation tests (must exist before snapshots ship)

| # | Test | Status |
|---|------|--------|
| M1 | Two-org fixture: write events in org A, dashboard endpoints called as user of org B return zero / empty | not built |
| M2 | Cache key collision test: `cache.get('dash:1:financial:day:2026-05-09')` does not return data populated by org 2 | not built |
| M3 | Snapshot job test: running `build_daily_metrics --org=A` does not touch any row with `organization_id != A` | not built |
| M4 | TZ-changed-org fixture: org changes timezone; pre-change snapshots retain `org_timezone_at_snapshot` of the old TZ; post-change snapshots use the new TZ; chart values do not silently shift | not built |
| M5 | Late-arrival rebuild test: import a backdated invoice via override command; verify the affected snapshot is rebuilt to `lifecycle_state='rebuilt'` and an audit row exists | not built |
| M6 | Cancellation test: confirm invoice on day D, freeze D, cancel invoice on day D+30; verify D snapshot unchanged AND `MetricAdjustments` row exists for day D+30 | not built |

---

## 10. Sign-off gate

This checklist is **complete** when:
1. Every `?` in this document is replaced with ✅ or ⛔.
2. Every ⛔ has a corresponding migration / code ticket linked.
3. T1, T2, T3 (anchor columns) are ✅ — no exception.
4. I1–I10 (core indexes) are ✅ on staging and verified by `EXPLAIN ANALYZE` of the
   actual snapshot job query.
5. C1, C2 (adjustments + audit) tables are migrated.
6. M1, M2, M3 (isolation tests) are written and passing.

Until then, no `DailyOrgMetrics` migration is created, no nightly job is wired, and no
`/api/v1/dashboard/financial/*` endpoint exists. Operations endpoints (per the contract's
re-prioritized sequence step 5) MAY be built before this is fully complete, since they
do not depend on the financial anchors. They still require I1–I3 and M1–M3.
