import re
import logging

from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)

User = get_user_model()

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_.\-]+$")
NAME_REGEX = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúñÑ ]+$")


class UserSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'role', 'specialty', 'is_active', 'organization', 'organization_name']


class CreateEmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=False, allow_blank=True, default='')
    last_name = serializers.CharField(required=False, allow_blank=True, default='')
    role = serializers.ChoiceField(
        choices=['ADMIN', 'VET', 'ASSISTANT'],
        default='ASSISTANT'
    )
    specialty = serializers.CharField(required=False, allow_blank=True, default='')
    organization_id = serializers.IntegerField(required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name',
                  'role', 'specialty', 'organization_id']

    def validate_username(self, value):
        if not USERNAME_REGEX.match(value):
            raise serializers.ValidationError(
                "El nombre de usuario solo puede contener letras, números, puntos, guiones y guiones bajos."
            )
        return value

    def validate_first_name(self, value):
        if not value:
            return value
        if not NAME_REGEX.match(value.strip()):
            raise serializers.ValidationError(
                "El nombre solo puede contener letras y espacios."
            )
        return value.strip().title()

    def validate_last_name(self, value):
        if not value:
            return value
        if not NAME_REGEX.match(value.strip()):
            raise serializers.ValidationError(
                "El apellido solo puede contener letras y espacios."
            )
        return value.strip().title()

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("La contraseña debe tener al menos 8 caracteres.")
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError("La contraseña debe contener al menos una letra mayúscula.")
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError("La contraseña debe contener al menos un número.")
        return value

    def validate_organization_id(self, value):
        if value and not Organization.objects.filter(id=value).exists():
            raise serializers.ValidationError("La organización no existe")
        return value

    def create(self, validated_data):
        validated_data.pop('organization_id', None)

        request = self.context.get('request')
        organization = request.user.organization if request else None

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            specialty=validated_data.get('specialty', ''),
            role=validated_data.get('role', 'ASSISTANT'),
            organization=organization,
        )

        self._assign_rbac_role(user, organization)
        return user

    def _assign_rbac_role(self, user, organization):
        if not organization:
            return
        from apps.core.models import Role, UserRole
        try:
            db_role = Role.objects.get(
                name=user.role,
                organization=organization,
                is_system_role=True,
            )
            UserRole.objects.get_or_create(user=user, role=db_role)
        except Role.DoesNotExist:
            logger.warning(
                "Rol '%s' no encontrado en org %s al crear usuario %s — "
                "ejecuta seed_permissions",
                user.role, organization.id, user.id,
            )
