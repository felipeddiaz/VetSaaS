from rest_framework.viewsets import ModelViewSet
from rest_framework import generics
from apps.organizations.models import Organization, OrganizationSettings
from apps.organizations.serializers import OrganizationSerializer, OrganizationSettingsSerializer
from apps.core.permissions import HybridPermission


class OrganizationViewSet(ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [HybridPermission]
    resource_name = "organization"

    def get_queryset(self):
        return Organization.objects.filter(pk=self.request.user.organization_id)


class OrganizationSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSettingsSerializer
    permission_classes = [HybridPermission]
    resource_name = "organization"
    http_method_names = ['get', 'patch']

    def get_object(self):
        org = self.request.user.organization
        settings, _ = OrganizationSettings.objects.get_or_create(organization=org)
        return settings
