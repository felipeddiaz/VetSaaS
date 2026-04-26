import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.permissions import HybridPermission, make_permission
from apps.core.views import TenantQueryMixin

from .models import MedicalRecord, MedicalRecordService
from .policies import (
    assert_can_modify_charges,
    can_close_medical_record,
    log_ownership_denied,
)
from .serializers import (
    MedicalRecordSerializer,
    MedicalRecordDetailSerializer,
    MedicalRecordServiceSerializer,
)


events_logger = logging.getLogger("medical_records.events")


class MedicalRecordPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class MedicalRecordListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [HybridPermission]
    pagination_class = MedicalRecordPagination
    resource_name = "medicalrecord"

    def get_queryset(self):
        pet_id = self.request.query_params.get('pet')
        queryset = MedicalRecord.objects.for_organization(self.request.user.organization)

        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            veterinarian=self.request.user
        )


class MedicalRecordDetailView(TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MedicalRecordDetailSerializer
    permission_classes = [HybridPermission]
    resource_name = "medicalrecord"

    def get_queryset(self):
        return MedicalRecord.objects.for_organization(self.request.user.organization)

    def _check_not_closed(self, instance):
        if instance.status == MedicalRecord.Status.CLOSED:
            from rest_framework.exceptions import PermissionDenied
            from .policies import log_closed_denied
            log_closed_denied(user=self.request.user, medical_record=instance, request=self.request)
            raise PermissionDenied("La consulta está cerrada y no puede modificarse.")

    def update(self, request, *args, **kwargs):
        self._check_not_closed(self.get_object())
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._check_not_closed(self.get_object())
        return super().destroy(request, *args, **kwargs)


class MedicalRecordByPetView(TenantQueryMixin, generics.ListAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [HybridPermission]
    pagination_class = MedicalRecordPagination
    resource_name = "medicalrecord"

    def get_queryset(self):
        pet_id = self.kwargs.get('pet_id')
        return MedicalRecord.objects.for_organization(
            self.request.user.organization
        ).filter(pet_id=pet_id).order_by('-created_at')


class MedicalRecordServiceListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = MedicalRecordServiceSerializer
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

    def get_queryset(self):
        mr = self._get_medical_record()
        return MedicalRecordService.objects.filter(
            medical_record=mr
        ).select_related('service')

    def perform_create(self, serializer):
        with transaction.atomic():
            mr = get_object_or_404(
                MedicalRecord.objects.select_for_update(),
                pk=self.kwargs['medical_record_pk'],
                organization=self.request.user.organization,
            )
            assert_can_modify_charges(self.request.user, mr, self.request)
            service = serializer.validated_data['service']
            if service.organization_id != self.request.user.organization_id:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'service': 'Servicio fuera de tu organización'})
            mrs = serializer.save(medical_record=mr)
            self._sync_invoice_item(mrs)

    def _sync_invoice_item(self, mrs):
        from apps.billing.services import get_or_create_invoice_for_medical_record
        from apps.billing.models import InvoiceItem
        invoice = get_or_create_invoice_for_medical_record(mrs.medical_record)
        if invoice.status != 'draft':
            return
        item, created = InvoiceItem.objects.get_or_create(
            invoice=invoice,
            service=mrs.service,
            defaults={
                'description': mrs.service.name,
                'quantity': mrs.quantity,
                'unit_price': mrs.service.base_price,
            }
        )
        if not created:
            item.quantity += mrs.quantity
            item.save()


class MedicalRecordServiceDeleteView(generics.DestroyAPIView):
    permission_classes = [HybridPermission]
    resource_name = "medicalrecord"
    required_permission = 'medicalrecord.update'

    def get_object(self):
        mr = get_object_or_404(
            MedicalRecord,
            pk=self.kwargs['medical_record_pk'],
            organization=self.request.user.organization,
        )
        return get_object_or_404(
            MedicalRecordService,
            pk=self.kwargs['pk'],
            medical_record=mr,
        )

    def perform_destroy(self, instance):
        with transaction.atomic():
            mr = get_object_or_404(
                MedicalRecord.objects.select_for_update(),
                pk=instance.medical_record_id,
                organization=self.request.user.organization,
            )
            assert_can_modify_charges(self.request.user, mr, self.request)
            self._sync_invoice_item_delete(instance)
            instance.delete()

    def _sync_invoice_item_delete(self, mrs):
        from apps.billing.models import InvoiceItem
        invoice_id = mrs.medical_record.invoice_id
        if not invoice_id:
            return
        item = InvoiceItem.objects.filter(
            invoice_id=invoice_id,
            service=mrs.service,
            is_active=True,
        ).first()
        if item is None or item.invoice.status != 'draft':
            return
        new_qty = item.quantity - mrs.quantity
        if new_qty <= 0:
            item.delete()
        else:
            item.quantity = new_qty
            item.save()


@api_view(['POST'])
@permission_classes([make_permission("medicalrecord.close")])
def close_medical_record(request, pk):
    with transaction.atomic():
        medical_record = get_object_or_404(
            MedicalRecord.objects.select_for_update(),
            pk=pk,
            organization=request.user.organization,
        )

        if not can_close_medical_record(request.user, medical_record):
            log_ownership_denied(user=request.user, medical_record=medical_record, request=request)
            raise PermissionDenied("No puedes finalizar esta consulta")

        if medical_record.status == MedicalRecord.Status.CLOSED:
            events_logger.info(
                "MEDICAL_RECORD_CLOSE_IDEMPOTENT",
                extra={
                    "user_id": request.user.id,
                    "organization_id": request.user.organization_id,
                    "medical_record_id": medical_record.id,
                    "endpoint": request.path,
                    "method": request.method,
                },
            )
            return Response(MedicalRecordDetailSerializer(medical_record, context={"request": request}).data)

        medical_record.status = MedicalRecord.Status.CLOSED
        medical_record.closed_at = timezone.now()
        medical_record.closed_by = request.user
        medical_record.save(update_fields=['status', 'closed_at', 'closed_by'])

        events_logger.info(
            "MEDICAL_RECORD_CLOSED",
            extra={
                "user_id": request.user.id,
                "organization_id": request.user.organization_id,
                "medical_record_id": medical_record.id,
                "endpoint": request.path,
                "method": request.method,
            },
        )
        return Response(MedicalRecordDetailSerializer(medical_record, context={"request": request}).data)
