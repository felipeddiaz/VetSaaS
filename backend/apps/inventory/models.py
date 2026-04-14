from django.db import models
from apps.core.models import OrganizationalModel


class Product(OrganizationalModel):
    CATEGORY_CHOICES = [
        ('medication', 'Medicamento'),
        ('food', 'Alimento'),
        ('accessory', 'Accesorio'),
        ('other', 'Otro'),
    ]

    name = models.CharField(max_length=255)
    internal_code = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    requires_prescription = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        unique_together = [['organization', 'internal_code']]


class Presentation(OrganizationalModel):
    UNIT_CHOICES = [
        ('tablet', 'Tableta'),
        ('capsule', 'Cápsula'),
        ('ml', 'ml'),
        ('vial', 'Vial'),
        ('ampoule', 'Ampolleta'),
        ('piece', 'Pieza'),
        ('bag', 'Bolsa'),
        ('bottle', 'Frasco'),
        ('tube', 'Tubo'),
        ('kg', 'kg'),
        ('g', 'g'),
        ('unit', 'Unidad'),
    ]

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='presentation',
    )
    name = models.CharField(max_length=255)
    base_unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    # quantity: cantidad por unidad de esta presentación (default 1).
    # Existe para escalar a Fase 3 (múltiples presentaciones con conversión).
    # En Fase 1 no se usa en lógica — siempre vale 1.
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def is_low_stock(self):
        return self.stock <= self.min_stock

    def __str__(self):
        return f"{self.product.name} — {self.name}"

    class Meta:
        ordering = ['product__name']


class StockMovement(OrganizationalModel):
    MOVEMENT_TYPES = [
        ('in', 'Entrada'),
        ('out', 'Salida'),
        ('adjustment', 'Ajuste'),
    ]

    presentation = models.ForeignKey(
        Presentation,
        on_delete=models.CASCADE,
        related_name='movements',
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    medical_record = models.ForeignKey(
        'medical_records.MedicalRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    invoice = models.ForeignKey(
        'billing.Invoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class MedicalRecordProduct(models.Model):
    """
    Productos consumidos durante una consulta médica.
    El stock se ajusta automáticamente via save() y delete().
    """
    medical_record = models.ForeignKey(
        'medical_records.MedicalRecord',
        on_delete=models.CASCADE,
        related_name='products_used',
    )
    presentation = models.ForeignKey(
        Presentation,
        on_delete=models.PROTECT,
        related_name='medical_record_usages',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = [['medical_record', 'presentation']]

    def save(self, *args, **kwargs):
        from .services import apply_stock_movement
        if self.pk:
            old = MedicalRecordProduct.objects.get(pk=self.pk)
            diff = self.quantity - old.quantity
            if diff != 0:
                apply_stock_movement(
                    presentation=self.presentation,
                    quantity=abs(diff),
                    movement_type='out' if diff > 0 else 'in',
                    organization=self.medical_record.organization,
                    reason='Ajuste por edición de consulta médica',
                    medical_record=self.medical_record,
                )
        else:
            apply_stock_movement(
                presentation=self.presentation,
                quantity=self.quantity,
                movement_type='out',
                organization=self.medical_record.organization,
                reason='Consumido en consulta médica',
                medical_record=self.medical_record,
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from .services import apply_stock_movement
        apply_stock_movement(
            presentation=self.presentation,
            quantity=self.quantity,
            movement_type='in',
            organization=self.medical_record.organization,
            reason='Reversión por eliminación de producto en consulta',
            medical_record=self.medical_record,
        )
        super().delete(*args, **kwargs)
