from django.contrib import admin
from apps.core.admin import TenantAwareAdmin
from .models import Prescription, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0


@admin.register(Prescription)
class PrescriptionAdmin(TenantAwareAdmin):
    list_display = ['id', 'pet', 'veterinarian', 'created_at', 'organization']
    list_filter = ['organization']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [PrescriptionItemInline]
