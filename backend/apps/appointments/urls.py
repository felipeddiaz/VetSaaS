from django.urls import path
from .views import AppointmentListCreateView, AppointmentDetailView, update_status, walk_in, appointment_history, assign_patient, create_with_patient

urlpatterns = [
    path("", AppointmentListCreateView.as_view()),
    path("create-with-patient/", create_with_patient),
    path("walk-in/", walk_in),
    path("<str:pk>/", AppointmentDetailView.as_view()),
    path("<str:pk>/status/", update_status),
    path("<str:pk>/history/", appointment_history),
    path("<str:pk>/assign-patient/", assign_patient),
]
