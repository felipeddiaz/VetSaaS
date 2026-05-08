# ADR: Separación CREATE (borrador) vs CLOSE (validación clínica)

**Fecha**: 2026-05-05  
**Estado**: Implementado

## Contexto

El stepper de creación de consultas tiene 4 pasos:
1. Diagnóstico
2. Tratamiento y signos vitales
3. Productos
4. Facturación y cierre

Originalmente, el serializer `MedicalRecordSerializer` validaba que **tanto `diagnosis` como `treatment` fueran obligatorios en CREATE**. Esto rompía el flujo del stepper: al crear el registro en el Paso 1, el backend rechazaba la consulta porque `treatment` aún estaba vacío (el usuario recién lo llenaría en el Paso 2).

## Problema

El backend asumía que CREATE = consulta completa, pero el flujo real es:
- CREATE → borrador clínico (estado `open`)
- CLOSE → validación clínica real (estado `closed`)

## Decisión

### 1. CREATE solo requiere `diagnosis`

En `MedicalRecordSerializer.validate()`, se eliminó la validación de `treatment` obligatorio para creaciones:

```python
# En creación el diagnóstico es obligatorio. El tratamiento se valida al cerrar.
if not self.instance:
    if not data.get('diagnosis', '').strip():
        raise serializers.ValidationError({'diagnosis': 'El diagnóstico es obligatorio.'})
    # treatment YA NO se valida aquí
```

**Nota**: `sanitize_text()` ya se aplicó antes de esta validación, así que `<script>` → `""` → es rechazado correctamente.

### 2. CLOSE valida según `consultation_type`

En `close_medical_record` (FBV), se agregaron validaciones clínicas antes del cierre:

```python
# Validación de campos requeridos para cierre
diagnosis = sanitize_text(medical_record.diagnosis or '', max_length=400)
if not diagnosis.strip():
    raise ValidationError({"diagnosis": "El diagnóstico es obligatorio."})

if medical_record.consultation_type != MedicalRecord.ConsultationType.VACCINE:
    treatment = sanitize_text(medical_record.treatment or '', max_length=400)
    if not treatment.strip():
        raise ValidationError({"treatment": "El tratamiento es obligatorio."})
```

**Excepción para `VACCINE`**: Las consultas de vacunación pueden cerrarse sin tratamiento, ya que en muchos flujos reales una vacuna no requiere tratamiento adicional.

### 3. Formato de error estandarizado

Ambas validaciones usan `raise ValidationError({...})` para que el exception handler global (`apps/core/exceptions.py`) las convierta al formato estándar:

```json
{
  "code": "validation_error",
  "errors": {
    "diagnosis": ["El diagnóstico es obligatorio."]
  }
}
```

Esto permite que el frontend mapee errores a steps específicos mediante `FIELD_TO_STEP`:

```javascript
const FIELD_TO_STEP = {
  consultation_type: 1,
  diagnosis: 1,
  notes: 1,
  treatment: 2,
  weight: 2
};
```

### 4. Logging de validaciones fallidas

Cada validación fallida en `close_medical_record` emite un log WARNING:

```python
events_logger.warning(
    "MEDICAL_RECORD_CLOSE_VALIDATION_FAILED",
    extra={
        "record_id": str(medical_record.public_id),
        "field": "diagnosis",  # o "treatment"
        "user_id": request.user.id,
        "organization_id": request.user.organization_id,
    },
)
```

Esto permite auditoría y soporte: se puede rastrear qué usuarios intentaron cerrar consultas incompletas y qué campos faltaron.

## Impacto en tests

### Tests modificados

| Test | Antes | Después |
|------|-------|---------|
| `test_close_general_sin_treatment` | 200 | **400** |
| `test_close_cirugia_sin_treatment` | 400 (solo surgery) | 400 (todos menos vaccine) |

### Tests nuevos

| Test | Esperado |
|------|----------|
| `test_create_sin_treatment_retorna_201` | 201 (CREATE sin treatment es válido) |
| `test_create_sin_diagnosis_retorna_400` | 400 (diagnosis sigue obligatorio) |
| `test_close_emergency_sin_treatment_retorna_400` | 400 |
| `test_close_vaccine_sin_treatment_retorna_200` | 200 (excepción vaccine) |
| `test_close_validation_failure_emits_warning_log` | log emitido |

## Alternativas consideradas

### A: Mantener validación en CREATE
**Rechazado**: Rompe el flujo del stepper. Requeriría refactor mayor para permitir "guardar borrador" sin validación.

### B: Validar treatment en CREATE pero permitir vacío
**Rechazado**: Inconsistente. Si es obligatorio, debe serlo siempre. Si no, no debe bloquear CREATE.

### C: Excepción para surgery solamente
**Parcialmente adoptado**: La excepción es para `VACCINE`, no para `surgery`. Cirugía **siempre** requiere tratamiento documentado.

## Estado de la consulta

| Estado | Acciones permitidas |
|--------|---------------------|
| `open` | PATCH, POST vitals, POST products, POST services |
| `closed` | Solo GET. Cualquier mutación retorna 403 |

## Relación con otros ADRs

- **ADR-01** (No refactor de módulos en v1): Este fix es quirúrgico, no requiere mover modelos.
- **ADR-05** (Sanitización en serializers): `sanitize_text()` se aplica antes de validar vacío.
- **ADR-08** (Dos gates de autorización): `assert_can_modify_medical_record` para vitales, `assert_can_modify_charges` para billing.

## Deuda técnica

Ninguna. La separación CREATE/CLOSE es el diseño correcto para un flujo clínico con stepper.
