# Modulo: Mascotas y Propietarios

## Objetivo

El modulo gestiona propietarios y sus mascotas.
Es el punto de entrada a todos los flujos clinicos del sistema.

## Modelos

### Owner (Propietario)

Campos:
- `name` — nombre del propietario
- `phone` — telefono de contacto (10 digitos, solo Mexico)
- `is_generic` — marca al propietario sintetico "Publico General" creado por organizacion

Reglas de negocio:
- telefono debe tener exactamente 10 digitos (validacion en serializer)
- la validacion de telefono se omite cuando `is_generic = True`
- existe un unico propietario generico por organizacion (constraint parcial en DB)
- el propietario generico se crea automaticamente al crear la organizacion via signal

### Pet (Mascota)

Campos:
- `name` — nombre de la mascota
- `species` — especie (valor de `SPECIES_CHOICES`)
- `breed` — raza (texto libre, opcional)
- `birth_date` — fecha de nacimiento (obligatoria para nuevos registros)
- `sex` — choices: `male`, `female`, `unknown`
- `color` — color (opcional, seleccion en frontend)
- `owner` — FK a Owner (CASCADE)
- `is_generic` — marca a la mascota genérica "Paciente Anónimo" de la organización

Existe exactamente una mascota genérica por organización (creada via signal junto al owner genérico).
Se usa en walk-ins anónimos cuando `allow_anonymous_walkin = True` y no se envía `pet`.
No aparece en búsquedas normales (el frontend la filtra).
No puede ser objetivo de `assign-patient` (sería reasignar de genérico a genérico).

## Validaciones de backend

### Nombre (mascota y propietario)

Regex: `^[A-Za-z0-9ÁÉÍÓÚáéíóúñÑ' \-]+$`

Permite: letras, numeros, espacios, acentos, apostrofe, guion.
Rechaza: signos de puntuacion, caracteres especiales, emojis.

### Especie

Lista cerrada definida como constante `SPECIES_CHOICES` en `apps/patients/models.py`:

```python
SPECIES_CHOICES = ['canino', 'felino', 'equino', 'ave', 'reptil', 'exotico', 'otro']
```

La misma lista se usa en serializer y en el dropdown del frontend.
No se almacena como `choices` en el campo del modelo para evitar migraciones al agregar especies.

### Telefono

Regex: `^\d{10}$`

Solo digitos, exactamente 10. No se valida para propietarios con `is_generic = True`.

### Fecha de nacimiento

Obligatoria en serializer para registros nuevos.
El modelo mantiene `null=True` para no forzar migracion de datos historicos.

## Filtros disponibles (GET /api/pets/)

- `search=<texto>` — busqueda por nombre (icontains, limite 20)
- `owner=<id>` — filtrar por propietario (limite 20)
- Combinables: `?search=luna&owner=3`

## Filtros disponibles (GET /api/owners/)

- `search=<texto>` — busqueda por nombre (icontains, limite 20)
- `is_generic=true/false` — filtrar propietario generico

El frontend usa `?is_generic=true` para obtener el propietario "Publico General" al cargar la vista de cobros.
El frontend usa `?is_generic=false` en el buscador de propietarios para excluir el generico de los resultados.

## Permisos RBAC

| Accion         | Codigo             |
|----------------|--------------------|
| Listar         | `patient.list`     |
| Ver detalle    | `patient.retrieve` |
| Crear          | `patient.create`   |
| Editar         | `patient.update`   |
| Eliminar       | `patient.destroy`  |

## Aislamiento multitenant

Toda query sobre `Pet` y `Owner` esta limitada a `request.user.organization`.
El serializer valida explicitamente que la organizacion del usuario este asignada antes de crear una mascota.

## Alta rapida desde citas

El endpoint `POST /api/appointments/create-with-patient/` crea owner + pet + cita en una sola
transacción atómica sin pasar por el módulo de mascotas.

- Si el teléfono del dueño ya existe en la organización, se reutiliza el owner (cliente que
  regresa con mascota nueva).
- La mascota siempre se crea nueva.
- Toda la validación de la cita (conflictos, fecha pasada, timezone) se delega al
  `AppointmentSerializer` existente dentro del mismo `transaction.atomic()`.

Esto no reemplaza el módulo Mascotas para altas completas (raza, color, historial previo).
Es un flujo de mínimo viable para no interrumpir la agenda.

## Relacion con otros modulos

- **Citas**: `Appointment.pet` es FK obligatoria (puede ser genérica en walk-in anónimo)
- **Historial clinico**: `MedicalRecord.pet` es FK obligatoria
- **Cobros**: `Invoice.owner` es FK obligatoria; `Invoice.pet` es nullable cuando `owner.is_generic = True`
- **Vacunas**: `VaccineRecord.pet` es FK — ver modulo de historial clinico
