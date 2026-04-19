from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.permissions import RolePermission

from .models import MedicalRecord
from .serializers import MedicalRecordSerializer, MedicalRecordDetailSerializer


class MedicalRecordPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class MedicalRecordListCreateView(generics.ListCreateAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [RolePermission]
    pagination_class = MedicalRecordPagination
    resource_name = "medicalrecord"

    def get_queryset(self):
        pet_id = self.request.query_params.get('pet')
        queryset = MedicalRecord.objects.filter(
            organization=self.request.user.organization
        )

        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            veterinarian=self.request.user
        )


class MedicalRecordDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MedicalRecordDetailSerializer
    permission_classes = [RolePermission]
    resource_name = "medicalrecord"

    def get_queryset(self):
        return MedicalRecord.objects.filter(
            organization=self.request.user.organization
        )


class MedicalRecordByPetView(generics.ListAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [RolePermission]
    pagination_class = MedicalRecordPagination
    resource_name = "medicalrecord"

    def get_queryset(self):
        pet_id = self.kwargs.get('pet_id')
        return MedicalRecord.objects.filter(
            organization=self.request.user.organization,
            pet_id=pet_id
        ).order_by('-created_at')
