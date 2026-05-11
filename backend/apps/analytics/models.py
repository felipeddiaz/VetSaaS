"""
Analytics snapshot infrastructure (Capa 4 minimal v1).

Two tables:
- DailyOrgMetrics — one row per (organization, org-local date) with the seven
  KPIs that v1 of the dashboard contract supports. Read-only externally.
- DashboardSnapshotAudit — append-only log of every state transition or build
  event affecting a snapshot row. Powers debugging and the analytics-health
  endpoint.

Design constraints (per dashboard-metrics-contract.md):
- Snapshots are NEVER computed for "today". Today is a live aggregate, full
  stop. The contract calls this out and the build service enforces it.
- lifecycle_state is persisted (provisional / frozen / rebuilt / corrupt).
- metrics_schema_version is recorded so future definition changes can
  dual-write without breaking historical comparisons.
- org_timezone_at_snapshot is frozen INTO the row at build time. Subsequent
  TZ changes to the org never re-bucket history.
- excluded_anchor_missing + build_warnings_count + provenance_mix_json
  are first-class diagnostic columns. A snapshot whose excluded count is
  non-zero is suspect; a corrupt-marked row is HIDDEN from charts but
  surfaced in audit endpoints.
"""
from django.db import models

from apps.core.models import OrganizationalModel


METRICS_SCHEMA_VERSION = 1

LIFECYCLE_PROVISIONAL = 'provisional'
LIFECYCLE_FROZEN = 'frozen'
LIFECYCLE_REBUILT = 'rebuilt'
LIFECYCLE_CORRUPT = 'corrupt'

LIFECYCLE_CHOICES = (
    (LIFECYCLE_PROVISIONAL, 'Provisional — inside mutation window'),
    (LIFECYCLE_FROZEN, 'Frozen — past mutation window'),
    (LIFECYCLE_REBUILT, 'Rebuilt — was frozen, then forcibly rewritten'),
    (LIFECYCLE_CORRUPT, 'Corrupt — anchor inconsistency detected; excluded from charts'),
)


class DailyOrgMetrics(OrganizationalModel):
    """
    One row per (organization, org-local date). Bucketing is computed using
    the timezone the organization had AT THE MOMENT THE SNAPSHOT WAS BUILT,
    captured into `org_timezone_at_snapshot`.
    """

    date = models.DateField(db_index=True)
    org_timezone_at_snapshot = models.CharField(max_length=64)
    metrics_schema_version = models.PositiveIntegerField(default=METRICS_SCHEMA_VERSION)
    lifecycle_state = models.CharField(
        max_length=16, choices=LIFECYCLE_CHOICES, default=LIFECYCLE_PROVISIONAL,
    )
    built_at = models.DateTimeField(auto_now=True)

    # ---- v1 minimal KPIs (7 — per Capa 4 v1 directive) ----
    revenue_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    revenue_accrual = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoices_paid_count = models.PositiveIntegerField(default=0)
    appointments_total = models.PositiveIntegerField(default=0)
    appointments_done = models.PositiveIntegerField(default=0)
    appointments_no_show = models.PositiveIntegerField(default=0)
    medical_records_closed = models.PositiveIntegerField(default=0)

    # ---- Diagnostic instrumentation ----
    excluded_anchor_missing = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Rows skipped because their analytics anchor was NULL. Should be "
            "zero post-Capa 1 CHECK constraints; non-zero = bug or imported "
            "data that bypassed the writer."
        ),
    )
    build_warnings_count = models.PositiveIntegerField(default=0)
    provenance_mix = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Per-anchor source breakdown for rows that fed this snapshot, "
            "e.g. {'paid_at': {'service': 921, 'fallback': 2}}. Lets the "
            "trust score for the snapshot day be reconstructed without "
            "re-querying the source tables."
        ),
    )

    class Meta:
        unique_together = [('organization', 'date')]
        ordering = ['-date']
        indexes = [
            models.Index(fields=['organization', '-date'],
                         name='idx_dom_org_date'),
            models.Index(fields=['organization', 'lifecycle_state'],
                         name='idx_dom_org_lifecycle'),
        ]

    def __str__(self):
        return f"{self.organization_id}@{self.date} [{self.lifecycle_state}]"


class DashboardSnapshotAudit(OrganizationalModel):
    """
    Append-only audit of snapshot lifecycle events. Every transition
    (build, freeze, rebuild, corruption-detected, late-arrival rebuild)
    creates one row.

    This is the primary debugging artifact. If a number on a chart looks
    wrong, the operator pulls every row here for that (org, date) and
    sees exactly what happened.
    """

    KIND_CHOICES = (
        ('build', 'Snapshot built (initial or normal nightly)'),
        ('skip_frozen', 'Skipped because row was frozen'),
        ('rebuild', 'Forced rebuild via --force'),
        ('freeze', 'Lifecycle transitioned to frozen'),
        ('corruption_detected', 'Marked corrupt due to anchor inconsistency'),
        ('late_arrival_rebuild', 'Rebuild triggered by late-arriving event'),
    )

    snapshot_date = models.DateField()
    from_state = models.CharField(max_length=16, blank=True)
    to_state = models.CharField(max_length=16, blank=True)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    reason = models.CharField(max_length=255, blank=True)
    triggered_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
    )
    triggered_by_system = models.BooleanField(
        default=True,
        help_text="False when a human user triggered (e.g. mgmt command run with --user).",
    )
    diff = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'snapshot_date', '-created_at'],
                         name='idx_dsa_org_date_created'),
        ]
