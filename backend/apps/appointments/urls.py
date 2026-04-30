from django.urls import path
from .views import AppointmentListCreateView, AppointmentDetailView, update_status, walk_in, appointment_history, assign_patient, create_with_patient

urlpatterns = [
    path("", AppointmentListCreateView.as_view()),
    path("create-with-patient/", create_with_patient),
    path("walk-in/", walk_in),
    path("<int:pk>/", AppointmentDetailView.as_view()),
    path("<int:pk>/status/", update_status),
    path("<int:pk>/history/", appointment_history),
    path("<int:pk>/assign-patient/", assign_patient),
]
