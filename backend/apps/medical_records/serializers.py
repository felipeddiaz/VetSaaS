from rest_framework import serializers
from .models import MedicalRecord


class MedicalRecordSerializer(serializers.ModelSerializer):
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    veterinarian_name = serializers.SerializerMethodField()
    appointment_date = serializers.SerializerMethodField()
    products_used = serializers.SerializerMethodField()
    prescription_id = serializers.ReadOnlyField()
    invoice_id = serializers.ReadOnlyField()

    class Meta:
        model = MedicalRecord
        fields = [
            'id', 'pet', 'pet_name', 'veterinarian', 'veterinarian_name',
            'appointment', 'appointment_date', 'diagnosis', 'treatment',
            'notes', 'weight', 'created_at', 'products_used',
            'prescription_id', 'invoice_id',
        ]
        read_only_fields = ['id', 'created_at', 'prescription_id', 'invoice_id']

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


class MedicalRecordDetailSerializer(MedicalRecordSerializer):
    class Meta(MedicalRecordSerializer.Meta):
        fields = MedicalRecordSerializer.Meta.fields + ['organization']
