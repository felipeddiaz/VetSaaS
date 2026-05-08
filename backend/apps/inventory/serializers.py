import re
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from django.db import transaction
from rest_framework import serializers
from .models import Product, Presentation, StockMovement, MedicalRecordProduct

PRODUCT_NAME_REGEX = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚáéíóúñÑ\s\.\-\(\)\/\%\+]+$")


def _validate_price(value, field_name='sale_price'):
    if value is None:
        raise serializers.ValidationError({field_name: "El precio es obligatorio."})
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise serializers.ValidationError({field_name: "Valor inválido."})
    if d <= Decimal('0.00'):
        raise serializers.ValidationError({field_name: "El precio debe ser mayor a 0."})


def _validate_non_negative(value, field_name, label):
    if value is None:
        raise serializers.ValidationError({field_name: f"{label} es obligatorio."})
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise serializers.ValidationError({field_name: "Valor inválido."})
    if d < Decimal('0'):
        raise serializers.ValidationError({field_name: f"{label} no puede ser negativo."})


class PresentationSerializer(serializers.ModelSerializer):
    product = serializers.IntegerField(source='product_id', read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    base_unit_display = serializers.CharField(source='get_base_unit_display', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Presentation
        fields = [
            'id', 'public_id', 'product', 'name', 'product_name', 'base_unit', 'base_unit_display', 'quantity',
            'sale_price', 'stock', 'min_stock', 'is_low_stock',
        ]
        read_only_fields = ['id', 'public_id', 'product', 'product_name']

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


class PresentationCreateSerializer(serializers.ModelSerializer):
    """Serializer for adding a new presentation variant to an existing product."""

    name = serializers.CharField(required=False, allow_blank=True, default='')
    stock = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True, allow_null=False
    )
    sale_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True, allow_null=False
    )

    class Meta:
        model = Presentation
        fields = ['id', 'name', 'base_unit', 'quantity', 'sale_price', 'stock', 'min_stock']
        read_only_fields = ['id']

    def validate_sale_price(self, value):
        _validate_price(value)
        return value

    def validate_stock(self, value):
        _validate_non_negative(value, 'stock', 'El stock')
        return value

    def validate_min_stock(self, value):
        _validate_non_negative(value, 'min_stock', 'El stock mínimo')
        return value


class ProductSerializer(serializers.ModelSerializer):
    presentations = PresentationSerializer(many=True, read_only=True)
    # Backward-compat: first presentation for existing frontend code
    presentation = serializers.SerializerMethodField()
    # Write-only input for product creation
    presentation_input = PresentationCreateSerializer(
        write_only=True, required=True, allow_null=False
    )
    internal_code = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default='',
    )

    class Meta:
        model = Product
        fields = [
            'id', 'public_id', 'name', 'internal_code', 'description',
            'category', 'requires_prescription', 'is_active',
            'presentations', 'presentation', 'presentation_input',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'public_id', 'created_at', 'updated_at']

    def get_presentation(self, obj):
        first = obj.presentations.first() if hasattr(obj, '_prefetched_objects_cache') else obj.presentations.first()
        if first is None:
            return None
        return PresentationSerializer(first).data

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre del producto es requerido.")
        if not PRODUCT_NAME_REGEX.match(value.strip()):
            raise serializers.ValidationError(
                "El nombre del producto contiene caracteres no permitidos. "
                "Use letras, números, espacios y los símbolos: . - ( ) / % +"
            )
        return value.strip()

    def validate(self, data):
        pres = data.get('presentation_input')
        if not pres:
            raise serializers.ValidationError("Se requiere al menos una presentación.")
        return data

    def validate_internal_code(self, value):
        if not value:
            return value
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
        pres_data = validated_data.pop('presentation_input', None)

        organization = self.context['request'].user.organization
        validated_data.pop('organization', None)

        internal_code = validated_data.pop('internal_code', '').strip()

        if not internal_code:
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

        if pres_data:
            pres_serializer = PresentationCreateSerializer(
                data=pres_data,
                context=self.context
            )
            pres_serializer.is_valid(raise_exception=True)

            data = dict(pres_serializer.validated_data)
            if not data.get('name'):
                data['name'] = product.name

            pres = Presentation(product=product, organization=organization, **data)
            pres.full_clean()
            Presentation.objects.bulk_create([pres])

        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        pres_data = validated_data.pop('presentation_input', None)
        validated_data.pop('organization', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if pres_data is not None:
            first_pres = instance.presentations.first()
            if first_pres is None:
                raise serializers.ValidationError({
                    'presentation': 'Este producto no tiene presentaciones. Agrega una primero.'
                })

            # pres_data viene como lista de dicts (many=True)
            if isinstance(pres_data, list):
                update_data = pres_data[0] if pres_data else {}
            else:
                update_data = pres_data

            if 'stock' in update_data and update_data['stock'] != first_pres.stock:
                raise serializers.ValidationError({
                    'presentation': {
                        'stock': 'Usa el endpoint de ajuste de stock para modificar existencias.'
                    }
                })
            update_data.pop('name', None)  # name is immutable via this endpoint
            for attr, value in update_data.items():
                setattr(first_pres, attr, value)
            first_pres.save()
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
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
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
        validators = []

    def validate_presentation(self, presentation):
        if presentation and presentation.organization != self.context['request'].user.organization:
            raise serializers.ValidationError('Acceso inválido.')
        return presentation

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
