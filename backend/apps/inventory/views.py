from django.db.models import F
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Product, Presentation, StockMovement, MedicalRecordProduct
from .serializers import (
    ProductSerializer,
    PresentationSerializer,
    StockMovementSerializer,
    StockAdjustmentSerializer,
    MedicalRecordProductSerializer,
)


class ProductListCreateView(generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Product.objects
            .filter(organization=self.request.user.organization)
            .select_related('presentation')
        )
        if self.request.query_params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Product.objects
            .filter(organization=self.request.user.organization)
            .select_related('presentation')
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def low_stock_products(request):
    """Productos activos cuyo stock <= min_stock. Filtrado a nivel DB."""
    products = (
        Product.objects
        .filter(
            organization=request.user.organization,
            is_active=True,
            presentation__stock__lte=F('presentation__min_stock'),
        )
        .select_related('presentation')
    )
    return Response(ProductSerializer(products, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def adjust_stock(request, pk):
    """Ajuste manual de stock (entrada, salida o corrección)."""
    from django.core.exceptions import ValidationError as DjValidationError
    from .services import apply_stock_movement

    product = get_object_or_404(
        Product.objects.select_related('presentation'),
        pk=pk,
        organization=request.user.organization,
    )

    # Después de las migraciones todo producto tiene presentación,
    # pero validamos defensivamente.
    if not hasattr(product, 'presentation'):
        return Response(
            {'error': 'Este producto no tiene presentación configurada.'},
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
            presentation=product.presentation,
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


class StockMovementListView(generics.ListAPIView):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            StockMovement.objects
            .filter(organization=self.request.user.organization)
            .select_related('presentation__product', 'created_by')
        )
        # Filtrar por product_id (conveniencia para el frontend)
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(presentation__product_id=product_id)
        # Filtrar directamente por presentation_id
        presentation_id = self.request.query_params.get('presentation')
        if presentation_id:
            queryset = queryset.filter(presentation_id=presentation_id)
        return queryset


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unit_choices(request):
    """Catálogo cerrado de unidades base válidas."""
    return Response([
        {'value': key, 'label': label}
        for key, label in Presentation.UNIT_CHOICES
    ])


class MedicalRecordProductListCreateView(generics.ListCreateAPIView):
    serializer_class = MedicalRecordProductSerializer
    permission_classes = [IsAuthenticated]

    def _get_medical_record(self):
        from apps.medical_records.models import MedicalRecord
        return get_object_or_404(
            MedicalRecord,
            pk=self.kwargs['medical_record_pk'],
            organization=self.request.user.organization,
        )

    def get_queryset(self):
        medical_record = self._get_medical_record()
        return (
            MedicalRecordProduct.objects
            .filter(medical_record=medical_record)
            .select_related('presentation__product')
        )

    def perform_create(self, serializer):
        medical_record = self._get_medical_record()
        presentation = serializer.validated_data['presentation']
        if presentation.organization_id != self.request.user.organization_id:
            raise ValidationError({'presentation': 'Presentación fuera de tu organización'})
        serializer.save(medical_record=medical_record)


class MedicalRecordProductDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_object(self):
        from apps.medical_records.models import MedicalRecord
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


class PresentationListView(generics.ListAPIView):
    serializer_class = PresentationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Presentation.objects.filter(
            organization=self.request.user.organization,
            product__is_active=True,
        ).select_related('product')
