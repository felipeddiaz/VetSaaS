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


def _warn_if_late_closed_at(organization, closed_at):
    """
    Late-arrival observability for MedicalRecord.closed_at (ADR p17 Día 5,
    warn-only phase).

    Emits an ``ANCHOR_LATE_ARRIVAL`` warning on the ``analytics.events``
    logger when ``closed_at`` falls in a bucket already considered frozen
    for the ``clinical`` metric class. Side-effect free if the bucket is
    still in the open window.

    TEMPORAL: this helper lives in ``views.py`` because there is no
    ``medical_records/services.py::close_medical_record_service()`` yet
    (ADR p9 violation acknowledged in ADR p17 §Deuda). When that service
    exists, this helper migrates there.
    """
    from apps.analytics.services import is_bucket_frozen
    from apps.core.datetime_utils import org_today_local

    closed_date = org_today_local(organization, now=closed_at)
    if not is_bucket_frozen('clinical', closed_date, organization):
        return
    today = org_today_local(organization)
    age_days = max(0, (today - closed_date).days)
    logging.getLogger('analytics.events').warning(
        'ANCHOR_LATE_ARRIVAL',
        extra={
            'event': 'ANCHOR_LATE_ARRIVAL',
            'anchor_field': 'closed_at',
            'anchor_value_iso': closed_at.isoformat(),
            'bucket_date_local_iso': closed_date.isoformat(),
            'frozen_threshold_days': 2,
            'age_days': age_days,
            'organization_id': organization.pk,
            'writer': 'close_medical_record',
            'metric_class': 'clinical',
        },
    )


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
        from apps.billing.models import InvoiceItem
        from apps.billing.services import (
            apply_invoice_item_quantity_delta,
            get_or_create_invoice_for_medical_record,
        )

        with transaction.atomic():
            mr = resolve_public_id(
                MedicalRecord.objects.for_organization(self.request.user.organization).select_for_update(),
                self.kwargs['medical_record_pk'],
            )
            assert_can_modify_charges(self.request.user, mr, self.request)
            service = serializer.validated_data['service']
            quantity = serializer.validated_data['quantity']
            if service.organization_id != self.request.user.organization_id:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'service': 'Servicio fuera de tu organización'})

            invoice = get_or_create_invoice_for_medical_record(mr)
            if invoice.status == 'draft':
                item = (
                    InvoiceItem.objects
                    .select_for_update()
                    .filter(invoice=invoice, service=service, is_active=True)
                    .first()
                )
                if item is None:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        service=service,
                        description=service.name,
                        quantity=quantity,
                        unit_price=service.base_price,
                        organization=invoice.organization,
                    )
                else:
                    apply_invoice_item_quantity_delta(item, quantity)

            serializer.save(medical_record=mr)


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
            item = None
            if invoice_id:
                locked_invoice = Invoice.objects.for_organization(
                    self.request.user.organization
                ).select_for_update().filter(pk=invoice_id).first()
                if locked_invoice is not None:
                    item = InvoiceItem.objects.select_for_update().filter(
                        invoice=locked_invoice,
                        service=instance.service,
                        is_active=True,
                    ).first()

            fresh_instance = MedicalRecordService.objects.select_for_update().get(
                pk=instance.pk,
                medical_record=mr,
            )

            if item is not None and item.invoice.status == 'draft':
                projected = item.quantity - fresh_instance.quantity
                if projected <= 0:
                    item.delete()
                else:
                    apply_invoice_item_quantity_delta(item, -fresh_instance.quantity)
            fresh_instance.delete()


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

        # Late-arrival observability (ADR p17 Día 5, warn-only).
        # Call lives inside the active transaction so the log only emits
        # if commit succeeds (a rollback unwinds before the helper runs).
        _warn_if_late_closed_at(medical_record.organization, medical_record.closed_at)

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


class VaccineRecordDetailView(TenantQueryMixin, generics.RetrieveUpdateAPIView):
    """PR-4B / ADR p16: DELETE removido por consistencia con la motivación
    NOM-007/NOM-046 que justificó VaccineRecord.pet PROTECT. Permitir borrar
    el registro vacunal directamente contradice "vacuna es documento legal
    retenido 5 años". Para anular un registro creado por error, usar PATCH
    (campo notes / status) — soft-delete real es deuda A5 (Fase 2)."""
    serializer_class = VaccineRecordSerializer
    permission_classes = [HybridPermission]
    resource_name = "vaccinerecord"
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return VaccineRecord.objects.for_organization(
            self.request.user.organization
        ).select_related('pet', 'applied_by', 'medical_record')


_MR_STATUS_LABEL = dict(MedicalRecord.Status.choices)
_MR_TYPE_LABEL = dict(MedicalRecord.ConsultationType.choices)


def _mr_fmt_dt(value):
    if not value:
        return ""
    try:
        return value.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return str(value)


@api_view(['GET'])
@permission_classes([make_permission("medicalrecord.retrieve")])
def medical_record_pdf(request, pk):
    """Genera el resumen clínico del registro como archivo PDF."""
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, LongTable,
    )
    from django.http import HttpResponse
    from apps.core.pdf_utils import safe_pdf_text, safe_filename_segment

    record = resolve_public_id(
        MedicalRecord.objects
            .for_organization(request.user.organization)
            .select_related('pet__owner', 'veterinarian', 'appointment', 'organization')
            .prefetch_related(
                'vital_signs',
                'services_used__service',
                'products_used__presentation__product',
                'prescription__items__product',
            ),
        pk,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Consulta #{record.id}",
    )
    styles = getSampleStyleSheet()
    h_org = ParagraphStyle('h_org', parent=styles['Heading1'], fontSize=16, spaceAfter=4)
    h_title = ParagraphStyle('h_title', parent=styles['Heading2'], fontSize=13, spaceAfter=2)
    h_sub = ParagraphStyle('h_sub', parent=styles['Heading3'], fontSize=11, spaceBefore=10, spaceAfter=4)
    body = styles['BodyText']
    body_sm = ParagraphStyle('body_sm', parent=body, fontSize=9, leading=11)

    flow = []
    flow.append(Paragraph(safe_pdf_text(record.organization.name), h_org))
    flow.append(Paragraph("RESUMEN DE CONSULTA", h_title))
    flow.append(Paragraph(
        f"Estado: <b>{_MR_STATUS_LABEL.get(record.status, record.status)}</b> "
        f"&nbsp;·&nbsp; Tipo: {_MR_TYPE_LABEL.get(record.consultation_type, record.consultation_type)}",
        body_sm,
    ))
    flow.append(Paragraph(f"Fecha: {_mr_fmt_dt(record.created_at)}", body_sm))
    if record.closed_at:
        flow.append(Paragraph(f"Cerrada: {_mr_fmt_dt(record.closed_at)}", body_sm))

    if record.veterinarian_id:
        vet = record.veterinarian
        vet_name = f"{vet.first_name} {vet.last_name}".strip() or vet.username
        spec = f" &nbsp;·&nbsp; {safe_pdf_text(vet.specialty)}" if getattr(vet, 'specialty', '') else ""
        flow.append(Paragraph("Veterinario", h_sub))
        flow.append(Paragraph(f"{safe_pdf_text(vet_name)}{spec}", body))

    flow.append(Paragraph("Paciente", h_sub))
    pet = record.pet
    flow.append(Paragraph(
        f"<b>Nombre:</b> {safe_pdf_text(pet.name)} "
        f"&nbsp; <b>Especie:</b> {safe_pdf_text(pet.species)} "
        f"&nbsp; <b>Raza:</b> {safe_pdf_text(pet.breed or '-')}",
        body,
    ))
    if pet.owner_id:
        flow.append(Paragraph(
            f"<b>Dueño:</b> {safe_pdf_text(pet.owner.name)} "
            f"&nbsp; <b>Teléfono:</b> {safe_pdf_text(pet.owner.phone)}",
            body,
        ))

    if record.appointment_id and getattr(record.appointment, 'reason', ''):
        flow.append(Paragraph("Motivo", h_sub))
        flow.append(Paragraph(safe_pdf_text(record.appointment.reason), body))

    last_vital = None
    for v in record.vital_signs.all():
        if last_vital is None or (v.recorded_at and v.recorded_at > last_vital.recorded_at):
            last_vital = v
    if last_vital:
        parts = []
        if last_vital.weight is not None:
            parts.append(f"<b>Peso:</b> {last_vital.weight} kg")
        if last_vital.temperature is not None:
            parts.append(f"<b>T°:</b> {last_vital.temperature} °C")
        if last_vital.heart_rate is not None:
            parts.append(f"<b>FC:</b> {last_vital.heart_rate} lpm")
        if last_vital.respiratory_rate is not None:
            parts.append(f"<b>FR:</b> {last_vital.respiratory_rate} rpm")
        if parts:
            flow.append(Paragraph("Signos vitales", h_sub))
            flow.append(Paragraph(" &nbsp;·&nbsp; ".join(parts), body))
    elif record.weight is not None:
        flow.append(Paragraph("Signos vitales", h_sub))
        flow.append(Paragraph(f"<b>Peso:</b> {record.weight} kg", body))

    if record.diagnosis:
        flow.append(Paragraph("Diagnóstico", h_sub))
        flow.append(Paragraph(
            safe_pdf_text(record.diagnosis).replace('\n', '<br/>'), body,
        ))

    if record.treatment:
        flow.append(Paragraph("Tratamiento", h_sub))
        flow.append(Paragraph(
            safe_pdf_text(record.treatment).replace('\n', '<br/>'), body,
        ))

    services = list(record.services_used.all())
    if services:
        flow.append(Paragraph("Servicios aplicados", h_sub))
        rows = [["Servicio", "Cantidad"]]
        for s in services:
            rows.append([
                Paragraph(safe_pdf_text(s.service.name if s.service_id else "-"), body_sm),
                f"{s.quantity:g}",
            ])
        t = LongTable(rows, colWidths=[12 * cm, 4.3 * cm], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeee')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ]))
        flow.append(t)

    products = list(record.products_used.all())
    if products:
        flow.append(Paragraph("Productos utilizados", h_sub))
        rows = [["Producto", "Presentación", "Cantidad"]]
        for p in products:
            pres = p.presentation
            prod_name = safe_pdf_text(pres.product.name if pres and pres.product_id else "-")
            pres_name = safe_pdf_text(pres.name if pres else "-")
            rows.append([
                Paragraph(prod_name, body_sm),
                Paragraph(pres_name, body_sm),
                f"{p.quantity:g}",
            ])
        t = LongTable(rows, colWidths=[7.5 * cm, 6 * cm, 2.8 * cm], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeee')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
        ]))
        flow.append(t)

    if record.notes:
        flow.append(Paragraph("Notas", h_sub))
        flow.append(Paragraph(
            safe_pdf_text(record.notes).replace('\n', '<br/>'), body,
        ))

    prescription = getattr(record, 'prescription', None)
    if prescription:
        flow.append(Paragraph("Receta", h_sub))
        for i, item in enumerate(prescription.items.all(), 1):
            first_pres = next(iter(item.product.presentations.all()), None)
            unit = first_pres.get_base_unit_display() if first_pres else ""
            line = (
                f"<b>{i}. {safe_pdf_text(item.product.name)}</b> — "
                f"{item.quantity:g} {safe_pdf_text(unit)}".rstrip()
            )
            flow.append(Paragraph(line, body))
            detail_parts = [f"Dosis: {safe_pdf_text(item.dose)}"]
            if item.duration:
                detail_parts.append(f"Duración: {safe_pdf_text(item.duration)}")
            if item.instructions:
                detail_parts.append(f"Instrucciones: {safe_pdf_text(item.instructions)}")
            flow.append(Paragraph(" &nbsp;·&nbsp; ".join(detail_parts), body_sm))
        if prescription.notes:
            flow.append(Paragraph(
                f"<i>Notas de receta:</i> {safe_pdf_text(prescription.notes)}",
                body_sm,
            ))

    doc.build(flow)
    buffer.seek(0)

    pet_segment = safe_filename_segment(pet.name)
    filename = f"consulta_{record.id}_{pet_segment}.pdf"
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
