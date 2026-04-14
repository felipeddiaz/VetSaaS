from django.contrib import admin
from .models import Product, Presentation, StockMovement, MedicalRecordProduct


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'internal_code', 'category', 'requires_prescription', 'is_active', 'organization']
    list_filter = ['is_active', 'category', 'organization']
    search_fields = ['name', 'internal_code']


@admin.register(Presentation)
class PresentationAdmin(admin.ModelAdmin):
    list_display = ['product', 'name', 'base_unit', 'stock', 'min_stock', 'sale_price', 'organization']
    list_filter = ['base_unit', 'organization']
    search_fields = ['name', 'product__name']
    readonly_fields = ['product']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['presentation', 'movement_type', 'quantity', 'reason', 'created_by', 'created_at']
    list_filter = ['movement_type', 'organization']
    readonly_fields = ['created_at']


@admin.register(MedicalRecordProduct)
class MedicalRecordProductAdmin(admin.ModelAdmin):
    list_display = ['medical_record', 'presentation', 'quantity']
