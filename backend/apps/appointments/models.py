from django.db import models
from apps.patients.models import Pet
from apps.users.models import User
from apps.core.models import OrganizationalModel


class Appointment(OrganizationalModel):
    STATUS_CHOICES = (
        ('scheduled', 'Programada'),
        ('canceled', 'Cancelada'),
        ('done', 'Completada'),
    )

    pet = models.ForeignKey("patients.Pet", on_delete=models.CASCADE)
    veterinarian = models.ForeignKey("users.User", on_delete=models.CASCADE)

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    start_datetime = models.DateTimeField(null=True, blank=True, db_index=True)
    end_datetime = models.DateTimeField(null=True, blank=True, db_index=True)
    timezone_at_creation = models.CharField(max_length=64, default='UTC')

    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")

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
