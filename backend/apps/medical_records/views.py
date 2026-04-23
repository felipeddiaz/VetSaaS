from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.permissions import HybridPermission
from apps.core.views import TenantQueryMixin

from .models import MedicalRecord
from .serializers import MedicalRecordSerializer, MedicalRecordDetailSerializer


class MedicalRecordPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class MedicalRecordListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [HybridPermission]
    pagination_class = MedicalRecordPagination
    resource_name = "medicalrecord"

    def get_queryset(self):
        pet_id = self.request.query_params.get('pet')
        queryset = MedicalRecord.objects.for_organization(self.request.user.organization)

        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            veterinarian=self.request.user
        )


class MedicalRecordDetailView(TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MedicalRecordDetailSerializer
    permission_classes = [HybridPermission]
    resource_name = "medicalrecord"

    def get_queryset(self):
        return MedicalRecord.objects.for_organization(self.request.user.organization)


class MedicalRecordByPetView(TenantQueryMixin, generics.ListAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [HybridPermission]
    pagination_class = MedicalRecordPagination
    resource_name = "medicalrecord"

    def get_queryset(self):
        pet_id = self.kwargs.get('pet_id')
        return MedicalRecord.objects.for_organization(
            self.request.user.organization
        ).filter(pet_id=pet_id).order_by('-created_at')
