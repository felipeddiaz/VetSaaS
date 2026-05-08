from django.db import IntegrityError, transaction
from .models import Owner, Pet


def get_or_create_generic_patient(organization):
    """
    Crea Owner y Pet genéricos si no existen.
    Maneja race conditions via UniqueConstraint + retry defensivo.
    Returns (owner, pet).
    """
    try:
        with transaction.atomic():
            owner, _ = Owner.objects.get_or_create(
                organization=organization,
                is_generic=True,
                defaults={
                    'name': 'Propietario Genérico',
                    'phone': '0000000000',
                }
            )

            pet, _ = Pet.objects.get_or_create(
                organization=organization,
                is_generic=True,
                defaults={
                    'name': 'Paciente Genérico',
                    'owner': owner,
                    'species': 'otro',
                }
            )

            return owner, pet
    except IntegrityError:
        # Constraint violated en Owner o Pet — re-fetch ambos
        owner = Owner.objects.filter(
            organization=organization,
            is_generic=True,
        ).first()

        if not owner:
            raise RuntimeError("Generic owner missing after IntegrityError retry")

        pet = Pet.objects.filter(
            organization=organization,
            is_generic=True,
        ).first()

        if not pet:
            raise RuntimeError("Generic pet missing after IntegrityError retry")

        return owner, pet
