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
from apps.dashboard.views import (
    dashboard_stats, analytics_health, operations_series, financial_series,
    dashboard_summary,
)
from apps.users.views import (
    MeView,
    StaffListView,
    StaffCreateView,
    StaffDeactivateView
)
from rest_framework.routers import DefaultRouter
from apps.patients.views import PetViewSet, OwnerViewSet
from apps.organizations.views import (
    OrganizationMeView,
    OrganizationLegacyView,
    OrganizationSettingsView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from rest_framework.permissions import AllowAny
import logging
from apps.core.throttling import LoginRateThrottle, LoginUserRateThrottle
from apps.core.sanitize import sanitize_text

_login_logger = logging.getLogger('django')


class ThrottledTokenObtainPairView(TokenObtainPairView):
    # Issue #13 / ADR p15: el default global REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES
    # ahora es IsAuthenticated. Las vistas públicas (login, refresh) DEBEN declarar
    # AllowAny explícito para no romper el flujo de autenticación.
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, LoginUserRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code in (400, 401):
            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            raw_username = (request.data or {}).get('username', '')
            _login_logger.warning(
                "LOGIN_FAILED",
                extra={
                    "ip": ip.split(',')[0].strip(),
                    # sanitizar para prevenir payload injection en logs
                    "username": sanitize_text(raw_username, max_length=100),
                }
            )
        return response


class PublicTokenRefreshView(TokenRefreshView):
    """Refresh endpoint público — sin esto, el default IsAuthenticated bloquea
    el flujo de renovación de tokens (Issue #13 / ADR p15).

    Throttle dedicado (LoginRateThrottle) para prevenir spam de refresh con un
    token robado — sin él solo aplicaría user/anon default (500/h), insuficiente
    para una operación de credencial-equivalente."""
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, LoginUserRateThrottle]

router = DefaultRouter()
router.register(r'pets', PetViewSet, basename='patient')
router.register(r'owners', OwnerViewSet, basename='owner')
# Nota PR-4B / ADR p16: `organizations` ya NO es ModelViewSet — list/create/
# destroy no se exponen. Dos paths explícitos abajo: /me/ (singleton) y
# /<int:pk>/ (legacy con validación + Sunset RFC 8594).

urlpatterns = [
    path('admin/', admin.site.urls),
    # Rutas explícitas que colisionarían con el router deben ir ANTES del include del router
    path('api/organizations/settings/', OrganizationSettingsView.as_view()),
    path('api/organizations/me/', OrganizationMeView.as_view(), name='organization-me'),
    path('api/organizations/<int:pk>/', OrganizationLegacyView.as_view(), name='organization-legacy'),
    path('api/appointments/', include('apps.appointments.urls')),
    path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', PublicTokenRefreshView.as_view(), name='token_refresh'),
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
    path('api/internal/analytics-health/', analytics_health),
    path('api/v1/dashboard/operations/series/', operations_series),
    path('api/v1/dashboard/financial/series/', financial_series),
    path('api/v1/dashboard/summary/', dashboard_summary),
]
