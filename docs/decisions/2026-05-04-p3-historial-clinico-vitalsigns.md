# ADR: Rediseño estructural del historial clinico P3

**Fecha**: 2026-05-04  
**Estado**: Implementado

## Contexto

El modulo `medical_records` tenia un modelo plano que ya no escalaba para la UI con stepper de 4 pasos, panel lateral persistente y timeline clinico enriquecido.

Los problemas concretos:
- No habia forma de clasificar el tipo de consulta (general vs cirugia vs vacuna vs emergencia)
- No existia historial de signos vitales — el peso era un campo plano en `MedicalRecord`, sin historia
- No habia endpoint de summary para el panel lateral: el frontend hacia multiples requests independientes
- El cierre de consulta no validaba que el diagnostico estuviera completo

## Decisiones implementadas

### 1. Campo `consultation_type` en MedicalRecord

Se agrego `consultation_type` con choices `general | vaccine | surgery | emergency` y default `general`.

Motivo: el tipo de consulta condiciona el flujo clinico y las validaciones en cierre. Una cirugia sin `treatment` documentado no deberia poder cerrarse.

Migracion: `medical_records.0012_add_consultation_type` (AddField con default, sin data migration).

---

### 2. Modelo VitalSigns — append-only

Se creo el modelo `VitalSigns` con campos `weight`, `temperature`, `heart_rate`, `respiratory_rate`, `recorded_by`, `recorded_at`.

Decisiones de diseno:

**Append-only**: no hay endpoints PATCH ni DELETE. Cada medicion es un registro nuevo e inmutable. Razon: los datos clinicos tienen valor historico; modificar un vital pasado seria incorrecto desde el punto de vista medico.

**`recorded_at` en lugar de solo `created_at`**: `created_at` representa el ingreso al sistema (auto, inmutable). `recorded_at` representa el momento clinico real, que puede diferir en importaciones o carga tardia de datos. Todos los `order_by` sobre vitales usan `('-recorded_at', '-created_at')`.

**Sin `public_id`**: `VitalSigns` es un modelo interno como `MedicalRecordService`. El ID secuencial es suficiente, no se expone en URLs publicas independientes.

**`organization` en `save()`**: se asigna automaticamente desde `medical_record.organization` como defensa en profundidad. El `perform_create` tambien lo asigna explicitamente, pero el `save()` garantiza consistencia ante llamadas directas a `.create()`.

Migracion: `medical_records.0013_create_vitalsigns`.

---

### 3. Coexistencia de MedicalRecord.weight y VitalSigns.weight

`MedicalRecord` tenia un campo `weight` existente con datos en produccion y logica `force_weight` en el serializer.

Alternativas consideradas:
- A) Migrar todos los datos a `VitalSigns` en v1 — invasivo, alto riesgo de datos
- B) Eliminar `MedicalRecord.weight` — rompe compatibilidad con registros historicos
- C) Coexistencia en v1, migracion formal en v2 — elegida

En v1 ambos campos coexisten. Los helpers centrales priorizan `VitalSigns`:
- `_get_last_weight(pet)`: ultimo peso global del paciente (busca VitalSigns primero, luego MedicalRecord)
- `get_current_weight(record)`: peso a mostrar en el panel lateral de una consulta (idem)

La funcion `_validate_weight_change` es compartida entre `MedicalRecordSerializer` y `VitalSignsSerializer`. La logica de deteccion de cambio brusco de peso ahora consulta ambas fuentes via `_get_last_weight`.

---

### 4. `force_weight` declarado como campo de serializer

Antes: `force_weight` se leia de `request.data` manualmente, sin documentacion en el schema.

Ahora: se declara como `BooleanField(write_only=True, required=False, default=False)` en ambos serializers (`MedicalRecordSerializer` y `VitalSignsSerializer`). Ventaja: aparece en el schema OpenAPI generado automaticamente y el frontend puede "verlo".

La lectura usa `bool(self.initial_data.get('force_weight', False))` para accederlo antes del ciclo de validacion del campo.

---

### 5. Endpoint summary — agregador para el panel lateral

Se creo `GET /api/medical-records/<pk>/summary/` para eliminar el patron de multiples requests que el frontend necesitaria para poblar el panel lateral.

El endpoint retorna en una sola respuesta: datos del paciente, ultimo vital, diagnostico, tipo de consulta, totales de factura y proxima vacuna.

Detalles tecnicos:
- `for_organization()` siempre va primero en la cadena de queryset (antes de `select_related`/`prefetch_related`)
- `VaccineRecord` no se hace prefetch desde `MedicalRecord` porque la relacion correcta es `VaccineRecord → pet`, no `VaccineRecord → medical_record`
- `last_vitals.weight` usa `get_current_weight(record)` (helper central) para no duplicar logica
- Los `Decimal` se devuelven sin `str()`: DRF los serializa correctamente a JSON

---

### 6. Dos gates de autorizacion en policies.py

`assert_can_modify_charges` existia para productos y servicios (dominio billing).

Se creo `assert_can_modify_medical_record` para datos clinicos puros (signos vitales). Aunque ambos bloquean si la consulta esta `closed`, son semanticamente distintos:
- `assert_can_modify_charges`: gate billing — valida org + estado + ownership del VET
- `assert_can_modify_medical_record`: gate clinico — valida org + estado

No mezclar. Usar el gate correcto segun el dominio del dato que se esta modificando.

---

### 7. HybridPermission: inferencia incorrecta de accion para sub-recursos anidados

**Problema**: `HybridPermission._method_to_action` distingue `list` de `retrieve` buscando `pk` en los kwargs. Para `VitalSignsListCreateView` registrada como `/medical-records/<pk>/vitals/`, el `pk` del registro padre hace que GET se mapee a `retrieve` en lugar de `list`.

**Solucion**: declarar `required_permission` explicitamente en `initial()` segun el metodo HTTP:

```python
def initial(self, request, *args, **kwargs):
    if request.method == 'GET':
        self.required_permission = 'medicalrecord.vitals.list'
    else:
        self.required_permission = 'medicalrecord.vitals.create'
    return super().initial(request, *args, **kwargs)
```

**Regla derivada**: para cualquier vista de lista anidada bajo una URL con `<pk>` de otro recurso, no confiar en la inferencia automatica de `HybridPermission`. Declarar `required_permission` explicitamente.

---

### 8. Validacion de cierre con campos obligatorios

El endpoint `close_medical_record` no validaba contenido clinico antes de cerrar.

Ahora antes de ejecutar el bloqueo de transaccion, se valida:
- `diagnosis` no puede estar vacio (todos los tipos)
- `treatment` no puede estar vacio si `consultation_type = surgery`

Si la consulta ya estaba `closed`, retorna `200` directamente sin re-validar (idempotencia se preserva).

---

## Nuevos permisos RBAC

| Codigo | VET | ASSISTANT |
|--------|:---:|:---------:|
| `medicalrecord.vitals.create` | ✅ | ❌ |
| `medicalrecord.vitals.list` | ✅ | ✅ |
| `medicalrecord.summary.retrieve` | ✅ | ✅ |

Requiere `python manage.py seed_permissions` en el proximo deploy para persistir en DB.

---

## Tests

Se agregaron 5 tests en `test_close.py` (validacion de cierre con tipos) y 19 tests en `test_vitals.py` (POST/GET vitales, RBAC, summary, fallbacks de peso). Total suite: 87 tests, todos en verde.

## Deuda tecnica generada

- Migrar `MedicalRecord.weight` a `VitalSigns` (data migration + eliminar campo heredado) — diferido a v2
