import logging

from django.db import transaction
from django.db.models import F
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from apps.core.permissions import HybridPermission, make_permission
from apps.core.views import TenantQueryMixin
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


class ProductDetailView(TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"

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

    product = get_object_or_404(
        Product.objects.prefetch_related('presentations'),
        pk=pk,
        organization=request.user.organization,
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
        apply_stock_movement(
            presentation=presentation,
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

    presentation = get_object_or_404(
        Presentation.objects.select_related('product'),
        pk=pk,
        organization=request.user.organization,
    )

    serializer = StockAdjustmentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    movement_type = serializer.validated_data['movement_type']
    quantity = serializer.validated_data['quantity']
    reason = serializer.validated_data.get('reason', '')
    if movement_type == 'adjustment' and not reason:
        reason = f'Ajuste manual a {quantity}'

    try:
        apply_stock_movement(
            presentation=presentation,
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
        product = get_object_or_404(
            Product,
            pk=self.kwargs['product_pk'],
            organization=self.request.user.organization,
        )
        serializer.save(
            product=product,
            organization=self.request.user.organization,
        )


class PresentationDetailView(TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    """Update or delete a specific presentation variant."""
    serializer_class = PresentationCreateSerializer
    permission_classes = [HybridPermission]
    resource_name = "inventory"
    http_method_names = ['get', 'patch', 'delete']

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
        return get_object_or_404(
            MedicalRecord,
            pk=self.kwargs['medical_record_pk'],
            organization=self.request.user.organization,
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
        with transaction.atomic():
            medical_record = get_object_or_404(
                MedicalRecord.objects.select_for_update(),
                pk=self.kwargs['medical_record_pk'],
                organization=self.request.user.organization,
            )
            self._assert_can_modify(medical_record)
            presentation = serializer.validated_data['presentation']
            quantity = serializer.validated_data['quantity']
            if presentation.organization_id != self.request.user.organization_id:
                raise ValidationError({'presentation': 'Presentación fuera de tu organización'})

            mrp = MedicalRecordProduct.objects.filter(
                medical_record=medical_record,
                presentation=presentation,
            ).first()

            if mrp is not None:
                mrp.quantity += quantity
                mrp.save()
            else:
                mrp = serializer.save(medical_record=medical_record)

            self._sync_invoice_item(medical_record, presentation, quantity)

    def _sync_invoice_item(self, medical_record, presentation, quantity_delta):
        from apps.billing.services import get_or_create_invoice_for_medical_record
        from apps.billing.models import InvoiceItem

        invoice = get_or_create_invoice_for_medical_record(medical_record)
        if invoice.status != 'draft':
            return
        item, created = InvoiceItem.objects.get_or_create(
            invoice=invoice,
            presentation=presentation,
            defaults={
                'description': str(presentation),
                'quantity': quantity_delta,
                'unit_price': presentation.sale_price,
            }
        )
        if not created:
            item.quantity += quantity_delta
            item.save()


class MedicalRecordProductDeleteView(generics.DestroyAPIView):
    permission_classes = [HybridPermission]
    resource_name = "medicalrecord"
    required_permission = 'medicalrecord.update'

    def get_object(self):
        medical_record = get_object_or_404(
            MedicalRecord,
            pk=self.kwargs['medical_record_pk'],
            organization=self.request.user.organization,
        )
        return get_object_or_404(
            MedicalRecordProduct,
            pk=self.kwargs['pk'],
            medical_record=medical_record,
        )

    def perform_destroy(self, instance):
        with transaction.atomic():
            medical_record = get_object_or_404(
                MedicalRecord.objects.select_for_update(),
                pk=instance.medical_record_id,
                organization=self.request.user.organization,
            )
            assert_can_modify_charges(self.request.user, medical_record, self.request)
            self._sync_invoice_item_delete(instance)
            instance.delete()

    def _sync_invoice_item_delete(self, mrp):
        from apps.billing.models import InvoiceItem

        invoice_id = mrp.medical_record.invoice_id
        if not invoice_id:
            return

        item = InvoiceItem.objects.filter(
            invoice_id=invoice_id,
            presentation=mrp.presentation,
            is_active=True,
        ).first()
        if item is None:
            return

        if item.invoice.status != 'draft':
            events_logger.warning(
                "MEDICAL_RECORD_INVOICE_SYNC_SKIPPED",
                extra={
                    "user_id": self.request.user.id,
                    "organization_id": self.request.user.organization_id,
                    "medical_record_id": mrp.medical_record_id,
                    "invoice_id": item.invoice_id,
                    "endpoint": self.request.path,
                    "method": self.request.method,
                },
            )
            return

        new_quantity = item.quantity - mrp.quantity
        if new_quantity <= 0:
            item.delete()
        else:
            item.quantity = new_quantity
            item.save()
