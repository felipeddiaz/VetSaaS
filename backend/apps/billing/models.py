from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from apps.core.models import OrganizationalModel
from apps.billing.money import discount_amount, invoice_totals, line_subtotal, money


class Service(OrganizationalModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    # is_active, created_at, updated_at heredados de OrganizationalModel

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Invoice(OrganizationalModel):
    STATUS_CHOICES = (
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmada'),
        ('paid', 'Pagada'),
        ('cancelled', 'Cancelada'),
    )
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Efectivo'),
        ('card', 'Tarjeta'),
        ('transfer', 'Transferencia'),
        ('other', 'Otro'),
    )
    INVOICE_TYPE_CHOICES = (
        ('consultation', 'Consulta médica'),
        ('direct_sale', 'Venta directa'),
    )

    invoice_type = models.CharField(
        max_length=20,
        choices=INVOICE_TYPE_CHOICES,
        default='consultation',
    )
    medical_record = models.OneToOneField(
        'medical_records.MedicalRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice',
    )
    appointment = models.OneToOneField(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice'
    )
    owner = models.ForeignKey(
        'patients.Owner',
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    pet = models.ForeignKey(
        'patients.Pet',
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices_created'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        null=True,
        blank=True
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    notes = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    # created_at, updated_at heredados de OrganizationalModel

    def clean(self):
        org = self.organization_id
        if org and self.owner_id and self.owner.organization_id != org:
            raise ValidationError("El propietario no pertenece a la misma organizacion que la factura.")
        if org and self.pet_id and self.pet.organization_id != org:
            raise ValidationError("La mascota no pertenece a la misma organizacion que la factura.")
        if org and self.appointment_id and self.appointment.organization_id != org:
            raise ValidationError("La cita no pertenece a la misma organizacion que la factura.")
        if org and self.medical_record_id and self.medical_record.organization_id != org:
            raise ValidationError("El registro medico no pertenece a la misma organizacion que la factura.")

    def recalculate_totals(self):
        # ⚠️ all_objects: bypasses tenant filter — necesario porque este método
        # puede correr desde InvoiceItem.save() cuando el contexto ya fue limpiado
        # (ej. señales post_save). Do NOT replace with objects.
        raw_subtotal = sum(
            item.subtotal
            for item in InvoiceItem.all_objects.filter(invoice=self, is_active=True)
        )
        subtotal, tax_amount, total = invoice_totals(raw_subtotal, self.tax_rate)
        Invoice.all_objects.filter(pk=self.pk).update(
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
        )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["organization", "status", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tax_rate__gte=0) & models.Q(tax_rate__lte=1),
                name="invoice_tax_rate_range",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name="invoice_subtotal_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(total__gte=models.F('subtotal')),
                name="invoice_total_gte_subtotal",
            ),
        ]


class InvoiceItem(OrganizationalModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='items'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_items'
    )
    presentation = models.ForeignKey(
        'inventory.Presentation',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='invoice_items',
    )
    # TODO (v2):
    # Hacer 'presentation' obligatorio a nivel DB (null=False)
    # cuando todos los flujos, seeds y frontend estén completamente migrados.
    DISCOUNT_TYPE_CHOICES = (
        ('percentage', 'Porcentaje'),
        ('fixed', 'Monto fijo'),
    )

    discount_type = models.CharField(
        max_length=10,
        choices=DISCOUNT_TYPE_CHOICES,
        null=True,
        blank=True,
    )

    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Monto o porcentaje del descuento. 0 = sin descuento."
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        # Hereda organization del invoice — sin query extra
        if self.invoice_id and not self.organization_id:
            self.organization_id = self.invoice.organization_id

        gross = money(self.quantity * self.unit_price)
        disc = discount_amount(gross, self.discount_type, self.discount_value)
        self.subtotal = line_subtotal(self.quantity, self.unit_price, disc)

        super().save(*args, **kwargs)
        self.invoice.recalculate_totals()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        invoice.recalculate_totals()

    class Meta:
        unique_together = [('invoice', 'presentation')]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="invoiceitem_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0),
                name="invoiceitem_unit_price_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0),
                name="invoiceitem_subtotal_non_negative",
            ),
            # XOR: exactamente uno de service o presentation debe estar presente
            models.CheckConstraint(
                condition=(
                    (Q(service__isnull=False) & Q(presentation__isnull=True)) |
                    (Q(service__isnull=True)  & Q(presentation__isnull=False))
                ),
                name="invoiceitem_exactly_one_source",
            ),
        ]


class InvoiceAuditLog(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='audit_logs')
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
