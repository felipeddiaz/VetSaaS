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
    """
    Status y payment_method son read-only intencionalmente. Cualquier transición
    de estado debe pasar por billing/services.py (confirm_invoice, pay_invoice,
    cancel_invoice) para preservar el contrato de event-authority documentado en
    docs/dashboard-metrics-contract.md §2.7. Editar status desde el admin dejaría
    paid_at NULL y rompería los snapshots de revenue silenciosamente.
    """
    list_display = ['id', 'pet', 'owner', 'status', 'total', 'created_at', 'organization']
    list_filter = ['status', 'organization']
    readonly_fields = [
        'status', 'payment_method',
        'subtotal', 'tax_amount', 'total',
        'paid_at', 'created_at', 'updated_at',
    ]
    inlines = [InvoiceItemInline]
