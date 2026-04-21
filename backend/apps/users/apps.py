from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_create_default_superuser, sender=self)


def _create_default_superuser(sender, **kwargs):
    from django.contrib.auth import get_user_model
    from apps.organizations.models import Organization
    import os

    username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

    if not username or not password:
        return

    User = get_user_model()
    org, _ = Organization.objects.get_or_create(name='VetCare Internal')

    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            'is_superuser': True,
            'is_staff': True,
        }
    )

    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True

    if getattr(user, 'organization', None) is None:
        user.organization = org
        user.role = 'ADMIN_SAAS'

    user.save()
