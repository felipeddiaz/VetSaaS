import logging
from datetime import date

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.permissions import HybridPermission, make_permission
from apps.core.sanitize import sanitize_text
from apps.core.views import TenantQueryMixin, PublicIdLookupMixin, resolve_public_id

from .models import MedicalRecord, MedicalRecordService, VaccineRecord, VitalSigns
from .models import get_current_weight
from .policies import (
    assert_can_modify_charges,
    assert_can_modify_medical_record,
    can_close_medical_record,
    log_ownership_denied,
)
from .serializers import (
    MedicalRecordSerializer,
    MedicalRecordDetailSerializer,
    MedicalRecordServiceSerializer,
    VaccineRecordSerializer,
    VitalSignsSerializer,
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
        queryset = MedicalRecord.objects.for_organization(self.request.user.organization).select_related(
            'pet', 'veterinarian', 'appointment', 'prescription'
        ).prefetch_related(
            'products_used__presentation__product',
            'services_used__service',
            'prescription__items__product__presentations',
            'vital_signs',
        )

        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            veterinarian=self.request.user
        )


class MedicalRecordDetailView(PublicIdLookupMixin, TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MedicalRecordDetailSerializer
    permission_classes = [HybridPermission]
    resource_name = "medicalrecord"
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return MedicalRecord.objects.for_organization(self.request.user.organization).select_related(
            'pet', 'veterinarian', 'appointment', 'prescription'
        ).prefetch_related(
            'products_used__presentation__product',
            'services_used__service',
            'prescription__items__product__presentations',
            'vital_signs',
        )

    def _check_not_closed(self, instance):
        if instance.status == MedicalRecord.Status.CLOSED:
            from .policies import log_closed_denied
            log_closed_denied(user=self.request.user, medical_record=instance, request=self.request)
            raise PermissionDenied("La consulta está cerrada y no puede modificarse.")

    def update(self, request, *args, **kwargs):
        self._check_not_closed(self.get_object())
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._check_not_closed(instance)
        from apps.billing.models import Invoice
        if Invoice.objects.filter(medical_record=instance).exists():
            raise PermissionDenied("No se puede eliminar una consulta con factura asociada.")
        from .policies import medical_record_has_clinical_content
        if medical_record_has_clinical_content(instance):
            raise PermissionDenied(
                "No se puede eliminar una consulta con contenido clínico registrado. "
                "Si es un error, contacta al administrador."
            )
        events_logger.info(
            "MEDICAL_RECORD_DELETED",
            extra={
                "user_id": request.user.id,
                "organization_id": request.user.organization_id,
                "medical_record_id": instance.id,
                "public_id": str(instance.public_id),
                "endpoint": request.path,
                "method": request.method,
            },
        )
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
        ).filter(pet_id=pet_id).select_related(
            'pet', 'veterinarian', 'appointment', 'prescription'
        ).prefetch_related(
            'products_used__presentation__product',
            'services_used__service',
            'prescription__items__product__presentations',
            'vital_signs',
        ).order_by('-created_at')


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
        return resolve_public_id(
            MedicalRecord.objects.for_organization(self.request.user.organization),
            self.kwargs['medical_record_pk'],
        )

    def get_queryset(self):
        mr = self._get_medical_record()
        return MedicalRecordService.objects.filter(
            medical_record=mr
        ).select_related('service')

    def perform_create(self, serializer):
        with transaction.atomic():
            mr = resolve_public_id(
                MedicalRecord.objects.for_organization(self.request.user.organization).select_for_update(),
                self.kwargs['medical_record_pk'],
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
        mr = resolve_public_id(
            MedicalRecord.objects.for_organization(self.request.user.organization),
            self.kwargs['medical_record_pk'],
        )
        return get_object_or_404(
            MedicalRecordService,
            pk=self.kwargs['pk'],
            medical_record=mr,
        )

    def perform_destroy(self, instance):
        with transaction.atomic():
            mr = resolve_public_id(
                MedicalRecord.objects.for_organization(self.request.user.organization).select_for_update(),
                self.kwargs['medical_record_pk'],
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


class VitalSignsListCreateView(generics.ListCreateAPIView):
    serializer_class = VitalSignsSerializer
    permission_classes = [HybridPermission]
    pagination_class = MedicalRecordPagination
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'vitals'

    def initial(self, request, *args, **kwargs):
        # HybridPermission infiere "retrieve" cuando hay "pk" en kwargs — evitar
        if request.method == 'GET':
            self.required_permission = 'medicalrecord.vitals.list'
        else:
            self.required_permission = 'medicalrecord.vitals.create'
        return super().initial(request, *args, **kwargs)

    def _get_medical_record(self):
        return resolve_public_id(
            MedicalRecord.objects.for_organization(self.request.user.organization),
            self.kwargs['pk'],
        )

    def get_queryset(self):
        mr = self._get_medical_record()
        return (
            VitalSigns.objects
            .for_organization(self.request.user.organization)
            .filter(medical_record=mr)
            .order_by('-recorded_at', '-created_at')
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['pet'] = self._get_medical_record().pet
        return ctx

    def perform_create(self, serializer):
        mr = self._get_medical_record()
        assert_can_modify_medical_record(self.request.user, mr, self.request)
        serializer.save(
            medical_record=mr,
            organization=mr.organization,
            recorded_by=self.request.user,
        )
        events_logger.info(
            "VITAL_SIGNS_CREATED",
            extra={
                "user_id": self.request.user.id,
                "organization_id": self.request.user.organization_id,
                "medical_record_id": mr.id,
            },
        )


class MedicalRecordSummaryView(generics.GenericAPIView):
    permission_classes = [make_permission("medicalrecord.summary.retrieve")]

    def get(self, request, pk):
        mr = resolve_public_id(
            MedicalRecord.objects
                .for_organization(request.user.organization)
                .select_related('pet__owner', 'appointment')
                .prefetch_related('vital_signs'),
            pk,
        )

        last_vital = mr.vital_signs.order_by('-recorded_at', '-created_at').first()
        weight = get_current_weight(mr)

        invoice = None
        if mr.invoice_id:
            from apps.billing.models import Invoice
            invoice = (
                Invoice.objects
                .filter(pk=mr.invoice_id)
                .only('status', 'subtotal', 'tax_amount', 'total')
                .first()
            )

        next_vaccine = (
            VaccineRecord.objects
            .filter(pet=mr.pet, next_due_date__gte=date.today())
            .order_by('next_due_date')
            .first()
        )

        data = {
            "patient": {
                "name": mr.pet.name,
                "species": mr.pet.species,
                "breed": mr.pet.breed,
                "birth_date": mr.pet.birth_date,
            },
            "last_vitals": {
                "weight": weight,
                "temperature": last_vital.temperature if last_vital else None,
                "heart_rate": last_vital.heart_rate if last_vital else None,
                "respiratory_rate": last_vital.respiratory_rate if last_vital else None,
                "recorded_at": last_vital.recorded_at if last_vital else None,
                "has_vitals": last_vital is not None,
            },
            "diagnosis": mr.diagnosis,
            "consultation_type": mr.consultation_type,
            "status": mr.status,
            "totals": {
                "subtotal": invoice.subtotal,
                "tax_amount": invoice.tax_amount,
                "total": invoice.total,
                "status": invoice.status,
            } if invoice else None,
            "next_vaccine_date": next_vaccine.next_due_date if next_vaccine else None,
        }
        return Response(data)


@api_view(['POST'])
@permission_classes([make_permission("medicalrecord.close")])
def close_medical_record(request, pk):
    with transaction.atomic():
        medical_record = resolve_public_id(
            MedicalRecord.objects.select_for_update().filter(
                organization=request.user.organization,
            ),
            pk,
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

        # Validación de campos requeridos para cierre
        diagnosis = sanitize_text(medical_record.diagnosis or '', max_length=400)
        if not diagnosis.strip():
            events_logger.warning(
                "MEDICAL_RECORD_CLOSE_VALIDATION_FAILED",
                extra={
                    "record_id": str(medical_record.public_id),
                    "field": "diagnosis",
                    "user_id": request.user.id,
                    "organization_id": request.user.organization_id,
                },
            )
            raise ValidationError({"diagnosis": "El diagnóstico es obligatorio."})

        if medical_record.consultation_type != MedicalRecord.ConsultationType.VACCINE:
            treatment = sanitize_text(medical_record.treatment or '', max_length=400)
            if not treatment.strip():
                events_logger.warning(
                    "MEDICAL_RECORD_CLOSE_VALIDATION_FAILED",
                    extra={
                        "record_id": str(medical_record.public_id),
                        "field": "treatment",
                        "user_id": request.user.id,
                        "organization_id": request.user.organization_id,
                    },
                )
                raise ValidationError({"treatment": "El tratamiento es obligatorio."})

        medical_record.status = MedicalRecord.Status.CLOSED
        medical_record.closed_at = timezone.now()
        medical_record.closed_at_source = 'service'
        medical_record.closed_by = request.user
        medical_record.save(update_fields=[
            'status', 'closed_at', 'closed_at_source', 'closed_by',
        ])

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


class VaccineRecordListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = VaccineRecordSerializer
    permission_classes = [HybridPermission]
    resource_name = "vaccinerecord"

    def get_queryset(self):
        qs = VaccineRecord.objects.for_organization(
            self.request.user.organization
        ).select_related('pet', 'applied_by', 'medical_record')
        pet_id = self.request.query_params.get('pet')
        if pet_id:
            qs = qs.filter(pet_id=pet_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            applied_by=self.request.user,
        )


class VaccineRecordDetailView(TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = VaccineRecordSerializer
    permission_classes = [HybridPermission]
    resource_name = "vaccinerecord"

    def get_queryset(self):
        return VaccineRecord.objects.for_organization(
            self.request.user.organization
        ).select_related('pet', 'applied_by', 'medical_record')
