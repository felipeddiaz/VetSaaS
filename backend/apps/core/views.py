from rest_framework.exceptions import PermissionDenied


class TenantQueryMixin:
    """
    Mixin que garantiza que el usuario tiene organización antes de procesar la request.
    Agregar como primer mixin en todas las CBVs que accedan a datos de tenant.
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not request.user.organization:
            raise PermissionDenied("User has no organization assigned")
