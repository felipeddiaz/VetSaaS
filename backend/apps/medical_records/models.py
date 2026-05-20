from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from apps.patients.models import Pet
from apps.users.models import User
from apps.core.models import OrganizationalModel, PublicIdMixin


class MedicalRecord(PublicIdMixin, OrganizationalModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Abierta'
        CLOSED = 'closed', 'Cerrada'

    class ConsultationType(models.TextChoices):
        GENERAL   = 'general',   'General'
        VACCINE   = 'vaccine',   'Vacuna'
        SURGERY   = 'surgery',   'Cirugía'
        EMERGENCY = 'emergency', 'Emergencia'

    pet = models.ForeignKey(Pet, on_delete=models.PROTECT, related_name='medical_records')
    veterinarian = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='medical_records', null=True, blank=True)
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name='medical_record')

    diagnosis = models.TextField(max_length=400, blank=True)
    treatment = models.TextField(max_length=400, blank=True)
    notes = models.TextField(max_length=5000, blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    consultation_type = models.CharField(
        max_length=20,
        choices=ConsultationType.choices,
        default=ConsultationType.GENERAL,
        db_index=True,
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)

    # Analytics anchor (editable=False, solo escrito por close_medical_record view).
    # Ver docs/dashboard-metrics-contract.md §2.7.
    closed_at = models.DateTimeField(null=True, blank=True, editable=False)
    CLOSED_AT_SOURCE_CHOICES = (
        ('service', 'View writer (close_medical_record)'),
        ('fallback', 'Backfilled from updated_at'),
        ('legacy', 'Existed before provenance tracking'),
    )
    closed_at_source = models.CharField(
        max_length=24, choices=CLOSED_AT_SOURCE_CHOICES,
        default='service', editable=False,
    )
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_medical_records')
    # created_at, updated_at heredados de OrganizationalModel

    def clean(self):
        org = self.organization_id
        if org and self.pet_id and self.pet.organization_id != org:
            raise ValidationError("La mascota no pertenece a la misma organizacion que el registro medico.")
        if org and self.veterinarian_id and self.veterinarian.organization_id != org:
            raise ValidationError("El veterinario no pertenece a la misma organizacion que el registro medico.")
        if org and self.appointment_id and self.appointment.organization_id != org:
            raise ValidationError("La cita no pertenece a la misma organizacion que el registro medico.")

    def save(self, *args, **kwargs):
        # Invariante de event-authority: si el registro queda en estado CLOSED,
        # closed_at NO puede ser NULL. Defensa en profundidad sobre el
        # CHECK constraint a nivel DB (migración 0014). Bloquea bypasses
        # tipo `mr.status='closed'; mr.save()` desde shell o código nuevo
        # que no use close_medical_record(). Ver docs/analytics-schema-audit.md §2.5.
        if self.status == self.Status.CLOSED and self.closed_at is None:
            raise ValidationError(
                "MedicalRecord no puede quedar 'closed' sin closed_at. "
                "Usa medical_records/views.py::close_medical_record."
            )
        super().save(*args, **kwargs)

    @property
    def prescription_id(self):
        try:
            return self.prescription.id
        except Exception:
            return None

    @property
    def invoice_id(self):
        # Factura directa vinculada al registro (walk-in o venta con consulta)
        try:
            return self.invoice.id
        except Exception:
            pass
        # Factura via cita
        if self.appointment_id:
            try:
                return self.appointment.invoice.id
            except Exception:
                return None
        return None

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "pet", "-created_at"]),
            # Capa 3 — analytics. Soportan medical_records_closed,
            # appointments_done_without_medical_record (conversion join),
            # medical_records_open* (clinical backlog).
            models.Index(fields=["organization", "status", "-closed_at"],
                         name="idx_mr_org_status_closed_at"),
            models.Index(fields=["organization", "appointment"],
                         name="idx_mr_org_appointment"),
            models.Index(fields=["organization", "status", "-created_at"],
                         name="idx_mr_org_status_created"),
        ]
        constraints = [
            # Event-authority invariant (analytics): si status='closed',
            # closed_at NO puede ser NULL. Bloquea bypasses tipo
            # `mr.status='closed'; mr.save()` desde shell o queryset.update().
            # Ver docs/analytics-schema-audit.md §2.5.
            models.CheckConstraint(
                condition=~models.Q(status='closed') | models.Q(closed_at__isnull=False),
                name="medicalrecord_closed_status_requires_closed_at",
            ),
        ]


class VaccineRecord(OrganizationalModel):
    STATUS_CURRENT = 'current'
    STATUS_OVERDUE = 'overdue'
    STATUS_NO_SCHEDULED = 'no_scheduled'

    pet = models.ForeignKey(Pet, on_delete=models.PROTECT, related_name='vaccine_records')
    vaccine_name = models.CharField(max_length=255)
    application_date = models.DateField()
    next_due_date = models.DateField(null=True, blank=True)
    applied_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='applied_vaccines'
    )
    notes = models.TextField(blank=True)
    medical_record = models.ForeignKey(
        MedicalRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='vaccine_records'
    )

    @property
    def status(self):
        if not self.next_due_date:
            return self.STATUS_NO_SCHEDULED
        from django.utils import timezone
        return self.STATUS_CURRENT if self.next_due_date > timezone.localdate() else self.STATUS_OVERDUE

    class Meta:
        ordering = ['-application_date', '-id']
        indexes = [
            models.Index(fields=['pet', 'vaccine_name']),
            # Capa 3 — analytics. vaccines_applied + vaccines_due_window.
            models.Index(fields=['organization', 'application_date'],
                         name='idx_vacc_org_app_date'),
            models.Index(fields=['organization', 'next_due_date'],
                         name='idx_vacc_org_next_due'),
        ]


class VitalSigns(OrganizationalModel):
    """
    Registro histórico de signos vitales por consulta. Append-only: sin PATCH/DELETE.
    recorded_at representa el momento clínico real, que puede diferir de created_at
    en importaciones o carga tardía de datos.
    """
    medical_record   = models.ForeignKey(
        MedicalRecord, on_delete=models.CASCADE, related_name='vital_signs'
    )
    weight           = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperature      = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    heart_rate       = models.PositiveSmallIntegerField(null=True, blank=True)
    respiratory_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    recorded_by      = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_vitals'
    )
    recorded_at      = models.DateTimeField(default=timezone.now, db_index=True)

    def save(self, *args, **kwargs):
        if not self.organization_id:
            self.organization = self.medical_record.organization
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-recorded_at', '-created_at']
        indexes = [
            models.Index(fields=['medical_record', '-recorded_at', '-created_at']),
            models.Index(fields=['-recorded_at', '-created_at']),
        ]


class MedicalRecordService(OrganizationalModel):
    """
    Servicio clínico aplicado durante una consulta (consulta, vacuna, cirugía, etc.).
    Sincroniza automáticamente con InvoiceItem vía la view — no en el modelo.
    """
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.CASCADE,
        related_name='services_used',
    )
    service = models.ForeignKey(
        'billing.Service',
        on_delete=models.PROTECT,
        related_name='medical_record_usages',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)

    def save(self, *args, **kwargs):
        if self.medical_record_id and not self.organization_id:
            self.organization_id = self.medical_record.organization_id
        super().save(*args, **kwargs)

    class Meta:
        unique_together = [['medical_record', 'service']]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="medicalrecordservice_quantity_positive",
            ),
        ]


# ---------------------------------------------------------------------------
# Helpers de peso — fuente de verdad compartida entre serializers
# ---------------------------------------------------------------------------

def _get_last_weight(pet):
    """
    Historial global del paciente: último peso entre VitalSigns y MedicalRecord.
    Prioriza VitalSigns (más granular). Ordenado por recorded_at (momento clínico).
    """
    last_vital = (
        VitalSigns.objects
        .filter(medical_record__pet=pet, weight__isnull=False)
        .order_by('-recorded_at', '-created_at')
        .first()
    )
    if last_vital:
        return last_vital.weight
    last_mr = (
        MedicalRecord.objects
        .filter(pet=pet, weight__isnull=False)
        .order_by('-created_at')
        .first()
    )
    return last_mr.weight if last_mr else None


def get_current_weight(record):
    """
    Peso a mostrar para una consulta específica (panel lateral).
    Diferente a _get_last_weight, que busca en toda la historia del paciente.
    """
    last_vital = record.vital_signs.order_by('-recorded_at', '-created_at').first()
    if last_vital and last_vital.weight is not None:
        return last_vital.weight
    return record.weight
