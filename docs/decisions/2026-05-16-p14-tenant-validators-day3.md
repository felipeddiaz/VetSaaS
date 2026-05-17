# ADR p14: Tenant validators en serializers — Día 3 (P0 #8-9)

**Fecha:** 2026-05-16
**Estado:** Implementado (Fase 1 hotfix). Fase 2 (extracción a mixin) planificada post-beta.
**Impacto:** `billing`, `prescriptions`. Tangencial: `core` (logging).
**Sigue a:** ADR p12 (concurrencia) + ADR p13 (remediación Día 1-2)

---

## Contexto

Tras Días 1-2 (concurrencia cerrada) quedaban 2 P0 multitenant pre-beta:

- **P0 #8 — `InvoiceSerializer`** (`backend/apps/billing/serializers.py:140-181`): sin tenant check para `owner / pet / appointment / medical_record`. Defensa única era `Invoice.clean()` (`billing/models.py:132-141`) que levantaba `django.core.exceptions.ValidationError` — DRF no la mapeaba a 400 y devolvía **HTTP 500** crudo. Cliente podía crear Invoice con FKs cross-org y exponer error interno + enumeración de PKs cross-tenant antes del crash.

- **P0 #9 — `PrescriptionItemSerializer` + `PrescriptionItemWriteSerializer`** (`prescriptions/serializers.py`): ninguno validaba tenant en `product`. `WriteSerializer` solo chequeaba `requires_prescription`. Cliente podía referenciar `Product` de otra organización; el render del PDF (`prescription_pdf`) imprimía nombre + presentación → **leak en el PDF entregado al paciente**.

El codebase ya tiene **7 sitios** con el patrón `if x and x.organization != request.user.organization: raise ValidationError('Acceso inválido')` (en `medical_records/serializers.py`, `prescriptions/serializers.py::PrescriptionSerializer`, `appointments/serializers.py`). Añadir 5+ sitios más en Día 3 consolidaba la deuda.

---

## Decisiones rechazadas (y por qué)

### Opción A — Copia-pega de 5 validators más
Rechazada: agrega 5 sitios duplicados, drift de mensajes (`'Acceso inválido.'` vs `'Acceso inválido'`), drift de acceso (`self.context['request']` hard vs `.get()` defensive), sin observabilidad.

### Opción B — Promoción a `TenantScopedSerializerMixin` + `TenantScopedPrimaryKeyRelatedField` en `apps/core/`
Arquitectónicamente correcta, pero rechazada por **timing pre-beta + blast radius**:

1. **Cambio de contrato API silencioso** — `TenantScopedPrimaryKeyRelatedField` produce `"Invalid pk \"12\" - object does not exist"` (mensaje DRF interno en inglés) en lugar de `"Acceso inválido."` (español, canónico). Rompe snapshots de frontend, mezcla idiomas, descalibra parsers de error.
2. **Cambio de filosofía semántica** — el proyecto sigue "el recurso existe pero no puedes acceder" (400 + `'Acceso inválido'`). El field tenant-scoped cambia a "no existe" (404-ish). Decisión arquitectónica que requiere ADR propio + consenso, no hotfix P0.
3. **Saturación de `TENANT_MISMATCH_DETECTED`** — ese evento hoy es ERROR severity ("intento real → investigar inmediato"). Si se emite también en cada typo de UI / ID stale del frontend, mata la señal operacional.
4. **Side effects en `validate()` legacy** — los serializers de `billing/appointments/medical_records` ya tienen lógica compleja en `validate()`. Un mixin que llama `super().validate()` y luego revalida tenant puede alterar el orden de validación e introducir bugs sutiles solo visibles en staging.
5. **DRF caching de fields + nested serializers** — `PrimaryKeyRelatedField.get_queryset()` dinámico tiene comportamiento implícito en nested many=True, partial updates, admin reuse. Riesgo framework-level.
6. **`apps/core/` promueve "infra oficial"** — todos los módulos futuros dependerían del mixin antes de battle-testing.
7. **Blast radius** — un hotfix mal local rompe 1 endpoint; una abstracción transversal mal puede romper N serializers a la vez. Pre-beta = mínima incertidumbre.

---

## Decisión adoptada: helper local + 4 fixes quirúrgicos

### Fix 1 — Helper local `_validate_same_org` + 4 `validate_<fk>` en `InvoiceSerializer`

Helper de 25 líneas inline en `billing/serializers.py` (duplicado idéntico en `prescriptions/serializers.py`). Centraliza:
- Comparación `value.organization_id != request.user.organization_id`
- Emisión de log estructurado `TENANT_VALIDATION_REJECTED` (WARNING)
- Manejo de `None` (FKs opcionales) y atributos faltantes (defensivo)

Validators DRF estándar por field (no mixin), invocados con `_get_request()` que aplica `.get('request')` + `assert is not None`. Patrón canónico del proyecto — ver memoria [feedback-serializer-context-access].

```python
def validate_owner(self, owner):
    return _validate_same_org(owner, self._get_request(), 'owner', 'InvoiceSerializer')
# ... pet, appointment, medical_record
```

### Fix 2 + Fix 3 — Tenant check en ambos `PrescriptionItem(Write)Serializer`

`PrescriptionItemWriteSerializer.validate_product` añade tenant check **antes** del `requires_prescription` existente (no revelar atributos de productos cross-org).

`PrescriptionItemSerializer.validate_product` se agrega nuevo — DRF propaga `context` del parent `PrescriptionSerializer` al nested item. El assert protege contra reuse fuera de DRF (admin, shell, tests directos).

### Fix 4 — Bug PATCH parcial en `InvoiceSerializer.validate()` (incluido tras feedback usuario)

`InvoiceSerializer.validate()` exigía `pet` incluso en PATCH minimalistas (`{"notes": "x"}`) porque chequeaba `data['pet']` sin considerar el `instance` existente. Bloqueaba flujos UX legítimos. Fix mecánico de 4 líneas — resolver con fallback al instance:

```python
owner = data.get('owner', getattr(self.instance, 'owner', None))
pet = data.get('pet', getattr(self.instance, 'pet', None))
```

Originalmente out-of-scope; incluido en Día 3 porque tocábamos el mismo serializer y el bug afecta UX real (PATCH minimalistas). Cubierto por 5 tests de regresión (T1.b).

### Decisión observabilidad: nuevo evento `TENANT_VALIDATION_REJECTED`

Logger nuevo: `apps.tenant_validation` → handler `rbac_console` (JSON estructurado, ya configurado para Railway).

**Por qué no reusar `TENANT_MISMATCH_DETECTED`:**
- `TENANT_MISMATCH_DETECTED` (ERROR severity) emitido por `HybridPermission.has_object_permission` en `core/permissions.py:281, 346` — significa "intento real de acceso object-level cross-org, investigar".
- `TENANT_VALIDATION_REJECTED` (WARNING severity) emitido por serializers — incluye typos de UI, IDs stale, retry races, error humano. Mucha mayor frecuencia esperada.

Mezclarlos saturaría la señal operacional y mataría el valor del evento ERROR. Separación explícita en `settings.py LOGGING.loggers`:

```python
'apps.tenant_validation': {
    'handlers': ['rbac_console'],
    'level': 'WARNING',
    'propagate': False,
},
```

### Decisión sobre `Invoice.clean()`: se mantiene como app-side defense-in-depth (legacy residue)

`Invoice.clean()` valida que `owner / pet / appointment / medical_record` pertenezcan a `invoice.organization`. NO es DB-side (no es CHECK constraint, no es trigger). Es lógica Python que solo dispara en `full_clean()`, no automáticamente en `save()`.

Se mantiene en Día 3 como app-side defense-in-depth (cubre callers no-DRF: shell, admin, mgmt commands, tests directos al ORM). Pero se etiqueta explícitamente como **legacy residue** para migración futura:

- **Fase 2A**: extraer validación a `billing/services.py::create_invoice()` (single authoritative writer).
- **Fase 2B**: agregar DB-level CHECK constraint o trigger PL/pgSQL que enforce `invoice.organization = owner.organization = pet.organization = ...`. Esto sí es defense-in-depth real (sobrevive bypass de Python).

---

## Plan Fase 2 (post-beta, sprint dedicado)

Cuando los helpers locales hayan acumulado ≥4 semanas de uptime sin issues:

1. **Extraer `TenantScopedSerializerMixin`** a `apps/core/serializers.py`:

```python
class TenantScopedSerializerMixin:
    tenant_fields: list[str] = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if request is None or not hasattr(request, 'user'):
            return attrs
        user_org_id = getattr(request.user, 'organization_id', None)
        if user_org_id is None:
            return attrs
        errors = {}
        for field in self.tenant_fields:
            obj = attrs.get(field)
            if obj is None:
                continue
            obj_org_id = getattr(obj, 'organization_id', None)
            if obj_org_id and obj_org_id != user_org_id:
                # emit TENANT_VALIDATION_REJECTED + accumulate error
                errors[field] = ['Acceso inválido.']
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
```

2. **Migrar 9 sitios** a usar el mixin (los 2 nuevos de Día 3 + los 7 pre-existentes):
   - `apps/billing/serializers.py::InvoiceSerializer` → `tenant_fields = ['owner', 'pet', 'appointment', 'medical_record']`
   - `apps/prescriptions/serializers.py::PrescriptionSerializer` → `['medical_record', 'pet']`
   - `apps/prescriptions/serializers.py::PrescriptionItem(Write)Serializer` → `['product']`
   - `apps/medical_records/serializers.py` (2 clases con `validate_pet/appointment/veterinarian/medical_record`)
   - `apps/appointments/serializers.py` (1 clase con `validate_pet`)

3. **Eliminar helpers locales** `_validate_same_org` de `billing/serializers.py` y `prescriptions/serializers.py`.

4. **Evaluar `TenantScopedPrimaryKeyRelatedField`** — requiere coordinación con frontend (mensajes UX en inglés vs español). Decisión arquitectónica separada (¿404 vs 400 para cross-tenant?).

5. **Migrar `Invoice.clean()`** a `billing/services.py::create_invoice()` + CHECK constraint DB.

---

## Trade-offs explícitos aceptados

| Trade-off | Estado |
|-----------|--------|
| ✅ Resuelve P0 #8-9 sin tocar API contract ni semantics | OK |
| ✅ Centraliza body del check + logging en 1 helper local por archivo | OK |
| ✅ Evento de log separado (WARNING vs ERROR) preserva señal de `TENANT_MISMATCH_DETECTED` | OK |
| ✅ Sin mixin, sin field subclass, sin `apps/core/` promotion, sin `@expectedFailure` | OK |
| ✅ Fix 4 PATCH partial resuelto (no documentado como deuda) | OK |
| ⚠️ Helper duplicado en 2 archivos (billing + prescriptions) | Aceptable — Fase 2 elimina |
| ⚠️ 7 sitios pre-existentes con `validate_<fk>` duplicado siguen | Documentado, Fase 2 |
| ⚠️ `Invoice.clean()` legacy residue sigue activo | Documentado, Fase 2B |

---

## Tests agregados

### `backend/apps/billing/tests/test_invoice_multitenancy.py` (extender)

**T1.a — Tests P0 #8 (6 nuevos):**
- `test_invoice_create_cross_tenant_owner_returns_400`
- `test_invoice_create_cross_tenant_pet_returns_400`
- `test_invoice_create_cross_tenant_appointment_returns_400`
- `test_invoice_create_cross_tenant_medical_record_returns_400`
- `test_cross_tenant_emits_tenant_validation_rejected_log` (assertLogs `apps.tenant_validation`)
- `test_invoice_same_org_fks_passes` (smoke positivo)

**T1.b — Tests Fix 4 PATCH partial (8 nuevos):**
- `test_patch_notes_only_succeeds`
- `test_patch_status_only_succeeds`
- `test_patch_owner_same_org_preserves_existing_pet`
- `test_patch_owner_cross_org_returns_400`
- `test_patch_explicit_null_pet_returns_400`
- `test_patch_does_not_overwrite_existing_fk_when_omitted`
- `test_create_without_pet_still_returns_400` (no regresión)
- `test_create_with_generic_owner_forces_direct_sale` (no regresión)

### `backend/apps/prescriptions/tests/test_multitenancy.py` (nuevo dir + archivo)

**T2 — Tests P0 #9 (7 nuevos):**
- `test_create_prescription_with_nested_cross_tenant_product_returns_400`
- `test_create_prescription_with_nested_same_org_product_succeeds`
- `test_add_item_endpoint_cross_tenant_product_returns_400`
- `test_add_item_endpoint_same_org_product_without_requires_prescription_returns_domain_error` (verifica orden: tenant primero, requires_prescription después)
- `test_cross_tenant_emits_tenant_validation_rejected_log`
- `test_patch_prescription_replace_items_cross_tenant_product_returns_400` (nested update edge case)
- `test_patch_prescription_notes_only_does_not_touch_items`

---

## Métricas de validación

- `python manage.py check` → no issues
- `python manage.py test apps.billing.tests.test_invoice_multitenancy` → **20/20 OK** (6 originales + 14 nuevos)
- `python manage.py test apps.prescriptions.tests.test_multitenancy` → **7/7 OK**
- Logs estructurados verificados: `TENANT_VALIDATION_REJECTED source='serializer'` con todos los campos requeridos
- Suite completa CLAUDE.md sin regresión (corrida final pendiente)

---

## Referencias

- `docs/decisions/2026-05-16-p12-concurrency-lock-order-hardening.md` — sprint Días 1-2
- `docs/decisions/2026-05-16-p13-day12-concurrency-remediation.md` — remediación Día 1-2
- `docs/decisions/2026-05-09-p9-analytics-anchor-authority.md` — patrón "single authoritative writer"
- `CLAUDE.md` sección "Validación de FKs en serializers" — actualizada con regla `.get() + assert`
- Memoria `feedback-serializer-context-access.md` — preferencia del usuario sobre acceso defensivo a context
- Memoria `feedback-invoice-item-f-expression.md` — patrón "abstracción local antes que promoción prematura a core"
