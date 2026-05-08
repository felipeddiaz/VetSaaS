from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.users.models import User
from apps.organizations.models import Organization

class InvoiceTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(
            username="test",
            password="123456",
            organization=self.org
        )
        self.client.force_authenticate(user=self.user)

    def test_invoice_not_found_returns_spanish(self):
        url = "/api/billing/invoices/999999/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "not_found")
        self.assertIn("no existe", response.data["message"].lower())