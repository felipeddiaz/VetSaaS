from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response
from apps.organizations.models import Organization
from apps.organizations.serializers import OrganizationSerializer


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
