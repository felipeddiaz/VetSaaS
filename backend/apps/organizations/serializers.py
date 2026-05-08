from rest_framework import serializers
from django.utils import timezone
from zoneinfo import available_timezones

from .models import Organization, OrganizationTimezoneAudit, OrganizationSettings


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'timezone', 'timezone_updated_at', 'created_at']
        read_only_fields = ['timezone_updated_at', 'created_at']

    def validate_timezone(self, value):
        if value not in available_timezones():
            raise serializers.ValidationError('Zona horaria inválida')
        return value

    def update(self, instance, validated_data):
        request = self.context.get('request')
        changed_by = request.user if request and request.user.is_authenticated else None

        old_timezone = instance.timezone
        updated = super().update(instance, validated_data)

        if 'timezone' in validated_data and validated_data['timezone'] != old_timezone:
            updated.timezone_updated_at = timezone.now()
            updated.save(update_fields=['timezone_updated_at'])
            OrganizationTimezoneAudit.objects.create(
                organization=updated,
                old_timezone=old_timezone,
                new_timezone=validated_data['timezone'],
                changed_by=changed_by,
            )

        return updated


class OrganizationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationSettings
        fields = [
            'auto_create_medical_record',
            'auto_create_invoice_on_done',
            'require_confirmation_before_start',
            'allow_anonymous_walkin',
            'show_status_change_history',
        ]
