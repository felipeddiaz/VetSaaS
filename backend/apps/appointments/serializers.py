from rest_framework import serializers
from django.db.models import Q

from apps.core.datetime_utils import get_context_timezone, local_date_time_to_utc

from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    veterinarian_name = serializers.CharField(source='veterinarian.get_full_name', read_only=True)
    medical_record_ids = serializers.ReadOnlyField()
    invoice_id = serializers.ReadOnlyField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'pet', 'pet_name', 'veterinarian', 'veterinarian_name',
            'date', 'start_time', 'end_time', 'reason', 'notes', 'status',
            'medical_record_ids', 'invoice_id',
        ]
        read_only_fields = ['id', 'medical_record_ids', 'invoice_id']

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

        vet_pk = veterinarian_id.pk if hasattr(veterinarian_id, 'pk') else veterinarian_id
        conflicts = Appointment.objects.filter(
            organization=org,
            veterinarian_id=vet_pk,
            status='scheduled',
        )

        if instance:
            conflicts = conflicts.exclude(pk=instance.pk)

        conflicts = conflicts.filter(
            Q(start_datetime__lt=end_utc, end_datetime__gt=start_utc)
        )

        if target_status == 'scheduled' and conflicts.exists():
            raise serializers.ValidationError(
                {'error': 'Ya existe una cita para este veterinario en ese horario'}
            )

        attrs['start_datetime'] = start_utc
        attrs['end_datetime'] = end_utc
        attrs['timezone_at_creation'] = str(get_context_timezone(org))
        return attrs
