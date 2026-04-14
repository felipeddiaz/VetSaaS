from django.core.management.base import BaseCommand
from apps.users.models import User
from apps.organizations.models import Organization

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        if User.objects.filter(email="admin@test.com").exists():
            self.stdout.write("Admin ya existe")
            return

        org = Organization.objects.create(name="Mi Clínica")

        User.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="123456",
            first_name="Admin",
            last_name="Principal",
            organization=org,
            role="ADMIN"
        )

        self.stdout.write("Admin creado correctamente")