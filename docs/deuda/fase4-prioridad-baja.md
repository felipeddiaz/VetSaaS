# Fase 4 — Deuda prioridad baja (mejoras arquitectónicas)

Items que NO son bugs ni vulnerabilidades, sino decisiones arquitectónicas que mejoran el sistema a largo plazo. Resolver después de Fases 2-3 o cuando un sprint específico lo requiera.

---

## C1 — Decisión semántica: cross-tenant access → 400 "Acceso inválido" vs 404 "Not found"

**Origen:** ADR p14 — decisión rechazada en Día 3.

**Filosofía actual del proyecto:** "el recurso existe pero no puedes acceder" → 400 + `'Acceso inválido.'`. Aplicado en todos los serializers (Día 3 mantiene este patrón).

**Alternativa más fuerte (404 "Not found"):** ocultar incluso la existencia del PK. Requiere:
- `TenantScopedPrimaryKeyRelatedField` con `queryset=Model.objects.for_organization(org)` — FK foreign no resuelve → "Invalid pk... object does not exist".
- Frontend actualizado para parsear mensaje DRF interno (inglés) o backend traduce.
- ADR explícito documentando el cambio de contrato API.

**Trade-offs:**

| Filosofía | Pro | Con |
|-----------|-----|-----|
| **400 "Acceso inválido"** (actual) | Mensaje en español, parsers de error consistentes, frontend ya integrado | Revela existencia del PK (enumeración cross-tenant posible) |
| **404 "Not found"** | Aislamiento más fuerte, no revela PKs, alineado con REST best-practices | Cambio de contrato API, requiere coordinación frontend, mensajes en inglés (DRF default) o traducción custom |

**Bloqueado por:** decisión arquitectónica + coordinación con equipo frontend + ADR.

**Criterio de cierre (si se decide migrar):**
- ADR explícito documentando trade-off.
- `TenantScopedPrimaryKeyRelatedField` extraído a `apps/core/fields.py`.
- Mensajes 404 traducidos al español (custom error handler).
- Frontend tests E2E actualizados.
- Backwards compat por 1-2 releases (200 → 404).

**Estimación:** 1 sprint completo (incluye coordinación + frontend + ADR + tests).

---

## C2 — `InvoiceSerializer.validate()` acoplamiento de reglas (generic owner forces direct_sale)

**Origen:** Pre-existente. `InvoiceSerializer.validate()` (`billing/serializers.py:191-204` post-Día 3) implementa:

```python
if owner and getattr(owner, 'is_generic', False):
    data['invoice_type'] = 'direct_sale'   # ← side effect
elif pet is None and not (owner and getattr(owner, 'is_generic', False)):
    raise serializers.ValidationError(...)
```

**Problema arquitectónico:** el `validate()` MUTA `data['invoice_type']` (side effect) en lugar de validar. Esto es lógica de dominio en el serializer, no validación.

**Riesgo bajo (funciona, no es bug):** pero:
- Mezcla validación con mutación.
- Si un caller no-DRF llama `Invoice.objects.create(...)` con `owner=<generic>, invoice_type='consultation'`, el create NO fuerza `direct_sale`. Solo el serializer lo hace.
- Source-of-truth del "generic owner forces direct_sale" está en el serializer, no en `Invoice.save()` ni en `services.py`.

**Solución (post Fase 2 A2):** mover la regla al service-layer junto con la migración de `Invoice.clean()`:

```python
# apps/billing/services.py
@transaction.atomic
def create_invoice(*, organization, owner, pet=None, invoice_type='consultation', **fields):
    if owner.is_generic:
        invoice_type = 'direct_sale'   # regla autoritativa
    if not owner.is_generic and pet is None:
        raise ValidationError("La mascota es requerida para ventas con cliente registrado.")
    # ... validación de tenant (heredada de A2)
    return Invoice.objects.create(
        organization=organization, owner=owner, pet=pet,
        invoice_type=invoice_type, **fields,
    )
```

`InvoiceSerializer.validate()` se reduce a validación pura (sin mutación).

**Bloqueado por:** A2 (Invoice.clean() migration). Hacer en el mismo sprint que A2.

**Criterio de cierre:**
- Regla "generic owner → direct_sale" centralizada en `services.py`.
- `InvoiceSerializer.validate()` sin side effects (sin `data['invoice_type'] = ...`).
- Tests directos al service confirman regla.
- Tests DRF (test_invoice_multitenancy) siguen pasando.

**Estimación:** 1 día (post A2).

---

## Tracking

Cuando un item se cierre, mover a `docs/deuda/cerrado/` con su PR asociado + fecha de cierre.
