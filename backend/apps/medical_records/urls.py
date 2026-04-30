from django.urls import path
from .views import (
    MedicalRecordListCreateView,
    MedicalRecordDetailView,
    MedicalRecordByPetView,
    MedicalRecordServiceListCreateView,
    MedicalRecordServiceDeleteView,
    close_medical_record,
    VaccineRecordListCreateView,
    VaccineRecordDetailView,
)

urlpatterns = [
    path("medical-records/", MedicalRecordListCreateView.as_view()),
    path("medical-records/<int:pk>/", MedicalRecordDetailView.as_view()),
    path("medical-records/<int:pk>/close/", close_medical_record),
    path("medical-records/pet/<int:pet_id>/", MedicalRecordByPetView.as_view()),
    path("medical-records/<int:medical_record_pk>/services/", MedicalRecordServiceListCreateView.as_view()),
    path("medical-records/<int:medical_record_pk>/services/<int:pk>/", MedicalRecordServiceDeleteView.as_view()),
    path("vaccines/", VaccineRecordListCreateView.as_view()),
    path("vaccines/<int:pk>/", VaccineRecordDetailView.as_view()),
]
