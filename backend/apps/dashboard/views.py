from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.datetime_utils import filter_by_local_day, org_now_utc, org_today_local
from apps.core.permissions import make_permission


@api_view(['GET'])
@permission_classes([make_permission("dashboard.view")])
def dashboard_stats(request):
    from apps.appointments.models import Appointment
    from apps.medical_records.models import MedicalRecord
    from apps.inventory.models import Product

    org = request.user.organization
    if org is None:
        return Response({'detail': 'Usuario sin organización asignada.'}, status=400)
    today_local = org_today_local(org)
    now_utc = org_now_utc(org)

    appointments_qs = Appointment.objects.filter(
        organization=org,
        status__in=['scheduled', 'done'],
    )
    appointments_today = filter_by_local_day(
        appointments_qs,
        'start_datetime',
        org,
        today_local,
    ).count()

    recent_records = MedicalRecord.objects.filter(
        organization=org,
    ).order_by('-created_at').values(
        'id', 'pet__name', 'diagnosis', 'created_at',
        'veterinarian__first_name', 'veterinarian__last_name',
    )[:5]

    from django.db.models import F
    low_stock_qs = Product.objects.filter(
        organization=org,
        is_active=True,
        presentation__stock__lte=F('presentation__min_stock'),
    ).select_related('presentation')
    low_stock = [
        {
            'id': p.id,
            'name': p.name,
            'stock': str(p.presentation.stock),
            'min_stock': str(p.presentation.min_stock),
            'unit': p.presentation.get_base_unit_display(),
        }
        for p in low_stock_qs
    ]

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
