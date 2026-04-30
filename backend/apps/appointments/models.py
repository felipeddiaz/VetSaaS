from django.core.exceptions import ValidationError
from django.db import models
from apps.patients.models import Pet
from apps.users.models import User
from apps.core.models import OrganizationalModel


class Appointment(OrganizationalModel):
    STATUS_CHOICES = (
        ('scheduled', 'Programada'),
        ('confirmed', 'Confirmada'),
        ('in_progress', 'En consulta'),
        ('done', 'Completada'),
        ('canceled', 'Cancelada'),
        ('no_show', 'No se presentó'),
    )

    pet = models.ForeignKey("patients.Pet", on_delete=models.PROTECT)
    veterinarian = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True)

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    start_datetime = models.DateTimeField(null=True, blank=True, db_index=True)
    end_datetime = models.DateTimeField(null=True, blank=True, db_index=True)
    timezone_at_creation = models.CharField(max_length=64, default='UTC')

    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")

    def clean(self):
        org = self.organization_id
        if org and self.pet_id and self.pet.organization_id != org:
            raise ValidationError("La mascota no pertenece a la misma organizacion que la cita.")
        if org and self.veterinarian_id and self.veterinarian.organization_id != org:
            raise ValidationError("El veterinario no pertenece a la misma organizacion que la cita.")

    @property
    def medical_record_ids(self):
        return list(self.medical_record.order_by('id').values_list('id', flat=True))

    @property
    def invoice_id(self):
        try:
            return self.invoice.id
        except Exception:
            return None

    class Meta:
        ordering = ["date", "start_time"]
        indexes = [
            models.Index(fields=["organization", "date", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F('start_time')),
                name="appointment_end_after_start",
            ),
        ]


class AppointmentStatusChange(OrganizationalModel):
    appointment = models.ForeignKey(
        Appointment, on_delete=models.CASCADE, related_name='status_changes'
    )
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointment_status_changes',
    )
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
