from .models import Appointment

def create_appointment(user, data):
    # eliminar organization de los datos enviados para evitar inyecciones
    data.pop("organization", None)

    # evitar doble reserva (usando for_user si está disponible, o filter seguro)
    exists = Appointment.objects.filter(
        organization=user.organization,
        veterinarian=data.get("veterinarian"),
        datetime=data.get("datetime"),
        status="scheduled"
    ).exists()

    if exists:
        raise Exception("Horario ocupado")

    return Appointment.objects.create(organization=user.organization, **data)