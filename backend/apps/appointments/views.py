import re
from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.datetime_utils import filter_by_local_day, org_now_local, org_today_local, local_date_time_to_utc, get_context_timezone
from apps.core.permissions import HybridPermission, make_permission, user_has_permission
from apps.core.sanitize import sanitize_text
from apps.core.views import TenantQueryMixin, PublicIdLookupMixin, resolve_public_id
from apps.organizations.utils import get_org_setting, SETTING_AUTO_MEDICAL_RECORD
from apps.patients.models import Pet, SPECIES_CHOICES
from apps.users.models import User

from .models import Appointment, AppointmentStatusChange
from .serializers import AppointmentSerializer, AppointmentStatusChangeSerializer

ALLOWED_TRANSITIONS = {
    'scheduled':   {'confirmed', 'in_progress', 'canceled', 'no_show'},
    'confirmed':   {'in_progress', 'canceled', 'no_show'},
    'in_progress': {'done', 'canceled'},
    'done':        set(),
    'canceled':    {'scheduled'},
    'no_show':     {'scheduled'},
}


class AppointmentListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [HybridPermission]
    resource_name = "appointment"

    def get_queryset(self):
        org = self.request.user.organization
        queryset = Appointment.objects.for_organization(org).select_related('pet__owner', 'veterinarian')

        veterinarian_id = self.request.query_params.get('veterinarian')
        date = self.request.query_params.get('date')
        pet_id = self.request.query_params.get('pet')

        if veterinarian_id:
            queryset = queryset.filter(veterinarian_id=veterinarian_id)
        if date:
            parsed = parse_date(date)
            if parsed:
                queryset = filter_by_local_day(queryset, 'start_datetime', org, parsed)
        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)

        return queryset.order_by('start_datetime', 'id')

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class AppointmentDetailView(PublicIdLookupMixin, TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [HybridPermission]
    resource_name = "appointment"
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return Appointment.objects.for_organization(self.request.user.organization).select_related('pet__owner', 'veterinarian')

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in ('scheduled', 'confirmed'):
            return Response(
                {'error': 'Solo se pueden cancelar citas programadas o confirmadas'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.status = 'canceled'
        instance.save()
        return Response(status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([make_permission("appointment.update")])
def update_status(request, pk):
    if not request.user.organization:
        raise PermissionDenied("User has no organization assigned")
    appointment = resolve_public_id(
        Appointment.objects.for_organization(request.user.organization),
        pk,
    )

    new_status = request.data.get('status')
    valid_statuses = set(ALLOWED_TRANSITIONS.keys())
    if new_status not in valid_statuses:
        return Response({'error': 'Estado inválido'}, status=status.HTTP_400_BAD_REQUEST)

    from_status = appointment.status
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if new_status not in allowed:
        return Response(
            {'error': f'No se puede pasar de "{from_status}" a "{new_status}"'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Toggle: require_confirmation_before_start
    # Aplica a CUALQUIER transición hacia in_progress, no solo desde scheduled
    if new_status == 'in_progress':
        if get_org_setting(appointment.organization, 'require_confirmation_before_start'):
            if from_status != 'confirmed':
                raise ValidationError({
                    "status": "Esta clínica requiere confirmar la cita antes de iniciarla. "
                              "Cambia el estado a 'confirmed' primero."
                })

    if new_status == 'scheduled' and from_status in ('canceled', 'no_show'):
        today = org_today_local(request.user.organization)
        if appointment.date < today:
            return Response(
                {'error': 'La fecha original ya pasó. Crea una nueva cita.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    from apps.core.sanitize import sanitize_text
    cancellation_reason = ''
    update_fields = ['status']
    appointment.status = new_status
    if new_status == 'canceled':
        cancellation_reason = sanitize_text(request.data.get('cancellation_reason') or '', max_length=100)
        if cancellation_reason:
            appointment.cancellation_reason = cancellation_reason
            update_fields.append('cancellation_reason')

    # Atomic: el log de estado y el save van juntos; si uno falla, el otro se revierte
    with transaction.atomic():
        appointment.save(update_fields=update_fields)

        AppointmentStatusChange.objects.create(
            appointment=appointment,
            from_status=from_status,
            to_status=new_status,
            changed_by=request.user,
            reason=cancellation_reason,
            organization=appointment.organization,
        )

        # Toggle: auto_create_medical_record
        if new_status == 'done':
            if get_org_setting(appointment.organization, SETTING_AUTO_MEDICAL_RECORD):
                from apps.medical_records.models import MedicalRecord
                MedicalRecord.objects.get_or_create(
                    appointment=appointment,
                    defaults={
                        'pet': appointment.pet,
                        'veterinarian': appointment.veterinarian,
                        'organization': appointment.organization,
                        'diagnosis': '',
                        'treatment': '',
                    }
                )

    serializer = AppointmentSerializer(appointment, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([make_permission("appointment.retrieve")])
def appointment_history(request, pk):
    appointment = resolve_public_id(
        Appointment.objects.for_organization(request.user.organization),
        pk,
    )
    changes = appointment.status_changes.select_related('changed_by').all()
    return Response(AppointmentStatusChangeSerializer(changes, many=True).data)


@api_view(['PATCH'])
@permission_classes([make_permission("appointment.update")])
def assign_patient(request, pk):
    """
    Vincula una cita con paciente genérico a un paciente real.
    Solo válido cuando appointment.pet.is_generic=True.
    Propaga a MedicalRecord asociado si está abierto.
    Registra el cambio en AppointmentStatusChange.
    """
    appointment = resolve_public_id(
        Appointment.objects.select_related('pet').for_organization(request.user.organization),
        pk,
    )

    if not appointment.pet.is_generic:
        raise ValidationError(
            "Solo se puede reasignar paciente cuando la cita tiene un paciente genérico asignado."
        )

    pet_id = request.data.get('pet')
    if not pet_id:
        return Response({'error': 'Se requiere pet_id.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        new_pet = Pet.objects.for_organization(request.user.organization).get(pk=pet_id)
    except Pet.DoesNotExist:
        return Response({'error': 'Mascota no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    if new_pet.is_generic:
        return Response(
            {'error': 'No se puede vincular al paciente genérico.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        old_pet_name = appointment.pet.name
        appointment.pet = new_pet
        appointment.save(update_fields=['pet'])

        from apps.medical_records.models import MedicalRecord
        MedicalRecord.objects.filter(
            appointment=appointment,
            organization=appointment.organization,
            status=MedicalRecord.Status.OPEN,
        ).update(pet=new_pet)

        AppointmentStatusChange.objects.create(
            appointment=appointment,
            from_status=appointment.status,
            to_status=appointment.status,
            changed_by=request.user,
            reason=f"Paciente reasignado de '{old_pet_name}' a '{new_pet.name}'",
            organization=appointment.organization,
        )

    return Response(AppointmentSerializer(appointment, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([make_permission("appointment.create")])
def create_with_patient(request):
    """
    Crea atómicamente: owner (get_or_create por teléfono+org) + pet + cita.
    Si el teléfono ya existe en la org, reutiliza el owner y crea solo la mascota nueva.
    Cualquier error revierte toda la transacción: no quedan registros huérfanos.
    """
    org = request.user.organization
    if not org:
        raise PermissionDenied("User has no organization assigned")

    owner_name     = request.data.get('owner_name', '').strip()
    owner_phone    = request.data.get('owner_phone', '').strip()
    pet_name       = request.data.get('pet_name', '').strip()
    pet_species    = request.data.get('pet_species', '').strip()
    pet_sex        = request.data.get('pet_sex', 'unknown')
    pet_birth_date = request.data.get('pet_birth_date') or None

    errors = {}
    if not owner_name:
        errors['owner_name'] = 'El nombre del dueño es requerido.'
    if not re.match(r'^\d{10}$', owner_phone):
        errors['owner_phone'] = 'El teléfono debe tener exactamente 10 dígitos.'
    if not pet_name:
        errors['pet_name'] = 'El nombre de la mascota es requerido.'
    if pet_species not in SPECIES_CHOICES:
        errors['pet_species'] = f'Especie inválida. Opciones: {", ".join(SPECIES_CHOICES)}'
    if not request.data.get('veterinarian'):
        errors['veterinarian'] = 'El veterinario es requerido.'
    if not request.data.get('date'):
        errors['date'] = 'La fecha es requerida.'
    if not request.data.get('start_time'):
        errors['start_time'] = 'La hora de inicio es requerida.'
    if not request.data.get('end_time'):
        errors['end_time'] = 'La hora de fin es requerida.'
    if not request.data.get('reason', '').strip():
        errors['reason'] = 'El motivo es requerido.'
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    appt_fields = {
        'veterinarian': request.data.get('veterinarian'),
        'date':         request.data.get('date'),
        'start_time':   request.data.get('start_time'),
        'end_time':     request.data.get('end_time'),
        'reason':       request.data.get('reason', '').strip(),
        'notes':        request.data.get('notes', ''),
        'status':       'scheduled',
    }

    from apps.patients.models import Owner
    with transaction.atomic():
        owner, _ = Owner.objects.get_or_create(
            organization=org,
            phone=owner_phone,
            defaults={'name': owner_name},
        )
        pet = Pet.objects.create(
            name=pet_name,
            species=pet_species,
            sex=pet_sex,
            birth_date=pet_birth_date,
            owner=owner,
            organization=org,
        )
        serializer = AppointmentSerializer(
            data={**appt_fields, 'pet': pet.id},
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        appt = serializer.save(organization=org)

    return Response(AppointmentSerializer(appt, context={'request': request}).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([make_permission("appointment.create")])
def walk_in(request):
    org = request.user.organization
    if not org:
        raise PermissionDenied("User has no organization assigned")

    pet_id = request.data.get('pet')
    vet_id = request.data.get('veterinarian')
    reason = sanitize_text(request.data.get('reason') or '', max_length=255)
    notes = sanitize_text(request.data.get('notes') or '', max_length=5000)

    if not reason.strip():
        raise ValidationError({'reason': 'El motivo de la consulta es requerido.'})
    if not vet_id:
        raise ValidationError({'veterinarian': 'El veterinario es requerido.'})

    # Toggle: allow_anonymous_walkin
    if not pet_id:
        if not get_org_setting(org, 'allow_anonymous_walkin'):
            raise ValidationError('Walk-in anónimo no está configurado.')

        from apps.patients.utils import get_or_create_generic_patient
        _, pet = get_or_create_generic_patient(org)
    else:
        try:
            pet = Pet.objects.for_organization(org).get(pk=pet_id)
        except Pet.DoesNotExist:
            raise NotFound('Mascota no encontrada.')

    try:
        vet = User.objects.get(pk=vet_id, organization=org, is_active=True)
    except User.DoesNotExist:
        raise NotFound('Veterinario no encontrado.')

    # RBAC validation: assigned veterinarian must have permission to create walk-in appointments
    if not user_has_permission(vet, 'appointments.create_walkin'):
        raise PermissionDenied('El veterinario asignado no tiene permiso para crear citas walk-in.')

    now_local = org_now_local(org)
    today = now_local.date()
    start_time = now_local.time().replace(second=0, microsecond=0)
    end_local = now_local + timedelta(minutes=30)
    end_time = end_local.time().replace(second=0, microsecond=0)

    start_utc = local_date_time_to_utc(org, today, start_time)
    end_utc = local_date_time_to_utc(org, today, end_time)

    with transaction.atomic():
        # Lock en la fila del vet para serializar walk-ins concurrentes del mismo vet
        User.objects.select_for_update().get(pk=vet.pk)
        existing = Appointment.objects.filter(
            organization=org,
            veterinarian=vet,
            created_at__gte=timezone.now() - timedelta(seconds=10),
            status='in_progress',
        ).first()
        if existing:
            serializer = AppointmentSerializer(existing, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        appointment = Appointment.objects.create(
            organization=org,
            pet=pet,
            veterinarian=vet,
            date=today,
            start_time=start_time,
            end_time=end_time,
            start_datetime=start_utc,
            end_datetime=end_utc,
            timezone_at_creation=str(get_context_timezone(org)),
            reason=reason,
            notes=notes,
            status='in_progress',
            created_by=request.user,
        )

    serializer = AppointmentSerializer(appointment, context={'request': request})
    return Response(serializer.data, status=status.HTTP_201_CREATED)
