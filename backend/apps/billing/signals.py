from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='medical_records.MedicalRecord')
def create_draft_invoice_on_medical_record(sender, instance, created, **kwargs):
    """
    Al crear una consulta sin cita asociada, genera automáticamente una Invoice draft.
    Si hay appointment, la signal de appointment ya se encarga de crear la invoice.
    """
    if not created:
        return
    if instance.appointment_id:
        return
    from apps.billing.services import get_or_create_invoice_for_medical_record
    get_or_create_invoice_for_medical_record(instance)


@receiver(post_save, sender='appointments.Appointment')
def create_draft_invoice_on_done(sender, instance, **kwargs):
    """
    When an appointment is marked as done, automatically create a draft invoice.
    Uses get_or_create to guarantee idempotency (runs safely on every save).
    """
    if instance.status != 'done':
        return

    from .models import Invoice
    Invoice.objects.get_or_create(
        appointment=instance,
        defaults={
            'owner': instance.pet.owner,
            'pet': instance.pet,
            'organization': instance.organization,
            'status': 'draft',
        }
    )
