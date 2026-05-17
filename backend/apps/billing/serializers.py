import logging
import re
from rest_framework import serializers
from decimal import Decimal
from .models import Service, Invoice, InvoiceItem
from .money import discount_amount, money
from apps.core.sanitize import sanitize_text

SERVICE_NAME_REGEX = re.compile(r'^[A-Za-z0-9ÁÉÍÓÚáéíóúñÑ\s\-\(\)\/\%\+]+$')

# Logger dedicado para rechazos de tenant en serializers (ADR p14) — evento
# TENANT_VALIDATION_REJECTED a severidad WARNING. Separado de
# TENANT_MISMATCH_DETECTED (HybridPermission, ERROR) para no saturar la señal
# operacional con typos de UI / IDs stale del frontend.
tenant_logger = logging.getLogger('apps.tenant_validation')


def _validate_same_org(value, request, field_name, serializer_name):
    """
    Helper local: verifica que `value` pertenezca a la organización del
    request.user. Emite TENANT_VALIDATION_REJECTED en caso de violación.
    Retorna `value` si pasa (o si es None — FK opcional).

    NO se promueve a apps/core/ todavía (ADR p14 Fase 2). Battle-testing
    primero en los 2 sitios de Día 3, luego extracción a mixin centralizado.
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


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'public_id', 'name', 'description', 'base_price', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'public_id', 'created_at', 'updated_at']

    def validate_name(self, value):
        clean = sanitize_text(value or '', max_length=255)
        if not clean.strip():
            raise serializers.ValidationError("El nombre del servicio es obligatorio.")
        if not SERVICE_NAME_REGEX.match(clean):
            raise serializers.ValidationError(
                "El nombre contiene caracteres no permitidos."
            )
        return clean

    def validate_description(self, value):
        return sanitize_text(value or '', max_length=5000)

    def validate_base_price(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0.")
        return value


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
            if not self.instance and InvoiceItem.objects.filter(invoice=invoice, service=service).exists():
                raise serializers.ValidationError(
                    "Este servicio ya está incluido en la factura."
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
            if presentation.product.requires_prescription and invoice.invoice_type == 'direct_sale':
                raise serializers.ValidationError(
                    f"'{presentation.product.name}' requiere receta médica y no puede venderse directamente."
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
    prescription_suggestions = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'public_id', 'invoice_type', 'appointment', 'medical_record',
            'owner', 'owner_name', 'pet', 'pet_name',
            'status', 'payment_method', 'tax_rate',
            'subtotal', 'tax_amount', 'total',
            'notes', 'created_by', 'created_by_name',
            'paid_at', 'created_at', 'updated_at',
            'items', 'prescription_suggestions',
        ]
        read_only_fields = [
            'id', 'public_id', 'subtotal', 'tax_amount', 'total',
            'created_by', 'paid_at', 'created_at', 'updated_at',
            'tax_rate',
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return ''

    def validate_notes(self, value):
        from apps.core.sanitize import sanitize_text
        return sanitize_text(value or '', max_length=5000)

    def _get_request(self):
        """Acceso defensivo + assert. Loud failure si falta el context."""
        request = self.context.get('request')
        assert request is not None, (
            "InvoiceSerializer requiere 'request' en su context. "
            "Si lo invocas fuera de una view DRF (shell, admin, mgmt command), "
            "pasa context={'request': fake_request} con user.organization seteado."
        )
        return request

    def validate_owner(self, owner):
        return _validate_same_org(owner, self._get_request(), 'owner', 'InvoiceSerializer')

    def validate_pet(self, pet):
        return _validate_same_org(pet, self._get_request(), 'pet', 'InvoiceSerializer')

    def validate_appointment(self, appointment):
        return _validate_same_org(appointment, self._get_request(), 'appointment', 'InvoiceSerializer')

    def validate_medical_record(self, mr):
        return _validate_same_org(mr, self._get_request(), 'medical_record', 'InvoiceSerializer')

    def validate(self, data):
        # Resolver owner y pet considerando partial PATCH: los campos ausentes
        # heredan del instance actual. CREATE no tiene instance → fallback None.
        # Fix 4 (ADR p14): permite PATCH minimalistas tipo {"notes": "x"} sin
        # forzar al cliente a re-enviar pet/owner en cada PATCH.
        owner = data.get('owner', getattr(self.instance, 'owner', None))
        pet = data.get('pet', getattr(self.instance, 'pet', None))
        if owner and getattr(owner, 'is_generic', False):
            # Generic owner: force direct_sale, pet is optional
            data['invoice_type'] = 'direct_sale'
        elif pet is None and not (owner and getattr(owner, 'is_generic', False)):
            raise serializers.ValidationError({'pet': 'La mascota es requerida para ventas con cliente registrado.'})
        return data

    def get_prescription_suggestions(self, obj):
        """
        Productos recetados disponibles para agregar a la factura.
        Solo se expone cuando la factura está en borrador y tiene una consulta con receta.
        """
        if obj.status != 'draft' or not obj.medical_record_id:
            return []
        try:
            rx = obj.medical_record.prescription
        except Exception:
            return []
        suggestions = []
        for item in rx.items.select_related('product').prefetch_related('product__presentations').all():
            pres = item.product.presentations.first()
            if not pres:
                continue
            suggestions.append({
                'prescription_item_id': item.id,
                'product_name': item.product.name,
                'presentation_id': pres.id,
                'presentation_name': str(pres),
                'dose': item.dose,
                'suggested_quantity': str(item.quantity),
                'unit_price': str(pres.sale_price),
            })
        return suggestions
