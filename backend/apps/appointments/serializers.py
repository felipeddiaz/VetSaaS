from rest_framework import serializers
from django.db.models import Q
from django.utils.timezone import now

from apps.core.datetime_utils import get_context_timezone, local_date_time_to_utc

from .models import Appointment, AppointmentStatusChange


class AppointmentSerializer(serializers.ModelSerializer):
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    pet_is_generic = serializers.BooleanField(source='pet.is_generic', read_only=True)
    owner_id = serializers.IntegerField(source='pet.owner_id', read_only=True)
    owner_name = serializers.CharField(source='pet.owner.name', read_only=True)
    veterinarian_name = serializers.CharField(source='veterinarian.get_full_name', read_only=True)
    medical_record_ids = serializers.ReadOnlyField()
    invoice_id = serializers.ReadOnlyField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'pet', 'pet_name', 'pet_is_generic', 'owner_id', 'owner_name',
            'veterinarian', 'veterinarian_name',
            'date', 'start_time', 'end_time', 'reason', 'notes',
            'status', 'cancellation_reason',
            'medical_record_ids', 'invoice_id',
        ]
        read_only_fields = ['id', 'pet_is_generic', 'owner_id', 'owner_name', 'medical_record_ids', 'invoice_id']

    def validate_pet(self, value):
        request = self.context.get('request')
        if request and value.organization_id != request.user.organization_id:
            raise serializers.ValidationError('Mascota fuera de tu organización')
        return value

    def validate_veterinarian(self, value):
        request = self.context.get('request')
        if request and value.organization_id != request.user.organization_id:
            raise serializers.ValidationError('Veterinario fuera de tu organización')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return attrs

        org = request.user.organization
        instance = getattr(self, 'instance', None)

        local_date = attrs.get('date', instance.date if instance else None)
        start_time = attrs.get('start_time', instance.start_time if instance else None)
        end_time = attrs.get('end_time', instance.end_time if instance else None)
        veterinarian_id = attrs.get('veterinarian', instance.veterinarian if instance else None)
        target_status = attrs.get('status', instance.status if instance else 'scheduled')

        if not (local_date and start_time and end_time and veterinarian_id):
            return attrs

        if end_time <= start_time:
            raise serializers.ValidationError({'end_time': 'La hora fin debe ser mayor a la hora inicio'})

        start_utc = local_date_time_to_utc(org, local_date, start_time)
        end_utc = local_date_time_to_utc(org, local_date, end_time)

        if not instance and start_utc < now():
            raise serializers.ValidationError({"date": "No se pueden crear citas en el pasado."})

        vet_pk = veterinarian_id.pk if hasattr(veterinarian_id, 'pk') else veterinarian_id
        conflicts = Appointment.objects.filter(
            organization=org,
            veterinarian_id=vet_pk,
            status__in=['scheduled', 'confirmed', 'in_progress'],
        )

        if instance:
            conflicts = conflicts.exclude(pk=instance.pk)

        conflicts = conflicts.filter(
            Q(start_datetime__lt=end_utc, end_datetime__gt=start_utc)
        )

        if target_status in ('scheduled', 'confirmed', 'in_progress') and conflicts.exists():
            raise serializers.ValidationError(
                {'error': 'Ya existe una cita para este veterinario en ese horario'}
            )

        pet = attrs.get('pet', instance.pet if instance else None)
        raw_owner = self.context['request'].data.get('owner_id')
        if pet and raw_owner:
            if str(pet.owner_id) != str(raw_owner):
                raise serializers.ValidationError(
                    {'pet': 'La mascota no pertenece al propietario seleccionado'}
                )

        attrs['start_datetime'] = start_utc
        attrs['end_datetime'] = end_utc
        attrs['timezone_at_creation'] = str(get_context_timezone(org))
        return attrs


class AppointmentStatusChangeSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()
    from_status_display = serializers.SerializerMethodField()
    to_status_display = serializers.SerializerMethodField()

    STATUS_LABELS = {
        'scheduled': 'Programada', 'confirmed': 'Confirmada',
        'in_progress': 'En consulta', 'done': 'Completada',
        'canceled': 'Cancelada', 'no_show': 'No se presentó',
    }

    class Meta:
        model = AppointmentStatusChange
        fields = [
            'id', 'from_status', 'from_status_display',
            'to_status', 'to_status_display',
            'changed_by', 'changed_by_name', 'reason', 'created_at',
        ]

    def get_changed_by_name(self, obj):
        if obj.changed_by:
            return f"{obj.changed_by.first_name} {obj.changed_by.last_name}".strip() or obj.changed_by.username
        return None

    def get_from_status_display(self, obj):
        return self.STATUS_LABELS.get(obj.from_status, obj.from_status)

    def get_to_status_display(self, obj):
        return self.STATUS_LABELS.get(obj.to_status, obj.to_status)
