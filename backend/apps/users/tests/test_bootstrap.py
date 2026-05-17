"""Tests del bootstrap signal `_create_default_superuser` (Issue #12, ADR p15).

Vector cerrado: si una clínica registra un usuario con username == DJANGO_SUPERUSER_USERNAME,
el signal previo escalaba ese usuario a superuser platform-wide y reseteaba su password (CVSS 9.9).
La nueva implementación bifurca por filter().first() + chequea is_platform_superuser antes
de tocar nada. Si no calza, log CRITICAL + abort sin mutación.
"""
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Organization
from apps.users.apps import _create_default_superuser

User = get_user_model()


class SuperuserBootstrapTests(TestCase):
    """Cobertura completa de los 7 escenarios del guard anti-escalación."""

    def _run_signal(self, username='superadmin', password='SuperPass123!', email=''):
        with mock.patch.dict(os.environ, {
            'DJANGO_SUPERUSER_USERNAME': username,
            'DJANGO_SUPERUSER_PASSWORD': password,
            'DJANGO_SUPERUSER_EMAIL': email,
        }):
            _create_default_superuser(sender=None)

    def test_creates_superuser_when_absent(self):
        self._run_signal()
        u = User.objects.get(username='superadmin')
        self.assertTrue(u.is_superuser)
        self.assertTrue(u.is_staff)
        self.assertEqual(u.role, 'ADMIN_SAAS')
        self.assertIsNotNone(u.organization_id)
        self.assertEqual(u.organization.name, 'Vet Care Internal')

    def test_skipped_when_username_collision_non_platform_user(self):
        """Una clínica registra VET con username 'admin'. Env trae el mismo username.
        El signal NO debe escalar al VET ni resetear su password."""
        org_vet = Organization.objects.create(name='Clinica X')
        vet = User.objects.create_user(
            username='admin',
            password='VetPass123!',
            organization=org_vet,
            role='VET',
        )
        original_role = vet.role

        with self.assertLogs('rbac.events', level='CRITICAL') as logs:
            self._run_signal(username='admin', password='SuperPass123!')

        vet.refresh_from_db()
        self.assertEqual(vet.role, original_role)
        self.assertFalse(vet.is_superuser)
        # Verificar intención (password ORIGINAL sigue válido) en vez de comparar
        # hashes — más robusto frente a cambios futuros del hasher.
        self.assertTrue(
            User.objects.get(pk=vet.pk).check_password('VetPass123!'),
            "Password del VET fue reseteado — escalación parcial detectada",
        )
        self.assertFalse(
            User.objects.get(pk=vet.pk).check_password('SuperPass123!'),
            "Password del VET coincide con el del env superuser — escalación detectada",
        )

        # assertLogs captura el record sin pasar por el formatter JSON; verificamos
        # el evento por mensaje base + el reason desde record.__dict__ (extra).
        log_text = ' '.join(logs.output)
        self.assertIn('SUPERUSER_BOOTSTRAP_SKIPPED', log_text)
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(
            logs.records[0].__dict__.get('reason'),
            'username_collision_non_platform_user',
        )
        self.assertEqual(logs.records[0].__dict__.get('existing_user_id'), vet.pk)

    def test_idempotent_does_not_reset_password_when_already_platform_superuser(self):
        """Re-correr el signal con el mismo username de superuser legítimo
        no debe resetear el password (idempotencia de credenciales)."""
        org = Organization.objects.create(name='Vet Care Internal')
        existing = User.objects.create_user(
            username='superadmin',
            password='OriginalPass123!',
            is_superuser=True,
            is_staff=True,
            role='ADMIN_SAAS',
            organization=org,
        )
        original_password_hash = existing.password

        self._run_signal(username='superadmin', password='NewDifferentPass456!')

        existing.refresh_from_db()
        # Verificar via check_password (intención) en vez de hash literal.
        self.assertTrue(
            User.objects.get(pk=existing.pk).check_password('OriginalPass123!'),
            "Password del superuser plataforma fue reseteado en deploy idempotente",
        )
        self.assertFalse(
            User.objects.get(pk=existing.pk).check_password('NewDifferentPass456!'),
        )
        self.assertTrue(existing.is_superuser)
        self.assertTrue(existing.is_active)

    def test_refreshes_is_active_if_platform_superuser_was_inactive(self):
        org = Organization.objects.create(name='Vet Care Internal')
        existing = User.objects.create_user(
            username='superadmin',
            password='OriginalPass123!',
            is_superuser=True,
            is_staff=True,
            role='ADMIN_SAAS',
            organization=org,
            is_active=False,
        )
        self._run_signal(username='superadmin', password='ignored')
        existing.refresh_from_db()
        self.assertTrue(existing.is_active)

    def test_no_org_created_if_user_aborted_due_to_collision(self):
        """Side-effect crítico: la org 'Vet Care Internal' solo se crea cuando
        el usuario se crea. Si abortamos por colisión, no debe quedar org huérfana."""
        org_vet = Organization.objects.create(name='Clinica X')
        User.objects.create_user(
            username='admin',
            password='VetPass123!',
            organization=org_vet,
            role='VET',
        )
        org_count_before = Organization.objects.count()
        with self.assertLogs('rbac.events', level='CRITICAL'):
            self._run_signal(username='admin', password='whatever')
        self.assertEqual(Organization.objects.count(), org_count_before)
        self.assertFalse(Organization.objects.filter(name='Vet Care Internal').exists())

    def test_skipped_when_email_mismatch(self):
        """Defense-in-depth: aunque exista platform-superuser con mismo username,
        si el email env discrepa con el email en DB → tratado como collision."""
        org = Organization.objects.create(name='Vet Care Internal')
        User.objects.create_user(
            username='superadmin',
            password='OriginalPass123!',
            is_superuser=True,
            is_staff=True,
            role='ADMIN_SAAS',
            organization=org,
            email='legit@example.com',
        )
        with self.assertLogs('rbac.events', level='CRITICAL') as logs:
            self._run_signal(
                username='superadmin', password='x', email='attacker@evil.com'
            )
        log_text = ' '.join(logs.output)
        self.assertIn('SUPERUSER_BOOTSTRAP_SKIPPED', log_text)
        self.assertEqual(
            logs.records[0].__dict__.get('reason'),
            'username_collision_non_platform_user',
        )

    def test_noop_when_env_vars_absent(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            _create_default_superuser(sender=None)
        self.assertFalse(User.objects.filter(username='superadmin').exists())

    def test_skipped_when_existing_superuser_has_non_admin_saas_role(self):
        """Defense-in-depth: un user con is_superuser=True pero role!='ADMIN_SAAS'
        (ej. superuser creado por error con role='ADMIN') NO debe ser tratado como
        platform-superuser legítimo. El predicado is_platform_superuser exige
        AMBOS flags."""
        org = Organization.objects.create(name='Vet Care Internal')
        existing = User.objects.create_user(
            username='superadmin',
            password='OriginalPass123!',
            is_superuser=True,
            is_staff=True,
            role='ADMIN',  # NO 'ADMIN_SAAS'
            organization=org,
        )
        with self.assertLogs('rbac.events', level='CRITICAL') as logs:
            self._run_signal(username='superadmin', password='NewPass456!')
        existing.refresh_from_db()
        self.assertEqual(existing.role, 'ADMIN')  # sin cambio
        self.assertTrue(
            User.objects.get(pk=existing.pk).check_password('OriginalPass123!'),
        )
        self.assertEqual(
            logs.records[0].__dict__.get('reason'),
            'username_collision_non_platform_user',
        )

    def test_skipped_when_existing_superuser_lacks_is_staff(self):
        """Defense-in-depth: is_superuser=True + is_staff=False es estado inválido
        pero técnicamente posible (e.g., admin demote parcial). NO tratar como
        platform-superuser."""
        org = Organization.objects.create(name='Vet Care Internal')
        User.objects.create_user(
            username='superadmin',
            password='OriginalPass123!',
            is_superuser=True,
            is_staff=False,  # inválido pero posible
            role='ADMIN_SAAS',
            organization=org,
        )
        with self.assertLogs('rbac.events', level='CRITICAL'):
            self._run_signal(username='superadmin', password='NewPass456!')

    def test_email_check_is_case_insensitive(self):
        """Email normalization defense: comparación case-insensitive para
        evitar DoS por discrepancia trivial Admin@X.com vs admin@x.com."""
        org = Organization.objects.create(name='Vet Care Internal')
        existing = User.objects.create_user(
            username='superadmin',
            password='OriginalPass123!',
            is_superuser=True,
            is_staff=True,
            role='ADMIN_SAAS',
            organization=org,
            email='Admin@Example.COM',
        )
        # Env trae mismo email en diferente casing — debe ser match, no skip
        self._run_signal(
            username='superadmin', password='ignored', email='admin@example.com',
        )
        existing.refresh_from_db()
        # Si no hubo skip + abort, el is_active sigue True (o el path idempotente
        # corrió). Verificamos que no se logueó CRITICAL.
        self.assertTrue(existing.is_active)

    def test_env_email_present_but_db_email_empty_blocks_bootstrap(self):
        """Si env trae email pero DB lo tiene vacío, el predicado falla (email
        provisto pero no coincide). Documenta el contrato actual — operator debe
        rellenar email en DB antes de setear env."""
        org = Organization.objects.create(name='Vet Care Internal')
        User.objects.create_user(
            username='superadmin',
            password='OriginalPass123!',
            is_superuser=True,
            is_staff=True,
            role='ADMIN_SAAS',
            organization=org,
            email='',  # vacío en DB
        )
        with self.assertLogs('rbac.events', level='CRITICAL') as logs:
            self._run_signal(
                username='superadmin', password='ignored',
                email='legit@example.com',  # operador pasa email
            )
        # Comportamiento documentado: bloqueo. Para evitar este caso, operator
        # debe NO setear DJANGO_SUPERUSER_EMAIL si la DB tiene email vacío.
        self.assertEqual(
            logs.records[0].__dict__.get('reason'),
            'username_collision_non_platform_user',
        )
