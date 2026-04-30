from django.core.exceptions import ValidationError
from django.db import models
from apps.core.models import OrganizationalModel

SPECIES_CHOICES = ['canino', 'felino', 'equino', 'ave', 'reptil', 'exótico', 'otro']


class Owner(OrganizationalModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    is_generic = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['organization'],
                condition=models.Q(is_generic=True),
                name='unique_generic_owner_per_organization',
            )
        ]


class Pet(OrganizationalModel):
    SEX_CHOICES = (
        ('male', 'Macho'),
        ('female', 'Hembra'),
        ('unknown', 'Desconocido'),
    )

    name = models.CharField(max_length=255)
    species = models.CharField(max_length=100)
    breed = models.CharField(max_length=100, blank=True, default='')
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=SEX_CHOICES, default='unknown')
    color = models.CharField(max_length=100, blank=True, default='')

    is_generic = models.BooleanField(default=False)

    owner = models.ForeignKey(
        Owner,
        on_delete=models.CASCADE,
        related_name="pets"
    )

    def clean(self):
        if self.owner_id and self.organization_id:
            if self.owner.organization_id != self.organization_id:
                raise ValidationError("El propietario no pertenece a la misma organizacion que la mascota.")

    class Meta:
        indexes = [
            models.Index(fields=["organization", "owner"]),
        ]