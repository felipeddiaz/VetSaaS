from rest_framework import serializers
from .models import Prescription, PrescriptionItem


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
        if not value or not value.strip():
            raise serializers.ValidationError("La dosis es obligatoria.")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0.")
        return value


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True)
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    veterinarian_name = serializers.SerializerMethodField()

    class Meta:
        model = Prescription
        fields = [
            'id', 'medical_record', 'veterinarian', 'veterinarian_name',
            'pet', 'pet_name', 'notes', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'veterinarian', 'created_at', 'updated_at']

    def get_veterinarian_name(self, obj):
        return f"{obj.veterinarian.first_name} {obj.veterinarian.last_name}".strip()

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError(
                "La receta debe tener al menos un medicamento."
            )
        return items

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

    def validate_product(self, product):
        if not product.requires_prescription:
            raise serializers.ValidationError(
                "Este producto no requiere receta. Puede dispensarse directamente desde inventario."
            )
        return product
