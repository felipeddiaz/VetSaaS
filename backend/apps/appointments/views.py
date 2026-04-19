from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.utils.dateparse import parse_date

from apps.core.datetime_utils import filter_by_local_day
from apps.core.permissions import RolePermission, make_permission

from .models import Appointment
from .serializers import AppointmentSerializer


class AppointmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [RolePermission]
    resource_name = "appointment"

    def get_queryset(self):
        org = self.request.user.organization
        queryset = Appointment.objects.filter(
            organization=org,
            status__in=['scheduled', 'done']
        )

        veterinarian_id = self.request.query_params.get('veterinarian')
        date = self.request.query_params.get('date')
        pet_id = self.request.query_params.get('pet')

        if veterinarian_id:
            queryset = queryset.filter(veterinarian_id=veterinarian_id)
        if date:
            parsed = parse_date(date)
            if parsed:
                queryset = filter_by_local_day(queryset, 'start_datetime', org, parsed)
        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)

        return queryset.order_by('start_datetime', 'id')

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class AppointmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [RolePermission]
    resource_name = "appointment"

    def get_queryset(self):
        return Appointment.objects.filter(
            organization=self.request.user.organization
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.status = 'canceled'
        instance.save()
        return Response(status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([make_permission("appointment.update")])
def update_status(request, pk):
    try:
        appointment = Appointment.objects.get(
            pk=pk,
            organization=request.user.organization
        )
    except Appointment.DoesNotExist:
        return Response(
            {'error': 'Cita no encontrada'},
            status=status.HTTP_404_NOT_FOUND
        )

    new_status = request.data.get('status')
    if new_status not in ['scheduled', 'canceled', 'done']:
        return Response(
            {'error': 'Estado inválido'},
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = AppointmentSerializer(
        appointment,
        data={'status': new_status},
        partial=True,
        context={'request': request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)
