from django.urls import path
from .views import (
    MedicalRecordListCreateView,
    MedicalRecordDetailView,
    MedicalRecordByPetView,
)

urlpatterns = [
    path("medical-records/", MedicalRecordListCreateView.as_view()),
    path("medical-records/<int:pk>/", MedicalRecordDetailView.as_view()),
    path("medical-records/pet/<int:pet_id>/", MedicalRecordByPetView.as_view()),
]
