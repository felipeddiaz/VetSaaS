from datetime import date
from decimal import Decimal
from rest_framework import serializers
from .models import MedicalRecord, MedicalRecordService, VaccineRecord
from .policies import can_close_medical_record, can_modify_medical_record_charges


class MedicalRecordSerializer(serializers.ModelSerializer):
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    veterinarian_name = serializers.SerializerMethodField()
    appointment_date = serializers.SerializerMethodField()
    products_used = serializers.SerializerMethodField()
    prescription_id = serializers.ReadOnlyField()
    prescription_summary = serializers.SerializerMethodField()
    invoice_id = serializers.ReadOnlyField()
    status = serializers.CharField(read_only=True)
    closed_at = serializers.DateTimeField(read_only=True)
    closed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    can_modify_charges = serializers.SerializerMethodField()
    can_close = serializers.SerializerMethodField()

    force_weight = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = MedicalRecord
        fields = [
            'id', 'pet', 'pet_name', 'veterinarian', 'veterinarian_name',
            'appointment', 'appointment_date', 'diagnosis', 'treatment',
            'notes', 'weight', 'force_weight', 'created_at', 'products_used',
            'prescription_id', 'prescription_summary', 'invoice_id',
            'status', 'closed_at', 'closed_by',
            'can_modify_charges', 'can_close',
        ]
        read_only_fields = [
            'id', 'created_at', 'prescription_id', 'invoice_id',
            'status', 'closed_at', 'closed_by',
        ]

    def validate_weight(self, value):
        if value is not None and value <= Decimal('0'):
            raise serializers.ValidationError("El peso debe ser mayor a 0.")
        return value

    def validate(self, data):
        data = super().validate(data)
        weight = data.get('weight')
        force_weight = data.pop('force_weight', False)

        # En creaciones manuales vía API, diagnóstico y tratamiento son obligatorios.
        # La auto-creación desde update_status usa get_or_create directamente (no este serializer).
        if not self.instance:
            if not data.get('diagnosis', '').strip():
                raise serializers.ValidationError({'diagnosis': 'El diagnóstico es obligatorio.'})
            if not data.get('treatment', '').strip():
                raise serializers.ValidationError({'treatment': 'El tratamiento es obligatorio.'})

        # Only warn on updates with an existing record
        if weight and self.instance:
            last = MedicalRecord.objects.filter(
                pet=self.instance.pet, weight__isnull=False
            ).exclude(pk=self.instance.pk).order_by('-created_at').first()
            if last and last.weight:
                change_pct = abs(weight - last.weight) / last.weight * 100
                if change_pct > 150 and not force_weight:
                    raise serializers.ValidationError({
                        'weight': (
                            f'Cambio brusco de peso: último registro {last.weight} kg → '
                            f'nuevo {weight} kg ({change_pct:.0f}%). '
                            f'Envía force_weight=true para confirmar.'
                        )
                    })
        return data

    def get_veterinarian_name(self, obj):
        if obj.veterinarian:
            return f"{obj.veterinarian.first_name} {obj.veterinarian.last_name}"
        return ""

    def get_appointment_date(self, obj):
        if obj.appointment:
            return obj.appointment.date
        return None

    def get_products_used(self, obj):
        from apps.inventory.serializers import MedicalRecordProductSerializer
        return MedicalRecordProductSerializer(obj.products_used.all(), many=True).data

    def get_prescription_summary(self, obj):
        prescription = getattr(obj, 'prescription', None)
        if not prescription:
            return None

        from apps.prescriptions.serializers import PrescriptionItemSerializer

        return {
            'id': prescription.id,
            'notes': prescription.notes,
            'items': PrescriptionItemSerializer(
                prescription.items.select_related('product').prefetch_related('product__presentations').all(),
                many=True,
            ).data,
            'created_at': prescription.created_at,
        }

    def _request_user(self):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        return request.user

    def get_can_modify_charges(self, obj):
        user = self._request_user()
        if not user:
            return False
        return can_modify_medical_record_charges(user, obj)

    def get_can_close(self, obj):
        user = self._request_user()
        if not user:
            return False
        return can_close_medical_record(user, obj)


class MedicalRecordDetailSerializer(MedicalRecordSerializer):
    services_used = serializers.SerializerMethodField()

    class Meta(MedicalRecordSerializer.Meta):
        fields = MedicalRecordSerializer.Meta.fields + ['organization', 'services_used']

    def get_services_used(self, obj):
        return MedicalRecordServiceSerializer(
            obj.services_used.all(), many=True,
            context=self.context,
        ).data


class MedicalRecordServiceSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    unit_price = serializers.DecimalField(
        source='service.base_price', max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = MedicalRecordService
        fields = ['id', 'service', 'service_name', 'quantity', 'unit_price']


class VaccineRecordSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    applied_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VaccineRecord
        fields = [
            'id', 'pet', 'vaccine_name', 'application_date', 'next_due_date',
            'applied_by', 'applied_by_name', 'notes', 'medical_record', 'status',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'created_at']

    def get_applied_by_name(self, obj):
        if obj.applied_by:
            return f"{obj.applied_by.first_name} {obj.applied_by.last_name}".strip()
        return None

    def validate_vaccine_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre de la vacuna es requerido.")
        return value.strip()

    def validate_application_date(self, value):
        if value > date.today():
            raise serializers.ValidationError("La fecha de aplicación no puede ser en el futuro.")
        return value

    def validate(self, data):
        next_due = data.get('next_due_date')
        app_date = data.get('application_date')
        if next_due and app_date and next_due <= app_date:
            raise serializers.ValidationError({
                'next_due_date': 'La fecha de próxima dosis debe ser posterior a la fecha de aplicación.'
            })
        return data
