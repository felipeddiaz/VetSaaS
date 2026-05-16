"""
Walk-in endpoint tests — RBAC validation + sanitization
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Permission, Role, UserRole
from apps.core.permissions_codes import PERMISSION_CODES, PERMISSIONS
from apps.appointments.models import Appointment
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
        # Ensure admin gets its role
        _assign_role(cls.admin, cls.roles["ADMIN"])
        # Assign a standard VET role to the vet_with_perm so it keeps default perms
        _assign_role(cls.vet_with_perm, cls.roles["VET"])
        # For vet_without_perm create a DB role WITHOUT permissions and assign it -> this forces
        # DB-backed empty permission set (HybridPermission will use DB perms and deny)
        # Remove any auto-assigned system UserRole created by signals during user creation
        UserRole.objects.filter(user=cls.vet_without_perm).delete()
        no_perm_role = Role.objects.create(name="NoPermRole", organization=cls.org, is_system_role=False)
        UserRole.objects.create(user=cls.vet_without_perm, role=no_perm_role)
        # Clear any cached permissions that might have been populated earlier
        if hasattr(cls.vet_without_perm, '_cached_permissions'):
            delattr(cls.vet_without_perm, '_cached_permissions')

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
        cls.pet_b = Pet.objects.create(
            name="Michi",
            species="cat",
            owner=cls.owner,
            organization=cls.org,
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_walkin_vet_without_permission_returns_403(self):
        """Veterinarian without appointments.create_walkin permission should get 403."""
        self.auth(self.admin)
        # Create an isolated vet user for this assertion to avoid cross-test signals/cache
        from apps.core.models import Role, UserRole
        from apps.core.permissions import user_has_permission
        temp_vet = _make_user("temp_vet_no_perm", self.org, "VET")
        # Remove any auto-assigned roles and assign an explicit no-perm role
        UserRole.objects.filter(user=temp_vet).delete()
        no_perm_role = Role.objects.create(name="TempNoPerm", organization=self.org, is_system_role=False)
        UserRole.objects.create(user=temp_vet, role=no_perm_role)

        # Ensure helper reports no permission before calling endpoint
        self.assertFalse(user_has_permission(temp_vet, 'appointment.create_walkin'))

        response = self.client.post("/api/appointments/walk-in/", {
            "pet": self.pet.id,
            "veterinarian": temp_vet.id,
            "reason": "Consulta de emergencia",
        })

        # Expect 403 when the assigned veterinarian lacks the DB-backed walk-in permission
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            msg=f"Expected 403 when vet lacks permission, got {response.status_code}: {response.data}",
        )

    def test_walkin_vet_with_permission_succeeds(self):
        """Veterinarian with appointments.create_walkin permission should succeed."""
        self.auth(self.admin)
        
        response = self.client.post("/api/appointments/walk-in/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "Consulta de emergencia",
        })
        
        # May return 201 or 200 (existing appointment)
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

    def test_walkin_reason_sanitized(self):
        """Reason field should be sanitized (XSS removed)."""
        self.auth(self.admin)
        
        response = self.client.post("/api/appointments/walk-in/", {
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
        
        response = self.client.post("/api/appointments/walk-in/", {
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
        
        response = self.client.post("/api/appointments/walk-in/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "   ",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.data or {}
        # API may wrap validation errors under {'code':..., 'errors': {...}}
        if isinstance(data, dict) and 'errors' in data:
            self.assertIn('reason', data['errors'])
        else:
            self.assertIn('reason', data)

    def test_walkin_without_pet_toggle_off_returns_400(self):
        """When allow_anonymous_walkin is OFF and pet is omitted, return 400."""
        self.auth(self.admin)
        # Ensure toggle is off (default), but be explicit
        from apps.organizations.models import OrganizationSettings
        OrganizationSettings.objects.filter(organization=self.org).delete()
        OrganizationSettings.objects.create(organization=self.org, allow_anonymous_walkin=False)

        response = self.client.post("/api/appointments/walk-in/", {
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

        response = self.client.post("/api/appointments/walk-in/", {
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
        response = self.client.post("/api/appointments/walk-in/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": long_reason,
        })
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        if response.status_code == status.HTTP_201_CREATED:
            self.assertLessEqual(len(response.data.get("reason", "")), 255)

    def test_walkin_dedup_does_not_reuse_different_pet(self):
        self.auth(self.admin)

        first = self.client.post("/api/appointments/walk-in/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "Walkin uno",
        })
        second = self.client.post("/api/appointments/walk-in/", {
            "pet": self.pet_b.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "Walkin dos",
        })

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(first.data["id"], second.data["id"])

    def test_walkin_dedup_does_not_reuse_non_walkin_appointment(self):
        self.auth(self.admin)
        Appointment.objects.create(
            organization=self.org,
            pet=self.pet,
            veterinarian=self.vet_with_perm,
            date="2026-01-01",
            start_time="10:00:00",
            end_time="10:30:00",
            start_datetime="2026-01-01T10:00:00Z",
            end_datetime="2026-01-01T10:30:00Z",
            timezone_at_creation="UTC",
            reason="Cita regular",
            status='in_progress',
            walk_in=False,
            created_by=self.admin,
        )

        response = self.client.post("/api/appointments/walk-in/", {
            "pet": self.pet.id,
            "veterinarian": self.vet_with_perm.id,
            "reason": "Walkin real",
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Appointment.objects.get(pk=response.data["id"]).walk_in)
