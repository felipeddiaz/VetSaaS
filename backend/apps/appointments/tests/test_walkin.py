"""
Walk-in endpoint tests — RBAC validation + sanitization
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.users.models import User


def _seed_org_roles(org):
    """Crea Permission + Roles para una org."""
    wildcard, _ = Permission.objects.get_or_create(code="*.*")
    perms_map = {}
    for code in PERMISSION_CODES:
        p, _ = Permission.objects.get_or_create(code=code)
        perms_map[code] = p

    roles = {}
    for role_name, perm_codes in PERMISSIONS.items():
        if role_name == "ADMIN_SAAS":
            continue
        role, _ = Role.objects.get_or_create(
            name=role_name,
            organization=org,
            defaults={"is_system_role": True},
        )
        if "*.*" in perm_codes:
            role.permissions.set([wildcard])
        else:
            role.permissions.set([perms_map[c] for c in perm_codes if c in perms_map])
        roles[role_name] = role
    return roles


def _make_user(username, org, role):
    return User.objects.create_user(
        username=username,
        password="testpass!",
        organization=org,
        role=role,
    )


def _assign_role(user, role):
    UserRole.objects.get_or_create(user=user, role=role)


def _create_role_with_permission(username, org, perm_code):
    """Create user with a specific permission via custom role."""
    user = _make_user(username, org, "VET")
    
    perm, _ = Permission.objects.get_or_create(code=perm_code)
    role = Role.objects.create(
        name=f"CustomRole_{username}",
        organization=org,
        is_system_role=False,
    )
    role.permissions.add(perm)
    UserRole.objects.create(user=user, role=role)
    
    return user


class WalkInRBACTests(APITestCase):
    """Tests for walk_in endpoint RBAC validation."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Clínica Test", timezone="UTC")
        cls.roles = _seed_org_roles(cls.org)

        cls.admin = _make_user("admin_test", cls.org, "ADMIN")
        # Use canonical permission code 'appointment.create_walkin'
        cls.vet_with_perm = _create_role_with_permission("vet_with_perm", cls.org, "appointment.create_walkin")
        cls.vet_without_perm = _make_user("vet_no_perm", cls.org, "VET")

        _assign_role(cls.admin, cls.roles["ADMIN"])
        _assign_role(cls.vet_with_perm, cls.roles["VET"])
        _assign_role(cls.vet_without_perm, cls.roles["VET"])

        cls.owner = Owner.objects.create(
            name="Propietario Test",
            phone="1234567890",
            organization=cls.org,
        )
        cls.pet = Pet.objects.create(
            name="Buddy",
            species="dog",
            owner=cls.owner,
            organization=cls.org,
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_walkin_vet_without_permission_returns_403(self):
        """Veterinarian without appointments.create_walkin permission should get 403."""
        self.auth(self.admin)
        
        response = self.client.post("/api/appointments/walkin/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_without_perm.id,
            "reason": "Consulta de emergencia",
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # DRF PermissionDenied returns detail string
        self.assertIn("permiso", str(response.data.get("detail", "")).lower())

    def test_walkin_vet_with_permission_succeeds(self):
        """Veterinarian with appointments.create_walkin permission should succeed."""
        self.auth(self.admin)
        
        response = self.client.post("/api/appointments/walkin/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "Consulta de emergencia",
        })
        
        # May return 201 or 200 (existing appointment)
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

    def test_walkin_reason_sanitized(self):
        """Reason field should be sanitized (XSS removed)."""
        self.auth(self.admin)
        
        response = self.client.post("/api/appointments/walkin/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "<script>alert(1)</script>Motivo válido",
        })
        
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        if response.status_code == status.HTTP_201_CREATED:
            self.assertNotIn("<script>", response.data["reason"])

    def test_walkin_notes_sanitized(self):
        """Notes field should be sanitized."""
        self.auth(self.admin)
        
        response = self.client.post("/api/appointments/walkin/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "Motivo válido",
            "notes": "<img src=x onerror=alert(1)>Nota maliciosa",
        })
        
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        if response.status_code == status.HTTP_201_CREATED:
            self.assertNotIn("<img", response.data.get("notes", ""))

    def test_walkin_empty_reason_returns_400(self):
        """Empty reason after sanitization should return 400."""
        self.auth(self.admin)
        
        response = self.client.post("/api/appointments/walkin/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "   ",
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)

    def test_walkin_without_pet_toggle_off_returns_400(self):
        """When allow_anonymous_walkin is OFF and pet is omitted, return 400."""
        self.auth(self.admin)
        # Ensure toggle is off (default), but be explicit
        from apps.organizations.models import OrganizationSettings
        OrganizationSettings.objects.filter(organization=self.org).delete()
        OrganizationSettings.objects.create(organization=self.org, allow_anonymous_walkin=False)

        response = self.client.post("/api/appointments/walkin/", {
            "veterinarian": self.vet_with_perm.id,
            "reason": "Consulta sin mascota",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_walkin_without_pet_toggle_on_uses_generic(self):
        """When allow_anonymous_walkin is ON and pet omitted, system assigns generic patient."""
        self.auth(self.admin)
        from apps.organizations.models import OrganizationSettings
        OrganizationSettings.objects.filter(organization=self.org).delete()
        OrganizationSettings.objects.create(organization=self.org, allow_anonymous_walkin=True)

        response = self.client.post("/api/appointments/walkin/", {
            "veterinarian": self.vet_with_perm.id,
            "reason": "Consulta anonima",
        })
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        if response.status_code == status.HTTP_201_CREATED:
            pet_id = response.data.get("pet")
            from apps.patients.models import Pet
            pet = Pet.objects.get(pk=pet_id)
            self.assertTrue(pet.is_generic)

    def test_walkin_reason_truncation(self):
        """Long reason values are truncated to 255 and saved without error."""
        self.auth(self.admin)
        long_reason = "a" * 300
        response = self.client.post("/api/appointments/walkin/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": long_reason,
        })
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        if response.status_code == status.HTTP_201_CREATED:
            self.assertLessEqual(len(response.data.get("reason", "")), 255)
