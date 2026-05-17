# Fase 3 — Deuda prioridad media (sprint dedicado)

Items que NO bloquean producto pero mejoran arquitectura y reducen surface area de bugs futuros. Resolver después de Fase 2.

---

## B1 — `apply_stock_movement` contrato caller-must-lock

**Origen:** ADR p13 (remediación Día 1-2). `apps/inventory/services.py::apply_stock_movement` hace `refresh_from_db()` (sin lock) para validar stock. Caller DEBE poseer `select_for_update()` sobre `presentation` externamente. Contrato documentado en docstring pero NO enforced en runtime.

**Riesgo:** próximo contribuidor agrega caller sin lock → race condition vuelve. Documentación de docstring puede perderse en refactor.

**Solución (3 opciones — evaluar trade-off):**

### Opción 1 — Lock-internal (defensivo, doble-lock cuando caller ya lockeó)
```python
def apply_stock_movement(presentation, quantity, movement_type, ...):
    locked = Presentation.objects.select_for_update().get(pk=presentation.pk)
    if movement_type == 'out':
        if locked.stock < quantity:
            raise ValidationError(...)
        Presentation.all_objects.filter(pk=locked.pk).update(stock=F('stock') - quantity)
    # ...
```
Trade-off: doble lock cuando caller ya lockeó (Postgres lo reutiliza, latencia mínima). Más simple para nuevos contribuidores.

### Opción 2 — Assert + runtime check (mantener contrato actual + fail-fast)
```python
def apply_stock_movement(presentation, ..., _caller_holds_lock=False):
    if not _caller_holds_lock:
        raise RuntimeError(
            "Caller debe pasar _caller_holds_lock=True y haber lockeado presentation. "
            "Ver docstring."
        )
    # ... lógica actual
```
Trade-off: parámetro feo, requiere disciplina pero es loud failure.

### Opción 3 — Postgres advisory lock por presentation_id (independente de SELECT FOR UPDATE)
```python
def apply_stock_movement(presentation, ...):
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)",
                    ['presentation', presentation.pk])
    # ... lógica con lock garantizado
```
Trade-off: lock independiente del row, más fuerte. Pero overhead.

**Criterio de cierre:**
- Decisión documentada (cuál opción).
- Tests de concurrencia que verifiquen que callers sin lock externo siguen siendo seguros (Opción 1) o fallan loud (Opción 2).
- Removed warning del docstring sobre contrato implícito.

**Estimación:** 2 días (decisión + implementación + tests).

---

## B2 — `PrescriptionItemSerializer` vs `PrescriptionItemWriteSerializer` duplicación

**Origen:** ADR p14 (post-review feedback). Ambos serializers representan el mismo dominio (`PrescriptionItem`), pero:
- `PrescriptionItemSerializer` (nested) NO valida `requires_prescription`
- `PrescriptionItemWriteSerializer` (endpoint dedicado) SÍ valida `requires_prescription`
- Ambos ahora validan tenant (Día 3, duplicado)
- Tests separados, validators separados

**Riesgo:** serializer drift. Agregar regla nueva en uno y olvidar el otro = bug silencioso. Refactor de un serializer puede no propagarse al otro.

**Solución (post Fase 2 A1 — mixin disponible):**

```python
class _PrescriptionItemBase(TenantScopedSerializerMixin, serializers.ModelSerializer):
    tenant_fields = ['product']

    def validate_dose(self, value): ...
    def validate_duration(self, value): ...
    def validate_instructions(self, value): ...
    def validate_quantity(self, value): ...

    class Meta:
        model = PrescriptionItem
        abstract = True


class PrescriptionItemSerializer(_PrescriptionItemBase):
    """Nested en PrescriptionSerializer.items — sin requires_prescription check."""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.SerializerMethodField()

    def get_product_unit(self, obj):
        pres = obj.product.presentations.first()
        return pres.base_unit if pres else None

    class Meta(_PrescriptionItemBase.Meta):
        fields = ['id', 'product', 'product_name', 'product_unit',
                  'dose', 'duration', 'quantity', 'instructions']


class PrescriptionItemWriteSerializer(_PrescriptionItemBase):
    """Endpoint /items/ — exige requires_prescription."""
    class Meta(_PrescriptionItemBase.Meta):
        fields = ['id', 'product', 'dose', 'duration', 'quantity', 'instructions']

    def validate_product(self, product):
        product = super().validate_product(product)  # tenant del mixin
        if not product.requires_prescription:
            raise serializers.ValidationError("...")
        return product
```

**Criterio de cierre:**
- Base abstract con validadores compartidos.
- Subclases con `Meta` específico y deltas.
- Tests duplicados consolidados.
- Bloqueado por A1 (mixin).

**Estimación:** 1 día (post A1).

---

## B3 — RBAC Fase 4 — quitar `User.role` legacy

**Origen:** CLAUDE.md "Gate Fase 4: `RBAC_FALLBACK_ALLOWED` ausente en logs por 7 días → listo para cortar `User.role`". Documentado pero no ejecutado.

**Riesgo si no se cierra:**
- `User.role` sigue siendo source-of-truth secundaria.
- Doble lectura (`User.role` + `UserRole` RBAC) confunde nuevos contribuidores.
- Reglas duplicadas: si un endpoint chequea `user.role == 'ADMIN'` directamente, bypasea el RBAC DB.

**Criterio de cierre (pre-requisito antes de iniciar):**
- ✅ Monitoreo Railway por 7 días consecutivos confirma `RBAC_FALLBACK_ALLOWED` count = 0.
- ✅ ≥500 requests totales en el periodo.
- ✅ ≥1 request por cada endpoint crítico (matriz documentada en `apps/core/permissions.py`).

**Trabajo:**
1. Eliminar el `_FALLBACK` path en `HybridPermission.has_permission`.
2. Eliminar `RBACPolicy.STATIC_FALLBACK` dict.
3. Migrar `User.role` a `null=True, blank=True` (mantener field por compatibilidad de queries de analytics).
4. Eliminar checks directos `user.role == 'X'` en views/services — todos deben usar RBAC DB.
5. Tests existentes pasan sin cambios (RBAC DB ya es authoritative).

**Criterio de cierre:**
- `grep -rn "user.role" backend/apps/` solo en analytics/dashboards (read-only).
- `HybridPermission` simplificado a solo DB lookup.
- Suite completa OK.
- Documentación actualizada (CLAUDE.md "RBAC" section).

**Estimación:** 2-3 días (incluye monitoreo + cleanup).

---

## B4 — `_validate_same_org` helper duplicado eliminado por Mixin

**Origen:** ADR p14 — los helpers locales `_validate_same_org` en `billing/serializers.py` y `prescriptions/serializers.py` son idénticos (excepto `serializer_name`). Se decidió mantenerlos duplicados en Día 3 para evitar promoción prematura a `apps/core/`.

**Bloqueado por A1.** Cuando el mixin se extraiga:

1. Eliminar `_validate_same_org` de `billing/serializers.py` y `prescriptions/serializers.py`.
2. Eliminar `tenant_logger` local — el mixin lo expone.
3. Eliminar `import logging` si no se usa para otra cosa.

**Criterio de cierre:**
- `grep -rn "_validate_same_org" backend/` → no results.
- Suite completa OK.

**Estimación:** 1 hora (mecánico, post A1).

---

## B5 — `_create_default_superuser` signal → management command explícito

**Origen:** ADR p15 (Día 4 PR-4A). El fix #12 cerró el vector de privilege escalation pero mantuvo la implementación como signal `post_migrate`. Los signals son frágiles para invariantes de seguridad:

- Doble-fire en multi-worker Railway (mitigado por la guard idempotente, pero superficie innecesaria).
- Orden de boot no controlable cuando hay múltiples apps con `post_migrate`.
- Difícil de testear en aislamiento — los tests actuales invocan la función directamente sin pasar por el signal.
- Operacional: `python manage.py bootstrap_superuser` es discoverable; un signal escondido no.

**Riesgo si no se cierra:**
- Próximo contribuidor podría agregar otro signal `post_migrate` que dependa del estado del superuser, generando race condition.
- Si el signal falla silenciosamente (excepción capturada por Django), el deploy queda sin superuser sin alarma.
- El logger `rbac.events` captura `SUPERUSER_BOOTSTRAP_CREATED` / `_SKIPPED` pero no garantiza alerting — un mgmt command con exit code 0/1/2 permite wire directo a CI.

**Solución:**

```python
# apps/users/management/commands/bootstrap_superuser.py
class Command(BaseCommand):
    help = "Bootstrap del superuser de plataforma desde env vars. Idempotente."

    def handle(self, *args, **options):
        from apps.users.apps import _create_default_superuser  # reusar lógica actual
        _create_default_superuser(sender=None)
        # exit 0 si todo OK
```

`Procfile` Railway actualizado:
```
web: python manage.py collectstatic --noinput && python manage.py migrate --no-input && python manage.py seed_permissions && python manage.py bootstrap_superuser && gunicorn ...
```

Signal en `apps.py` se elimina. `post_migrate.connect(...)` removido.

**Criterio de cierre:**
- Mgmt command creado + smoke en staging.
- `Procfile` actualizado.
- Signal `post_migrate` removido de `apps.py`.
- Tests actuales (`test_bootstrap.py`) pasan sin cambios (invocan función standalone, no signal).
- Documentación en `CLAUDE.md` (sección "Setup inicial") actualizada.

**Estimación:** 1 día (incluye verificación de Procfile y rollback plan).

---

## B6 — `seed_permissions --prune` destructivo de Permission huérfanos

**Origen:** ADR p15 (Día 4 PR-4A) — observado durante review de surface area de permisos.

**Riesgo si no se cierra:**
- `seed_permissions` hoy solo **añade** códigos a `Permission`. Códigos eliminados de `PERMISSION_CODES` en el código quedan vivos en DB.
- Los `Role` siguen apuntando a esos permisos huérfanos. Si se elimina un código por seguridad, el grant sigue ahí.
- No hay forma de auditar drift entre código y DB salvo manual.

**Solución:**

```python
# seed_permissions.py
def add_arguments(self, parser):
    parser.add_argument('--prune', action='store_true',
        help="ELIMINA permisos en DB que no están en PERMISSION_CODES.")
    parser.add_argument('--dry-run', action='store_true',
        help="Reporta qué se eliminaría sin tocar DB.")

def handle(self, *args, **options):
    seed_existing_codes()
    if options['prune']:
        orphans = Permission.objects.exclude(code__in=PERMISSION_CODES)
        if options['dry_run']:
            self.stdout.write(f"Would delete: {list(orphans.values_list('code', flat=True))}")
        else:
            count = orphans.count()
            orphans.delete()  # CASCADE elimina UserRole/Role grants vinculados
            self.stdout.write(f"Pruned {count} orphan permissions.")
```

**Criterio de cierre:**
- `--prune` y `--dry-run` flags implementados.
- Tests: agregar permission, removerlo de `PERMISSION_CODES`, correr `--prune --dry-run` → reporta, correr `--prune` → elimina.
- Documentación: ejecutar `--prune` solo en mantenimiento window (no en cada deploy).
- Procfile NO incluye `--prune` automático.

**Estimación:** 1 día.

---

## Tracking

Cuando un item se cierre, mover a `docs/deuda/cerrado/` con su PR asociado + fecha de cierre.
