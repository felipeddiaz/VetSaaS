from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_create_default_superuser, sender=self)
        import apps.users.signals  # noqa: registra post_save en User


def _create_default_superuser(sender, **kwargs):
    """
    Bootstrap del superuser de plataforma desde env vars.

    Guard anti-escalación (Issue #12 / ADR p15):
    - Si el username NO existe en DB → crea un superuser nuevo con role='ADMIN_SAAS'
      dentro de un atomic block; ante IntegrityError por race condition multi-worker,
      re-fetch y reclasifica (rama "existe ya el superuser plataforma").
    - Si el username YA existe Y es el superuser de plataforma legítimo
      (is_superuser=True + is_staff=True + role='ADMIN_SAAS' + email coincide
      case-insensitive cuando se provee) → solo refresca is_active. NO resetea
      password (idempotencia de credenciales).
    - Si el username YA existe pero NO es el superuser de plataforma esperado
      (ej. una clínica registró un VET con ese username) → log CRITICAL y abort
      sin tocar al usuario. Sin esta guard, el signal escalaba cualquier usuario
      existente a superuser platform-wide y le reseteaba el password (CVSS 9.9).
    """
    import logging
    import os
    from django.contrib.auth import get_user_model
    from django.db import IntegrityError, transaction
    from apps.organizations.models import Organization

    logger = logging.getLogger('rbac.events')

    username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')

    if not username or not password:
        if username or password:
            # Solo uno de los dos seteado — config probablemente errónea.
            logger.warning("SUPERUSER_BOOTSTRAP_INCOMPLETE_ENV", extra={
                "event": "SUPERUSER_BOOTSTRAP_INCOMPLETE_ENV",
                "has_username": bool(username),
                "has_password": bool(password),
            })
        return

    User = get_user_model()

    def _is_platform_superuser(user):
        """Predicado canónico — usado tanto en el path de fetch como en el
        post-race re-fetch. Mantener en un único lugar para evitar drift."""
        if not (user.is_superuser and user.is_staff):
            return False
        if getattr(user, 'role', None) != 'ADMIN_SAAS':
            return False
        if email and (user.email or '').lower() != email.lower():
            return False
        return True

    def _handle_existing(user, *, reason_if_blocked):
        if not _is_platform_superuser(user):
            logger.critical("SUPERUSER_BOOTSTRAP_SKIPPED", extra={
                "event": "SUPERUSER_BOOTSTRAP_SKIPPED",
                "reason": reason_if_blocked,
                "username": username,
                "existing_user_id": user.pk,
                "existing_role": getattr(user, 'role', None),
                "existing_org_id": user.organization_id,
                "existing_is_superuser": user.is_superuser,
                "existing_is_staff": user.is_staff,
            })
            return
        # Superuser plataforma legítimo: solo refrescar is_active si está inactivo.
        # NO resetear password.
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])

    existing = User.objects.filter(username=username).first()
    if existing is not None:
        _handle_existing(existing, reason_if_blocked='username_collision_non_platform_user')
        return

    # Usuario no existe → crear dentro de atomic. Si otro worker creó en paralelo
    # (race en multi-worker Railway), IntegrityError dispara re-fetch y reclasifica.
    try:
        with transaction.atomic():
            org, _ = Organization.objects.get_or_create(name='Vet Care Internal')
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                role='ADMIN_SAAS',
                organization=org,
            )
        logger.info("SUPERUSER_BOOTSTRAP_CREATED", extra={
            "event": "SUPERUSER_BOOTSTRAP_CREATED",
            "username": username,
            "user_id": user.pk,
            "org_id": org.pk,
        })
    except IntegrityError:
        # Race condition multi-worker: otro proceso post_migrate creó el user
        # entre filter().first() y create_superuser(). Re-fetch y aplicar
        # mismo predicado — si el creado por el otro worker no calza con
        # is_platform_superuser, abort + log CRITICAL.
        raced = User.objects.filter(username=username).first()
        if raced is None:
            # IntegrityError por causa distinta a UNIQUE de username — re-raise.
            raise
        logger.warning("SUPERUSER_BOOTSTRAP_RACE_RESOLVED", extra={
            "event": "SUPERUSER_BOOTSTRAP_RACE_RESOLVED",
            "username": username,
            "user_id": raced.pk,
        })
        _handle_existing(raced, reason_if_blocked='race_condition_created_unexpected_user')
