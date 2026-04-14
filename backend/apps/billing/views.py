from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.datetime_utils import filter_by_local_day

from .models import Service, Invoice, InvoiceItem
from .serializers import ServiceSerializer, InvoiceSerializer, InvoiceItemSerializer
from .permissions import CanConfirmInvoice, CanPayInvoice


class BillingOrganizationMixin:
    """Garantiza que ninguna vista de facturación retorne datos de otra organización."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(organization=self.request.user.organization)


class ServiceListCreateView(BillingOrganizationMixin, generics.ListCreateAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Service.objects.filter(organization=self.request.user.organization)
        active_only = self.request.query_params.get('active')
        if active_only == 'true':
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class ServiceDetailView(BillingOrganizationMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Service.objects.filter(organization=self.request.user.organization)


class InvoiceListCreateView(BillingOrganizationMixin, generics.ListCreateAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Invoice.objects.filter(
            organization=self.request.user.organization
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
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user,
        )


class InvoiceDetailView(BillingOrganizationMixin, generics.RetrieveUpdateAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(organization=self.request.user.organization)

    def update(self, request, *args, **kwargs):
        invoice = self.get_object()
        if invoice.status == 'paid':
            return Response(
                {'error': 'No se puede editar una factura ya pagada'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)


@api_view(['PATCH'])
@permission_classes([CanConfirmInvoice])
def confirm_invoice(request, pk):
    from apps.billing.services import confirm_invoice as confirm_invoice_service

    invoice = get_object_or_404(Invoice, pk=pk, organization=request.user.organization)
    try:
        confirm_invoice_service(invoice, user=request.user)
    except ValidationError as e:
        return Response({'detail': e.messages}, status=status.HTTP_400_BAD_REQUEST)

    return Response(InvoiceSerializer(invoice).data)


@api_view(['PATCH'])
@permission_classes([CanPayInvoice])
def pay_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, organization=request.user.organization)
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
    invoice.status = 'paid'
    invoice.payment_method = payment_method
    invoice.paid_at = timezone.now()
    invoice.save(update_fields=['status', 'payment_method', 'paid_at', 'updated_at'])
    return Response(InvoiceSerializer(invoice).data)


class InvoiceItemCreateView(BillingOrganizationMixin, generics.CreateAPIView):
    serializer_class = InvoiceItemSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        invoice = get_object_or_404(
            Invoice.objects.filter(organization=self.request.user.organization),
            pk=self.kwargs['invoice_pk']
        )
        context['invoice'] = invoice
        return context

    def perform_create(self, serializer):
        invoice = get_object_or_404(
            Invoice,
            pk=self.kwargs['invoice_pk'],
            organization=self.request.user.organization,
        )
        if invoice.status != 'draft':
            raise ValidationError('Solo se pueden agregar ítems a facturas en borrador')
        serializer.save(invoice=invoice)


class InvoiceItemDetailView(BillingOrganizationMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InvoiceItemSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        invoice = get_object_or_404(
            Invoice,
            pk=self.kwargs['invoice_pk'],
            organization=self.request.user.organization,
        )
        return get_object_or_404(InvoiceItem, pk=self.kwargs['pk'], invoice=invoice)

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
@permission_classes([CanConfirmInvoice])
def cancel_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, organization=request.user.organization)
    notes = request.data.get('notes', '')
    try:
        from .services import cancel_invoice as cancel_invoice_service
        cancel_invoice_service(invoice, user=request.user, notes=notes)
    except DjValidationError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(InvoiceSerializer(invoice).data)
