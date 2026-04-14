from rest_framework import serializers
from .models import Service, Invoice, InvoiceItem


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'description', 'base_price', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceItemSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    presentation_name = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'invoice', 'service', 'service_name',
            'presentation', 'presentation_name',
            'product', 'product_name', 'description',
            'quantity', 'unit_price', 'subtotal',
        ]
        read_only_fields = ['id', 'subtotal', 'invoice']

    def get_presentation_name(self, obj):
        if obj.presentation:
            return str(obj.presentation)   # "Producto — Presentación"
        return None

    def validate(self, data):
        service = data.get('service')
        presentation = data.get('presentation')
        quantity = data.get('quantity')

        # Validar cantidad
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError(
                "La cantidad debe ser mayor a cero."
            )

        # Regla central: XOR — exactamente uno de los dos
        if service and presentation:
            raise serializers.ValidationError(
                "Un ítem es o un servicio o una presentación de inventario, no ambos."
            )
        if not service and not presentation:
            raise serializers.ValidationError(
                "Debe especificar 'service' o 'presentation'."
            )

        # Validación de organización (presentation debe ser de la misma org que la factura)
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
            # Feedback inmediato (lock real de concurrencia va en confirm_invoice)
            if presentation.stock <= 0:
                raise serializers.ValidationError(
                    f"'{presentation.product.name}' no tiene stock disponible."
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
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return ''
