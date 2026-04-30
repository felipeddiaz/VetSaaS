import logging

from apps.core.models import UserRole
from apps.core.permissions import _is_allowed
from apps.core.permissions_codes import PERMISSIONS


policy_logger = logging.getLogger("medical_records.events")


def _role_names(user) -> set[str]:
    if hasattr(user, "_cached_role_names"):
        return user._cached_role_names

    roles = set(
        UserRole.objects.filter(user=user).values_list("role__name", flat=True)
    )
    user._cached_role_names = roles
    return roles


def _permission_codes(user):
    if hasattr(user, "_cached_permissions"):
        return user._cached_permissions

    user_roles = UserRole.objects.select_related("role").prefetch_related(
        "role__permissions"
    ).filter(user=user)

    if not user_roles.exists():
        user._cached_permissions = None
        return None

    perms = set()
    for user_role in user_roles:
        perms.update(user_role.role.permissions.values_list("code", flat=True))

    user._cached_permissions = perms
    return perms


def _has_required_permission(user, required: str) -> bool:
    db_perms = _permission_codes(user)
    if db_perms is not None:
        return _is_allowed(required, list(db_perms))
    return _is_allowed(required, PERMISSIONS.get(user.role, []))


def can_modify_medical_record_charges(user, medical_record) -> bool:
    if not _has_required_permission(user, "medicalrecord.update"):
        return False

    if medical_record.organization_id != user.organization_id:
        return False

    if medical_record.status == medical_record.Status.CLOSED:
        return False

    role_names = _role_names(user)
    if "ADMIN_SAAS" in role_names or "ADMIN" in role_names:
        return True

    if "VET" in role_names and medical_record.veterinarian_id == user.id:
        return True

    return False


def can_close_medical_record(user, medical_record) -> bool:
    if not _has_required_permission(user, "medicalrecord.close"):
        return False

    if medical_record.organization_id != user.organization_id:
        return False

    role_names = _role_names(user)
    if "ADMIN_SAAS" in role_names or "ADMIN" in role_names:
        return True

    if "VET" in role_names and medical_record.veterinarian_id == user.id:
        return True

    return False


def assert_can_modify_charges(user, medical_record, request) -> None:
    """
    Lanza PermissionDenied si el usuario no puede modificar cargos del registro.
    Centralizado para usarse en ListCreate y Delete sin herencia común.
    """
    from rest_framework.exceptions import PermissionDenied

    if medical_record.organization_id != user.organization_id:
        log_ownership_denied(user=user, medical_record=medical_record, request=request)
        raise PermissionDenied("No puedes modificar consultas fuera de tu organización")

    if medical_record.status == medical_record.Status.CLOSED:
        log_closed_denied(user=user, medical_record=medical_record, request=request)
        raise PermissionDenied("La consulta está cerrada")

    if not can_modify_medical_record_charges(user, medical_record):
        log_ownership_denied(user=user, medical_record=medical_record, request=request)
        raise PermissionDenied("No puedes modificar esta consulta")


def log_ownership_denied(*, user, medical_record, request) -> None:
    policy_logger.warning(
        "MEDICAL_RECORD_OWNERSHIP_DENIED",
        extra={
            "user_id": user.id,
            "organization_id": user.organization_id,
            "medical_record_id": medical_record.id,
            "veterinarian_id": medical_record.veterinarian_id,
            "endpoint": request.path,
            "method": request.method,
        },
    )


def log_closed_denied(*, user, medical_record, request) -> None:
    policy_logger.warning(
        "MEDICAL_RECORD_CLOSED_DENIED",
        extra={
            "user_id": user.id,
            "organization_id": user.organization_id,
            "medical_record_id": medical_record.id,
            "veterinarian_id": medical_record.veterinarian_id,
            "endpoint": request.path,
            "method": request.method,
        },
    )
