from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.datetime_utils import (
    filter_by_local_day,
    get_context_timezone,
    local_day_bounds_utc,
    org_now_utc,
    org_today_local,
)
from apps.core.permissions import make_permission
from apps.medical_records.models import MedicalRecord
from apps.appointments.models import Appointment


# ---------------------------------------------------------------------------
# Analytics anchor health — operations / monitoring endpoint.
# Restringido a ADMIN_SAAS (rol estático platform-wide; el contrato analítico
# es responsabilidad del operador del SaaS, no de admins por organización).
# Devuelve provenance distribution + invariant findings + decay alerts.
# Diseñado para consumo por monitoring stack o por humano via curl.
# ---------------------------------------------------------------------------

LEGACY_DECAY_THRESHOLD_DAYS = 90
FALLBACK_WARN_PERCENT = 5.0


class IsAdminSaaS(permissions.BasePermission):
    message = "Solo ADMIN_SAAS puede consultar este endpoint."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'role', None) == 'ADMIN_SAAS'
        )


def _provenance_dist(model, source_field, org_filter):
    agg = (
        model.objects.filter(org_filter)
        .values(source_field)
        .annotate(c=Count('id'))
    )
    return {row[source_field]: row['c'] for row in agg}


def _trust_score(provenance, invariant_violations, unresolved_count):
    """Compute single-letter trust score per the audit doc convention."""
    if invariant_violations > 0:
        return 'F'
    if unresolved_count > 0:
        return 'C'
    fallback = sum(
        v for k, v in provenance.items() if k == 'fallback'
    )
    legacy = sum(v for k, v in provenance.items() if k == 'legacy')
    total = sum(provenance.values()) or 1
    fallback_pct = (fallback / total) * 100
    if fallback_pct > FALLBACK_WARN_PERCENT:
        return 'B'
    if legacy > 0:
        return 'B'
    return 'A'


@api_view(['GET'])
@permission_classes([IsAdminSaaS])
def analytics_health(request):
    """
    Returns a JSON snapshot of analytics anchor health for monitoring.

    Response shape:
      {
        "anchors": {
          "invoice.paid_at": {"service": N, "fallback": N, "legacy": N, ...},
          ...
        },
        "invariant_violations": {
          "invoice.paid_status_requires_paid_at": N,
          ...
        },
        "unresolved_provenance": N,
        "walk_in_suspect_count": N,
        "legacy_decay_alerts": [
          {"anchor": "invoice.paid_at", "rows": N,
           "oldest_legacy_age_days": N, "threshold_days": 90,
           "severity": "warning|critical"}
        ],
        "fallback_warnings": [...],
        "trust_score_per_anchor": {"invoice.paid_at": "A", ...},
        "checked_at": "2026-05-09T..."
      }
    """
    from apps.billing.models import Invoice
    from apps.medical_records.models import MedicalRecord
    from apps.appointments.models import Appointment

    org_id = request.query_params.get('org')
    org_filter = Q(organization_id=org_id) if org_id else Q()
    now = timezone.now()
    decay_cutoff = now - timedelta(days=LEGACY_DECAY_THRESHOLD_DAYS)

    anchors = {
        'invoice.paid_at': _provenance_dist(Invoice, 'paid_at_source', org_filter),
        'invoice.confirmed_at': _provenance_dist(Invoice, 'confirmed_at_source', org_filter),
        'invoice.cancelled_at': _provenance_dist(Invoice, 'cancelled_at_source', org_filter),
        'medicalrecord.closed_at': _provenance_dist(MedicalRecord, 'closed_at_source', org_filter),
    }

    invariants = {
        'invoice.paid_status_requires_paid_at':
            Invoice.objects.filter(org_filter, status='paid', paid_at__isnull=True).count(),
        'invoice.confirmed_status_requires_confirmed_at':
            Invoice.objects.filter(
                org_filter, status__in=['confirmed', 'paid'], confirmed_at__isnull=True,
            ).count(),
        'invoice.cancelled_status_requires_cancelled_at':
            Invoice.objects.filter(org_filter, status='cancelled', cancelled_at__isnull=True).count(),
        'medicalrecord.closed_status_requires_closed_at':
            MedicalRecord.objects.filter(org_filter, status='closed', closed_at__isnull=True).count(),
    }

    unresolved = Invoice.objects.filter(
        org_filter & (Q(confirmed_at_source='unresolved') | Q(cancelled_at_source='unresolved'))
    ).count()

    walk_in_suspect = (
        Appointment.objects
        .filter(org_filter, walk_in=False, status__in=['in_progress', 'done'])
        .exclude(status_changes__from_status='scheduled')
        .distinct()
        .count()
    )

    # ---- Decay alerts ----
    decay_alerts = []
    fallback_warnings = []

    decay_specs = [
        (Invoice, 'paid_at_source', 'paid_at', 'invoice.paid_at'),
        (Invoice, 'confirmed_at_source', 'confirmed_at', 'invoice.confirmed_at'),
        (Invoice, 'cancelled_at_source', 'cancelled_at', 'invoice.cancelled_at'),
        (MedicalRecord, 'closed_at_source', 'closed_at', 'medicalrecord.closed_at'),
    ]
    for model, src_field, anchor_field, label in decay_specs:
        legacy_qs = model.objects.filter(org_filter, **{src_field: 'legacy'})
        legacy_count = legacy_qs.count()
        if legacy_count == 0:
            continue
        oldest = legacy_qs.order_by(anchor_field).values_list(anchor_field, flat=True).first()
        age_days = (now - oldest).days if oldest else 0
        decay_alerts.append({
            'anchor': label,
            'rows': legacy_count,
            'oldest_legacy_age_days': age_days,
            'threshold_days': LEGACY_DECAY_THRESHOLD_DAYS,
            'severity': 'critical' if age_days > LEGACY_DECAY_THRESHOLD_DAYS else 'warning',
        })

    # ---- Fallback % warnings ----
    for label, dist in anchors.items():
        total = sum(dist.values())
        if total == 0:
            continue
        fb = dist.get('fallback', 0)
        pct = (fb / total) * 100
        if pct > FALLBACK_WARN_PERCENT:
            fallback_warnings.append({
                'anchor': label,
                'fallback_count': fb,
                'total': total,
                'percent': round(pct, 2),
                'threshold_percent': FALLBACK_WARN_PERCENT,
            })

    trust_per = {}
    for label in anchors:
        related_invariant = sum(
            v for k, v in invariants.items() if k.startswith(label.split('.')[0])
        )
        trust_per[label] = _trust_score(
            anchors[label],
            related_invariant,
            unresolved if label.startswith('invoice') else 0,
        )

    return Response({
        'anchors': anchors,
        'invariant_violations': invariants,
        'unresolved_provenance': unresolved,
        'walk_in_suspect_count': walk_in_suspect,
        'legacy_decay_alerts': decay_alerts,
        'fallback_warnings': fallback_warnings,
        'trust_score_per_anchor': trust_per,
        'checked_at': now,
    })


@api_view(['GET'])
@permission_classes([make_permission("dashboard.view")])
def dashboard_stats(request):
    from apps.appointments.models import Appointment
    from apps.medical_records.models import MedicalRecord
    from apps.inventory.models import Product

    org = request.user.organization
    if org is None:
        raise PermissionDenied("User has no organization assigned")
    today_local = org_today_local(org)
    now_utc = org_now_utc(org)

    appointments_qs = Appointment.objects.for_organization(org).filter(
        status__in=['scheduled', 'done'],
    )
    appointments_today = filter_by_local_day(
        appointments_qs,
        'start_datetime',
        org,
        today_local,
    ).count()

    recent_records = MedicalRecord.objects.for_organization(org).order_by('-created_at').values(
        'id', 'pet__name', 'diagnosis', 'created_at',
        'veterinarian__first_name', 'veterinarian__last_name',
    )[:5]

    from django.db.models import F
    low_stock_qs = Product.objects.for_organization(org).filter(
        presentations__stock__lte=F('presentations__min_stock'),
    ).prefetch_related('presentations').distinct()
    low_stock = []
    for p in low_stock_qs:
        for pres in p.presentations.all():
            if pres.stock <= pres.min_stock:
                low_stock.append({
                    'id': p.id,
                    'name': p.name,
                    'presentation_name': pres.name,
                    'stock': str(pres.stock),
                    'min_stock': str(pres.min_stock),
                    'unit': pres.get_base_unit_display(),
                })

    recent_list = []
    for r in recent_records:
        vet_name = f"{r['veterinarian__first_name'] or ''} {r['veterinarian__last_name'] or ''}".strip()
        recent_list.append({
            'id': r['id'],
            'pet_name': r['pet__name'],
            'diagnosis': r['diagnosis'],
            'created_at': r['created_at'],
            'veterinarian_name': vet_name,
        })

    return Response({
        'appointments_today': appointments_today,
        'recent_records': recent_list,
        'low_stock_products': low_stock,
        'low_stock_count': len(low_stock),
        'effective_timezone': org.timezone,
        'server_now_utc': now_utc,
        'local_today': today_local,
    })


# ===========================================================================
# Capa 5 — Daily series read endpoints (JSON-first; no frontend yet).
#
# Contract per user directive: every datapoint carries explicit `source` and
# `lifecycle_state`. snapshot rows come from DailyOrgMetrics; today is
# computed live via apps.analytics.services.compute_daily_metrics. corrupt
# rows are filtered out — surfaced via /api/internal/analytics-health/.
# ===========================================================================

# Hard cap per dashboard contract §5.1 (daily granularity).
MAX_RANGE_DAYS = 365
DEFAULT_RANGE_DAYS = 30

OPERATIONAL_FIELDS = (
    'appointments_total',
    'appointments_done',
    'appointments_no_show',
    'medical_records_closed',
)
FINANCIAL_FIELDS = (
    'revenue_paid',
    'revenue_accrual',
    'invoices_paid_count',
)
# Default values for missing-snapshot days. Money fields default to a Decimal
# so the JSON shape stays consistent across present / missing days
# (always serialized as string).
MISSING_DAY_DEFAULTS = {
    'appointments_total': 0,
    'appointments_done': 0,
    'appointments_no_show': 0,
    'medical_records_closed': 0,
    'revenue_paid': Decimal('0.00'),
    'revenue_accrual': Decimal('0.00'),
    'invoices_paid_count': 0,
}


def _parse_range(request, org):
    """Parse ?from / ?to / ?include_today. Returns (from_date, to_date,
    include_today) or raises ValueError with a human-readable message."""
    today = org_today_local(org)
    raw_to = request.query_params.get('to')
    raw_from = request.query_params.get('from')
    include_today = request.query_params.get('include_today', 'true').lower() != 'false'

    if raw_to:
        try:
            to_date = datetime.strptime(raw_to, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError("Invalid 'to' date; expected YYYY-MM-DD.")
    else:
        to_date = today

    if raw_from:
        try:
            from_date = datetime.strptime(raw_from, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError("Invalid 'from' date; expected YYYY-MM-DD.")
    else:
        from_date = to_date - timedelta(days=DEFAULT_RANGE_DAYS - 1)

    if from_date > to_date:
        raise ValueError("'from' must be <= 'to'.")
    days = (to_date - from_date).days + 1
    if days > MAX_RANGE_DAYS:
        raise ValueError(
            f"Range exceeds max {MAX_RANGE_DAYS} days for daily granularity."
        )
    return from_date, to_date, include_today


def _build_series(org, from_date, to_date, fields, include_today):
    """
    Build the series of (bucket_date → datapoint) for the given inclusive
    range. Snapshots fill historical days. Today is computed live (if
    requested AND today is within the range).
    """
    from apps.analytics.models import DailyOrgMetrics, LIFECYCLE_CORRUPT
    from apps.analytics.services import compute_daily_metrics

    today = org_today_local(org)

    # Pull all non-corrupt snapshots in range. Skip today (snapshots never
    # cover today by service rule).
    snapshot_rows = (
        DailyOrgMetrics.objects
        .for_organization(org)
        .filter(date__gte=from_date, date__lte=min(to_date, today - timedelta(days=1)))
        .exclude(lifecycle_state=LIFECYCLE_CORRUPT)
        .order_by('date')
    )
    snap_by_date = {row.date: row for row in snapshot_rows}

    series = []
    cursor = from_date
    while cursor <= to_date and cursor < today:
        snap = snap_by_date.get(cursor)
        if snap is None:
            # No snapshot built yet for this day. Surface as missing rather
            # than fake-zero, so the consumer can decide how to render.
            series.append({
                'bucket_date': cursor,
                'source': 'snapshot',
                'lifecycle_state': 'missing',
                'metrics_schema_version': None,
                'metrics': {f: MISSING_DAY_DEFAULTS[f] for f in fields},
            })
        else:
            series.append({
                'bucket_date': snap.date,
                'source': 'snapshot',
                'lifecycle_state': snap.lifecycle_state,
                'metrics_schema_version': snap.metrics_schema_version,
                'metrics': {f: getattr(snap, f) for f in fields},
            })
        cursor += timedelta(days=1)

    today_payload = None
    if include_today and from_date <= today <= to_date:
        live = compute_daily_metrics(org, today)
        today_payload = {
            'bucket_date': today,
            'source': 'live',
            'lifecycle_state': None,
            'metrics_schema_version': None,
            'metrics': {f: live[f] for f in fields},
        }

    return series, today_payload


def _serialize_value(v):
    """Normalize Decimals to strings for JSON correctness (no float drift)."""
    if isinstance(v, Decimal):
        return str(v)
    return v


def _serialize_datapoint(dp):
    return {
        **dp,
        'bucket_date': dp['bucket_date'].isoformat(),
        'metrics': {k: _serialize_value(v) for k, v in dp['metrics'].items()},
    }


def _build_response(org, from_date, to_date, series, today, notes):
    return {
        'range': {
            'from': from_date.isoformat(),
            'to': to_date.isoformat(),
            'tz': str(get_context_timezone(org)),
        },
        'series': [_serialize_datapoint(dp) for dp in series],
        'today': _serialize_datapoint(today) if today else None,
        'notes': notes,
    }


def _series_endpoint(request, fields, permission_check):
    if request.user.organization is None:
        raise PermissionDenied("User has no organization assigned.")
    permission_check(request.user)
    try:
        from_date, to_date, include_today = _parse_range(request, request.user.organization)
    except ValueError as exc:
        return Response(
            {'detail': str(exc),
             'meta': {'max_range_days': MAX_RANGE_DAYS}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    series, today_payload = _build_series(
        request.user.organization, from_date, to_date, fields, include_today,
    )

    notes = []
    missing_count = sum(1 for d in series if d['lifecycle_state'] == 'missing')
    if missing_count:
        notes.append(
            f"{missing_count} day(s) in range have no snapshot yet — they "
            "will populate after the next nightly build."
        )
    return Response(_build_response(
        request.user.organization, from_date, to_date, series, today_payload, notes,
    ))


@api_view(['GET'])
@permission_classes([make_permission('dashboard.view')])
def operations_series(request):
    """
    Operational daily series. Visible to ASSISTANT, VET, ADMIN.
    Reuses 'dashboard.view' permission for now (broad). Can split into
    'dashboard.operations.view' in a later sprint without breaking clients.
    """
    return _series_endpoint(
        request,
        fields=OPERATIONAL_FIELDS,
        permission_check=lambda user: None,  # already gated by HybridPermission
    )


def _require_admin_for_financial(user):
    """Financial series is ADMIN-only at the role layer (defense in depth
    on top of make_permission). Hard refuse for other roles."""
    if getattr(user, 'role', None) not in ('ADMIN', 'ADMIN_SAAS'):
        raise PermissionDenied(
            "Financial dashboard data is restricted to administrators."
        )


@api_view(['GET'])
@permission_classes([make_permission('dashboard.financial.view')])
def financial_series(request):
    """
    Financial daily series. Visible to ADMIN only.
    Permission code 'dashboard.financial.view' must be granted to the
    ADMIN role via seed_permissions; ADMIN already gets it via wildcard.
    """
    return _series_endpoint(
        request,
        fields=FINANCIAL_FIELDS,
        permission_check=_require_admin_for_financial,
    )


# ===========================================================================
# Capa 5 — Dashboard Summary (Hybrid Ops)
#
# Single endpoint that returns everything the operational dashboard needs:
# KPIs, timeline (30-min slots), waiting room, backlog, and stock alerts.
# Designed for <4 DB queries per request. Cached with org-prefixed keys.
# ===========================================================================

import json
from datetime import time as dt_time
from django.core.cache import cache
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce

SUMMARY_CACHE_TTL = 30  # seconds — operational data, short TTL
SUMMARY_CACHE_PREFIX = 'dash:summary'


def _cache_key(org_id):
    return f'{SUMMARY_CACHE_PREFIX}:{org_id}'


@api_view(['GET'])
@permission_classes([make_permission('dashboard.summary')])
def dashboard_summary(request):
    user = request.user
    org = user.organization
    if org is None:
        raise PermissionDenied("User has no organization assigned.")

    cached = cache.get(_cache_key(org.id))
    if cached is not None:
        return Response(cached)

    today_local = org_today_local(org)
    today_bounds = local_day_bounds_utc(org, today_local)
    now_utc = org_now_utc(org)

    # ---- Query 1: Today's appointments ----
    appointments = list(
        Appointment.objects
        .for_organization(org)
        .filter(
            start_datetime__gte=today_bounds[0],
            start_datetime__lt=today_bounds[1],
        )
        .select_related('pet', 'veterinarian', 'pet__owner')
        .order_by('start_datetime')
    )

    # ---- Query 2: Low stock count ----
    from apps.inventory.models import Presentation
    low_stock_presentations = list(
        Presentation.objects
        .for_organization(org)
        .filter(stock__lte=F('min_stock'))
        .select_related('product')
        .order_by('stock')[:5]
    )

    # ---- Query 3: Backlog counts ----
    open_qs = MedicalRecord.objects.for_organization(org).filter(status='open')
    stale_cutoff = now_utc - timedelta(hours=24)
    backlog_agg = open_qs.aggregate(
        total=Count('id'),
        stale_24h=Count('id', filter=Q(created_at__lt=stale_cutoff)),
        without_diagnosis=Count(
            'id',
            filter=Q(diagnosis__isnull=True) | Q(diagnosis=''),
        ),
    )
    top_stale = list(
        open_qs.filter(created_at__lt=stale_cutoff)
        .select_related('pet', 'veterinarian')
        .order_by('created_at')[:1]
    )

    # ---- Query 4: AR outstanding (ADMIN only) ----
    is_admin = getattr(user, 'role', None) in ('ADMIN', 'ADMIN_SAAS')
    ar_outstanding = None
    if is_admin:
        from apps.billing.models import Invoice
        ar_outstanding = str(
            Invoice.objects
            .for_organization(org)
            .filter(status='confirmed')
            .aggregate(total=Coalesce(Sum('total'), Decimal('0.00')))['total']
            .quantize(Decimal('0.01'))
        )

    # ---- Build KPIs ----
    kpis = {
        'in_progress_now': sum(1 for a in appointments if a.status == 'in_progress'),
        'pending_today': sum(
            1 for a in appointments
            if a.status in ('scheduled', 'confirmed')
        ),
        'low_stock_count': len(low_stock_presentations),
        'patients_today': len(
            set(a.pet_id for a in appointments if a.pet_id is not None)
        ),
    }
    if is_admin:
        kpis['ar_outstanding'] = ar_outstanding

    # ---- Build Timeline (30-min slots) ----
    slots = _build_timeline_slots(appointments, org)

    # ---- Build Waiting Room ----
    waiting_room = _build_waiting_room(appointments, now_utc, org)

    # ---- Build Backlog ----
    backlog = {
        'open_total': backlog_agg['total'],
        'stale_24h': backlog_agg['stale_24h'],
        'without_diagnosis': backlog_agg['without_diagnosis'],
    }
    if top_stale:
        mr = top_stale[0]
        backlog['top_stale'] = {
            'pet_name': mr.pet.name if mr.pet else None,
            'veterinarian_name': (
                f"{mr.veterinarian.first_name} {mr.veterinarian.last_name}".strip()
                if mr.veterinarian else None
            ),
            'hours_open': round(
                (now_utc - mr.created_at).total_seconds() / 3600, 1
            ),
            'has_diagnosis': bool(mr.diagnosis and mr.diagnosis.strip()),
        }
    else:
        backlog['top_stale'] = None

    # ---- Build Stock Alerts ----
    stock_alerts = []
    for pres in low_stock_presentations:
        stock_alerts.append({
            'product_name': pres.product.name,
            'presentation_name': pres.name,
            'stock': str(pres.stock),
            'min_stock': str(pres.min_stock),
            'unit': pres.get_base_unit_display(),
            'severity': 'critical' if pres.stock == 0 else 'warning',
        })

    payload = {
        'kpis': kpis,
        'timeline': slots,
        'waiting_room': waiting_room,
        'backlog': backlog,
        'stock_alerts': stock_alerts,
        'effective_timezone': org.timezone,
        'local_today': today_local.isoformat(),
    }

    cache.set(_cache_key(org.id), payload, SUMMARY_CACHE_TTL)
    return Response(payload)


# ---- Timeline builder ----

# Default clinic hours if no appointments exist for the day.
_DEFAULT_OPEN_TIME = dt_time(8, 0)
_DEFAULT_CLOSE_TIME = dt_time(20, 0)
_SLOT_MINUTES = 30


def _build_timeline_slots(appointments, org):
    tz = get_context_timezone(org)

    if appointments:
        first = min(a.start_datetime for a in appointments)
        last = max(a.start_datetime for a in appointments)
        first_local = first.astimezone(tz)
        last_local = last.astimezone(tz)
        # Floor to previous 30-min mark
        open_minutes = (first_local.hour * 60 + first_local.minute) // _SLOT_MINUTES * _SLOT_MINUTES
        close_minutes = ((last_local.hour * 60 + last_local.minute) // _SLOT_MINUTES + 1) * _SLOT_MINUTES
        day = first_local.date()
        open_time = dt_time(open_minutes // 60, open_minutes % 60)
        if close_minutes >= 24 * 60:
            close_time = dt_time(23, 59)
        else:
            close_time = dt_time(close_minutes // 60, close_minutes % 60)
    else:
        day = org_today_local(org)
        open_time = _DEFAULT_OPEN_TIME
        close_time = _DEFAULT_CLOSE_TIME

    # Build slot grid
    slots = []
    cursor_minutes = open_time.hour * 60 + open_time.minute
    end_minutes = close_time.hour * 60 + close_time.minute

    while cursor_minutes < end_minutes:
        slot_hour = cursor_minutes // 60
        slot_min = cursor_minutes % 60
        slot_time = dt_time(slot_hour, slot_min)

        # Find appointments that fall into this 30-min window
        slot_start_utc = datetime.combine(day, slot_time).replace(tzinfo=tz).astimezone(ZoneInfo('UTC'))
        slot_end_utc = slot_start_utc + timedelta(minutes=_SLOT_MINUTES)

        slot_appts = [
            a for a in appointments
            if slot_start_utc <= a.start_datetime < slot_end_utc
        ]

        if slot_appts:
            appt = slot_appts[0]
            slot_data = {
                'time': appt.start_datetime.astimezone(tz).strftime('%H:%M'),
                'public_id': str(appt.public_id) if hasattr(appt, 'public_id') and appt.public_id else str(appt.pk),
                'pet_name': appt.pet.name if appt.pet else None,
                'pet_is_generic': appt.pet.is_generic if appt.pet else False,
                'owner_name': appt.pet.owner.name if appt.pet and appt.pet.owner else None,
                'veterinarian_name': (
                    f"{appt.veterinarian.first_name} {appt.veterinarian.last_name}".strip()
                    if appt.veterinarian else None
                ),
                'reason': appt.reason,
                'status': appt.status,
                'walk_in': getattr(appt, 'walk_in', False),
            }
        else:
            slot_data = None

        slots.append({
            'time': slot_time.strftime('%H:%M'),
            'appointment': slot_data,
        })
        cursor_minutes += _SLOT_MINUTES

    return slots


def _build_waiting_room(appointments, now_utc, org):
    tz = get_context_timezone(org)
    items = []

    for appt in appointments:
        if appt.status not in ('scheduled', 'confirmed'):
            continue
        # Only include appointments whose start time is within [-30min, +60min] of now
        # or already past (patient is here waiting)
        local_start = appt.start_datetime.astimezone(tz)
        wait_minutes = (now_utc - appt.start_datetime).total_seconds() / 60

        # Show: starting within next 60 min, or already past (waiting) up to 30 min early arrival
        if -30 <= wait_minutes <= 60:
            items.append({
                'pet_name': appt.pet.name if appt.pet else None,
                'time': local_start.strftime('%H:%M'),
                'owner_name': appt.pet.owner.name if appt.pet and appt.pet.owner else None,
                'status': appt.status,
                'wait_minutes': max(0, int(wait_minutes)) if wait_minutes > 0 else 0,
                'is_late': wait_minutes > 30,
            })

    # Sort by wait time descending (longest waiting first)
    items.sort(key=lambda x: x['wait_minutes'], reverse=True)
    return items[:3]


# Need ZoneInfo for UTC conversion in timeline builder
from zoneinfo import ZoneInfo
