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