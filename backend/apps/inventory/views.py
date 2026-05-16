import logging

from django.db import transaction
from django.db.models import F
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from apps.core.permissions import HybridPermission, make_permission
from apps.core.views import TenantQueryMixin, PublicIdLookupMixin, resolve_public_id
from apps.medical_records.models import MedicalRecord
from apps.medical_records.policies import (
    assert_can_modify_charges,
    can_modify_medical_record_charges,
    log_closed_denied,
    log_ownership_denied,
)

from .models import Product, Presentation, StockMovement, MedicalRecordProduct
from .serializers import (
    ProductSerializer,
    PresentationSerializer,
    PresentationCreateSerializer,
    StockMovementSerializer,
    StockAdjustmentSerializer,
    MedicalRecordProductSerializer,
)


events_logger = logging.getLogger("medical_records.events")


class ProductListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"

    def get_queryset(self):
        queryset = (
            Product.objects
            .for_organization(self.request.user.organization)
            .prefetch_related('presentations')
        )
        if self.request.query_params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        # Filter by category with stock > 0 (for prescription autocomplete)
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        stock_gt = self.request.query_params.get('stock__gt')
        if stock_gt is not None:
            try:
                queryset = queryset.filter(
                    presentations__stock__gt=float(stock_gt)
                ).distinct()
            except ValueError:
                pass
        return queryset

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class ProductDetailView(PublicIdLookupMixin, TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return (
            Product.objects
            .for_organization(self.request.user.organization)
            .prefetch_related('presentations')
        )


@api_view(['GET'])
@permission_classes([make_permission("inventory.list")])
def low_stock_products(request):
    """Productos activos cuyo al menos una presentación tiene stock <= min_stock."""
    products = (
        Product.objects
        .filter(
            organization=request.user.organization,
            is_active=True,
            presentations__stock__lte=F('presentations__min_stock'),
        )
        .prefetch_related('presentations')
        .distinct()
    )
    return Response(ProductSerializer(products, many=True).data)


@api_view(['POST'])
@permission_classes([make_permission("inventory.update")])
def adjust_stock(request, pk):
    """Ajuste de stock para la primera presentación de un producto (backward compat)."""
    from django.core.exceptions import ValidationError as DjValidationError
    from .services import apply_stock_movement

    product = resolve_public_id(
        Product.objects.for_organization(request.user.organization).prefetch_related('presentations'),
        pk,
    )

    presentation = product.presentations.first()
    if presentation is None:
        return Response(
            {'error': 'Este producto no tiene presentaciones configuradas.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = StockAdjustmentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    movement_type = serializer.validated_data['movement_type']
    quantity = serializer.validated_data['quantity']
    reason = serializer.validated_data.get('reason', '')
    if movement_type == 'adjustment' and not reason:
        reason = f'Ajuste manual a {quantity}'

    try:
        with transaction.atomic():
            locked_pres = Presentation.objects.select_for_update().get(pk=presentation.pk)
            apply_stock_movement(
                presentation=locked_pres,
                quantity=quantity,
                movement_type=movement_type,
                organization=request.user.organization,
                reason=reason,
                created_by=request.user,
            )
    except DjValidationError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    product.refresh_from_db()
    return Response(ProductSerializer(product).data)


@api_view(['POST'])
@permission_classes([make_permission("inventory.update")])
def adjust_presentation_stock(request, pk):
    """Ajuste de stock para una presentación específica."""
    from django.core.exceptions import ValidationError as DjValidationError
    from .services import apply_stock_movement

    presentation = resolve_public_id(
        Presentation.objects.for_organization(request.user.organization).select_related('product'),
        pk,
    )

    serializer = StockAdjustmentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    movement_type = serializer.validated_data['movement_type']
    quantity = serializer.validated_data['quantity']
    reason = serializer.validated_data.get('reason', '')
    if movement_type == 'adjustment' and not reason:
        reason = f'Ajuste manual a {quantity}'

    try:
        with transaction.atomic():
            locked_pres = Presentation.objects.select_for_update().get(pk=presentation.pk)
            apply_stock_movement(
                presentation=locked_pres,
                quantity=quantity,
                movement_type=movement_type,
                organization=request.user.organization,
                reason=reason,
                created_by=request.user,
            )
    except DjValidationError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(PresentationSerializer(presentation).data)


class StockMovementListView(TenantQueryMixin, generics.ListAPIView):
    serializer_class = StockMovementSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"

    def get_queryset(self):
        queryset = (
            StockMovement.objects
            .for_organization(self.request.user.organization)
            .select_related('presentation__product', 'created_by')
        )
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(presentation__product_id=product_id)
        presentation_id = self.request.query_params.get('presentation')
        if presentation_id:
            queryset = queryset.filter(presentation_id=presentation_id)
        return queryset


@api_view(['GET'])
@permission_classes([make_permission("inventory.list")])
def unit_choices(request):
    """Catálogo cerrado de unidades base válidas."""
    return Response([
        {'value': key, 'label': label}
        for key, label in Presentation.UNIT_CHOICES
    ])


class PresentationListView(TenantQueryMixin, generics.ListAPIView):
    serializer_class = PresentationSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"

    def get_queryset(self):
        qs = Presentation.objects.for_organization(
            self.request.user.organization
        ).filter(product__is_active=True).select_related('product')
        category = self.request.query_params.get('product__category')
        if category:
            qs = qs.filter(product__category=category)
        stock_gt = self.request.query_params.get('stock__gt')
        if stock_gt is not None:
            try:
                qs = qs.filter(stock__gt=float(stock_gt))
            except ValueError:
                pass
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(product__name__icontains=search)
        return qs.order_by('product__name', 'name').select_related('product')


class PresentationCreateView(TenantQueryMixin, generics.CreateAPIView):
    """Add a new presentation variant to an existing product."""
    serializer_class = PresentationCreateSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"

    def perform_create(self, serializer):
        product = resolve_public_id(
            Product.objects.for_organization(self.request.user.organization),
            self.kwargs['product_pk'],
        )
        serializer.save(
            product=product,
            organization=self.request.user.organization,
        )


class PresentationDetailView(PublicIdLookupMixin, TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    """Update or delete a specific presentation variant."""
    serializer_class = PresentationCreateSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"
    http_method_names = ['get', 'patch', 'delete']
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return Presentation.objects.for_organization(
            self.request.user.organization
        ).select_related('product')

    def perform_destroy(self, instance):
        with transaction.atomic():
            pres = Presentation.objects.select_for_update().get(pk=instance.pk)
            if pres.stock > 0:
                raise ValidationError("No se puede eliminar una presentación con stock disponible.")
            if StockMovement.objects.filter(presentation=pres).exists():
                raise ValidationError(
                    "No se puede eliminar: esta presentación tiene movimientos de stock registrados."
                )
            from apps.billing.models import InvoiceItem
            if InvoiceItem.objects.filter(presentation=pres).exists():
                raise ValidationError(
                    "No se puede eliminar: esta presentación está referenciada en facturas."
                )
            if MedicalRecordProduct.objects.filter(presentation=pres).exists():
                raise ValidationError(
                    "No se puede eliminar: esta presentación fue usada en consultas médicas."
                )
            pres.delete()


class MedicalRecordProductListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = MedicalRecordProductSerializer
    permission_classes = [HybridPermission]
    resource_name = "medicalrecord"

    def initial(self, request, *args, **kwargs):
        if request.method == 'GET':
            self.required_permission = 'medicalrecord.retrieve'
        else:
            self.required_permission = 'medicalrecord.update'
        return super().initial(request, *args, **kwargs)

    def _get_medical_record(self):
        return resolve_public_id(
            MedicalRecord.objects.for_organization(self.request.user.organization),
            self.kwargs['medical_record_pk'],
        )

    def _assert_can_modify(self, medical_record):
        assert_can_modify_charges(self.request.user, medical_record, self.request)

    def get_queryset(self):
        medical_record = self._get_medical_record()
        if medical_record.organization_id != self.request.user.organization_id:
            raise PermissionDenied('No puedes acceder a consultas fuera de tu organización')
        return (
            MedicalRecordProduct.objects
            .filter(medical_record=medical_record)
            .select_related('presentation__product')
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['medical_record'] = self._get_medical_record()
        return ctx

    def perform_create(self, serializer):
        from apps.billing.models import InvoiceItem
        from apps.billing.services import (
            apply_invoice_item_quantity_delta,
            get_or_create_invoice_for_medical_record,
        )

        with transaction.atomic():
            medical_record = resolve_public_id(
                MedicalRecord.objects.for_organization(self.request.user.organization).select_for_update(),
                self.kwargs['medical_record_pk'],
            )
            self._assert_can_modify(medical_record)
            presentation = serializer.validated_data['presentation']
            quantity = serializer.validated_data['quantity']
            if presentation.organization_id != self.request.user.organization_id:
                raise ValidationError({'presentation': 'Presentación fuera de tu organización'})
            invoice = get_or_create_invoice_for_medical_record(medical_record)
            locked_pres = Presentation.objects.select_for_update().get(pk=presentation.pk)

            if invoice.status == 'draft':
                item = (
                    InvoiceItem.objects
                    .select_for_update()
                    .filter(invoice=invoice, presentation=locked_pres, is_active=True)
                    .first()
                )
                if item is None:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        presentation=locked_pres,
                        description=str(locked_pres),
                        quantity=quantity,
                        unit_price=locked_pres.sale_price,
                        organization=invoice.organization,
                    )
                else:
                    apply_invoice_item_quantity_delta(item, quantity)

            mrp = MedicalRecordProduct.objects.select_for_update().filter(
                medical_record=medical_record,
                presentation=locked_pres,
            ).first()

            if mrp is not None:
                previous_quantity = mrp.quantity
                mrp.quantity = previous_quantity + quantity
                mrp.save(locked_presentation=locked_pres, previous_quantity=previous_quantity)
            else:
                mrp = MedicalRecordProduct(
                    medical_record=medical_record,
                    presentation=locked_pres,
                    quantity=quantity,
                )
                mrp.save(locked_presentation=locked_pres)


class MedicalRecordProductDeleteView(generics.DestroyAPIView):
    permission_classes = [HybridPermission]
    resource_name = "medicalrecord"
    required_permission = 'medicalrecord.update'

    def get_object(self):
        mr = resolve_public_id(
            MedicalRecord.objects.for_organization(self.request.user.organization),
            self.kwargs['medical_record_pk'],
        )
        return get_object_or_404(
            MedicalRecordProduct,
            pk=self.kwargs['pk'],
            medical_record=mr,
        )

    def perform_destroy(self, instance):
        from apps.billing.models import Invoice
        from apps.billing.models import InvoiceItem
        from apps.billing.services import apply_invoice_item_quantity_delta

        with transaction.atomic():
            mr = resolve_public_id(
                MedicalRecord.objects.for_organization(self.request.user.organization).select_for_update(),
                self.kwargs['medical_record_pk'],
            )
            assert_can_modify_charges(self.request.user, mr, self.request)
            invoice_id = instance.medical_record.invoice_id
            locked_invoice = None
            if invoice_id:
                locked_invoice = Invoice.objects.for_organization(
                    self.request.user.organization
                ).select_for_update().filter(pk=invoice_id).first()

            locked_pres = Presentation.objects.select_for_update().get(pk=instance.presentation_id)

            item = None
            if locked_invoice is not None:
                item = InvoiceItem.objects.select_for_update().filter(
                    invoice=locked_invoice,
                    presentation=locked_pres,
                    is_active=True,
                ).first()

            fresh_instance = MedicalRecordProduct.objects.select_for_update().get(
                pk=instance.pk,
                medical_record=mr,
            )

            should_sync_invoice = True
            if item is not None and item.invoice.status != 'draft':
                events_logger.warning(
                    "MEDICAL_RECORD_INVOICE_SYNC_SKIPPED",
                    extra={
                        "user_id": self.request.user.id,
                        "organization_id": self.request.user.organization_id,
                        "medical_record_id": instance.medical_record_id,
                        "invoice_id": item.invoice_id,
                        "endpoint": self.request.path,
                        "method": self.request.method,
                    },
                )
                should_sync_invoice = False

            if item is not None and should_sync_invoice:
                projected = item.quantity - fresh_instance.quantity
                if projected <= 0:
                    item.delete()
                else:
                    apply_invoice_item_quantity_delta(item, -fresh_instance.quantity)

            fresh_instance.delete(locked_presentation=locked_pres)
