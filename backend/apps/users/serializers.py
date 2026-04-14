from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.organizations.models import Organization

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 
                  'role', 'specialty', 'is_active', 'organization', 'organization_name']


class CreateEmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
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

    def validate_organization_id(self, value):
        if value and not Organization.objects.filter(id=value).exists():
            raise serializers.ValidationError("La organización no existe")
        return value

    def create(self, validated_data):
        validated_data.pop('organization_id', None)  # Ignorar si viene del request
        
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
            organization=organization
        )
        return user
