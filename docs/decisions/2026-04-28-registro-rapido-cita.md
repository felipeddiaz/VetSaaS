# ADR: Registro rápido + cita (alta de paciente en el momento de agendar)

## Contexto

El formulario "Nueva cita" requería que la mascota ya estuviera registrada.
Si el paciente era nuevo, recepción debía salir al módulo Mascotas, registrar owner + pet,
volver a Citas y crear la cita: tres pasos con dos cambios de módulo.

Esto era un bloqueo operativo en horas pico.

## Decisión

Se extiende el formulario "Nueva cita" (`SidebarForm`) con un enlace de escape
**"No encuentro la mascota →"** que expande un formulario inline mínimo (`QuickPatientForm`).

Al guardar, un endpoint atómico crea owner + pet + cita en una sola transacción.

## Diseño UX

```
[Buscar mascota...]
No encuentro la mascota →      ← enlace pequeño, gris, bajo el SearchSelect

  Al hacer clic:

  ┌── Nuevo paciente ──────────────────────────────┐
  │  DUEÑO                                          │
  │  Nombre *   [________________]                  │
  │  Teléfono * [____] (10 dígitos)                 │
  │                                                 │
  │  MASCOTA                                        │
  │  Nombre *   [________________]                  │
  │  Especie *  [▾ canino/felino/...]               │
  │  Sexo       [▾ opcional]                        │
  │  F. Nacim.  [  fecha opcional  ]                │
  │                                                 │
  │              ← Cancelar                         │
  └─────────────────────────────────────────────────┘
```

No hay botón "Registrar" separado. El botón "Guardar cita" existente maneja ambos caminos:
- si hay `quickPatient` activo → llama al endpoint compuesto
- si hay `petItem` seleccionado → flujo normal

Cancelar colapsa el panel y restaura el SearchSelect.

## Endpoint

`POST /api/appointments/create-with-patient/`

```json
{
  "owner_name": "...",
  "owner_phone": "...",
  "pet_name": "...",
  "pet_species": "...",
  "pet_sex": "unknown",
  "pet_birth_date": null,
  "veterinarian": 3,
  "date": "2026-04-28",
  "start_time": "10:00",
  "end_time": "10:30",
  "reason": "...",
  "notes": ""
}
```

Lógica interna con `transaction.atomic()`:

```python
owner, _ = Owner.objects.get_or_create(
    organization=org,
    phone=owner_phone,
    defaults={'name': owner_name}
)
pet = Pet.objects.create(name=pet_name, species=..., owner=owner, organization=org)
serializer = AppointmentSerializer(data={...pet.id}, context={'request': request})
serializer.is_valid(raise_exception=True)
appt = serializer.save(organization=org)
```

Si el teléfono ya existe en la organización, se reutiliza el owner y se crea solo la mascota nueva.
Si el AppointmentSerializer falla (conflicto de horario, fecha pasada, etc.), toda la transacción
se revierte: no quedan owners ni mascotas huérfanas.

## Alternativas consideradas

### 1. Modal separado "Nuevo paciente" + redirigir a Citas

Descartada. Sigue siendo dos flujos. No resuelve la interrupción de la agenda.

### 2. Formulario inline completo (con raza, color, notas, etc.)

Descartada. El registro rápido es intencionalemente mínimo.
Para el alta completa sigue existiendo el módulo Mascotas.

### 3. Crear mascota en el SearchSelect con opción "+ Crear"

Considerada. Fue descartada porque el alta mínima requiere también el owner,
y el SearchSelect busca mascotas, no owners. Mezclar ambos flujos en el componente
lo volvería inmanejable.

## Componente reutilizable

`QuickPatientForm` (`frontend/src/components/QuickPatientForm.jsx`) expone:

```js
QuickPatientForm({ value, onChange, onCancel, disabled })
// value: { ownerName, ownerPhone, petName, species, sex, birthDate }
```

Es stateless: el estado lo mantiene el padre. Puede reutilizarse en otros contextos
(nueva factura con paciente nuevo, etc.) sin duplicar lógica.

## Consecuencias

Positivas:
- Alta de paciente nuevo sin interrumpir el flujo de agenda
- La transacción atómica garantiza consistencia: no hay registros huérfanos
- El mismo botón "Guardar cita" maneja ambos caminos (sin UX nueva para aprender)
- `QuickPatientForm` es reutilizable en otros módulos

Costos:
- El registro rápido crea mascotas con datos mínimos (sin raza, color, historial)
  El staff deberá completarlos desde el módulo Mascotas si es necesario
- El owner se reutiliza por teléfono: si el número cambia o hay error tipográfico,
  se crea un owner duplicado (aceptable para v1, resoluble desde Mascotas)

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `backend/apps/appointments/views.py` | + `create_with_patient` view |
| `backend/apps/appointments/urls.py` | + `path("create-with-patient/", ...)` |
| `frontend/src/components/QuickPatientForm.jsx` | **Nuevo** componente reutilizable |
| `frontend/src/api/appointments.js` | + `createAppointmentWithPatient` |
| `frontend/src/pages/appointments.jsx` | + modo quickPatient en SidebarForm, + `handleSaveWithPatient` en Appointments |
