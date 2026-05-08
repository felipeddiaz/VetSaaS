# ADR: PATCH en lugar de PUT para actualizaciones parciales

**Fecha**: 2026-05-05  
**Estado**: Implementado

## Contexto

El stepper de consultas usa actualizaciones parciales:
- **Paso 1**: envía solo `diagnosis`, `consultation_type`, `notes`
- **Paso 2**: envía solo `treatment` y signos vitales
- **Paso 3**: agrega productos (endpoint separado)

Originalmente, el frontend usaba `PUT /api/medical-records/<id>/` para actualizar el registro. En DRF, `PUT` significa "reemplazo completo del recurso", lo que implica:
- Todos los campos requeridos deben enviarse
- Campos omitidos pueden validarse como faltantes
- `organization` (heredado de `OrganizationalModel`) es `blank=False` → inferido como `required=True`

## Problema

El stepper enviaba solo campos parciales en cada paso. Cuando el backend recibía un `PUT` sin `organization`, DRF rechazaba la request:

```json
{
  "code": "validation_error",
  "errors": {
    "organization": ["Valor inválido."]
  }
}
```

Esto rompía el avance del Paso 2 al Paso 3.

## Decisión

### 1. Backend: `organization` en `read_only_fields`

En `MedicalRecordSerializer.Meta`:

```python
read_only_fields = [
    'id', 'public_id', 'created_at', 'prescription_id', 'invoice_id',
    'status', 'closed_at', 'closed_by',
    'organization',  # ← NUNCA debe venir del cliente
]
```

**Razón de seguridad**: `organization` define el tenant. Nunca debe ser modificable por el cliente, ni siquiera accidentalmente.

### 2. Backend: Override de `update()` como defensa extra

```python
def update(self, instance, validated_data):
    # Defensa: bloquear mutación de consulta cerrada
    if instance.status == MedicalRecord.Status.CLOSED:
        raise serializers.ValidationError({
            "non_field_errors": ["No se puede modificar una consulta cerrada."]
        })
    # Defensa: ignorar cualquier intento de cambiar organization
    validated_data.pop('organization', None)
    return super().update(instance, validated_data)
```

**Dos propósitos**:
1. Bloqueo de consultas cerradas a nivel serializer (defensa en profundidad, además del view layer)
2. Ignorar silenciosamente cualquier `organization` enviado (aunque `read_only_fields` ya lo bloquea)

### 3. Frontend: `PUT` → `PATCH` en todos los endpoints de actualización parcial

Archivos modificados:
- `api/medicalRecords.js:26`
- `api/pets.js:17`
- `api/inventory.js:13`
- `api/prescriptions.js:16`
- `api/billing.js:11`
- `api/appointments.js:16`

**Razón**: `PATCH` es semánticamente correcto para actualizaciones parciales. DRF `ModelViewSet` acepta `PATCH` nativamente.

### 4. Tests agregados

```python
def test_patch_without_organization_returns_200(self):
    """PATCH parcial (stepper) no requiere organization."""
    mr = self._make_record()
    self.client.force_authenticate(self.vet_a)
    r = self.client.patch(self._detail_url(mr.pk), {
        "treatment": "nuevo tratamiento",
    }, format="json")
    self.assertEqual(r.status_code, status.HTTP_200_OK)
    mr.refresh_from_db()
    self.assertEqual(mr.treatment, "nuevo tratamiento")

def test_patch_organization_is_ignored(self):
    """Intentar cambiar organization vía PATCH es ignorado."""
    mr = self._make_record()
    original_org = mr.organization_id
    self.client.force_authenticate(self.vet_a)
    r = self.client.patch(self._detail_url(mr.pk), {
        "organization": 999,
    }, format="json")
    self.assertEqual(r.status_code, status.HTTP_200_OK)
    mr.refresh_from_db()
    self.assertEqual(mr.organization_id, original_org)
```

## Impacto multi-tenant

Esta decisión **no es solo conveniencia**, es seguridad:

| Escenario | Antes (PUT) | Después (PATCH + read_only) |
|-----------|-------------|-----------------------------|
| Usuario legítimo envía partial | 400 si falta org | 200, org ignorada |
| Usuario malicioso intenta cambiar org | Podría pasar validación | Ignorado silenciosamente |
| Nuevo campo requerido agregado al modelo | PUT se rompe | PATCH sigue funcionando |

## Alternativas consideradas

### A: Hacer `organization` opcional en el modelo
**Rechazado**: `organization` es fundamental para el aislamiento multi-tenant. No puede ser opcional.

### B: Inyectar `organization` en `perform_update`
**Parcialmente adoptado**: El view ya inyecta `organization` en `perform_create`, pero para `update` el objeto ya existe. Mejor es hacer `organization` read-only.

### C: Mantener PUT pero enviar todos los campos
**Rechazado**: Frágil. Cualquier campo nuevo requerido en el futuro rompería el stepper.

## Auditoría de endpoints PUT restantes

Todos los `updateX()` en `api/*.js` fueron convertidos a `PATCH`:

| Archivo | Endpoint | Riesgo antes | Después |
|---------|----------|--------------|---------|
| `medicalRecords.js` | `medical-records/<id>/` | **Alto** (stepper parcial) | ✅ |
| `pets.js` | `pets/<id>/` | Medio (form completo) | ✅ |
| `inventory.js` | `inventory/products/<id>/` | Medio | ✅ |
| `prescriptions.js` | `prescriptions/<id>/` | Bajo (sin uso activo) | ✅ |
| `billing.js` | `billing/services/<id>/` | Medio | ✅ |
| `appointments.js` | `appointments/<id>/` | Bajo (envía completo) | ✅ |

## Relación con otros ADRs

- **ADR-01** (No refactor de módulos en v1): Fix quirúrgico, sin mover modelos.
- **ADR-04** (Audit log en pay_invoice): Ídem — seguridad por capas.

## Deuda técnica

Ninguna. PATCH es el estándar HTTP para actualizaciones parciales.
