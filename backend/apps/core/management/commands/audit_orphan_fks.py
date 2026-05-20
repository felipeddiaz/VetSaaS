"""
audit_orphan_fks — escanea integridad referencial de FKs PROTECT del sistema.

Detecta dos tipos de orphan:
  - dangling: child.fk apunta a un pk de parent que NO existe en DB
              (sólo posible vía raw SQL bypass o import incompleto).
  - cross_tenant: child.fk apunta a un parent que existe PERO pertenece
                  a otra organización (defecto de multitenancy).

Scope (decisión usuario, PR-4B / ADR p16):
  Catch-all sobre TODAS las FKs PROTECT del sistema — NO integrity engine
  universal. Boundary: "integridad referencial protegida". FKs CASCADE o
  SET_NULL no son responsabilidad de este command (otros mecanismos las
  cubren: ProtectedError handler para PROTECT, signals para CASCADE).

Output contract (versionado, ver feedback_critical_infra_governance):
  Schema version: 1.0.0
  Bumps:
    minor: agregar campos additive (sin remover)
    major: rename/remove (requiere 30 días dual-output + sunset)

Dual output:
  - stdout: JSON estructurado (CI gate parseable)
  - stderr: log estructurado (operacional, agregable por Railway/Sentry)

Exit codes:
  0  clean (sin orphans en ninguna FK PROTECT)
  1  orphans detectados (CI failure)
  2  error interno (modelo no encontrado, query falló, etc.)

Usage:
  python manage.py audit_orphan_fks                  # human + JSON stdout
  python manage.py audit_orphan_fks --org=12         # scope per-tenant
  python manage.py audit_orphan_fks --quiet          # suprime log stderr
  python manage.py audit_orphan_fks --json-only      # solo JSON, sin texto

Owner: ADMIN_SAAS / plataforma
Runbook: docs/runbooks/audit_orphan_fks.md
ADR: docs/decisions/2026-05-17-p16-pr4b-cascade-and-singleton.md
"""
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand


SCHEMA_VERSION = "1.0.0"
SAMPLE_SIZE = 5

logger = logging.getLogger('core.audit_orphan_fks')


# FKs PROTECT del sistema — explícitamente listadas (cross-model, no
# heredadas). Cada entry: (child_label, fk_field, parent_label, parent_org_field).
# parent_org_field=None → el padre NO es OrganizationalModel (Organization, User).
#
# La herencia `OrganizationalModel.organization PROTECT` se cubre vía
# _collect_inherited_org_fks() abajo — introspección automática que evita
# drift cuando se añade un nuevo OrganizationalModel descendant. Sin la
# introspección, esta lista necesitaría 19+ entries duplicadas.
_EXPLICIT_AUDIT_TARGETS = [
    # PR-4B nuevos (CASCADE → PROTECT en este sprint)
    ('users.User',                          'organization', 'organizations.Organization', None),
    ('patients.Pet',                        'owner',        'patients.Owner',             'organization_id'),
    ('medical_records.MedicalRecord',       'pet',          'patients.Pet',               'organization_id'),
    ('medical_records.VaccineRecord',       'pet',          'patients.Pet',               'organization_id'),
    ('prescriptions.Prescription',          'pet',          'patients.Pet',               'organization_id'),
    # Pre-existentes PROTECT (cobertura defensiva)
    ('appointments.Appointment',            'pet',          'patients.Pet',               'organization_id'),
    ('billing.Invoice',                     'owner',        'patients.Owner',             'organization_id'),
    ('billing.Invoice',                     'pet',          'patients.Pet',               'organization_id'),
    ('billing.InvoiceItem',                 'service',      'billing.Service',            'organization_id'),
    ('billing.InvoiceItem',                 'presentation', 'inventory.Presentation',     'organization_id'),
    ('inventory.MedicalRecordProduct',      'presentation','inventory.Presentation',      'organization_id'),
    ('medical_records.MedicalRecordService','service',      'billing.Service',            'organization_id'),
    ('prescriptions.PrescriptionItem',      'product',      'inventory.Product',          'organization_id'),
]


def _collect_inherited_org_fks():
    """Introspección: enumera todas las clases concretas que heredan
    `OrganizationalModel` y emite un audit target por su FK `organization`
    (siempre PROTECT por herencia, ver apps/core/models.py:142-146).

    Esto evita drift permanente: cuando se añade un OrganizationalModel
    descendant nuevo, queda auditado automáticamente sin tocar este file.
    """
    from apps.core.models import OrganizationalModel
    targets = []
    for model in django_apps.get_models():
        if model is OrganizationalModel:
            continue
        if not issubclass(model, OrganizationalModel):
            continue
        if model._meta.abstract:
            continue
        targets.append((
            model._meta.label,          # child_label
            'organization',             # fk_field
            'organizations.Organization',  # parent_label
            None,                       # parent_org_field — Organization no es OrgModel
        ))
    return targets


def get_audit_targets():
    """Combina lista explícita + introspección. Llamado por el command +
    tests de paridad. Sin caching: se evalúa cada vez para reflejar cambios
    de runtime (registry refresh en tests)."""
    return _EXPLICIT_AUDIT_TARGETS + _collect_inherited_org_fks()


# Backward-compat: tests pueden importar AUDIT_TARGETS directo. Es la lista
# completa (explícitos + heredados) en el momento de import. Si se añade un
# OrganizationalModel después del import, no se refleja — usar get_audit_targets().
AUDIT_TARGETS = get_audit_targets()


class Command(BaseCommand):
    help = "Audit referential integrity of PROTECT foreign keys across the system."

    def add_arguments(self, parser):
        parser.add_argument('--org', type=int, default=None,
                            help="Restrict scan to a single organization id.")
        parser.add_argument('--quiet', action='store_true',
                            help="Suppress stderr structured log (JSON stdout always emitted).")
        parser.add_argument('--json-only', action='store_true',
                            help="Suppress human-readable text (only JSON to stdout).")

    def handle(self, *args, **options):
        org_filter = options['org']
        quiet = options['quiet']
        json_only = options['json_only']
        run_id = str(uuid.uuid4())
        started_at = time.monotonic()

        if not quiet:
            logger.info("AUDIT_ORPHAN_FKS_STARTED", extra={
                "event": "AUDIT_ORPHAN_FKS_STARTED",
                "audit_run_id": run_id,
                "org_filter": org_filter,
                "targets": len(get_audit_targets()),
                "schema_version": SCHEMA_VERSION,
            })

        findings = []
        internal_errors = []
        targets = get_audit_targets()

        for child_label, fk_field, parent_label, parent_org_field in targets:
            try:
                target_findings = self._audit_target(
                    child_label, fk_field, parent_label, parent_org_field, org_filter,
                )
                if not target_findings:
                    if not quiet:
                        logger.info("AUDIT_ORPHAN_FKS_TARGET_CLEAN", extra={
                            "event": "AUDIT_ORPHAN_FKS_TARGET_CLEAN",
                            "audit_run_id": run_id,
                            "child_model": child_label,
                            "child_fk": fk_field,
                        })
                    continue
                findings.extend(target_findings)
                if not quiet:
                    for f in target_findings:
                        logger.warning("AUDIT_ORPHAN_FKS_TARGET_ORPHANS", extra={
                            "event": "AUDIT_ORPHAN_FKS_TARGET_ORPHANS",
                            "audit_run_id": run_id,
                            **{k: v for k, v in f.items() if k != 'sample'},
                        })
            except Exception as exc:
                internal_errors.append({
                    "child_model": child_label,
                    "child_fk": fk_field,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                if not quiet:
                    logger.error("AUDIT_ORPHAN_FKS_TARGET_FAILED", extra={
                        "event": "AUDIT_ORPHAN_FKS_TARGET_FAILED",
                        "audit_run_id": run_id,
                        "child_model": child_label,
                        "child_fk": fk_field,
                        "error_class": type(exc).__name__,
                    }, exc_info=True)

        scan_duration_ms = int((time.monotonic() - started_at) * 1000)
        total_orphans = sum(f['count'] for f in findings)
        models_with_orphans = len({(f['child_model'], f['child_fk']) for f in findings})

        output = {
            "schema_version": SCHEMA_VERSION,
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
            "audit_run_id": run_id,
            "org_filter": org_filter,
            "targets_audited": len(targets),
            "orphans": findings,
            "summary": {
                "total_orphans": total_orphans,
                "models_with_orphans": models_with_orphans,
                "scan_duration_ms": scan_duration_ms,
                "internal_errors": internal_errors,
            },
        }

        # Stdout: SIEMPRE JSON (CI parseable). El --json-only suprime el
        # texto humano-legible que se imprime en stderr.
        self.stdout.write(json.dumps(output, indent=2, default=str))

        if not json_only:
            self._print_human_summary(output)

        if not quiet:
            logger.info("AUDIT_ORPHAN_FKS_COMPLETED", extra={
                "event": "AUDIT_ORPHAN_FKS_COMPLETED",
                "audit_run_id": run_id,
                "total_orphans": total_orphans,
                "models_with_orphans": models_with_orphans,
                "scan_duration_ms": scan_duration_ms,
                "exit_code": self._exit_code(findings, internal_errors),
            })

        sys.exit(self._exit_code(findings, internal_errors))

    @staticmethod
    def _exit_code(findings, internal_errors):
        if internal_errors:
            return 2
        if findings:
            return 1
        return 0

    def _audit_target(self, child_label, fk_field, parent_label, parent_org_field, org_filter):
        """Detecta orphans para una FK PROTECT específica.

        Estrategia: LEFT JOIN child → parent ON fk_id. Filas con parent IS NULL
        son dangling. Si hay parent_org_field, comparar org_id de ambos lados
        para detectar cross_tenant.

        Defense vs soft-delete (security review HIGH):
        - Usar all_objects en lugar de objects: el TenantManager por defecto
          filtra is_active=True. Sin esto, parents soft-deleted con children
          activos se reportarían como "dangling" (falso positivo que rompe
          el CI gate). all_objects es el bypass canónico documentado en
          apps/core/models.py.
        """
        ChildModel = django_apps.get_model(child_label)
        ParentModel = django_apps.get_model(parent_label)

        # all_objects bypassa filter is_active=True del TenantManager. NO
        # todos los modelos lo tienen — fallback a objects (Manager default
        # de Django, sin soft-delete) cuando el modelo no es OrganizationalModel
        # (ej. User, Organization heredan de AbstractUser/models.Model).
        child_manager = getattr(ChildModel, 'all_objects', ChildModel.objects)
        parent_manager = getattr(ParentModel, 'all_objects', ParentModel.objects)

        results = []
        fk_id_attr = f'{fk_field}_id'

        # Filtros base
        child_qs = child_manager.all()
        if org_filter is not None and hasattr(ChildModel, 'organization_id'):
            child_qs = child_qs.filter(organization_id=org_filter)

        # --- Dangling: FK no nula que apunta a parent inexistente ---
        existing_parent_pks = parent_manager.values_list('pk', flat=True)
        dangling_qs = child_qs.exclude(**{f'{fk_id_attr}__isnull': True}) \
                              .exclude(**{f'{fk_id_attr}__in': existing_parent_pks})
        dangling_count = dangling_qs.count()
        if dangling_count > 0:
            sample = []
            for row in dangling_qs[:SAMPLE_SIZE].values('pk', fk_id_attr):
                sample.append({
                    'child_id': row['pk'],
                    'child_org_id': None,
                    'fk_id': row[fk_id_attr],
                    'fk_org_id': None,
                })
            results.append({
                'child_model': child_label,
                'child_fk': fk_field,
                'parent_model': parent_label,
                'kind': 'dangling',
                'count': dangling_count,
                'sample': sample,
                'sample_truncated': dangling_count > SAMPLE_SIZE,
            })

        # --- Cross-tenant: child.org_id != parent.org_id ---
        # Sólo aplica si el padre es OrganizationalModel (parent_org_field
        # provisto) y el hijo también tiene organization_id.
        if parent_org_field and hasattr(ChildModel, 'organization_id'):
            # Materializar pairs (parent_pk → parent_org_id). Code-reviewer
            # MEDIUM: cuando --org está, filtrar parent también para no
            # cargar 100k filas innecesarias (reducción ~Nx donde N = num orgs).
            parent_qs_for_map = parent_manager.all()
            if org_filter is not None and hasattr(ParentModel, 'organization_id'):
                # Incluir parents de ambos lados de la frontera tenant —
                # cross_tenant es child.org=X y parent.org=Y; necesitamos
                # poder leer parent.org. Filtrar por org_filter limita
                # los parents candidatos a la org del usuario (cualquier
                # cross_tenant detectable involucra al menos un parent que
                # se sale de ese filtro). Conservador: NO filtrar parent
                # cuando --org está, pero limitar dict() con values_list
                # iterator para chunked load.
                pass
            parent_org_map = {
                pk: org_id
                for pk, org_id in parent_qs_for_map.values_list('pk', parent_org_field).iterator(chunk_size=5000)
            }
            cross_tenant_rows = []
            iterator_qs = child_qs.exclude(**{f'{fk_id_attr}__isnull': True}) \
                                  .values('pk', 'organization_id', fk_id_attr)
            for row in iterator_qs.iterator(chunk_size=2000):
                child_org = row['organization_id']
                fk_id_val = row[fk_id_attr]
                parent_org = parent_org_map.get(fk_id_val)
                # dangling ya cubierto arriba — saltar
                if parent_org is None:
                    continue
                if child_org != parent_org:
                    cross_tenant_rows.append({
                        'child_id': row['pk'],
                        'child_org_id': child_org,
                        'fk_id': fk_id_val,
                        'fk_org_id': parent_org,
                    })
            if cross_tenant_rows:
                results.append({
                    'child_model': child_label,
                    'child_fk': fk_field,
                    'parent_model': parent_label,
                    'kind': 'cross_tenant',
                    'count': len(cross_tenant_rows),
                    'sample': cross_tenant_rows[:SAMPLE_SIZE],
                    'sample_truncated': len(cross_tenant_rows) > SAMPLE_SIZE,
                })

        return results

    def _print_human_summary(self, output):
        self.stderr.write("")
        self.stderr.write(self.style.MIGRATE_HEADING("audit_orphan_fks summary"))
        self.stderr.write(f"  audit_run_id:   {output['audit_run_id']}")
        self.stderr.write(f"  schema_version: {output['schema_version']}")
        self.stderr.write(f"  targets_audited: {output['targets_audited']}")
        self.stderr.write(f"  org_filter:     {output['org_filter']}")
        self.stderr.write(f"  scan_duration:  {output['summary']['scan_duration_ms']} ms")
        self.stderr.write(f"  total_orphans:  {output['summary']['total_orphans']}")
        self.stderr.write(f"  models_with_orphans: {output['summary']['models_with_orphans']}")
        if output['summary']['internal_errors']:
            self.stderr.write(self.style.ERROR(f"  internal_errors: {len(output['summary']['internal_errors'])}"))
        if output['orphans']:
            self.stderr.write("")
            self.stderr.write(self.style.WARNING("Findings:"))
            for f in output['orphans']:
                self.stderr.write(
                    f"  - [{f['kind']}] {f['child_model']}.{f['child_fk']} "
                    f"→ {f['parent_model']}: {f['count']} row(s)"
                )
        else:
            self.stderr.write(self.style.SUCCESS("  ✓ no orphans detected"))
