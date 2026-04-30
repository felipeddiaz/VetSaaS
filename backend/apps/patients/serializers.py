import re

from rest_framework import serializers
from .models import Pet, Owner, SPECIES_CHOICES

NAME_REGEX = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚáéíóúñÑ\' \-]+$")
PHONE_REGEX = re.compile(r"^\d{10}$")


def _validate_name(value, field_label="Nombre"):
    if not value or not value.strip():
        raise serializers.ValidationError(f"{field_label} es requerido.")
    if not NAME_REGEX.match(value.strip()):
        raise serializers.ValidationError(
            f"{field_label} solo puede contener letras, números, espacios, acentos, apóstrofes y guiones."
        )
    return value.strip()


class OwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = ['id', 'name', 'phone', 'is_generic']
        read_only_fields = ['is_generic']

    def validate_name(self, value):
        return _validate_name(value, "Nombre del dueño")

    def validate_phone(self, value):
        # skip validation for generic owners
        instance = getattr(self, 'instance', None)
        is_generic = getattr(instance, 'is_generic', False)
        if is_generic:
            return value
        if not PHONE_REGEX.match(value or ''):
            raise serializers.ValidationError("El teléfono debe tener exactamente 10 dígitos.")
        return value


class PetSerializer(serializers.ModelSerializer):
    owner = OwnerSerializer()
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)

    class Meta:
        model = Pet
        fields = ['id', 'name', 'species', 'breed', 'birth_date', 'sex', 'color', 'owner', 'owner_id']

    def validate_name(self, value):
        return _validate_name(value, "Nombre de la mascota")

    def validate_species(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("La especie es requerida.")
        if value.strip().lower() not in SPECIES_CHOICES:
            raise serializers.ValidationError(
                f"Especie inválida. Opciones: {', '.join(SPECIES_CHOICES)}."
            )
        return value.strip().lower()

    def validate_birth_date(self, value):
        if value is None:
            raise serializers.ValidationError("La fecha de nacimiento es requerida.")
        return value

    def validate(self, attrs):
        request = self.context['request']
        if not request.user.organization:
            raise serializers.ValidationError({
                'organization': 'No tienes una organización asignada. Contacta al administrador del sistema.'
            })
        # phone validation: skip if owner is generic (create path doesn't have instance yet)
        owner_data = attrs.get('owner', {})
        phone = owner_data.get('phone', '')
        if phone and not PHONE_REGEX.match(phone):
            raise serializers.ValidationError({'owner': {'phone': 'El teléfono debe tener exactamente 10 dígitos.'}})
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        organization = request.user.organization

        owner_data = validated_data.pop('owner')
        owner, _ = Owner.objects.get_or_create(
            name=owner_data['name'],
            phone=owner_data['phone'],
            organization=organization
        )

        pet = Pet.objects.create(
            owner=owner,
            organization=organization,
            **validated_data
        )

        return pet

    def update(self, instance, validated_data):
        owner_data = validated_data.pop('owner')
        owner = instance.owner
        owner.name = owner_data.get('name', owner.name)
        owner.phone = owner_data.get('phone', owner.phone)
        owner.save()

        instance.name = validated_data.get('name', instance.name)
        instance.species = validated_data.get('species', instance.species)
        instance.breed = validated_data.get('breed', instance.breed)
        instance.birth_date = validated_data.get('birth_date', instance.birth_date)
        instance.sex = validated_data.get('sex', instance.sex)
        instance.color = validated_data.get('color', instance.color)
        instance.save()

        return instance
