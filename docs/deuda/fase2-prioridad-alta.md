# Fase 2 — Deuda prioridad alta (post-beta inmediato)

Items que **no bloquean beta** pero deben resolverse en el primer sprint post-launch. Todos tienen scope acotado y plan de migración documentado.

---

## A1 — Extracción de `TenantScopedSerializerMixin` + migración de 9 sitios

**Origen:** ADR p14 — Día 3 dejó dos helpers locales (`_validate_same_org`) duplicados en `billing/serializers.py` y `prescriptions/serializers.py`. Hay 7 sitios pre-existentes con el patrón `if x and x.organization != request.user.organization: raise ValidationError('Acceso inválido')` copy-pasted.

**Riesgo si no se cierra:**
- Drift semántico (mensajes inconsistentes: `'Acceso inválido.'` vs `'Acceso inválido'` sin punto).
- Drift de acceso al context (`['request']` vs `.get()`).
- Olvido humano al agregar FKs nuevos.
- Observabilidad inconsistente (algunos sitios emiten log, otros no).

**Solución:**

```python
# apps/core/serializers.py (nuevo)
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
                tenant_logger.warning("TENANT_VALIDATION_REJECTED", extra={...})
                errors[field] = ['Acceso inválido.']
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
```

**Sitios a migrar (9 total):**

| Archivo | Clase | `tenant_fields` |
|---------|-------|-----------------|
| `apps/billing/serializers.py` | `InvoiceSerializer` | `['owner', 'pet', 'appointment', 'medical_record']` |
| `apps/prescriptions/serializers.py` | `PrescriptionSerializer` | `['medical_record', 'pet']` |
| `apps/prescriptions/serializers.py` | `PrescriptionItemSerializer` | `['product']` |
| `apps/prescriptions/serializers.py` | `PrescriptionItemWriteSerializer` | `['product']` |
| `apps/medical_records/serializers.py` (clase 1) | (verificar) | `['pet', 'appointment', 'veterinarian']` |
| `apps/medical_records/serializers.py` (clase 2) | (verificar) | `['pet', 'medical_record']` |
| `apps/appointments/serializers.py` | (verificar) | `['pet']` |

**Criterio de cierre:**
- Mixin en `apps/core/serializers.py` con unit tests (`apps/core/tests/test_tenant_serializer_mixin.py`).
- 9 sitios migrados — `_validate_same_org` helpers locales eliminados.
- Suite completa sin regresión.
- ≥4 semanas de uptime de los helpers locales antes de migrar (battle-testing).

**Estimación:** 1 sprint de 3-5 días (extracción + migración + tests + revisión cross-modular).

---

## A2 — `Invoice.clean()` → service-layer + DB CHECK constraint

**Origen:** ADR p14 — `Invoice.clean()` (`billing/models.py:132-141`) actúa como segunda barrera Python-side tras `InvoiceSerializer.validate_<fk>`. NO es DB-side (no es CHECK constraint, no es trigger).

**Riesgo si no se cierra:**
- Bypass de Python (raw SQL, mgmt commands, admin import) deja factura con FKs cross-org en DB.
- `full_clean()` solo dispara explícitamente — no en cada `save()`.
- Lanza `django.core.exceptions.ValidationError` (no `serializers.ValidationError`) — DRF NO la mapea → 500 si llega.

**Solución (2 sub-fases):**

### A2.a — Mover validación a `billing/services.py::create_invoice()`

```python
@transaction.atomic
def create_invoice(*, organization, owner, pet=None, appointment=None,
                   medical_record=None, **fields):
    if owner.organization_id != organization.pk:
        raise ValidationError("owner: organización no coincide")
    if pet and pet.organization_id != organization.pk:
        raise ValidationError("pet: organización no coincide")
    # ... appointment, medical_record
    return Invoice.objects.create(
        organization=organization, owner=owner, pet=pet, ...
    )
```

Endpoint actual `InvoiceListCreateView` delega al service. `Invoice.clean()` se mantiene como fallback transitorio.

### A2.b — DB CHECK constraint o trigger PL/pgSQL

```sql
-- Migración Django
ALTER TABLE billing_invoice ADD CONSTRAINT invoice_owner_same_org
    CHECK (organization_id = (SELECT organization_id FROM patients_owner WHERE id = owner_id));
```

CHECK referencial requiere subquery — Postgres lo permite via trigger BEFORE INSERT/UPDATE, o via FK compuesto `(organization_id, owner_id) REFERENCES patients_owner(organization_id, id)` si se agrega unique constraint compuesto en `Owner`.

Evaluar trade-off: trigger más flexible, FK compuesto más eficiente (sin row lookup adicional).

**Criterio de cierre:**
- Service `create_invoice` con tests directos (sin pasar por DRF).
- DB CHECK/trigger aplicado vía migración Django.
- `Invoice.clean()` eliminado (legacy residue removed).
- Tests directos de ORM con FKs cross-org → `IntegrityError` (no `ValidationError`).

**Estimación:** 1 sprint de 4-6 días (service + DB constraints + tests + smoke staging).

---

## A3 — `closed_at` writer fuera de service (`medical_records/views.py:432`)

**Origen:** ADR p9 establece "anchor writers solo en `services.py`". `medical_records/views.py::close_medical_record` (línea ~432) escribe `medical_record.closed_at = timezone.now()` + `closed_at_source = 'service'` desde la view directamente.

**Riesgo si no se cierra:**
- Viola contrato analítico (ADR p9). El `'service'` source es técnicamente falso — el writer es la view, no un service.
- Si un caller futuro (mgmt command, signal) necesita cerrar MR, debe duplicar la lógica.
- Inconsistente con `billing/services.py` (todos los anchor writers están en services).

**Solución:**

```python
# apps/medical_records/services.py (nuevo o existente)
@transaction.atomic
def close_medical_record(medical_record, user):
    mr = MedicalRecord.objects.for_organization(
        medical_record.organization
    ).select_for_update().get(pk=medical_record.pk)
    if mr.status == MedicalRecord.Status.CLOSED:
        return mr  # idempotente
    # ... validaciones existentes (treatment obligatorio si SURGERY, etc.)
    mr.status = MedicalRecord.Status.CLOSED
    mr.closed_at = timezone.now()
    mr.closed_at_source = 'service'
    mr.save(update_fields=['status', 'closed_at', 'closed_at_source', 'updated_at'])
    # ... logging MEDICAL_RECORD_CLOSED
    return mr
```

View se reduce a:

```python
@api_view(['POST'])
@permission_classes([make_permission("medicalrecord.close")])
def close_medical_record(request, pk):
    mr = resolve_public_id(
        MedicalRecord.objects.for_organization(request.user.organization), pk
    )
    try:
        close_medical_record_service(mr, user=request.user)
    except DjValidationError as e:
        return Response({'detail': e.messages}, status=400)
    mr.refresh_from_db()
    return Response(MedicalRecordSerializer(mr).data)
```

**Criterio de cierre:**
- `apps/medical_records/services.py::close_medical_record` único writer del anchor `closed_at`.
- `audit_anchor_integrity` confirma `closed_at_source='service'` para todos los rows nuevos.
- Tests existentes (`test_close.py`) pasan sin cambios.
- View reducida a wrapper delgado.

**Estimación:** 1-2 días (extracción + tests + verificación analytics).

---

## A4 — `MedicalRecordProduct.delete()` no se invoca en cascade

**Origen:** ADR p13 (remediación Día 1-2) flagged como deuda. Django ORM bypasea `model.delete()` custom cuando un padre es eliminado en cascada (usa `QuerySet._raw_delete`). Si se borra un `MedicalRecord`, los `MedicalRecordProduct` cascadeados se eliminan **sin revertir stock**.

**Riesgo si no se cierra:**
- Si en el futuro se expone endpoint de delete de MR (no existe actualmente), stock queda inconsistente silenciosamente.
- Tests no cubren este flujo porque MR delete no es operación expuesta.
- Documentado en `docs/modules/inventory.md` como deuda, pero el comentario puede perderse con refactors.

**Solución (3 opciones — evaluar cuando se necesite expose MR delete):**

### Opción 1 — Signal `pre_delete` en `MedicalRecord`
```python
@receiver(pre_delete, sender=MedicalRecord)
def reverse_stock_on_mr_delete(sender, instance, **kwargs):
    with transaction.atomic():
        for mrp in instance.products_used.all():
            mrp.delete()  # invoca custom delete → revierte stock
```
Trade-off: signal lento si hay muchos productos, pero garantiza reversión.

### Opción 2 — `services.py::delete_medical_record()` que itera explícitamente
```python
@transaction.atomic
def delete_medical_record(mr):
    for mrp in mr.products_used.select_for_update().all():
        mrp.delete(locked_presentation=...)  # custom delete con lock
    mr.delete()
```
Trade-off: requiere disciplina (no exponer MR.delete() directamente).

### Opción 3 — DB trigger AFTER DELETE en `inventory_medicalrecordproduct`
Reversa stock vía SQL puro. Trade-off: lógica de negocio fuera de Python, más difícil de testear.

**Criterio de cierre:**
- Decisión documentada (cuál opción).
- Tests que simulan MR delete y verifican stock restaurado.
- Endpoint expuesto (si se decide exponerlo) con permisos restrictivos.

**Estimación:** 2-3 días (solo cuando MR delete sea requisito de producto).

---

## A5 — Soft-delete real (`is_active` / `deleted_at`) en `Owner` / `Pet` / `Organization`

**Origen:** ADR p15 (Día 4 PR-4A) — el guard `_create_default_superuser` evita escalación, pero no hay defensa para casos de cascade destructivo donde la org/pet/owner se elimina y arrastra historial clínico, facturas, audits.

**Riesgo si no se cierra:**
- Un admin (o un bug de UI) que dispara `DELETE /api/organizations/<pk>/` (o equivalente) hoy borraría irreversiblemente todo el árbol multitenant.
- Sin soft-delete, `ProtectedError` (PR-4B) será frecuente en flujos legítimos (intentar borrar pet con citas históricas).
- No hay recuperación de borrados accidentales — el último estado conocido es el backup nightly.
- Compliance (GDPR-like): "right to be forgotten" exige delete real con auditoría, no truncate sin huella.

**Solución:**

```python
class SoftDeleteMixin(models.Model):
    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', editable=False,
    )

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])
```

Modelos afectados: `Owner`, `Pet`, `Organization`. `TenantManager.for_organization()` filtra `is_active=True` por default. Manager separado `.all_with_deleted()` para admin / audit.

**Criterio de cierre:**
- Migraciones por modelo (3 modelos × 1 migración cada uno).
- `TenantManager` actualizado + tests de aislamiento.
- Endpoints DELETE convertidos a soft delete (admin) o hard delete (ADMIN_SAAS only).
- Tests: borrar pet → no aparece en listados, MR históricos preservan FK.
- Documentación en `docs/modules/patients.md` y `organizations.md`.

**Estimación:** 5-7 días (3 modelos + manager + tests + endpoints + comunicación frontend).

---

## A6 — `InvoiceAuditLog.invoice` `CASCADE` → `SET_NULL` + snapshot `invoice_public_id_at_delete`

**Origen:** ADR p15 (Día 4 PR-4A) — flagged durante revisión de cascades en PR-4B scope.

**Riesgo si no se cierra:**
- `InvoiceAuditLog.invoice` está en `on_delete=CASCADE` (verificar en `apps/billing/models.py`). Borrar una Invoice elimina TODO el rastro de auditoría que justificaba sus transiciones de estado.
- Audit log es append-only por contrato (ADR p9). El cascade rompe ese contrato silenciosamente.
- Si un admin borra una Invoice por error, no queda registro de quién la creó, confirmó o pagó.

**Solución:**

1. Migración: `InvoiceAuditLog.invoice = models.ForeignKey(..., on_delete=models.SET_NULL, null=True)`.
2. Snapshot: añadir `invoice_public_id_at_delete = models.UUIDField(null=True, editable=False)` para preservar referencia legible.
3. Pre-delete signal en `Invoice` → poblar `invoice_public_id_at_delete = invoice.public_id` en todos los audit logs antes de nullear la FK.

**Criterio de cierre:**
- Migración aplicada + audit logs históricos preservados.
- Test: borrar Invoice → audit log queda con `invoice=None` + `invoice_public_id_at_delete` populated.
- Endpoint de query de audit logs por `invoice_public_id_at_delete` (admin tooling).

**Estimación:** 1-2 días.

---

## A7 — `MedicalRecord.veterinarian` snapshot `vet_name_at_close` cuando User borrado

**Origen:** ADR p15 (Día 4 PR-4A) — análogo a A6 pero para MR.

**Riesgo si no se cierra:**
- `MedicalRecord.veterinarian` con `on_delete=PROTECT` o `SET_NULL` (verificar). Si PROTECT, no se puede borrar VET con MR históricos. Si SET_NULL, se pierde atribución.
- Para reportería y compliance, el MR cerrado debe preservar quién fue el VET responsable.
- A7 es defense-in-depth: aunque A5 (soft-delete) cubra el caso típico, hay casos legítimos de hard-delete (ADMIN_SAAS por GDPR request).

**Solución:**

```python
class MedicalRecord(models.Model):
    veterinarian = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, ...)
    vet_name_at_close = models.CharField(max_length=255, blank=True, default='', editable=False)
    vet_email_at_close = models.EmailField(blank=True, default='', editable=False)
```

En `close_medical_record_service` (cuando A3 esté implementado), poblar `vet_name_at_close = vet.get_full_name() or vet.username` + `vet_email_at_close = vet.email`.

**Criterio de cierre:**
- Migración + backfill de MR cerrados existentes desde `veterinarian.get_full_name()`.
- Test: borrar VET → MR cerrado preserva `vet_name_at_close`.
- Display frontend prefiere `vet_name_at_close` si `veterinarian is None`.

**Estimación:** 1 día.

---

## Tracking

Cuando un item se cierre, mover a `docs/deuda/cerrado/` con su PR asociado + fecha de cierre + ADR de implementación.
