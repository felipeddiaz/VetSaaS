from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.appointments.models import Appointment
from apps.inventory.models import MedicalRecordProduct, Presentation, StockMovement
from apps.medical_records.models import MedicalRecord

SUMMARY_CACHE_PREFIX = 'dash:summary'
SERIES_CACHE_PREFIX = 'dash:series'


def _invalidate_org_dashboard(org_id):
    cache.delete(f'{SUMMARY_CACHE_PREFIX}:{org_id}')
    try:
        cache.delete_pattern(f'{SERIES_CACHE_PREFIX}:{org_id}:*')
    except AttributeError:
        pass


@receiver(post_save, sender=Appointment)
@receiver(post_delete, sender=Appointment)
def invalidate_on_appointment_change(sender, instance, **kwargs):
    if instance.organization_id:
        _invalidate_org_dashboard(instance.organization_id)


@receiver(post_save, sender=MedicalRecord)
def invalidate_on_medical_record_change(sender, instance, **kwargs):
    if instance.organization_id:
        _invalidate_org_dashboard(instance.organization_id)


@receiver(post_save, sender=Presentation)
@receiver(post_save, sender=StockMovement)
@receiver(post_save, sender=MedicalRecordProduct)
def invalidate_on_stock_change(sender, instance, **kwargs):
    org_id = getattr(instance, 'organization_id', None)
    if org_id:
        _invalidate_org_dashboard(org_id)


@receiver(post_delete, sender=MedicalRecordProduct)
def invalidate_on_mr_product_deleted(sender, instance, **kwargs):
    org_id = getattr(instance, 'organization_id', None)
    if org_id:
        _invalidate_org_dashboard(org_id)
