from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from apps.organizations.models import Organization, OrganizationSettings
from apps.organizations.serializers import OrganizationSerializer, OrganizationSettingsSerializer


class IsAdminUser:
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'ADMIN'


class OrganizationViewSet(ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        # Cada admin solo ve su propia organización
        return Organization.objects.filter(pk=self.request.user.organization_id)

    def create(self, request, *args, **kwargs):
        if request.user.role != 'ADMIN':
            return Response(
                {'error': 'Solo el administrador del sistema puede crear organizaciones'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)


class OrganizationSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSettingsSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    http_method_names = ['get', 'patch']

    def get_object(self):
        org = self.request.user.organization
        settings, _ = OrganizationSettings.objects.get_or_create(organization=org)
        return settings
