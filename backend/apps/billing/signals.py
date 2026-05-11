from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.organizations.utils import get_org_setting, SETTING_AUTO_INVOICE_ON_DONE
from apps.medical_records.models import MedicalRecord


@receiver(post_save, sender='appointments.Appointment')
def create_draft_invoice_on_done(sender, instance, **kwargs):
    """
    Al marcar cita como done, crea factura draft vinculada a cita y consulta.

    Maneja race conditions via IntegrityError catch (dos procesos concurrentes).
    Si la invoice ya existía sin medical_record, la linkea correctamente.
    """
    if instance.status != 'done':
        return
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'status' not in update_fields:
        # Edits que no tocan el estado (notes, etc.) no deben re-disparar la
        # creación de factura. La invoice ya existe si la transición a done
        # ocurrió antes; el get_or_create igual sería seguro pero genera ruido.
        return
    if not get_org_setting(instance.organization, SETTING_AUTO_INVOICE_ON_DONE):
        return

    from .models import Invoice

    medical_record = (
        MedicalRecord.objects
        .filter(appointment=instance)
        .order_by('-created_at')
        .first()
    )

    defaults = {
        'owner': instance.pet.owner,
        'pet': instance.pet,
        'organization': instance.organization,
        'status': 'draft',
        'invoice_type': 'consultation',
        'medical_record': medical_record,
    }

    try:
        invoice, created = Invoice.objects.get_or_create(
            appointment=instance,
            defaults=defaults,
        )
    except IntegrityError:
        # Race condition: dos procesos concurrentes → re-fetch
        invoice = Invoice.objects.get(appointment=instance)
        created = False

    # Si la invoice ya existía (otra race) pero no tiene medical_record, linkearla
    if not created and invoice.medical_record_id is None and medical_record:
        invoice.medical_record = medical_record
        invoice.save(update_fields=['medical_record'])
