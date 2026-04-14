from django.db.models.signals import post_save
from django.dispatch import receiver


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
