"""
Tests para eliminación de mascotas (Pet delete).
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.appointments.models import Appointment
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


def _make_user(username, org, role):
    return User.objects.create_user(
        username=username,
        password="testpass!",
        organization=org,
        role=role,
    )


class PetDeleteTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Clínica Test", timezone="UTC")
        cls.admin = _make_user("admin_test", cls.org, "ADMIN")
        cls.vet = _make_user("vet_test", cls.org, "VET")

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_delete_generic_pet_returns_409(self):
        """Eliminar un paciente genérico devuelve 409."""
        self.auth(self.admin)
        generic_pet = Pet.objects.create(
            name="Paciente Genérico",
            species="otro",
            is_generic=True,
            owner=Owner.objects.create(
                name="Propietario Genérico",
                phone="0000000000",
                organization=self.org,
            ),
            organization=self.org,
        )

        response = self.client.delete(f"/api/pets/{generic_pet.public_id}/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["error"],
            "No se puede eliminar el paciente genérico del sistema.",
        )
        self.assertTrue(Pet.objects.filter(pk=generic_pet.pk).exists())

    def test_delete_pet_with_protected_relations_returns_409(self):
        """Eliminar mascota con citas asociadas devuelve 409 vía ProtectedError handler."""
        self.auth(self.admin)
        owner = Owner.objects.create(
            name="Propietario Test",
            phone="1234567890",
            organization=self.org,
        )
        pet = Pet.objects.create(
            name="Buddy",
            species="canino",
            owner=owner,
            organization=self.org,
        )
        now = timezone.now()
        Appointment.objects.create(
            organization=self.org,
            pet=pet,
            veterinarian=self.vet,
            date=now.date(),
            start_time=now.time(),
            end_time=(now + timezone.timedelta(minutes=30)).time(),
            start_datetime=now,
            end_datetime=now + timezone.timedelta(minutes=30),
            reason="Consulta general",
        )

        response = self.client.delete(f"/api/pets/{pet.public_id}/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "protected_resource")
        self.assertEqual(
            response.data["error"],
            "No se puede eliminar este registro porque tiene información asociada.",
        )
        self.assertTrue(Pet.objects.filter(pk=pet.pk).exists())

    def test_delete_pet_without_relations_returns_204(self):
        """Eliminar mascota sin citas ni facturas devuelve 204."""
        self.auth(self.admin)
        owner = Owner.objects.create(
            name="Propietario Test",
            phone="1234567890",
            organization=self.org,
        )
        pet = Pet.objects.create(
            name="Luna",
            species="felino",
            owner=owner,
            organization=self.org,
        )

        response = self.client.delete(f"/api/pets/{pet.public_id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Pet.objects.filter(pk=pet.pk).exists())
