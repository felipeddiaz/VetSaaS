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
        on_delete=models.CASCADE,
        related_name='prescriptions'
    )
    pet = models.ForeignKey(
        'patients.Pet',
        on_delete=models.CASCADE,
        related_name='prescriptions'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class PrescriptionItem(models.Model):
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
