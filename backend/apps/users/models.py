from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.organizations.models import Organization


class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN_SAAS', 'Admin SaaS'),
        ('ADMIN', 'Administrador'),
        ('VET', 'Veterinario'),
        ('ASSISTANT', 'Asistente'),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='ASSISTANT')
    specialty = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta(AbstractUser.Meta):
        indexes = [
            models.Index(fields=["organization", "role", "is_active"]),
        ]
