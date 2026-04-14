from django.db import models

class OrganizationQuerySet(models.QuerySet):
    """QuerySet that filters automatically by the organization of a user."""

    def for_user(self, user):
        """Return only objects belonging to the user's organization.
        If the user is anonymous, returns an empty queryset.
        """
        if user.is_anonymous:
            return self.none()
        return self.filter(organization=user.organization)

class OrganizationManager(models.Manager):
    """Manager that uses OrganizationQuerySet and exposes for_user()."""

    def get_queryset(self):
        return OrganizationQuerySet(self.model, using=self._db)

    def for_user(self, user):
        return self.get_queryset().for_user(user)

class OrganizationalModel(models.Model):
    """Abstract base model that adds an `organization` FK and the custom manager.
    All tenant‑aware models should inherit from this class.
    """
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='%(class)s_set',
    )

    objects = OrganizationManager()

    class Meta:
        abstract = True
