from django.db import models
from apps.core.models import OrganizationalModel


class Prescription(OrganizationalModel):
    medical_record = models.OneToOneField(
        'medical_records.MedicalRecord',
        on_delete=models.CASCADE,
        related_name='prescription'
    )
    veterinarian = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prescriptions'
    )
    pet = models.ForeignKey(
        'patients.Pet',
        on_delete=models.CASCADE,
        related_name='prescriptions'
    )
    notes = models.TextField(blank=True)
    # created_at, updated_at heredados de OrganizationalModel

    class Meta:
        ordering = ['-created_at']


class PrescriptionItem(OrganizationalModel):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='prescription_items'
    )
    dose = models.CharField(max_length=255)
    duration = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    instructions = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        # Hereda organization de la prescripción — sin query extra
        if self.prescription_id and not self.organization_id:
            self.organization_id = self.prescription.organization_id
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="prescriptionitem_quantity_positive",
            ),
        ]
