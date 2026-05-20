"""
Capa 4 minimal v1 snapshot services.

Public surface (use ONLY these from outside the module):
- is_bucket_frozen(metric_class, bucket_date, organization, *, now=None) → bool
- compute_daily_metrics(organization, bucket_date, *, now=None) → dict (pure; no writes)
- apply_snapshot(organization, bucket_date, *, force=False, user=None, now=None) → DailyOrgMetrics
- TODAY_REJECTED — exception raised when caller asks for "today" snapshot
- _analytics_queryset(model_cls) → manager (resolve visibility policy)
- ANALYTICS_VISIBILITY — static policy registry (governed, ADR p17)
- ANCHOR_REGISTRY — static anchor metadata (governed, ADR p17)

Design rules:
- Single helper for freeze decisions. No timezone.now() scattered. DST,
  rebuilds, late imports, TZ changes all touch ONE function.
- now is an argument, never a side-effect. timezone.now() is called ONCE
  at the entry point (mgmt command or HTTP view) and threaded through every
  helper that needs it. No internal re-read of timezone.now().
- compute_daily_metrics is pure: same inputs → same outputs (modulo source
  data changes between calls). Idempotency tests rely on this.
- apply_snapshot writes only when computed values differ from existing row.
  built_at advances on every write. lifecycle_state transitions are logged.
- \"today\" is never snapshotted. Today belongs to live aggregates per the
  contract. Caller gets a TODAY_REJECTED.
- corrupt rows are NOT silently dropped. They are persisted with
  lifecycle_state='corrupt' so audit endpoints can surface them.
- ANALYTICS_VISIBILITY and ANCHOR_REGISTRY are separate static constants.
  Neither uses callables, lambdas, dynamic imports, or runtime registration.
  Modifications require ADR + impact analysis + PO sign-off for financial metrics.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import logging

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.datetime_utils import (
    get_context_timezone,
    local_day_bounds_utc,
    org_today_local,
)

from .models import (
    DailyOrgMetrics,
    DashboardSnapshotAudit,
    LIFECYCLE_CORRUPT,
    LIFECYCLE_FROZEN,
    LIFECYCLE_PROVISIONAL,
    LIFECYCLE_REBUILT,
    METRICS_SCHEMA_VERSION,
)


logger = logging.getLogger('analytics.events')


class TodayRejected(Exception):
    """Raised when caller asks for a snapshot of the current org-local day."""


TODAY_REJECTED = TodayRejected


# ---------------------------------------------------------------------------
# Mutation windows — class → freeze_after_days. Source: contract §4.2.
# v1 covers only metrics in the v1 schema. Adding KPIs in v2 means adding
# entries here AND bumping METRICS_SCHEMA_VERSION.
# ---------------------------------------------------------------------------
DEFAULT_FREEZE_DAYS = 2  # cash basis financial + clinical activity
METRIC_CLASS_FREEZE_DAYS = {
    'operational': 1,   # appointments, walk-ins
    'clinical': 2,      # records closed, prescriptions, vaccines
    'financial_cash': 2,
    # The v1 minimal table is a single row per day that mixes classes.
    # We pick the LONGEST window of the included metrics to be conservative —
    # v1 only freezes after T+2.
}
V1_TABLE_FREEZE_DAYS = max(METRIC_CLASS_FREEZE_DAYS.values())


# ---------------------------------------------------------------------------
# ANALYTICS_VISIBILITY — static policy registry (ADR p17).
#
# Maps model → visibility policy for analytics-side reads.
# Governance is BINDING: modifications require ADR + impact analysis +
# PO sign-off if financial metrics are affected. DO NOT add lambdas,
# callables, dynamic imports, or plugin hooks.
#
# Policies:
#   'historical' → model_cls.all_objects (count all rows, active or inactive)
#
# Future (DO NOT add without ADR):
#   'historical_excluding_voided' → when voided_at column exists
#   'historical_excluding_archived' → when archived_at column exists
# ---------------------------------------------------------------------------
ANALYTICS_VISIBILITY = {
    'billing.Invoice':                'historical',
    'medical_records.MedicalRecord':  'historical',
    'appointments.Appointment':       'historical',
    'medical_records.VaccineRecord':  'historical',
}


def _analytics_queryset(model_cls):
    """
    Resolve the correct manager for an analytics-side read per ANALYTICS_VISIBILITY.

    Returns a manager (e.g. model_cls.all_objects) that the caller then chains
    with .filter(organization=org, ...).
    """
    dotted = f"{model_cls._meta.app_label}.{model_cls.__name__}"
    policy = ANALYTICS_VISIBILITY[dotted]
    if policy == 'historical':
        return model_cls.all_objects
    raise NotImplementedError(f"Policy {policy!r} requires ADR.")


# ---------------------------------------------------------------------------
# ANCHOR_REGISTRY — static anchor metadata (ADR p17).
#
# Describes every temporal anchor used by analytics computations.
# compute_daily_metrics, analytics_health, and audit_anchor_integrity
# derive their anchor lists from here. Replaces the parallel duplicated
# arrays that existed before Día 5.
#
# Governance identical to ANALYTICS_VISIBILITY:
# - Metadata static only (strings, dataclass fields).
# - No callables, no runtime registration.
# - New entries require ADR + impact analysis.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AnchorSpec:
    model: str               # 'billing.Invoice'
    anchor_field: str        # 'paid_at'
    source_field: str        # 'paid_at_source'
    status_filter: dict      # {'status': 'paid'} or {'status__in': [...]}
    metric_class: str        # 'financial_cash' | 'clinical' | 'operational'


ANCHOR_REGISTRY = (
    AnchorSpec(model='billing.Invoice',
               anchor_field='paid_at',
               source_field='paid_at_source',
               status_filter={'status': 'paid'},
               metric_class='financial_cash'),
    AnchorSpec(model='billing.Invoice',
               anchor_field='confirmed_at',
               source_field='confirmed_at_source',
               status_filter={'status__in': ['confirmed', 'paid']},
               metric_class='financial_cash'),
    AnchorSpec(model='billing.Invoice',
               anchor_field='cancelled_at',
               source_field='cancelled_at_source',
               status_filter={'status': 'cancelled'},
               metric_class='financial_cash'),
    AnchorSpec(model='medical_records.MedicalRecord',
               anchor_field='closed_at',
               source_field='closed_at_source',
               status_filter={'status': 'closed'},
               metric_class='clinical'),
)


# ---------------------------------------------------------------------------
# Freeze helper — single source of truth.
# ---------------------------------------------------------------------------
def is_bucket_frozen(metric_class, bucket_date, organization, *, now=None):
    """
    Return True iff the (organization, bucket_date) snapshot should be
    considered frozen relative to NOW.

    `metric_class` selects the freeze window (per contract §4.2). Pass
    'v1_table' for the v1 minimal DailyOrgMetrics table (uses longest of
    the included classes, T+2).

    `now` is injectable for tests. Production passes nothing and gets
    timezone.now().
    """
    now = now or timezone.now()
    today_local = org_today_local(organization, now=now)
    age_days = (today_local - bucket_date).days
    if age_days < 0:
        # Future bucket — never frozen, never built.
        return False
    if metric_class == 'v1_table':
        threshold = V1_TABLE_FREEZE_DAYS
    else:
        threshold = METRIC_CLASS_FREEZE_DAYS.get(metric_class, DEFAULT_FREEZE_DAYS)
    return age_days > threshold


# ---------------------------------------------------------------------------
# Pure computation — no writes.
# ---------------------------------------------------------------------------
def compute_daily_metrics(organization, bucket_date, *, now=None):
    """
    Compute the seven v1 KPIs for (organization, bucket_date). Returns a dict
    plus diagnostic counters. Does NOT touch DailyOrgMetrics / DashboardSnapshotAudit.

    ``now`` is accepted for signature symmetry with other analytics functions.
    The computation itself does not depend on ``now`` — it uses ``bucket_date``
    directly for UTC day bounds.
    """
    from apps.appointments.models import Appointment
    from apps.billing.models import Invoice
    from apps.medical_records.models import MedicalRecord

    start_utc, end_utc = local_day_bounds_utc(organization, bucket_date)

    # ---- Financial cash basis: anchored on paid_at ----
    invoice_paid_agg = _analytics_queryset(Invoice).filter(
        organization=organization,
        status='paid',
        paid_at__gte=start_utc,
        paid_at__lt=end_utc,
    ).aggregate(
        rev=Sum('total'),
        n=Count('id'),
    )
    revenue_paid = invoice_paid_agg['rev'] or Decimal('0.00')
    invoices_paid_count = invoice_paid_agg['n'] or 0

    # Defensive: rows that match the status filter but somehow have NULL anchor.
    # Should be 0 post-Capa 1 CHECK constraints; keep as instrumentation.
    excluded_paid_anchor_missing = _analytics_queryset(Invoice).filter(
        organization=organization,
        status='paid',
        paid_at__isnull=True,
    ).count()

    # ---- Financial accrual: anchored on confirmed_at ----
    accrual_agg = _analytics_queryset(Invoice).filter(
        organization=organization,
        status__in=['confirmed', 'paid'],
        confirmed_at__gte=start_utc,
        confirmed_at__lt=end_utc,
    ).aggregate(rev=Sum('total'))
    revenue_accrual = accrual_agg['rev'] or Decimal('0.00')

    excluded_confirmed_anchor_missing = _analytics_queryset(Invoice).filter(
        organization=organization,
        status__in=['confirmed', 'paid'],
        confirmed_at__isnull=True,
    ).count()

    # ---- Operational: anchored on Appointment.start_datetime ----
    appt_agg = _analytics_queryset(Appointment).filter(
        organization=organization,
        start_datetime__gte=start_utc,
        start_datetime__lt=end_utc,
    ).aggregate(
        total=Count('id'),
        done=Count('id', filter=Q(status='done')),
        no_show=Count('id', filter=Q(status='no_show')),
    )

    # ---- Clinical: medical records closed (anchored on closed_at) ----
    mr_closed = _analytics_queryset(MedicalRecord).filter(
        organization=organization,
        status='closed',
        closed_at__gte=start_utc,
        closed_at__lt=end_utc,
    ).count()

    excluded_closed_anchor_missing = _analytics_queryset(MedicalRecord).filter(
        organization=organization,
        status='closed',
        closed_at__isnull=True,
    ).count()

    excluded_total = (
        excluded_paid_anchor_missing
        + excluded_confirmed_anchor_missing
        + excluded_closed_anchor_missing
    )

    # ---- Provenance mix for the rows that fed this snapshot ----
    paid_prov = _provenance_breakdown(
        _analytics_queryset(Invoice).filter(
            organization=organization,
            status='paid',
            paid_at__gte=start_utc,
            paid_at__lt=end_utc,
        ),
        'paid_at_source',
    )
    confirmed_prov = _provenance_breakdown(
        _analytics_queryset(Invoice).filter(
            organization=organization,
            status__in=['confirmed', 'paid'],
            confirmed_at__gte=start_utc,
            confirmed_at__lt=end_utc,
        ),
        'confirmed_at_source',
    )
    closed_prov = _provenance_breakdown(
        _analytics_queryset(MedicalRecord).filter(
            organization=organization,
            status='closed',
            closed_at__gte=start_utc,
            closed_at__lt=end_utc,
        ),
        'closed_at_source',
    )

    return {
        'revenue_paid': revenue_paid,
        'revenue_accrual': revenue_accrual,
        'invoices_paid_count': invoices_paid_count,
        'appointments_total': appt_agg['total'] or 0,
        'appointments_done': appt_agg['done'] or 0,
        'appointments_no_show': appt_agg['no_show'] or 0,
        'medical_records_closed': mr_closed,
        'excluded_anchor_missing': excluded_total,
        'provenance_mix': {
            'paid_at': paid_prov,
            'confirmed_at': confirmed_prov,
            'closed_at': closed_prov,
        },
    }


def _provenance_breakdown(qs, source_field):
    agg = qs.values(source_field).annotate(c=Count('id'))
    return {row[source_field]: row['c'] for row in agg}


# ---------------------------------------------------------------------------
# Idempotent write.
# ---------------------------------------------------------------------------
SNAPSHOT_VALUE_FIELDS = (
    'revenue_paid',
    'revenue_accrual',
    'invoices_paid_count',
    'appointments_total',
    'appointments_done',
    'appointments_no_show',
    'medical_records_closed',
    'excluded_anchor_missing',
    'provenance_mix',
)


@transaction.atomic
def apply_snapshot(organization, bucket_date, *, force=False, user=None, now=None):
    """
    Build (or rebuild) the snapshot row for (organization, bucket_date).

    Idempotent: if the existing row already matches the computed values and
    its lifecycle state is consistent, no DB write occurs and built_at is
    NOT advanced. The caller can run this twice in a row and the second
    call is a no-op except for an audit log entry indicating "no change".

    Today's date is rejected (TodayRejected raised). Rebuild of a frozen
    row requires force=True; otherwise a 'skip_frozen' audit row is written.

    corrupt detection: if computed excluded_anchor_missing > 0, the row is
    persisted with lifecycle_state='corrupt'. The numbers in the metric
    fields are still written so operators can inspect them, but downstream
    read endpoints MUST filter out corrupt rows.
    """
    now = now or timezone.now()
    today_local = org_today_local(organization, now=now)
    if bucket_date >= today_local:
        raise TodayRejected(
            f"Snapshot of {bucket_date} for org {organization.id} rejected: "
            f"date is today or in the future (today_local={today_local})."
        )

    frozen = is_bucket_frozen('v1_table', bucket_date, organization, now=now)
    existing = DailyOrgMetrics.objects.filter(
        organization=organization, date=bucket_date,
    ).first()

    if existing and existing.lifecycle_state == LIFECYCLE_FROZEN and not force:
        DashboardSnapshotAudit.objects.create(
            organization=organization,
            snapshot_date=bucket_date,
            kind='skip_frozen',
            from_state=existing.lifecycle_state,
            to_state=existing.lifecycle_state,
            reason='Frozen row, no --force supplied.',
            triggered_by=user,
            triggered_by_system=user is None,
        )
        logger.info(
            "DASH_SNAPSHOT_FROZEN_SKIPPED",
            extra={'organization_id': organization.id, 'date': bucket_date.isoformat()},
        )
        return existing

    computed = compute_daily_metrics(organization, bucket_date, now=now)

    target_lifecycle = (
        LIFECYCLE_CORRUPT if computed['excluded_anchor_missing'] > 0
        else (LIFECYCLE_FROZEN if frozen else LIFECYCLE_PROVISIONAL)
    )
    if existing and existing.lifecycle_state == LIFECYCLE_FROZEN and force:
        target_lifecycle = LIFECYCLE_REBUILT

    if existing is None:
        snapshot = DailyOrgMetrics(
            organization=organization,
            date=bucket_date,
            org_timezone_at_snapshot=str(get_context_timezone(organization)),
            metrics_schema_version=METRICS_SCHEMA_VERSION,
            lifecycle_state=target_lifecycle,
            **{k: computed[k] for k in SNAPSHOT_VALUE_FIELDS},
        )
        snapshot.save()
        DashboardSnapshotAudit.objects.create(
            organization=organization,
            snapshot_date=bucket_date,
            kind='build',
            from_state='',
            to_state=target_lifecycle,
            reason='Initial build.',
            triggered_by=user,
            triggered_by_system=user is None,
            diff={'created': True},
        )
        logger.info(
            "DASH_SNAPSHOT_BUILT",
            extra={
                'organization_id': organization.id,
                'date': bucket_date.isoformat(),
                'lifecycle': target_lifecycle,
                'excluded': computed['excluded_anchor_missing'],
            },
        )
        if target_lifecycle == LIFECYCLE_CORRUPT:
            _log_corruption(organization, bucket_date, computed, user)
        return snapshot

    # Row exists. Compute diff.
    diff = _diff_existing(existing, computed, target_lifecycle)
    if not diff:
        # Truly idempotent path: no value change AND no lifecycle change.
        # Do NOT advance built_at. Audit row records "no_change" implicitly
        # by NOT being created — keep the audit log signal-rich.
        logger.info(
            "DASH_SNAPSHOT_NO_CHANGE",
            extra={
                'organization_id': organization.id,
                'date': bucket_date.isoformat(),
            },
        )
        return existing

    from_state = existing.lifecycle_state
    for field in SNAPSHOT_VALUE_FIELDS:
        setattr(existing, field, computed[field])
    existing.lifecycle_state = target_lifecycle
    # built_at uses auto_now — touched by save().
    existing.save(update_fields=list(SNAPSHOT_VALUE_FIELDS) + ['lifecycle_state', 'built_at'])

    DashboardSnapshotAudit.objects.create(
        organization=organization,
        snapshot_date=bucket_date,
        kind='rebuild' if from_state == LIFECYCLE_FROZEN else 'build',
        from_state=from_state,
        to_state=target_lifecycle,
        reason='Recomputed; values changed.' if force else 'Recomputed.',
        triggered_by=user,
        triggered_by_system=user is None,
        diff=diff,
    )
    logger.info(
        "DASH_SNAPSHOT_BUILT",
        extra={
            'organization_id': organization.id,
            'date': bucket_date.isoformat(),
            'lifecycle': target_lifecycle,
            'excluded': computed['excluded_anchor_missing'],
            'diff_keys': list(diff.keys()),
        },
    )
    if target_lifecycle == LIFECYCLE_CORRUPT and from_state != LIFECYCLE_CORRUPT:
        _log_corruption(organization, bucket_date, computed, user)
    return existing


def _diff_existing(existing, computed, target_lifecycle):
    diff = {}
    for field in SNAPSHOT_VALUE_FIELDS:
        new_val = computed[field]
        old_val = getattr(existing, field)
        # Decimal vs float comparison is exact because both are Decimal.
        if old_val != new_val:
            diff[field] = {'from': _json_safe(old_val), 'to': _json_safe(new_val)}
    if existing.lifecycle_state != target_lifecycle:
        diff['lifecycle_state'] = {
            'from': existing.lifecycle_state, 'to': target_lifecycle,
        }
    return diff


def _json_safe(v):
    if isinstance(v, Decimal):
        return str(v)
    return v


def _log_corruption(organization, bucket_date, computed, user):
    DashboardSnapshotAudit.objects.create(
        organization=organization,
        snapshot_date=bucket_date,
        kind='corruption_detected',
        from_state='',
        to_state=LIFECYCLE_CORRUPT,
        reason=(
            f"excluded_anchor_missing={computed['excluded_anchor_missing']}; "
            "row excluded from charts but persisted for inspection."
        ),
        triggered_by=user,
        triggered_by_system=user is None,
        diff={'excluded_anchor_missing': computed['excluded_anchor_missing']},
    )
    logger.error(
        "DASH_SNAPSHOT_CORRUPT",
        extra={
            'organization_id': organization.id,
            'date': bucket_date.isoformat(),
            'excluded': computed['excluded_anchor_missing'],
        },
    )
