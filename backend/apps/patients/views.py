from rest_framework.viewsets import ModelViewSet

from apps.core.permissions import HybridPermission
from apps.core.views import TenantQueryMixin

from .models import Pet, Owner
from .serializers import PetSerializer, OwnerSerializer


class PetViewSet(TenantQueryMixin, ModelViewSet):
    """
    Pacientes (mascotas). basename='patient' → permisos patient.*
    Soporta ?search=<nombre> y ?owner=<id> (combinables). Límite 20 cuando se filtra.
    """
    serializer_class = PetSerializer
    permission_classes = [HybridPermission]

    def get_queryset(self):
        qs = Pet.objects.for_organization(self.request.user.organization)
        search = self.request.query_params.get("search", "").strip()
        owner_id = self.request.query_params.get("owner", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        if search or owner_id:
            qs = qs[:20]
        return qs

    def get_serializer_context(self):
        return {'request': self.request}


class OwnerViewSet(TenantQueryMixin, ModelViewSet):
    """
    Propietarios. basename='owner' → permisos owner.*
    Soporta ?search=<nombre>. Límite 20 cuando se filtra.
    """
    serializer_class = OwnerSerializer
    permission_classes = [HybridPermission]

    def get_queryset(self):
        qs = Owner.objects.for_organization(self.request.user.organization)
        search = self.request.query_params.get("search", "").strip()
        is_generic = self.request.query_params.get("is_generic", "").strip()
        if is_generic == "true":
            qs = qs.filter(is_generic=True)
        elif is_generic == "false":
            qs = qs.filter(is_generic=False)
        if search:
            qs = qs.filter(name__icontains=search)[:20]
        return qs

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization
        )
