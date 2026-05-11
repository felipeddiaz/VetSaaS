# ADR p9: Analytics anchor authority + provenance

**Fecha**: 2026-05-09
**Estado**: Implementado (Capa 1 + Capa 2)
**Documentos relacionados**:
- `docs/dashboard-metrics-contract.md` (v0.3)
- `docs/analytics-schema-audit.md`
- `docs/analytics-readiness-checklist.md`

## Contexto

Antes de construir cualquier dashboard analítico se hizo una auditoría de
schema buscando "analytics lies": situaciones donde una métrica reportaría
silenciosamente un número incorrecto. Hallazgos críticos:

- `Invoice.confirmed_at` y `Invoice.cancelled_at` no existían → accrual y
  cancellation count solo derivables vía join a `InvoiceAuditLog`.
- `Invoice.paid_at` existía pero su único writer estaba en `views.py`, no
  en `services.py` — inconsistente con `confirm_invoice`/`cancel_invoice`.
- `MedicalRecord.closed_at` existía pero sin invariante DB. Cualquier
  `mr.status='closed'; mr.save()` desde shell o queryset.update() dejaba
  el anchor NULL.
- `AppointmentDetailView.destroy()` cancelaba con `instance.status='canceled'`
  bypaseando `update_status` → no se creaba `AppointmentStatusChange`,
  destruyendo event lineage.
- Django admin permitía editar `Invoice.status` con `paid_at` readonly →
  un admin podía dejar status='paid' con `paid_at=NULL`.
- No había walk-in flag persistido: walk-ins se inferían de "no scheduled
  ancestor en AppointmentStatusChange", inferencia frágil.

## Decisión

Cada anchor temporal usado por analytics tiene:

1. **Existencia explícita** — columna dedicada (no derivada), `editable=False`.
2. **Single authoritative writer** en `services.py` (no en `views.py`,
   no en signals, no en admin).
3. **CHECK constraint** a nivel DB que enforces el invariante
   `status='X' ⇒ anchor_X IS NOT NULL`. Bloquea bypasses vía
   `queryset.update()`, `bulk_update()`, raw SQL, admin.
4. **Provenance field** (`*_source`) con choices `service|audit_log|fallback|unresolved|legacy`.
   `service` es default para nuevos writes; otros valores se setean solo en backfill.

### Cambios concretos

**Anchors agregados/migrados**:
- `Invoice.confirmed_at`, `Invoice.cancelled_at` (nuevos, billing/0016)
- `Invoice.paid_at_source`, `confirmed_at_source`, `cancelled_at_source`
- `MedicalRecord.closed_at_source`
- `Appointment.walk_in BooleanField(db_index=True)` (appointments/0010)

**Authoritative writers**:
- `pay_invoice` movido de `views.py` a `billing/services.py`. View es wrapper
  delgado.
- `confirm_invoice` ahora setea `confirmed_at + confirmed_at_source='service'`.
- `cancel_invoice` ahora setea `cancelled_at + cancelled_at_source='service'`.
- `close_medical_record` ahora setea `closed_at_source='service'`.
- `walk_in` view ahora setea `Appointment.walk_in=True` al crear.

**CHECK constraints**:
- `invoice_paid_status_requires_paid_at` (billing/0015)
- `invoice_confirmed_status_requires_confirmed_at` (billing/0017)
- `invoice_cancelled_status_requires_cancelled_at` (billing/0017)
- `medicalrecord_closed_status_requires_closed_at` (medical_records/0014)

**Defense in depth**:
- `MedicalRecord.save()` también valida invariant a nivel modelo
  (raise `ValidationError` si status='closed' AND closed_at IS NULL).
- `InvoiceAdmin.readonly_fields` incluye `status`, `payment_method`,
  `paid_at`, `cancelled_at`, etc. Admin no puede mutar status sin pasar
  por services.
- `AppointmentDetailView.destroy()` ahora crea `AppointmentStatusChange`
  row en mismo `transaction.atomic()` para preservar lineage.

**Backfill no naive** (billing/0017):
Para `confirmed_at`, orden de preferencia:
1. Earliest `InvoiceAuditLog` row con `new_status='confirmed'` → `audit_log`
2. Latest audit row before any `paid` transition → `audit_log`
3. `created_at` SOLO si `status IN ('confirmed','paid')` AND no audit log → `fallback`
4. Otherwise: NULL + `confirmed_at_source='unresolved'`. NUNCA inventar timestamps.

Para `cancelled_at`: audit log → `updated_at` fallback.
Para `paid_at` existente (post-0015): mark all como `legacy` — no se puede
reconstruir provenance histórica.

### Decay alerts

`'legacy'` es one-way label. Para evitar que se vuelva "basura permanente
ignorada":

| Condición | Severidad | Acción |
|-----------|-----------|--------|
| `*_source='unresolved'` > 0 | P1 | Investigar inmediatamente |
| `fallback%` > 5% | warning | Inspeccionar fuente |
| `legacy` rows > 90d | critical | One-off backfill, eliminar `'legacy'` |

Enforcement:
- `python manage.py audit_anchor_integrity` (mgmt command, exit codes 0/1/2 para CI)
- `GET /api/internal/analytics-health/` (ADMIN_SAAS only) expone
  `legacy_decay_alerts` + `fallback_warnings` + `trust_score_per_anchor`

## Trust matrix (post-implementación)

| Anchor | Trust |
|--------|:-----:|
| `Invoice.paid_at` | A (DB-enforced + service writer) |
| `Invoice.confirmed_at` | A |
| `Invoice.cancelled_at` | A |
| `MedicalRecord.closed_at` | A (CHECK + save() guard) |
| `Appointment.walk_in` | A (persisted, not inferred) |
| `Organization.timezone_updated_at` | A (preexistente) |
| `Appointment.done_at` | D (no almacenado, contract usa `start_datetime`) |
| `VaccineRecord.application_date` / `next_due_date` | B (user-supplied) |

## Consecuencias

- Cualquier flujo nuevo que mute estado en estos modelos DEBE pasar por
  service. Un PR que escriba `invoice.status='paid'` directo es bug.
- Backfills futuros DEBEN respetar la política de provenance — NO setear
  anchors falsos. `'unresolved'` es preferible a un timestamp inventado.
- Tests obligatorios cuando se agregue un nuevo anchor:
  (a) writer en service, (b) CHECK constraint, (c) provenance field,
  (d) bulk-bypass resistance.
