from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from apps.core.permissions import RolePermission, make_permission
from apps.organizations.models import Organization
from apps.users.serializers import UserSerializer, CreateEmployeeSerializer

User = get_user_model()


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "specialty": user.specialty,
            "organization": user.organization.id if user.organization else None,
            "organization_name": user.organization.name if user.organization else None,
            "organization_timezone": user.organization.timezone if user.organization else "America/Mexico_City",
        })


class CreateEmployeeView(APIView):
    """Crear empleado (alias legacy — usar StaffCreateView)."""
    permission_classes = [make_permission("staff.create")]

    def post(self, request):
        serializer = CreateEmployeeSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StaffListView(APIView):
    permission_classes = [make_permission("staff.list")]

    def get(self, request):
        users = User.objects.filter(
            organization=request.user.organization,
            is_active=True
        ).exclude(role='ADMIN_SAAS')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class StaffCreateView(APIView):
    permission_classes = [make_permission("staff.create")]

    def post(self, request):
        serializer = CreateEmployeeSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StaffDeactivateView(APIView):
    permission_classes = [make_permission("staff.destroy")]

    def delete(self, request, pk):
        user = get_object_or_404(
            User,
            pk=pk,
            organization=request.user.organization
        )
        user.is_active = False
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
