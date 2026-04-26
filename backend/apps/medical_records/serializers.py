from rest_framework import serializers
from .models import MedicalRecord, MedicalRecordService
from .policies import can_close_medical_record, can_modify_medical_record_charges


class MedicalRecordSerializer(serializers.ModelSerializer):
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    veterinarian_name = serializers.SerializerMethodField()
    appointment_date = serializers.SerializerMethodField()
    products_used = serializers.SerializerMethodField()
    prescription_id = serializers.ReadOnlyField()
    invoice_id = serializers.ReadOnlyField()
    status = serializers.CharField(read_only=True)
    closed_at = serializers.DateTimeField(read_only=True)
    closed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    can_modify_charges = serializers.SerializerMethodField()
    can_close = serializers.SerializerMethodField()

    class Meta:
        model = MedicalRecord
        fields = [
            'id', 'pet', 'pet_name', 'veterinarian', 'veterinarian_name',
            'appointment', 'appointment_date', 'diagnosis', 'treatment',
            'notes', 'weight', 'created_at', 'products_used',
            'prescription_id', 'invoice_id',
            'status', 'closed_at', 'closed_by',
            'can_modify_charges', 'can_close',
        ]
        read_only_fields = [
            'id', 'created_at', 'prescription_id', 'invoice_id',
            'status', 'closed_at', 'closed_by',
        ]

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
