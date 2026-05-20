# ADR p16 — PR-4B: Cascade lockdown + Organization singleton (Día 4 hardening)

**Status:** ✅ Implementado 2026-05-17. Dark-launch 7 días en staging antes de merge a `main`.

**Predecesores:**
- ADR p15 (2026-05-17) — diseño completo Day 4 + PR-4A ya merged
- PR-4A (Issue #12 + #13) — superuser bootstrap anti-escalación + `DEFAULT_PERMISSION_CLASSES`

**Stakeholders:** felipeddiaz (autor). Reviews: backend-architect (PRINCIPAL), database-architect, security-auditor, senior-qa, code-reviewer.

---

## 1. Contexto

PR-4A cerró Issues #12 + #13 (vulns CVSS 9.9 + DRF perms missing default). Quedaban pendientes Issues #10 + #11 del audit pre-beta + 2 entregables operacionales: `ProtectedError` handler bounded + `audit_orphan_fks` mgmt command.

PR-4B agrupa los 4 deliverables como hardening pre-beta coherente: cascade semantics + singleton API + handler defensivo + auditoría operacional.

## 2. Decisiones

### 2.1 Issue #10 — `OrganizationViewSet` refactor

`ModelViewSet` reemplazado por dos views explícitas:

- **`OrganizationMeView`** (`/api/organizations/me/`) — `RetrieveUpdateAPIView` singleton. GET/PATCH sobre la org propia, sin pk en URL. Guard contra `user.organization=None` (404 explícito en lugar de TypeError silencioso).

- **`OrganizationLegacyView`** (`/api/organizations/<int:pk>/`) — retrocompat 90 días con:
  - Validación EXPLÍCITA `pk == request.user.organization_id` → 404 si mismatch (NUNCA "tu propia org silenciosamente")
  - Headers RFC 8594 en TODO response (200/404/405/410): `Deprecation: true`, `Sunset: 17-Aug-2026`, `Link: </api/organizations/me/>; rel="successor-version"`
  - Log estructurado `DEPRECATED_ENDPOINT_HIT` para tracking de adopción
  - **Fail-safe automático**: post-`_SUNSET_DATETIME` (2026-08-17) responde 410 Gone vía `_EndpointSunsetException(APIException)` raised en `initial()`. Sin esto, la "deprecation" sería voluntaria — el header sería el único enforcement.

Router `DefaultRouter.register('organizations', ...)` removido. List/create/destroy → 404 (sin ruta).

### 2.2 Issue #11 — CASCADE → PROTECT en 5 FKs

| Modelo.campo | Justificación |
|--------------|--------------|
| `User.organization` | NOM-024 retención prestador; preserva audit trails de `InvoiceAuditLog.changed_by`, `closed_by` |
| `Pet.owner` | NOM-046 expediente clínico — borrar Owner cascadeaba Pet → MR → todo el historial |
| `MedicalRecord.pet` | NOM-046 retención 5 años expediente |
| `VaccineRecord.pet` | NOM-007 + NOM-046 registro vacunal |
| `Prescription.pet` | NOM-046 receta como documento legal entregado al paciente (agregado por database-architect post-review v3) |

Migrations metadata-only (Postgres no recrea constraint para cambio Django-side `on_delete`). Lock breve, < 1s. Reversibles.

### 2.3 ProtectedError handler bounded (`apps/core/exceptions.py`)

`_handle_protected_error()` reemplaza el handler genérico:

- `isinstance(exc, ProtectedError)` — captura subclases (e.g. `RestrictedError` Django 4.1+). Override del `type(exc) is ProtectedError` inicial post code-reviewer.
- Probe `[:6]` vía `itertools.islice` — `exc.protected_objects` es `set`, no subscriptable.
- COUNT solo si probe saturado, con hard cap 1000.
- **Shape consistente** (código + tests): `protected_count: int` siempre + `protected_count_truncated: bool` separado. Sin esto, el campo alternaba str ("3" vs ">1000") — dos parsers en cliente.
- **Sample dict `{type, id, public_id}`** — NUNCA `str(obj)`. Evita PII leak + N+1 si `__str__` accede relations.
- Status **409 Conflict** (override ADR p15 §8 — decisión usuario: semántica REST por sobre conveniencia frontend; ver memoria `feedback-status-code-semantics`).

### 2.4 `audit_orphan_fks` mgmt command

Infraestructura crítica versionada (ver memoria `feedback-critical-infra-governance`):

- `SCHEMA_VERSION = "1.0.0"` — bump minor para additive, major para rename/remove + sunset 30 días.
- Exit codes documentados: 0 clean / 1 orphans / 2 internal error.
- Dual output: JSON stdout (CI parseable) + log estructurado stderr.
- **Cobertura catch-all sobre FKs PROTECT** (decisión usuario): 32 targets total — 13 explícitos cross-model + 19 `OrganizationalModel.organization` heredados (introspección `_collect_inherited_org_fks()`).
- **Defense vs soft-delete (security HIGH)**: usa `all_objects` (no `objects`) para no reportar falsos positivos cuando un parent está soft-deleted con children activos.
- Runbook obligatorio: `docs/runbooks/audit_orphan_fks.md`.

### 2.5 Guards `is_generic` en `OwnerViewSet.destroy` + `PetViewSet.destroy`

Walk-in dummy owner/pet (usado por `billing.services`) NUNCA debe borrarse. Guard explícito retorna 409 `{code: 'generic_resource_protected', message: ...}` antes de llegar al PROTECT-bound DB error. Mensaje específico vs genérico `resource_has_dependencies`.

### 2.6 Bloqueo DELETE en `VaccineRecordDetailView` + `PrescriptionDetailView`

Post-senior-qa HIGH: el lockdown era asimétrico — `Pet.delete()` protegido vía PROTECT pero el documento child (vacuna/receta) borrable directo. Removido DELETE de ambas views (`http_method_names = ['get', 'patch', 'head', 'options']`). Consistencia con motivación NOM-007/046.

### 2.7 Admin Django: `OrganizationAdmin` + `CustomUserAdmin` DELETE bloqueado

Post-senior-qa HIGH: admin Django NO pasa por `custom_exception_handler` — un DELETE bloqueado por PROTECT mostraría traceback técnico al operador. `has_delete_permission` override a `False` en ambos. Orgs/users se desactivan vía `is_active=False`, no se borran.

---

## 3. Decisión soft-delete A5 (usuario)

PR-4B NO implementa soft-delete real (`deleted_at`/`deleted_by`/etc.). Razón: 5-7 días, bloquea pre-beta. Decisión usuario: **frontend pivota a "Archivar/Desactivar"** usando `is_active` existente.

Implicación: endpoints DELETE de `Owner`/`Pet`/`MedicalRecord` quedan funcionales pero retornan 409 ProtectedError para registros con historia real (99% del tiempo). Frontend separate PR cambia label "Eliminar" → "Archivar".

## 4. Decisiones rechazadas

| Alternativa | Por qué se rechazó |
|-------------|-------------------|
| Soft-delete A5 en este PR | +5-7 días sprint, blast radius incompatible con pre-beta hardening |
| Status 400 ProtectedError (consistencia frontend) | Semántica REST 409 correcta — usuario explícito (memoria `feedback-status-code-semantics`) |
| 4 FKs sin `Prescription.pet` | Database-architect: inconsistencia visible NOM-046 (vacuna protegida, receta cascadeada). Agregado al scope |
| `audit_orphan_fks` solo 4 FKs nuevas | Catch-all sobre PROTECT (no integrity engine universal) — usuario decisión v3 |
| `str(p)` en handler sample | PII leak + N+1 — dict `{type, id, public_id}` |
| `type(exc) is ProtectedError` | No captura subclases (RestrictedError). isinstance() es estándar |
| Headers Sunset sin fail-safe 410 | "Deprecation" voluntaria. Fail-safe `_SUNSET_DATETIME` automático en `initial()` |
| Lista AUDIT_TARGETS sin introspección | Drift permanente cuando se añada nuevo OrganizationalModel. `_collect_inherited_org_fks()` evita esto |
| `Model.objects` en audit (incluye filter is_active=True) | Falso positivo: parent soft-deleted con children activos → "dangling" inexistente. `all_objects` bypass |
| DELETE permitido en VaccineRecord/Prescription | Lockdown asimétrico (Pet protegido, child borrable directo) — contradice motivación NOM |

## 5. Deuda documentada

| ID | Item | Razón diferir | Fase |
|----|------|--------------|------|
| A5 | Soft-delete real Owner/Pet/MR (`deleted_at`, `deleted_by`, `restore()`) | 5-7 días sprint dedicado | Fase 2 post-beta |
| A6 | `InvoiceAuditLog.invoice` CASCADE → SET_NULL + snapshot `invoice_public_id` | Diseño de snapshot fields | Fase 2 |
| A7 | `MedicalRecord.veterinarian` snapshot `vet_name_at_close` | Permite User delete sin perder trazabilidad | Fase 2 |
| B5 | Migrar `_create_default_superuser` signal → mgmt command `bootstrap_superuser` | Toca Procfile Railway | Fase 3 |
| B6 | `seed_permissions --prune` (destructivo) | Diseño de safety guards | Fase 3 |
| B7 | `User.organization` `null=True` → `null=False` con backfill 'Vet Care Internal' | Migración data + backfill | Fase 2 |
| D2 | Sunset operativo `/api/organizations/<pk>/` (track adopción + cortar a 410) | 90 días tracking → cortar 2026-08-17 (automático via `_SUNSET_DATETIME`) | Operacional |
| D3 | CI gate exit-code `audit_orphan_fks` en pipeline | Config CI, no en este PR | Operacional |
| D5 | `OrganizationTimezoneAudit.organization` CASCADE → SET_NULL | Análogo a A6 | Fase 2 |
| D6 | `Prescription.medical_record` CASCADE → SET_NULL + snapshot | Análogo a `Invoice.medical_record` | Fase 2 |
| D7 | `StockMovement.presentation` CASCADE → SET_NULL + snapshot | Preservar ledger contable | Fase 2 |
| C1 | Migration NOT VALID + VALIDATE split para tablas > 1M filas | Beta DB pequeña, no aplica aún | Cuando se escale |

## 6. Files modificados

**Modelos / migrations:**
- `backend/apps/users/models.py` + migration 0006
- `backend/apps/patients/models.py` + migration 0011
- `backend/apps/medical_records/models.py` + migration 0017
- `backend/apps/prescriptions/models.py` + migration 0006

**Views:**
- `backend/apps/organizations/views.py` — singleton + legacy + APIException 410
- `backend/apps/medical_records/views.py` — VaccineRecordDetailView `http_method_names`
- `backend/apps/prescriptions/views.py` — PrescriptionDetailView `http_method_names`
- `backend/apps/patients/views.py` — Owner/Pet `is_generic` guards alineados a `{code, message}`

**Routing:**
- `backend/config/urls.py` — router.register removido + 2 paths explícitos

**Admin:**
- `backend/apps/organizations/admin.py` — `has_delete_permission = False`
- `backend/apps/users/admin.py` — `has_delete_permission = False`

**Handler / mgmt:**
- `backend/apps/core/exceptions.py` — `_handle_protected_error` bounded
- `backend/apps/core/management/commands/audit_orphan_fks.py` — nuevo (versioned)

**Tests:**
- `backend/apps/organizations/tests/test_views.py` — nuevo (12 tests)
- `backend/apps/core/tests/test_cascade_lockdown.py` — nuevo (9 tests incluye DELETE bloqueado)
- `backend/apps/core/tests/test_exception_handler.py` — nuevo (8 tests)
- `backend/apps/core/tests/test_audit_orphan_fks.py` — nuevo (6 tests, 1 skip esperado)
- `backend/apps/patients/tests/test_pet_delete.py` — actualizado asserts al shape nuevo

**Docs:**
- `docs/decisions/2026-05-17-p16-pr4b-cascade-and-singleton.md` (este archivo)
- `docs/runbooks/audit_orphan_fks.md` (nuevo)

## 7. Tests verde — 327+ tests pasan

Suite completa con PR-4B aplicado. Sin regresiones en módulos pre-existentes (billing, medical_records, appointments, analytics, dashboard, prescriptions, users, organizations). `audit_anchor_integrity` sigue exit 0.

## 8. Rollout

**Dark-launch 7 días en staging:**
- Día 0: merge a `develop`, deploy staging
- Días 1-7: monitor `DEPRECATED_ENDPOINT_HIT` rate + `ProtectedError` rate + suite completa diaria + `audit_orphan_fks` nightly
- Día 8: merge a `main` (production) si todo green
- Día +90 (2026-08-17): fail-safe automático activa 410 Gone para legacy endpoint

**Rollback:**
- Cada deliverable reversible sin pérdida de datos. PROTECT no destruye; cliente recibe error.
- `git revert` migrations → CASCADE regresa. Sin schema irreversible.

## 9. Compliance con reglas analytics

- ✅ Anchor writers sin cambios (sin escrituras a `Invoice.status='paid'` directo)
- ✅ Provenance `'service'` en escritura nueva
- ✅ `build_daily_metrics` sigue idempotente
- ✅ Today nunca snapshot
- ✅ `source` y `lifecycle_state` en respuestas
- ✅ `cache.delete_many` no usado (sin signals nuevos)
- ✅ CHECK constraints preservados
- ✅ `METRICS_SCHEMA_VERSION` sin cambio (KPIs no afectados)
