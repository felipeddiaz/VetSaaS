from rest_framework import serializers
from .models import Prescription, PrescriptionItem


class PrescriptionItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.presentation.base_unit', read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = [
            'id', 'product', 'product_name', 'product_unit',
            'dose', 'duration', 'quantity', 'instructions',
        ]


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
            instance.items.all().delete()
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
