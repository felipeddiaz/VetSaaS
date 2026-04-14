from rest_framework import serializers
from .models import Pet, Owner


class OwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = ['id', 'name', 'phone']


class PetSerializer(serializers.ModelSerializer):
    owner = OwnerSerializer()
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)

    class Meta:
        model = Pet
        fields = ['id', 'name', 'species', 'breed', 'birth_date', 'sex', 'color', 'owner', 'owner_id']

    def validate(self, attrs):
        request = self.context['request']
        if not request.user.organization:
            raise serializers.ValidationError({
                'organization': 'No tienes una organización asignada. Contacta al administrador del sistema.'
            })
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
        request = self.context['request']
        organization = request.user.organization

        owner_data = validated_data.pop('owner')
        owner, _ = Owner.objects.get_or_create(
            name=owner_data['name'],
            phone=owner_data['phone'],
            organization=organization
        )

        instance.name = validated_data.get('name', instance.name)
        instance.species = validated_data.get('species', instance.species)
        instance.breed = validated_data.get('breed', instance.breed)
        instance.birth_date = validated_data.get('birth_date', instance.birth_date)
        instance.sex = validated_data.get('sex', instance.sex)
        instance.color = validated_data.get('color', instance.color)
        instance.owner = owner
        instance.save()

        return instance