from rest_framework.permissions import BasePermission

ROLES_THAT_CAN_PAY = {'ADMIN', 'ADMIN_SAAS'}
ROLES_THAT_CAN_CONFIRM = {'ADMIN', 'ADMIN_SAAS', 'VET', 'ASSISTANT'}


class CanConfirmInvoice(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) in ROLES_THAT_CAN_CONFIRM
        )


class CanPayInvoice(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) in ROLES_THAT_CAN_PAY
        )
