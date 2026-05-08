from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.datetime_utils import filter_by_local_day
from apps.core.permissions import HybridPermission
from apps.core.views import TenantQueryMixin, PublicIdLookupMixin, resolve_public_id

from .models import Service, Invoice, InvoiceItem
from .serializers import ServiceSerializer, InvoiceSerializer, InvoiceItemSerializer
from .permissions import CanConfirmInvoice, CanPayInvoice, CanCancelInvoice
from .services import _log_status_change


class BillingOrganizationMixin(TenantQueryMixin):
    """Garantiza que ninguna vista de facturación retorne datos de otra organización."""


class ServiceListCreateView(BillingOrganizationMixin, generics.ListCreateAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [HybridPermission]
    resource_name = "service"

    def get_queryset(self):
        queryset = Service.objects.for_organization(self.request.user.organization)
        active_only = self.request.query_params.get('active')
        if active_only == 'true':
            queryset = queryset.filter(is_active=True)
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class ServiceDetailView(PublicIdLookupMixin, BillingOrganizationMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [HybridPermission]
    resource_name = "service"
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return Service.objects.for_organization(self.request.user.organization)


class InvoiceListCreateView(BillingOrganizationMixin, generics.ListCreateAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [HybridPermission]
    resource_name = "invoice"

    def get_queryset(self):
        queryset = Invoice.objects.for_organization(
            self.request.user.organization
        ).select_related('owner', 'pet', 'appointment')

        owner_id = self.request.query_params.get('owner')
        pet_id = self.request.query_params.get('pet')
        invoice_status = self.request.query_params.get('status')
        paid_on = self.request.query_params.get('paid_on')
        created_on = self.request.query_params.get('created_on')

        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)
        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)
        if invoice_status:
            queryset = queryset.filter(status=invoice_status)

        if paid_on:
            parsed_paid_on = parse_date(paid_on)
            if parsed_paid_on:
                queryset = filter_by_local_day(
                    queryset,
                    'paid_at',
                    self.request.user.organization,
                    parsed_paid_on,
                )
        if created_on:
            parsed_created_on = parse_date(created_on)
            if parsed_created_on:
                queryset = filter_by_local_day(
                    queryset,
                    'created_at',
                    self.request.user.organization,
                    parsed_created_on,
                )

        return queryset

    def perform_create(self, serializer):
        org = self.request.user.organization
        serializer.save(
            organization=org,
            created_by=self.request.user,
            tax_rate=org.tax_rate,
        )


class InvoiceDetailView(PublicIdLookupMixin, BillingOrganizationMixin, generics.RetrieveUpdateAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [HybridPermission]
    resource_name = "invoice"
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return Invoice.objects.for_organization(self.request.user.organization)

    def update(self, request, *args, **kwargs):
        invoice = self.get_object()
        if invoice.status != 'draft':
            return Response(
                {'error': 'Solo se pueden editar facturas en borrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)


@api_view(['PATCH'])
@permission_classes([CanConfirmInvoice])
def confirm_invoice(request, pk):
    from apps.billing.services import confirm_invoice as confirm_invoice_service

    invoice = resolve_public_id(
        Invoice.objects.for_organization(request.user.organization), pk
    )
    try:
        confirm_invoice_service(invoice, user=request.user)
    except DjValidationError as e:
        return Response({'detail': e.messages}, status=status.HTTP_400_BAD_REQUEST)

    return Response(InvoiceSerializer(invoice).data)


@api_view(['PATCH'])
@permission_classes([CanPayInvoice])
def pay_invoice(request, pk):
    payment_method = request.data.get('payment_method')
    if not payment_method:
        return Response(
            {'error': 'Se requiere el campo payment_method'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    valid_methods = [m[0] for m in Invoice.PAYMENT_METHOD_CHOICES]
    if payment_method not in valid_methods:
        return Response(
            {'error': f'Método de pago inválido. Opciones: {valid_methods}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    with transaction.atomic():
        invoice = resolve_public_id(
            Invoice.objects.for_organization(request.user.organization).select_for_update(),
            pk
        )
        if invoice.status == 'paid':
            return Response(
                {'error': 'La factura ya fue pagada'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invoice.status != 'confirmed':
            return Response(
                {'error': 'Solo se pueden pagar facturas confirmadas. Confirma la factura primero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        previous_status = invoice.status
        invoice.status = 'paid'
        invoice.payment_method = payment_method
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=['status', 'payment_method', 'paid_at', 'updated_at'])
        _log_status_change(invoice, previous=previous_status, new='paid', user=request.user)
    return Response(InvoiceSerializer(invoice).data)


class InvoiceItemCreateView(BillingOrganizationMixin, generics.CreateAPIView):
    serializer_class = InvoiceItemSerializer
    permission_classes = [HybridPermission]
    resource_name = "invoice"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        invoice = resolve_public_id(
            Invoice.objects.for_organization(self.request.user.organization),
            self.kwargs['invoice_pk']
        )
        context['invoice'] = invoice
        return context

    def perform_create(self, serializer):
        from apps.inventory.models import Presentation as InventoryPresentation

        data = serializer.validated_data
        service = data.get('service')
        presentation = data.get('presentation')

        with transaction.atomic():
            invoice = resolve_public_id(
                Invoice.objects.for_organization(self.request.user.organization).select_for_update(),
                self.kwargs['invoice_pk']
            )
            if invoice.status != 'draft':
                raise ValidationError('Solo se pueden agregar ítems a cobros en borrador')

            if service:
                unit_price = service.base_price
                description = service.name
                serializer.save(invoice=invoice, unit_price=unit_price, description=description)
            else:
                locked_pres = InventoryPresentation.objects.select_for_update().filter(
                    pk=presentation.pk,
                    organization=self.request.user.organization,
                ).first()
                if locked_pres is None:
                    raise ValidationError("Presentación no encontrada en la organización.")
                if locked_pres.stock < data.get('quantity', 1):
                    raise ValidationError(
                        f"Stock insuficiente para '{locked_pres.product.name}': "
                        f"disponible {locked_pres.stock}, solicitado {data.get('quantity', 1)}."
                    )
                unit_price = locked_pres.sale_price
                description = str(locked_pres)
                serializer.save(invoice=invoice, unit_price=unit_price, description=description)


class InvoiceItemDetailView(BillingOrganizationMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InvoiceItemSerializer
    permission_classes = [HybridPermission]
    resource_name = "invoice"

    def _get_invoice(self):
        return resolve_public_id(
            Invoice.objects.for_organization(self.request.user.organization),
            self.kwargs['invoice_pk']
        )

    def get_object(self):
        return get_object_or_404(InvoiceItem, pk=self.kwargs['pk'], invoice=self._get_invoice())

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['invoice'] = self._get_invoice()
        return context

    def update(self, request, *args, **kwargs):
        item = self.get_object()
        if item.invoice.status != 'draft':
            return Response(
                {'error': 'Solo se pueden editar ítems de facturas en borrador'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        item = self.get_object()
        if item.invoice.status != 'draft':
            return Response(
                {'error': 'Solo se pueden eliminar ítems de facturas en borrador'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


@api_view(['PATCH'])
@permission_classes([CanCancelInvoice])
def cancel_invoice(request, pk):
    invoice = resolve_public_id(
        Invoice.objects.for_organization(request.user.organization), pk
    )
    from apps.core.sanitize import sanitize_text
    notes = sanitize_text(request.data.get('notes') or '', max_length=255)
    try:
        from .services import cancel_invoice as cancel_invoice_service
        cancel_invoice_service(invoice, user=request.user, notes=notes)
    except DjValidationError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(InvoiceSerializer(invoice).data)
