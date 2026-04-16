from django.core.exceptions import ValidationError
from django.db import models
from apps.patients.models import Pet
from apps.users.models import User
from apps.core.models import OrganizationalModel


class MedicalRecord(OrganizationalModel):
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name='medical_records')
    veterinarian = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='medical_records', null=True, blank=True)
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name='medical_record')

    diagnosis = models.TextField()
    treatment = models.TextField()
    notes = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # created_at, updated_at heredados de OrganizationalModel

    def clean(self):
        org = self.organization_id
        if org and self.pet_id and self.pet.organization_id != org:
            raise ValidationError("La mascota no pertenece a la misma organizacion que el registro medico.")
        if org and self.veterinarian_id and self.veterinarian.organization_id != org:
            raise ValidationError("El veterinario no pertenece a la misma organizacion que el registro medico.")
        if org and self.appointment_id and self.appointment.organization_id != org:
            raise ValidationError("La cita no pertenece a la misma organizacion que el registro medico.")

    @property
    def prescription_id(self):
        try:
            return self.prescription.id
        except Exception:
            return None

    @property
    def invoice_id(self):
        # Factura directa vinculada al registro (walk-in o venta con consulta)
        direct = self.invoices.order_by('id').values_list('id', flat=True).first()
        if direct:
            return direct
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
        ]
