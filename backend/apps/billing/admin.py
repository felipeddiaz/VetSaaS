from django.contrib import admin
from apps.core.admin import TenantAwareAdmin
from .models import Service, Invoice, InvoiceItem


@admin.register(Service)
class ServiceAdmin(TenantAwareAdmin):
    list_display = ['name', 'base_price', 'is_active', 'organization']
    list_filter = ['is_active', 'organization']
    search_fields = ['name']


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ['subtotal']


@admin.register(Invoice)
class InvoiceAdmin(TenantAwareAdmin):
    list_display = ['id', 'pet', 'owner', 'status', 'total', 'created_at', 'organization']
    list_filter = ['status', 'organization']
    readonly_fields = ['subtotal', 'tax_amount', 'total', 'paid_at', 'created_at', 'updated_at']
    inlines = [InvoiceItemInline]
