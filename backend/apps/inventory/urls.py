from django.urls import path
from .views import (
    ProductListCreateView,
    ProductDetailView,
    low_stock_products,
    adjust_stock,
    unit_choices,
    StockMovementListView,
    PresentationListView,
    MedicalRecordProductListCreateView,
    MedicalRecordProductDeleteView,
)

urlpatterns = [
    path('inventory/products/', ProductListCreateView.as_view()),
    path('inventory/products/low-stock/', low_stock_products),
    path('inventory/products/<int:pk>/', ProductDetailView.as_view()),
    path('inventory/products/<int:pk>/adjust/', adjust_stock),
    path('inventory/movements/', StockMovementListView.as_view()),
    path('inventory/presentations/', PresentationListView.as_view()),
    path('inventory/units/', unit_choices),
    path(
        'medical-records/<int:medical_record_pk>/products/',
        MedicalRecordProductListCreateView.as_view(),
    ),
    path(
        'medical-records/<int:medical_record_pk>/products/<int:pk>/',
        MedicalRecordProductDeleteView.as_view(),
    ),
]
