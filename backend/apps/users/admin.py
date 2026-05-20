from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'organization', 'role', 'is_active', 'is_superuser')
    list_filter = ('role', 'organization', 'is_active')
    search_fields = ('username', 'email')
    fieldsets = UserAdmin.fieldsets + (
        ('Veterinaria SaaS', {'fields': ('organization', 'role', 'specialty')}),
    )

    # PR-4B / ADR p16: DELETE bloqueado en admin. Aunque User no tiene FKs
    # downstream PROTECT que impidan el borrado, hacerlo viola la promesa
    # de retención (NOM-024, audit trails de InvoiceAuditLog.changed_by,
    # closed_by, etc.). Deuda A7 (snapshot vet_name_at_close en MR) bloquea
    # la habilitación del DELETE futura. Para desactivar un user, usar
    # is_active=False vía el endpoint /api/staff/<pk>/.
    def has_delete_permission(self, request, obj=None):
        return False