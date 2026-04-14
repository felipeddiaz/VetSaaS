from django.urls import path
from .views import AppointmentListCreateView, AppointmentDetailView, update_status

urlpatterns = [
    path("", AppointmentListCreateView.as_view()),
    path("<int:pk>/", AppointmentDetailView.as_view()),
    path("<int:pk>/status/", update_status),
]