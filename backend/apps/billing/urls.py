from django.urls import path
from .views import (
    ServiceListCreateView,
    ServiceDetailView,
    InvoiceListCreateView,
    InvoiceDetailView,
    confirm_invoice,
    pay_invoice,
    cancel_invoice,
    InvoiceItemCreateView,
    InvoiceItemDetailView,
)

urlpatterns = [
    path('billing/services/', ServiceListCreateView.as_view()),
    path('billing/services/<int:pk>/', ServiceDetailView.as_view()),
    path('billing/invoices/', InvoiceListCreateView.as_view()),
    path('billing/invoices/<int:pk>/', InvoiceDetailView.as_view()),
    path('billing/invoices/<int:pk>/confirm/', confirm_invoice),
    path('billing/invoices/<int:pk>/pay/', pay_invoice),
    path('billing/invoices/<int:pk>/cancel/', cancel_invoice),
    path('billing/invoices/<int:invoice_pk>/items/', InvoiceItemCreateView.as_view()),
    path('billing/invoices/<int:invoice_pk>/items/<int:pk>/', InvoiceItemDetailView.as_view()),
]
