# Runbook — `audit_orphan_fks`

**Owner:** ADMIN_SAAS / plataforma
**ADR:** [p16 — PR-4B Cascade lockdown + Organization singleton](../decisions/2026-05-17-p16-pr4b-cascade-and-singleton.md)
**Schema version:** 1.0.0
**Status:** Producción — operacional

## Propósito

Escanea la integridad referencial de FKs `on_delete=PROTECT` del sistema. Detecta dos tipos de orphan:

- **dangling**: FK no nula apunta a `pk` que no existe en parent (sólo posible vía bypass raw SQL o import incompleto).
- **cross_tenant**: FK apunta a un parent que existe pero pertenece a otra organización (defecto multitenancy).

Cobertura: 32 targets — 13 cross-model PROTECT explícitos + 19 `OrganizationalModel.organization` heredados (introspección automática).

## Uso

```bash
# Scan completo (todos los tenants)
python manage.py audit_orphan_fks

# Filtrar por organización específica
python manage.py audit_orphan_fks --org=12

# Solo JSON (suprime resumen humano)
python manage.py audit_orphan_fks --json-only

# Suprime structured logging stderr
python manage.py audit_orphan_fks --quiet
```

## Interpretación de exit codes

| Code | Significado | Acción |
|------|-------------|--------|
| **0** | DB limpia, sin orphans | Continuar deploy / cron termina OK |
| **1** | Orphans detectados (dangling o cross_tenant) | Investigar findings JSON. CI debe fallar |
| **2** | Error interno (modelo no encontrado, query falló) | Reintentar; si persiste, revisar `internal_errors` en JSON |

## Cadencia recomendada

- **Post-deploy**: ejecutar tras cada deploy que toque migrations relacionadas a FKs PROTECT.
- **Pre-snapshot**: opcional antes de `build_daily_metrics` (consistencia data warehouse).
- **Nightly cron**: opcional en producción para detección temprana de drift por raw SQL imports.

## Procedimiento de remediation por hallazgo

### `kind: dangling`

FK apunta a parent inexistente. Posibles causas:
1. Bypass raw SQL (DELETE directo bypaseando PROTECT)
2. Import incompleto / restore parcial
3. Bug histórico anterior a migración a PROTECT

Acciones:
1. Identificar fuente (¿quién hizo el bypass? — revisar log Postgres si hay audit)
2. Decidir: crear el parent faltante o nullear/borrar la FK
3. Si la FK es `null=False`: requiere migración data (no se puede simplemente nullear)

### `kind: cross_tenant`

FK apunta a parent de otra organización. Posibles causas:
1. Bug en serializer/view que no validó tenant
2. Migración data que mezcló orgs
3. Import legacy sin validación de aislamiento

Acciones:
1. Identificar el flujo que generó el orphan (revisar log `TENANT_VALIDATION_REJECTED` correlacionado)
2. Decidir: corregir la FK (mover al parent correcto de la org del child) o borrar el child
3. Auditar otros caminos del mismo serializer

## Output JSON contract

Schema versionado. Bump policy:
- **Minor** (1.0.0 → 1.1.0): campos additive
- **Major** (1.0.0 → 2.0.0): rename/remove → 30 días dual-output + sunset

```json
{
  "schema_version": "1.0.0",
  "scan_timestamp": "ISO-8601 UTC",
  "audit_run_id": "uuid",
  "org_filter": null | int,
  "targets_audited": 32,
  "orphans": [
    {
      "child_model": "patients.Pet",
      "child_fk": "owner",
      "parent_model": "patients.Owner",
      "kind": "dangling" | "cross_tenant",
      "count": int,
      "sample": [{"child_id": int, "child_org_id": int|null, "fk_id": int, "fk_org_id": int|null}, ...],
      "sample_truncated": bool
    }
  ],
  "summary": {
    "total_orphans": int,
    "models_with_orphans": int,
    "scan_duration_ms": int,
    "internal_errors": [{"child_model": str, "child_fk": str, "error": str}, ...]
  }
}
```

## Defenses contra falsos positivos

- **Soft-delete**: usa `all_objects` (no `objects`) — parent soft-deleted con children activos NO se reporta como dangling.
- **Race condition**: scan no es transaccional; un INSERT entre el child_qs y parent_pks puede producir falso positivo transitorio. Reintentar el scan.
- **Lista AUDIT_TARGETS**: explícitamente listada en `apps/core/management/commands/audit_orphan_fks.py` + introspección automática para `OrganizationalModel.organization`. Si añades una FK PROTECT nueva en una app que NO sea via `OrganizationalModel`, debes añadirla manualmente.

## Performance

- Scan duration: O(targets × indexed lookups). Beta DB ~1 segundo.
- Memoria: dict in-memory `parent_org_map` materializa pks parent — para tablas > 1M filas considerar split por org.
- I/O: chunked via `iterator(chunk_size=2000)` para queryset child.

## Killproof / re-entrance

- Comando NO escribe a DB (solo lectura) — kill-9 mid-scan no deja state inconsistente.
- Dos invocaciones paralelas: no destructivas pero desperdicio I/O. Para evitar, usar advisory lock externo (cron lockfile).

## Versioning

Para cambios al output schema:
1. Bump `SCHEMA_VERSION` en `apps/core/management/commands/audit_orphan_fks.py`
2. Si es **major**: agregar `--output-format=1` flag para dual-output durante 30 días
3. Actualizar este runbook con el nuevo schema
4. Notificar a operations (CI que parse el JSON puede romper)
