import logging
from rest_framework import serializers
from .models import Prescription, PrescriptionItem
from apps.core.sanitize import sanitize_text

# Logger dedicado para rechazos de tenant en serializers (ADR p14). Separado
# de TENANT_MISMATCH_DETECTED (HybridPermission, ERROR) — éste es WARNING.
tenant_logger = logging.getLogger('apps.tenant_validation')


def _validate_same_org(value, request, field_name, serializer_name):
    """
    Idéntico al helper en apps/billing/serializers.py (ADR p14 Fase 1).
    Fase 2 (post-beta) extrae a apps/core/serializers.py como mixin.
    """
    if value is None:
        return value
    user_org_id = getattr(request.user, 'organization_id', None)
    obj_org_id = getattr(value, 'organization_id', None)
    if user_org_id is None or obj_org_id is None:
        return value
    if obj_org_id != user_org_id:
        tenant_logger.warning("TENANT_VALIDATION_REJECTED", extra={
            "source": "serializer",
            "serializer": serializer_name,
            "field": field_name,
            "user_id": getattr(request.user, 'pk', None),
            "user_org_id": user_org_id,
            "resource_org_id": obj_org_id,
            "resource_pk": getattr(value, 'pk', None),
            "endpoint": getattr(request, 'path', None),
            "method": getattr(request, 'method', None),
        })
        raise serializers.ValidationError('Acceso inválido.')
    return value


class PrescriptionItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.SerializerMethodField()

    def get_product_unit(self, obj):
        pres = obj.product.presentations.first()
        return pres.base_unit if pres else None

    class Meta:
        model = PrescriptionItem
        fields = [
            'id', 'product', 'product_name', 'product_unit',
            'dose', 'duration', 'quantity', 'instructions',
        ]

    def validate_dose(self, value):
        clean = sanitize_text(value or '', max_length=255)
        if not clean.strip():
            raise serializers.ValidationError("La dosis es obligatoria.")
        return clean

    def validate_duration(self, value):
        return sanitize_text(value or '', max_length=255)

    def validate_instructions(self, value):
        return sanitize_text(value or '', max_length=5000)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0.")
        return value

    def validate_product(self, product):
        # Tenant isolation (ADR p14 — P0 #9). Aplica también a items nested
        # en PrescriptionSerializer.items (DRF propaga context al child).
        request = self.context.get('request')
        assert request is not None, (
            "PrescriptionItemSerializer requiere 'request' en su context. "
            "Si se invoca via PrescriptionSerializer nested, el context se "
            "propaga automáticamente desde el parent (DRF default)."
        )
        return _validate_same_org(product, request, 'product', 'PrescriptionItemSerializer')


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True)
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    veterinarian_name = serializers.SerializerMethodField()

    class Meta:
        model = Prescription
        fields = [
            'id', 'public_id', 'medical_record', 'veterinarian', 'veterinarian_name',
            'pet', 'pet_name', 'notes', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'public_id', 'veterinarian', 'created_at', 'updated_at']

    def get_veterinarian_name(self, obj):
        return f"{obj.veterinarian.first_name} {obj.veterinarian.last_name}".strip()

    def validate_notes(self, value):
        return sanitize_text(value or '', max_length=5000)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError(
                "La receta debe tener al menos un medicamento."
            )
        return items

    def validate_medical_record(self, mr):
        if mr and mr.organization != self.context['request'].user.organization:
            raise serializers.ValidationError('Acceso inválido.')
        return mr

    def validate_pet(self, pet):
        if pet and pet.organization != self.context['request'].user.organization:
            raise serializers.ValidationError('Acceso inválido.')
        return pet

    def validate(self, attrs):
        medical_record = attrs.get('medical_record')
        if medical_record and not self.instance:
            if hasattr(medical_record, 'prescription'):
                raise serializers.ValidationError(
                    "Esta consulta ya tiene una receta. Editá la existente."
                )
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        prescription = Prescription.objects.create(**validated_data)
        for item_data in items_data:
            PrescriptionItem.objects.create(prescription=prescription, **item_data)
        return prescription

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            PrescriptionItem.all_objects.filter(prescription=instance).delete()
            for item_data in items_data:
                PrescriptionItem.objects.create(prescription=instance, **item_data)

        return instance


class PrescriptionItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = ['id', 'product', 'dose', 'duration', 'quantity', 'instructions']

    def validate_dose(self, value):
        clean = sanitize_text(value or '', max_length=255)
        if not clean.strip():
            raise serializers.ValidationError("La dosis es obligatoria.")
        return clean

    def validate_duration(self, value):
        return sanitize_text(value or '', max_length=255)

    def validate_instructions(self, value):
        return sanitize_text(value or '', max_length=5000)

    def validate_product(self, product):
        # Tenant check primero — no revelar `requires_prescription` de productos
        # de otra organización (ADR p14 — P0 #9).
        request = self.context.get('request')
        assert request is not None, (
            "PrescriptionItemWriteSerializer requiere 'request' en su context."
        )
        _validate_same_org(product, request, 'product', 'PrescriptionItemWriteSerializer')
        if not product.requires_prescription:
            raise serializers.ValidationError(
                "Este producto no requiere receta. Puede dispensarse directamente desde inventario."
            )
        return product
