from rest_framework.viewsets import ModelViewSet

from apps.core.permissions import RolePermission

from .models import Pet, Owner
from .serializers import PetSerializer, OwnerSerializer


class PetViewSet(ModelViewSet):
    """
    Pacientes (mascotas). basename='patient' → permisos patient.*
    """
    serializer_class = PetSerializer
    permission_classes = [RolePermission]

    def get_queryset(self):
        return Pet.objects.filter(
            organization=self.request.user.organization
        )

    def get_serializer_context(self):
        return {'request': self.request}


class OwnerViewSet(ModelViewSet):
    """
    Propietarios. basename='owner' → permisos owner.*
    """
    serializer_class = OwnerSerializer
    permission_classes = [RolePermission]

    def get_queryset(self):
        return Owner.objects.filter(
            organization=self.request.user.organization
        )

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization
        )
