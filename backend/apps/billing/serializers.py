from rest_framework import serializers
from decimal import Decimal
from .models import Service, Invoice, InvoiceItem
from .money import discount_amount, money


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'description', 'base_price', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceItemSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    presentation_name = serializers.SerializerMethodField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    description = serializers.CharField(read_only=True)
    discount_amount = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'invoice', 'service', 'service_name',
            'presentation', 'presentation_name', 'description',
            'quantity', 'unit_price',
            'discount_type', 'discount_value', 'discount_amount',
            'subtotal',
        ]
        read_only_fields = ['id', 'subtotal', 'invoice']

    def get_presentation_name(self, obj):
        if obj.presentation:
            return str(obj.presentation)   # "Producto — Presentación"
        return None

    def get_discount_amount(self, obj):
        gross = money(obj.quantity * obj.unit_price)
        return str(discount_amount(gross, obj.discount_type, obj.discount_value))

    def validate(self, data):
        service = data.get('service')
        presentation = data.get('presentation')
        quantity = data.get('quantity')
        discount_type = data.get('discount_type')
        discount_value = data.get('discount_value', Decimal('0.00'))

        # Validar cantidad
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a cero.")

        # XOR: exactamente uno de los dos
        if service and presentation:
            raise serializers.ValidationError(
                "Un ítem es o un servicio o una presentación de inventario, no ambos."
            )
        if not service and not presentation:
            raise serializers.ValidationError(
                "Debe especificar 'service' o 'presentation'."
            )

        # Validación multitenant de service (NUEVO)
        if service:
            invoice = self.context.get('invoice')
            if invoice is None:
                raise RuntimeError(
                    "InvoiceItemSerializer requiere 'invoice' en su contexto."
                )
            if service.organization_id != invoice.organization_id:
                raise serializers.ValidationError(
                    "El servicio no pertenece a la organización de la factura."
                )

        # Validación de organización (presentation — ya existía)
        if presentation:
            invoice = self.context.get('invoice')
            if invoice is None:
                raise RuntimeError(
                    "InvoiceItemSerializer requiere 'invoice' en su contexto."
                )
            if presentation.organization_id != invoice.organization_id:
                raise serializers.ValidationError(
                    "La presentación no pertenece a la organización de la factura."
                )
            if presentation.stock <= 0:
                raise serializers.ValidationError(
                    f"'{presentation.product.name}' no tiene stock disponible."
                )

        # Validación de descuento (NUEVO)
        if discount_value is not None and discount_value < 0:
            raise serializers.ValidationError("El valor del descuento no puede ser negativo.")

        if discount_type == 'percentage' and discount_value > 100:
            raise serializers.ValidationError("El descuento porcentual no puede superar 100%.")

        if discount_type and (discount_value is None or discount_value <= 0):
            raise serializers.ValidationError(
                "Si se especifica tipo de descuento, el valor debe ser mayor a cero."
            )

        if discount_value and discount_value > 0 and not discount_type:
            raise serializers.ValidationError(
                "Debe especificar 'discount_type' si indica un valor de descuento."
            )

        return data


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    owner_name = serializers.CharField(source='owner.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_type', 'appointment', 'medical_record',
            'owner', 'owner_name', 'pet', 'pet_name',
            'status', 'payment_method', 'tax_rate',
            'subtotal', 'tax_amount', 'total',
            'notes', 'created_by', 'created_by_name',
            'paid_at', 'created_at', 'updated_at',
            'items',
        ]
        read_only_fields = [
            'id', 'subtotal', 'tax_amount', 'total',
            'created_by', 'paid_at', 'created_at', 'updated_at',
            'tax_rate',   # NUEVO: se hereda de org, no editable por cliente
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return ''
