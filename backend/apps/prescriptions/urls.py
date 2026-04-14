from django.urls import path
from .views import (
    PrescriptionListCreateView,
    PrescriptionDetailView,
    PrescriptionByPetView,
    PrescriptionItemCreateView,
    PrescriptionItemDeleteView,
    prescription_pdf,
)

urlpatterns = [
    path('prescriptions/', PrescriptionListCreateView.as_view()),
    path('prescriptions/<int:pk>/', PrescriptionDetailView.as_view()),
    path('prescriptions/<int:pk>/pdf/', prescription_pdf),
    path('prescriptions/pet/<int:pet_id>/', PrescriptionByPetView.as_view()),
    path('prescriptions/<int:prescription_pk>/items/', PrescriptionItemCreateView.as_view()),
    path('prescriptions/<int:prescription_pk>/items/<int:pk>/', PrescriptionItemDeleteView.as_view()),
]
