"""
Mixin para todas las clases ModelAdmin que usen OrganizationalModel.

Problema sin esto:
  El TenantManager devuelve .none() cuando no hay contexto de tenant.
  El admin de Django corre en requests normales donde el superadmin puede
  tener organization=None, lo que haría invisible todos los registros.

Solución:
  TenantAwareAdmin sobreescribe get_queryset() para usar all_objects,
  que bypassa el TenantManager y devuelve todos los registros.
  El filtro por organización lo provee list_filter = ['organization'].
"""

from django.contrib import admin


class TenantAwareAdmin(admin.ModelAdmin):
    """
    Base para admins de modelos multitenant.
    Usa all_objects para que superadmins vean todos los registros.
    Siempre incluir 'organization' en list_filter.
    """

    def get_queryset(self, request):
        # all_objects: bypassa TenantManager — el admin necesita ver todos los tenants
        model = self.model
        if hasattr(model, 'all_objects'):
            return model.all_objects.get_queryset()
        return super().get_queryset(request)

    def has_delete_permission(self, request, obj=None):
        # Borrado físico deshabilitado en admin — usar soft delete (is_active=False)
        # o hard_delete() desde shell si es absolutamente necesario.
        return False
