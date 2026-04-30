import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='organizations.Organization')
def initialize_organization(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .models import OrganizationSettings
        OrganizationSettings.objects.get_or_create(organization=instance)

        from apps.patients.models import Owner, Pet
        generic_owner, _ = Owner.objects.get_or_create(
            organization=instance,
            is_generic=True,
            defaults={'name': 'Público General', 'phone': ''},
        )
        Pet.objects.get_or_create(
            owner=generic_owner,
            is_generic=True,
            defaults={
                'name': 'Paciente Anónimo',
                'species': 'otro',
                'organization': instance,
            }
        )
    except Exception as e:
        logger.error("Error inicializando organización %s: %s", instance.pk, e)
        # No re-raise: la org debe quedar creada aunque el setup auxiliar falle
