from uuid import uuid4
from django.db import transaction
from rest_framework import serializers
from .models import Product, Presentation, StockMovement, MedicalRecordProduct


class PresentationSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    base_unit_display = serializers.CharField(source='get_base_unit_display', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Presentation
        fields = [
            'id', 'name', 'product_name', 'base_unit', 'base_unit_display', 'quantity',
            'sale_price', 'stock', 'min_stock', 'is_low_stock',
        ]
        read_only_fields = ['id', 'name', 'product_name']  # name lo controla el backend

    def validate_sale_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio de venta debe ser mayor a 0.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo.")
        return value

    def validate_min_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock mínimo no puede ser negativo.")
        return value


class ProductSerializer(serializers.ModelSerializer):
    presentation = PresentationSerializer()
    # internal_code es opcional: si no viene, el backend genera uno automáticamente
    internal_code = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default='',
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'internal_code', 'description',
            'category', 'requires_prescription', 'is_active',
            'presentation', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_internal_code(self, value):
        if not value:
            return value  # se generará automáticamente en create()
        request = self.context.get('request')
        if request:
            qs = Product.objects.filter(
                organization=request.user.organization,
                internal_code=value,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "Este código ya está en uso en tu organización."
                )
        return value

    @transaction.atomic
    def create(self, validated_data):
        presentation_data = validated_data.pop('presentation')
        # Organization siempre desde contexto — nunca del payload (seguridad multitenant)
        organization = self.context['request'].user.organization
        validated_data.pop('organization', None)

        internal_code = validated_data.pop('internal_code', '').strip()

        if not internal_code:
            # UUID temporal evita colisiones bajo requests concurrentes
            product = Product.objects.create(
                **validated_data,
                organization=organization,
                internal_code=f'__tmp_{uuid4().hex}',
            )
            product.internal_code = f'PROD-{organization.id}-{product.pk:04d}'
            product.save()
        else:
            product = Product.objects.create(
                **validated_data,
                organization=organization,
                internal_code=internal_code,
            )

        # Backend controla presentation.name — siempre igual al nombre del producto
        presentation_data['name'] = product.name
        Presentation.objects.create(
            product=product,
            organization=organization,
            **presentation_data,
        )
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        presentation_data = validated_data.pop('presentation', None)
        validated_data.pop('organization', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if presentation_data is not None:
            if (
                'stock' in presentation_data
                and presentation_data['stock'] != instance.presentation.stock
            ):
                raise serializers.ValidationError({
                    'presentation': {
                        'stock': 'Usa el endpoint de ajuste de stock para modificar existencias.'
                    }
                })
            # Si el nombre del producto cambió, la presentación lo refleja
            presentation_data['name'] = validated_data.get('name') or instance.name
            pres = instance.presentation
            for attr, value in presentation_data.items():
                setattr(pres, attr, value)
            pres.save()
        return instance


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='presentation.product.name', read_only=True)
    presentation_name = serializers.CharField(source='presentation.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            'id', 'presentation', 'product_name', 'presentation_name',
            'movement_type', 'quantity', 'reason', 'medical_record',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'created_by']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return ''


class StockAdjustmentSerializer(serializers.Serializer):
    movement_type = serializers.ChoiceField(choices=['in', 'out', 'adjustment'])
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class MedicalRecordProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='presentation.product.name', read_only=True)
    presentation_name = serializers.CharField(source='presentation.name', read_only=True)
    base_unit = serializers.CharField(source='presentation.base_unit', read_only=True)
    base_unit_display = serializers.CharField(
        source='presentation.get_base_unit_display', read_only=True
    )

    class Meta:
        model = MedicalRecordProduct
        fields = [
            'id', 'presentation', 'product_name', 'presentation_name',
            'base_unit', 'base_unit_display', 'quantity',
        ]

    def validate(self, attrs):
        presentation = attrs.get('presentation')
        if not presentation:
            return attrs
        product = presentation.product
        if not product.requires_prescription:
            return attrs
        medical_record = self.context.get('medical_record')
        if not medical_record:
            return attrs
        from apps.prescriptions.models import PrescriptionItem
        has_active_rx = PrescriptionItem.objects.filter(
            prescription__medical_record=medical_record,
            prescription__is_active=True,
            product=product,
        ).exists()
        if not has_active_rx:
            raise serializers.ValidationError(
                f"{product.name} requiere receta médica activa. "
                "Crea la receta antes de agregar este producto a la consulta."
            )
        return attrs
