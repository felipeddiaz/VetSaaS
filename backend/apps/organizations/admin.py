from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'timezone', 'tax_rate', 'created_at')
    search_fields = ('name',)
