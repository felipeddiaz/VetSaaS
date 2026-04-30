"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from apps.dashboard.views import dashboard_stats
from apps.users.views import (
    MeView,
    StaffListView,
    StaffCreateView,
    StaffDeactivateView
)
from rest_framework.routers import DefaultRouter
from apps.patients.views import PetViewSet, OwnerViewSet
from apps.organizations.views import OrganizationViewSet, OrganizationSettingsView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from apps.core.throttling import LoginRateThrottle


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [LoginRateThrottle]

router = DefaultRouter()
router.register(r'pets', PetViewSet, basename='patient')
router.register(r'owners', OwnerViewSet, basename='owner')
router.register(r'organizations', OrganizationViewSet, basename='organization')

urlpatterns = [
    path('admin/', admin.site.urls),
    # Rutas explícitas que colisionarían con el router deben ir ANTES del include del router
    path('api/organizations/settings/', OrganizationSettingsView.as_view()),
    path('api/appointments/', include('apps.appointments.urls')),
    path('api/token/', ThrottledTokenObtainPairView.as_view()),
    path('api/token/refresh/', TokenRefreshView.as_view()),
    path('api/', include(router.urls)),
    path('api/me/', MeView.as_view()),
    path('api/staff/', StaffListView.as_view(), name='staff-list'),
    path('api/staff/create/', StaffCreateView.as_view(), name='staff-create'),
    path('api/staff/<int:pk>/', StaffDeactivateView.as_view(), name='staff-deactivate'),
    path('api/', include('apps.medical_records.urls')),
    path('api/', include('apps.inventory.urls')),
    path('api/', include('apps.billing.urls')),
    path('api/', include('apps.prescriptions.urls')),
    path('api/dashboard/stats/', dashboard_stats),
]
