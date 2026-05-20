from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'timezone', 'tax_rate', 'created_at')
    search_fields = ('name',)

    # PR-4B / ADR p16: DELETE bloqueado en admin. User.organization es PROTECT
    # tras este sprint — un intento de borrar org desde admin levantaría
    # ProtectedError que NO pasa por custom_exception_handler (es admin Django,
    # no DRF), produciendo un traceback técnico para el operador. Bloquear
    # explícitamente mantiene la promesa: orgs no se borran, se desactivan
    # (deuda A5 — soft-delete real en Fase 2).
    def has_delete_permission(self, request, obj=None):
        return False
