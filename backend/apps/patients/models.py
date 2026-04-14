from django.db import models
from apps.core.models import OrganizationalModel

class Owner(OrganizationalModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)


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

    owner = models.ForeignKey(
        Owner,
        on_delete=models.CASCADE,
        related_name="pets"
    )