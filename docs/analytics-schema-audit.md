# Analytics Schema Audit

Version: 0.1
Owner: Backend
Status: PASO 2 of analytics roadmap. Read-only audit against current `develop` branch.
Last updated: 2026-05-09
Companion to: `dashboard-metrics-contract.md`, `analytics-readiness-checklist.md`

This document is the result of auditing the actual schema and code paths against every
anchor / FK / index / writer required by the dashboard contract. Findings are framed
not as "missing fields" but as **analytics lies**: situations where a metric would
silently report a wrong number because the underlying anchor is missing, mutable,
written from multiple places, bypassable, or temporally incorrect.

Method: read of `models.py`, `services.py`, `views.py`, `signals.py`, `admin.py` and
`serializers.py` for the four affected apps (`billing`, `medical_records`, `appointments`,
`organizations`), plus `grep` for `.update(`, `\.status\s*=\s*['"]`, `auto_now`, and
direct `closed_at|paid_at|...` writes. Did not run the code.

Legend:
- ✅ Verified present and correct.
- ⚠️ Present but with caveat — analytics is fragile.
- ⛔ Missing or broken — blocker for the metric.
- 🔓 Bypassable — there is a path that skips the authoritative writer.

---

## 1. Anchor matrix (5-dimensional + trust level per contract §2.7)

For each anchor: existence, reliability (always written when status changes),
unicity-of-writer, reversibility (can the anchor change after first write), temporal
correctness (does the timestamp represent the event), and indexing for snapshot queries.

**Trust levels** (executive read of analytics risk per anchor):

| Level | Meaning |
|-------|---------|
| **A** | DB-enforced (CHECK constraint or NOT NULL with logical guarantee) AND single writer in service layer |
| **B** | Single writer but only app-enforced (no DB-level invariant). Bypassable via shell / queryset / admin |
| **C** | Convention only — multiple write sites or no writer documented; works today by accident |
| **D** | Inferred from other fields / event history. Not stored explicitly |
| **F** | Missing entirely. Cannot be derived without lossy fallbacks |

| Anchor | Trust | Exists | Reliable | Single writer | Immutable | Indexed | Verdict |
|--------|:----:|:------:|:--------:|:-------------:|:---------:|:-------:|:--------|
| `Invoice.paid_at` | **B** | ✅ | ⚠️ | 🔓 | ⚠️ | ⛔ | Field present but writer is in `billing/views.py::pay_invoice`, NOT `services.py`. Inconsistent with `confirm_invoice` / `cancel_invoice`. Direct `Invoice.objects.update(status='paid')` would leave it NULL. Admin can edit `status` (paid_at is readonly so admin set-to-paid leaves NULL). Backfill source: `InvoiceAuditLog` rows with `new_status='paid'`. After C1+C2+C5+M14: → **A**. |
| `Invoice.confirmed_at` | **F** | ⛔ | — | — | — | ⛔ | **Field does not exist.** `confirm_invoice` mutates only `status`. The only authoritative timestamp for an "invoice was confirmed" event is `InvoiceAuditLog.created_at` where `new_status='confirmed'`. Hard blocker for `revenue_accrual` and `ar_aging_buckets`. After M1+M15: → **A**. |
| `Invoice.cancelled_at` | **F** | ⛔ | — | — | — | ⛔ | **Field does not exist.** Same situation. `InvoiceAuditLog` is the only source. **Decision (v0.3)**: ADD column, do NOT rely on audit-log anchor. Reasons: (a) consistency with `paid_at` / `confirmed_at`; (b) audit log writers can change semantics without breaking schema, silently corrupting metric; (c) negative-adjustment math in §2.8 of contract reads cleaner against an explicit timestamp. After M2: → **A** (with M15-equivalent constraint). |
| `MedicalRecord.closed_at` | **B** | ✅ | ⚠️ | 🔓 | ⚠️ | ⛔ | Field present, set in `medical_records/views.py::close_medical_record` line 420 inside `transaction.atomic()`. No model `save()` enforces invariant `status='closed' ⇒ closed_at IS NOT NULL`. Direct `mr.status='closed'; mr.save()` from any other code path leaves `closed_at` NULL. After C4+M16: → **A**. |
| `Appointment.done_at` | **D** | ⛔ | — | — | — | — | Inferred via `AppointmentStatusChange.created_at` where `to_status='done'`. Acceptable per contract §3.2.2 since `start_datetime` is the canonical anchor for daily bucketing. No "time-from-scheduled-to-done" v2 metric is feasible without adding the column. |
| `Appointment.canceled` (transition timestamp) | **D / 🔓** | ⛔ | — | — | — | — | No dedicated field. Worse: `AppointmentDetailView.destroy()` (line 79) does `instance.status='canceled'; instance.save()` which **bypasses `update_status` entirely** and therefore creates NO `AppointmentStatusChange` row. **Critical analytics lie 2.1**. After C3: bypass closed → trust rises to **D** (inferred via AppointmentStatusChange, but reliable). |
| `Appointment.walk_in` | **D** | ⛔ | — | — | — | — | Field does not exist. Walk-ins are inferred from "no `scheduled` ancestor in AppointmentStatusChange + status is `in_progress` at creation". Inference is fragile and breaks if any future flow legitimately starts a scheduled appointment via "force start". After M13+C7: → **A**. |
| `VaccineRecord.application_date` | **B** | ✅ | ✅ | ✅ | ⚠️ | ⛔ | Field is `DateField` (not DateTime) named `application_date` — contract section 3.3.7 says `applied_at`. Naming mismatch. Daily granularity is fine for `vaccines_applied`. User-supplied at create time, so "application_date in the past" is allowed (intentional — vaccine applied yesterday recorded today). No index on `(org, application_date)`. After M11: → **B** (still user-supplied; daily bucket OK). |
| `VaccineRecord.next_due_date` | **B** | ✅ | ✅ | ✅ | ✅ | ⛔ | Used by `vaccines_due_window`. No index on `(org, next_due_date)`. Will scan at scale. After M12: → **B**. |
| `Organization.timezone_updated_at` + `OrganizationTimezoneAudit` | **A** | ✅ | ✅ | ✅ | ✅ | n/a | **Already implemented**. `OrganizationSerializer.update()` writes `timezone_updated_at` and inserts `OrganizationTimezoneAudit` row. Closes checklist B5. |

### Trust score summary (current state)

| Trust | Anchors |
|-------|---------|
| **A** | 1 (Organization TZ) |
| **B** | 4 (paid_at, closed_at, application_date, next_due_date) |
| **C** | 0 |
| **D** | 3 (done_at, canceled timestamp, walk_in) |
| **F** | 2 (confirmed_at, cancelled_at) |

Half of all anchors are below trust level B. No financial anchor reaches A. Snapshots
built today against this state would be unreliable from day one.

### Trust score target (after Capa 1 + Capa 2 of the sprint)

| Trust | Anchors |
|-------|---------|
| **A** | 5 (Org TZ, paid_at, confirmed_at, cancelled_at, closed_at, walk_in) |
| **B** | 2 (application_date, next_due_date) |
| **D** | 1 (done_at — accepted, contract anchors elsewhere) |

This is the minimum bar before any snapshot infrastructure ships.

---

## 2. Analytics lies catalog (concrete bugs that WOULD emerge)

Each item below is a mistake the dashboard would silently make if it were built today
against the current schema.

### 2.1 Cancelled appointments via DELETE are invisible
**Source**: `appointments/views.py:79` — `AppointmentDetailView.destroy()` does
`instance.status='canceled'; instance.save()`. No `AppointmentStatusChange` row is
created.
**Lie**: any metric derived from `AppointmentStatusChange` (e.g. "cancellations per day
by user") undercounts. The Appointment row's status field eventually says `canceled`,
but the audit trail is missing the transition.
**Impact**: `appointments_canceled` metric — if anchored on `Appointment.status` is OK;
if anchored on `AppointmentStatusChange` is wrong. Contract anchors on
`Appointment.start_datetime` so the count is fine, BUT the *who-cancelled-when*
attribution metric for v2 is broken from day one.
**Fix**: route DELETE through `update_status` (or a shared helper) so the
`AppointmentStatusChange` row is always written. Alternatively, add a model `save()`
override that detects status transitions and records them — but that fights the
existing pattern.

### 2.2 `pay_invoice` lives in views, not services
**Source**: `billing/views.py:179` is the only site where `invoice.status='paid'` is
set. `confirm_invoice` and `cancel_invoice` are in `services.py`.
**Lie**: contract §2.7 says each anchor has a single authoritative *service*. Today
`paid_at` has a single writer but in the wrong layer. A future feature that needs to
mark an invoice paid (e.g. webhook from a payment provider, batch reconciliation
command) will either duplicate the logic in another view or import a view function from
a service module — both wrong.
**Impact**: not a current data bug, but a structural fragility that will cause
duplicate writers later. Migrate `pay_invoice` body to `billing/services.py::pay_invoice`
and have the view call it. Match the pattern of confirm/cancel.

### 2.3 No `Invoice.confirmed_at` makes accrual impossible without audit log join
**Source**: `billing/models.py:99` — only `paid_at` exists.
**Lie**: `revenue_accrual` (contract §3.1.2) is defined as "anchor `confirmed_at`".
With no column, snapshots must join `InvoiceAuditLog` to find when each invoice
became `confirmed`. That is a 2-table aggregation per snapshot run, slower at scale,
and broken if an invoice was confirmed twice (state machine prevents it today, but
the join would silently pick whichever audit row sorts first).
**Impact**: blocker B2 in checklist. Add `Invoice.confirmed_at` column and have
`confirm_invoice` set it inside the same atomic block. Backfill from `InvoiceAuditLog`
on migration.

### 2.4 No `Invoice.cancelled_at`
Same situation as 2.3, scoped to cancellations. Decision: add the column (consistent)
or commit to using `InvoiceAuditLog.created_at` filtered by `new_status='cancelled'`
as the anchor (cheaper migration but couples analytics to audit log forever).

### 2.5 `MedicalRecord` has no invariant `status='closed' ⇒ closed_at NOT NULL`
**Source**: `medical_records/models.py:35` defines `closed_at` as nullable. The model's
`save()` does NOT enforce that closing-the-record sets the timestamp. Today the only
code path that flips `status` to `closed` is the close view — but nothing prevents a
future migration / management command / shell session from doing
`mr.status='closed'; mr.save()` and producing a row that says "closed" with NULL
`closed_at`.
**Lie**: `medical_records_closed` snapshot would silently exclude the row (anchor NULL)
or count it on the wrong day if a fallback is used.
**Fix**: either (a) enforce in `save()` (`if status='closed' and not closed_at: raise`)
or (b) add a CHECK constraint at the DB level. Defense in depth: do both.

### 2.6 `paid_at` indexable only via `(org, status, created_at)` today
**Source**: `billing/models.py:131` — only one compound index. The aging query for
`ar_aging_buckets` filters on `(org, status='confirmed', confirmed_at)` and the cash
basis query filters on `(org, status='paid', paid_at)`. Neither is indexed.
**Lie**: at 2M invoices, a `revenue_paid` snapshot scan takes seconds where it should
take milliseconds. Snapshot job will eventually exceed its window.
**Fix**: add `Index(fields=['organization', 'status', 'paid_at'])` and (post-migration)
`Index(fields=['organization', 'status', 'confirmed_at'])`.

### 2.7 `MedicalRecord` index missing `appointment_id` for conversion
**Source**: only index is `(organization, pet, -created_at)`.
**Lie**: `done_to_invoice_conversion` joins `MedicalRecord` on `appointment_id`. With
no index, the snapshot query becomes a hash join over the whole MR table per night.
**Fix**: add `Index(fields=['organization', 'appointment'])` and
`Index(fields=['organization', 'status', '-closed_at'])`.

### 2.8 `Invoice.appointment_id` and `Invoice.medical_record_id` are not indexed
**Source**: only the OneToOne unique constraints (which create indexes implicitly), so
this is partially OK. But the dashboard query patterns include `WHERE
organization_id=X AND appointment_id IN (...)` — that's not the same access path.
Verify with `EXPLAIN` before declaring resolved.

### 2.9 Walk-in detection has no boolean field
**Source**: `Appointment` has no `walk_in` column. Walk-ins are inferred:
`appointments/views.py::walk_in` creates with `status='in_progress'` directly,
skipping `scheduled`. The only signal is "no `AppointmentStatusChange` from `scheduled`
to anything" — fragile.
**Lie**: `walk_ins_total` (contract §3.2.5) cannot be computed reliably. Counting
`status='in_progress' AND no scheduled history` is brittle and breaks if a real
scheduled appointment gets manually set to `in_progress` via admin or via a future
"force start" feature.
**Fix**: add `Appointment.walk_in BooleanField(default=False)`; set `True` in the
walk-in creation view. Backfill from `AppointmentStatusChange` history (rows where the
appointment has no scheduled→x transition).

### 2.10 `Appointment.priority` does not exist
**Source**: not in model.
**Lie**: contract §3.2.8 listed `priority` as a field on `next_appointments`. With no
field, that column is just absent. Drop from contract or add with `choices=('low',
'normal', 'high')`. Not a blocker.

### 2.11 `VaccineRecord` field is `application_date` not `applied_at`
**Source**: `medical_records/models.py:84`. `DateField` (not DateTime).
**Lie**: contract calls it `applied_at` and assumes DateTime. Cosmetic mismatch + the
contract should not promise sub-day granularity for vaccines. Update contract to use
`application_date` and acknowledge daily granularity is the cap.

### 2.12 No index on `VaccineRecord.next_due_date`
**Source**: `medical_records/models.py:103-105` — only index is
`(pet, vaccine_name)`.
**Lie**: `vaccines_due_window` does `WHERE organization=X AND next_due_date BETWEEN ...`
which scans every vaccine record in the org.
**Fix**: add `Index(fields=['organization', 'next_due_date'])`.

### 2.13 `auto_now` is correctly NOT used on any analytics anchor
**Verified**: every `auto_now` usage is on `updated_at`. No anchor (`paid_at`,
`closed_at`, `application_date`, `next_due_date`, `recorded_at`) uses `auto_now`.
This is correct — `auto_now` would re-write the anchor on any save, destroying
historical correctness.
**However**: `updated_at` IS being used implicitly to gate the "anti-stale check" in
the stepper (per `CONTEXTO_ACTUAL_PROYECTO.md` ADR-p4). That's fine for optimistic
concurrency, NOT fine if any analytics metric is ever derived from `updated_at`. Audit
periodically that no future code uses `updated_at` as an event timestamp.

### 2.14 `Invoice.recalculate_totals` uses `all_objects.update`
**Source**: `billing/models.py:122`.
**Verdict**: ✅ acceptable. Updates only money fields, not status / timestamps. Does
not touch any analytics anchor. The pattern is documented and tenant-safe because the
filter is by `pk`. No lie here.

### 2.15 Django admin can edit `Invoice.status` without setting `paid_at`
**Source**: `billing/admin.py:23` — `paid_at` is readonly, but `status` is editable
(not in `readonly_fields`). An admin user can change status to `paid` via Django admin
and `paid_at` stays NULL.
**Lie**: an "admin-paid" invoice never appears in `revenue_paid` snapshots.
**Fix**: either add `status` to readonly_fields in admin (force admins to use the API)
or override `save_model` to call `pay_invoice` service when status transitions.

### 2.16 Django admin: no `MedicalRecord` admin, no `Appointment` admin
**Verified**: only `Invoice`, `Service`, `MedicalRecordProduct` are registered in admin.
No risk of admin bypass for medical_records / appointments anchors. ✅

### 2.17 `create_draft_invoice_on_done` signal is conditionally idempotent
**Source**: `billing/signals.py:9-53`. Triggers on every `Appointment.save()` if
`status='done'`. The `get_or_create(appointment=instance)` makes it safe against
duplicates per appointment, but it fires on every save of a done appointment (e.g.
editing notes on a done appointment). Cheap (existence check) but unnecessary.
**Verdict**: ⚠️ not a lie, but a noisy hot path. Add `if kwargs.get('update_fields')
and 'status' not in kwargs['update_fields']: return`.

### 2.18 `assign_patient` does `MedicalRecord.objects.filter(...).update(pet=...)`
**Source**: `appointments/views.py:223`. Bypasses `MedicalRecord.save()` and any future
signals. Only updates `pet`. No analytics anchor affected today.
**Verdict**: ✅ acceptable for v1, but worth a comment explaining why.

---

## 3. Required migrations (ordered, with rationale)

| # | Migration | Reason | Affected metrics |
|---|-----------|--------|------------------|
| M1 | `Invoice.confirmed_at = DateTimeField(null=True, blank=True)` + backfill from `InvoiceAuditLog` | Anchor for accrual + AR aging | `revenue_accrual`, `ar_aging_buckets` |
| M2 | `Invoice.cancelled_at = DateTimeField(null=True, blank=True)` + backfill | Anchor for cancellation count, future net-revenue | `invoices_cancelled_count`, reversal adjustments |
| M3 | `Index(['organization','status','paid_at'])` on Invoice | Cash-basis snapshot scan | `revenue_paid`, `invoices_paid_count` |
| M4 | `Index(['organization','status','confirmed_at'])` on Invoice (after M1) | Accrual + AR aging scan | `revenue_accrual`, `ar_aging_buckets` |
| M5 | `Index(['organization','appointment'])` on Invoice | Conversion join | `done_to_invoice_conversion` |
| M6 | `Index(['organization','medical_record'])` on Invoice | Conversion join (walk-in path) | `done_to_invoice_conversion` |
| M7 | `Index(['organization','status','-closed_at'])` on MedicalRecord | Closed-records snapshot | `medical_records_closed` |
| M8 | `Index(['organization','appointment'])` on MedicalRecord | `appointments_done_without_medical_record` | clinical backlog |
| M9 | `Index(['organization','status','-created_at'])` on MedicalRecord | Open backlog scans | `medical_records_open*` |
| M10 | `Index(['organization','start_datetime','status'])` on Appointment | Operational rollups (replaces existing `(org,date,status)` which uses local `date`, not the indexed `start_datetime`) | all operational metrics |
| M11 | `Index(['organization','application_date'])` on VaccineRecord | `vaccines_applied` snapshot | clinical |
| M12 | `Index(['organization','next_due_date'])` on VaccineRecord | `vaccines_due_window` | clinical |
| M13 | `Appointment.walk_in = BooleanField(default=False)` + backfill from history (rows with no scheduled→* transition) | Walk-in metric authoritative source | `walk_ins_total` |
| M14 | CHECK constraint on Invoice: `status='paid' ⇒ paid_at IS NOT NULL` | Defense against admin / queryset.update bypass | analytics integrity |
| M15 | CHECK constraint on Invoice: `status='confirmed' ⇒ confirmed_at IS NOT NULL` (post M1) | Same | analytics integrity |
| M16 | CHECK constraint on MedicalRecord: `status='closed' ⇒ closed_at IS NOT NULL` | Same | clinical integrity |

Total: 16 migrations. M1, M2, M13 are data migrations (backfill); the rest are
metadata. M14–M16 must run AFTER backfills complete (they reject existing NULL rows
otherwise).

---

## 4. Required code fixes (independent of migrations)

| # | Fix | Where | Reason |
|---|-----|-------|--------|
| C1 | Move `pay_invoice` body to `billing/services.py::pay_invoice`; view becomes a thin wrapper | `billing/views.py:148-184` → `billing/services.py` | Single authoritative writer (contract §2.7) |
| C2 | Add `services.py::pay_invoice` to set `paid_at` inside the same atomic block | new function | Mirror `confirm_invoice` / `cancel_invoice` pattern |
| C3 | Route `AppointmentDetailView.destroy()` cancellation through `update_status` (or a shared `_cancel_appointment(...)` helper) so `AppointmentStatusChange` is always written | `appointments/views.py:72-81` | Fix lie 2.1 |
| C4 | Add `MedicalRecord.save()` guard: if `status='closed'` and `closed_at is None`, raise `ValueError` (or auto-set with logged warning) | `medical_records/models.py` | Fix lie 2.5 |
| C5 | Lock `Invoice.status` field in admin: either add to `readonly_fields` or override `save_model` to call services | `billing/admin.py` | Fix lie 2.15 |
| C6 | `create_draft_invoice_on_done` signal: short-circuit if `update_fields` is set and does not include `status` | `billing/signals.py` | Fix lie 2.17 (perf) |
| C7 | Add `Appointment.walk_in` write in `walk_in` view (post M13) | `appointments/views.py:379` | Authoritative writer for walk-in flag |
| C8 | Update `OrganizationalModel` or add unit test asserting that no `.update(status=...)` calls exist outside services in the four affected apps | `apps/billing`, `apps/medical_records`, `apps/appointments` | Anti-regression for §2.7 |

---

## 5. Contract amendments (from this audit)

The dashboard contract v0.2 needs minor edits before implementation, recorded here so
they can be applied as v0.3:

- §3.2.5 / §3.3.7 / §3.3.8: rename `applied_at` → `application_date` and `next_due` →
  `next_due_date` to match the actual model. Acknowledge daily granularity.
- §3.2.8 `next_appointments`: drop `priority` field (does not exist).
- §3.1.2: `Invoice.confirmed_at` is **planned** (M1 above), not present today.
  Implementation step "B2" in checklist remains a hard blocker.
- §3.1.6: `Invoice.cancelled_at` is **planned** (M2 above). Until M2 ships, anchor
  on `InvoiceAuditLog.created_at` filtered by `new_status='cancelled'`.
- §2.7 event-authority table: list `pay_invoice` as `billing/services.py::pay_invoice`
  with note "currently in views, fix C1 above before this is true".
- §3.2.5 `walk_ins_total`: anchor changes from inferred to `Appointment.walk_in=True`
  after M13 ships. Until then the metric is unreliable (lie 2.9).

---

## 6. Re-stated readiness checklist (verdict per row)

Updates to `analytics-readiness-checklist.md` §1, §2, §3:

§1 — Anchors:
- T1 `Invoice.paid_at` → ⚠️ (exists; fix C1+C2 to make writer canonical, then ✅)
- T2 `Invoice.confirmed_at` → ⛔ (M1 required)
- T3 `Invoice.cancelled_at` → ⛔ (M2 required) — OR commit to audit-log anchor
- T4 `MedicalRecord.closed_at` → ⚠️ (exists; fix C4+M16 to enforce invariant)
- T5 `Appointment.done_at` → ⛔ acceptable (contract uses `start_datetime`)
- T6 `VaccineRecord` anchor → ✅ as `application_date` (rename in contract)

§2 — FKs:
- F1 `MedicalRecord.appointment_id` → ✅ exists, ⛔ index missing (M8)
- F2 `Invoice.appointment_id` → ✅ exists (OneToOne), ⛔ compound index for query pattern (M5)
- F3 `Invoice.medical_record_id` → ✅ exists (OneToOne), ⛔ compound index (M6)
- F4, F5 → ✅

§3 — Indexes: every row in the indexes table maps to M3–M12. None present today.

§4 — Authoritative services: S1 needs C1+C2; S2 ✅; S3 needs M2 first; S4 ✅
(reinforce with C4); S5 acceptable (no field).

§5 — Tables to create: unchanged (C1, C2, C3 in checklist still required).

§6 — Late-arriving data: unchanged (no enforcement today).

§7 — Cancellation/reversal: depends on M2 + `MetricAdjustments` table.

§8 — Throttling: unchanged (none of the dashboard scopes exist).

§9 — Multi-tenant tests: unchanged (none built).

---

## 7. Implementation order (concrete, after this audit)

Strict sequence. Skipping ahead invalidates downstream work.

1. **Code fixes that don't need migrations**: C1, C2 (move pay_invoice), C5 (admin
   lock), C6 (signal short-circuit). These can land today, no schema change.
2. **Migration wave 1 — schema**: M1, M2, M13 (new columns) + M3–M12 (indexes).
   Backfill scripts for M1 and M2 from `InvoiceAuditLog`. Backfill for M13 from
   `AppointmentStatusChange` history.
3. **Code fixes that depend on migrations**: C7 (set walk_in on creation),
   anchor wiring in services (set `confirmed_at`, `cancelled_at`).
4. **Migration wave 2 — invariants**: M14, M15, M16 (CHECK constraints). Will fail
   if backfill from wave 1 was incomplete — that is the point.
5. **Code fix C4** (model `save()` guard) — defense in depth alongside M16.
6. **Code fix C3** (route DELETE cancel through update_status) — closes lie 2.1.
7. **Code fix C8** (anti-regression test).
8. **Contract bump to v0.3** with the amendments in §5 above.
9. **Then and only then**: build `MetricAdjustments` table, build `DailyOrgMetrics`,
   write the nightly job. Per checklist §10 sign-off gate.

Estimated migrations: 16. Estimated code fixes: 8. Total scope before any snapshot
table is created: roughly one focused sprint.

---

## 7B. Capa 3 — Indexes (applied 2026-05-09)

The following indexes were created. Naming kept short due to PostgreSQL's
30-char limit on Django index names.

| Index | Table | Columns | Used by |
|-------|-------|---------|---------|
| `idx_inv_org_status_paid` | `billing_invoice` | (organization, status, paid_at) | `revenue_paid`, `invoices_paid_count`, `tax_collected` |
| `idx_inv_org_status_conf` | `billing_invoice` | (organization, status, confirmed_at) | `revenue_accrual`, `ar_aging_buckets` |
| `idx_inv_org_status_canc` | `billing_invoice` | (organization, status, cancelled_at) | `invoices_cancelled_count`, reversal lookups |
| `idx_mr_org_status_closed_at` | `medical_records_medicalrecord` | (organization, status, -closed_at) | `medical_records_closed`, `consultations_with_charges` |
| `idx_mr_org_appointment` | `medical_records_medicalrecord` | (organization, appointment) | `appointments_done_without_medical_record`, `done_to_invoice_conversion` |
| `idx_mr_org_status_created` | `medical_records_medicalrecord` | (organization, status, -created_at) | `medical_records_open*` |
| `idx_appt_org_start_status` | `appointments_appointment` | (organization, start_datetime, status) | every operational rollup |
| `idx_vacc_org_app_date` | `medical_records_vaccinerecord` | (organization, application_date) | `vaccines_applied` |
| `idx_vacc_org_next_due` | `medical_records_vaccinerecord` | (organization, next_due_date) | `vaccines_due_window` |
| `idx_stockmov_org_pres_created` | `inventory_stockmovement` | (organization, presentation, -created_at) | `ProductDailyConsumption`, stockout prediction |
| `idx_presc_org_created` | `prescriptions_prescription` | (organization, -created_at) | `prescriptions_issued` |

### EXPLAIN findings (dev DB, sparse data)

`EXPLAIN` was executed against representative analytics queries. With small
tables PG legitimately prefers `Seq Scan` and that does not invalidate the
indexes — they exist and are usable. To verify each index could be chosen,
queries were re-run with `SET enable_seqscan=off` and the planner picked
the expected index in every case (or a viable alternative on tied costs).

Notable nuances surfaced for production tuning:

- `mr_closed` and `mr_open_backlog`: with empty stats the planner prefers
  the auto-generated single-column index on `status` over the new compound
  `(organization, status, -closed_at)`. After production data accumulates,
  run `ANALYZE` explicitly so the planner re-prices and switches.
- `vacc_due` picks `idx_vacc_org_app_date` instead of the better
  `idx_vacc_org_next_due` because both indexes share the leading `org` key
  and the planner sees no win. Will resolve under real cardinality.
- For `done_to_invoice_conversion`, the anti-join planner picks
  `idx_mr_org_status_created` for the MR side and `idx_appt_org_start_status`
  for the Appt side. That is the desired path.

**Operational rule**: after each significant data import or after the
nightly snapshot job runs for the first time, run `ANALYZE billing_invoice;`
`ANALYZE medical_records_medicalrecord;` `ANALYZE appointments_appointment;`
`ANALYZE inventory_stockmovement;` `ANALYZE medical_records_vaccinerecord;`
to give the planner real statistics. PG autovacuum will catch up eventually,
but the first dashboard page load after a backfill should not pay the
"first analyze" tax.

---

## 7C. Legacy provenance decay policy

Provenance source `'legacy'` exists to acknowledge that we do not know how
existing rows were originally written. It is intentionally a one-way label:
any row created BEFORE provenance tracking carries it forever, because we
have no signal to upgrade them.

Risk: `'legacy'` quietly becomes "permanent corruption ignored". Counter
that by alerting and budgeting cleanup work.

| Condition | Severity | Action |
|-----------|----------|--------|
| any row with `*_source='unresolved'` | P1 | Investigate immediately. Either set the correct anchor manually with audit log evidence, or change the row's status so the invariant no longer applies. Do NOT silence the alert. |
| `fallback%` of any anchor > 5% of total non-zero rows | warning | Inspect what produced the fallback writes. Likely a bypass path or a migration that didn't have authoritative data. Patch the source. |
| `legacy` rows still present 90 days after the provenance migration shipped | warning → critical (`>90d`) | Run a one-off backfill task that uses the most recent available signal (audit log, updated_at) and either upgrades to `audit_log`/`fallback` or marks as `unresolved`. The point is to STOP reporting `'legacy'` — every row should be classified. |
| any anchor has 0 rows but the model has rows in the relevant status | informational | Snapshots will be missing data. Triggers a re-run of the audit_anchor_integrity command. |

These thresholds are enforced by:

1. `audit_anchor_integrity` mgmt command — emits non-zero exit code when
   invariant violations or unresolved rows exist. Wire to nightly cron;
   page on non-zero exit.
2. `/api/internal/analytics-health/` endpoint — returns
   `legacy_decay_alerts` and `fallback_warnings` arrays. Scrape from
   monitoring stack.

The trust score per anchor in the analytics-health response collapses all
of the above into a single A/B/C/D/F for at-a-glance health.

---

## 8. What this audit did NOT cover

For full transparency, items intentionally out of scope of PASO 2:

- Performance test of the proposed indexes against a representative dataset (need
  `EXPLAIN ANALYZE` on staging with realistic row counts).
- Audit of `prescriptions` and `inventory` apps (relevant for `prescriptions_issued`
  and `ProductDailyConsumption` but lower priority — financial / clinical first).
- `users.User` and `patients.Pet` audit for soft-delete / merge flows that could
  retroactively change snapshot identity.
- Cron infrastructure on Railway (whether per-org local-time scheduling is realistic
  or we settle for a single global UTC cron — contract §4.4 already accepts UTC for v1).
- Migration rehearsal on a copy of production data.

These belong to PASO 3 (build) and PASO 4 (rehearse), which start only after this
audit's findings are resolved.
