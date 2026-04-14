from rest_framework import serializers
from .models import Appointment

class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = "__all__"

    def validate(self, data):
        vet = data["veterinarian"]
        date = data["date"]
        start = data["start_time"]
        end = data["end_time"]

        conflicts = Appointment.objects.filter(
            veterinarian=vet,
            date=date,
            status="scheduled",
            start_time__lt=end,
            end_time__gt=start,
        )

        if conflicts.exists():
            raise serializers.ValidationError(
                "El veterinario ya tiene una cita en ese horario."
            )

        return data