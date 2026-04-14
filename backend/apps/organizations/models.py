from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from zoneinfo import available_timezones

class Organization(models.Model):
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default='UTC')
    timezone_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.timezone not in available_timezones():
            raise ValidationError({'timezone': 'Zona horaria inválida'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationTimezoneAudit(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='timezone_audits',
    )
    old_timezone = models.CharField(max_length=64)
    new_timezone = models.CharField(max_length=64)
    changed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organization_timezone_changes',
    )
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-changed_at']

