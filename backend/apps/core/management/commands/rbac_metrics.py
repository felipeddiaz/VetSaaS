"""
rbac_metrics — Calcula métricas de observabilidad RBAC desde logs.

Lee logs/rbac_events.log y produce:
  - fallback_rate por endpoint y rol
  - tenant_mismatch_count
  - critical_endpoint_coverage

Uso:
  python manage.py rbac_metrics
  python manage.py rbac_metrics --since 2026-04-01
  python manage.py rbac_metrics --endpoint /api/billing/invoices/ --role VET

Gate de Fase 4:
  fallback_rate = 0  sostenido 7 días
  tenant_mismatch_count = 0
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


CRITICAL_ENDPOINTS = {
    "/api/billing/",
    "/api/inventory/",
    "/api/appointments/",
    "/api/medical-records/",
    "/api/staff/",
    "/api/dashboard/",
    "/api/pets/",
    "/api/owners/",
}


class Command(BaseCommand):
    help = "Métricas RBAC: fallback_rate, tenant_mismatch_count, cobertura de endpoints"

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            help="Filtrar eventos desde esta fecha ISO (ej: 2026-04-01)",
            default=None,
        )
        parser.add_argument(
            "--endpoint",
            help="Filtrar por prefijo de endpoint",
            default=None,
        )
        parser.add_argument(
            "--role",
            help="Filtrar por rol de usuario",
            default=None,
        )

    def handle(self, *args, **options):
        log_path = Path(settings.BASE_DIR) / "logs" / "rbac_events.log"

        if not log_path.exists():
            self.stdout.write(self.style.WARNING(
                f"No existe {log_path} — sin eventos aún. "
                "Genera tráfico y vuelve a ejecutar."
            ))
            sys.exit(0)

        since_filter = options["since"]
        endpoint_filter = options["endpoint"]
        role_filter = options["role"]

        since_dt = None
        if since_filter:
            since_dt = datetime.fromisoformat(since_filter).replace(tzinfo=timezone.utc)

        events = self._load_events(log_path, since_dt, endpoint_filter, role_filter)

        if not events:
            self.stdout.write(self.style.WARNING("Sin eventos en el período/filtro indicado."))
            sys.exit(0)

        self._print_summary(events)

    def _load_events(self, path, since_dt, endpoint_filter, role_filter):
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if since_dt:
                    ts = datetime.fromisoformat(e.get("timestamp", "")).replace(tzinfo=timezone.utc)
                    if ts < since_dt:
                        continue

                if endpoint_filter and not (e.get("path") or "").startswith(endpoint_filter):
                    continue

                if role_filter and e.get("role") != role_filter:
                    continue

                events.append(e)
        return events

    def _print_summary(self, events):
        total = len(events)
        db_allowed = sum(1 for e in events if e["event"] == "RBAC_DB_ALLOWED")
        fallback_allowed = sum(1 for e in events if e["event"] == "RBAC_FALLBACK_ALLOWED")
        denied = sum(1 for e in events if e["event"] == "RBAC_DENIED")
        tenant_mismatch = sum(1 for e in events if e["event"] == "TENANT_MISMATCH_DENY")

        denominator = db_allowed + fallback_allowed
        fallback_rate = (fallback_allowed / denominator * 100) if denominator else 0.0

        # Cobertura de endpoints críticos
        paths_seen = {e.get("path", "") for e in events}
        covered = sum(
            1 for ep in CRITICAL_ENDPOINTS
            if any(p.startswith(ep) for p in paths_seen)
        )
        coverage = covered / len(CRITICAL_ENDPOINTS) * 100

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  MÉTRICAS RBAC")
        self.stdout.write("=" * 60)
        self.stdout.write(f"  Total eventos          : {total}")
        self.stdout.write(f"  RBAC_DB_ALLOWED        : {db_allowed}")
        self.stdout.write(f"  RBAC_FALLBACK_ALLOWED  : {fallback_allowed}")
        self.stdout.write(f"  RBAC_DENIED            : {denied}")
        self.stdout.write(f"  TENANT_MISMATCH_DENY   : {tenant_mismatch}")
        self.stdout.write("-" * 60)

        style = self.style.SUCCESS if fallback_rate == 0 else self.style.WARNING
        self.stdout.write(style(
            f"  fallback_rate          : {fallback_rate:.2f}%  "
            f"(gate Fase 4: 0%)"
        ))

        mismatch_style = self.style.SUCCESS if tenant_mismatch == 0 else self.style.ERROR
        self.stdout.write(mismatch_style(
            f"  tenant_mismatch_count  : {tenant_mismatch}  "
            f"(gate Fase 4: 0)"
        ))

        cov_style = self.style.SUCCESS if coverage >= 100 else self.style.WARNING
        self.stdout.write(cov_style(
            f"  endpoint_coverage      : {coverage:.0f}%  "
            f"(objetivo: 100%)"
        ))

        # Fase 4 gate check
        self.stdout.write("-" * 60)
        if fallback_rate == 0 and tenant_mismatch == 0 and coverage >= 100:
            self.stdout.write(self.style.SUCCESS(
                "  FASE 4 GATE: PASADO — listo para corte RBAC (verificar ventana 7 días)"
            ))
        else:
            reasons = []
            if fallback_rate > 0:
                reasons.append(f"fallback_rate={fallback_rate:.2f}% (necesita 0%)")
            if tenant_mismatch > 0:
                reasons.append(f"tenant_mismatch={tenant_mismatch} (necesita 0)")
            if coverage < 100:
                reasons.append(f"coverage={coverage:.0f}% (necesita 100%)")
            self.stdout.write(self.style.ERROR(
                f"  FASE 4 GATE: BLOQUEADO — {'; '.join(reasons)}"
            ))

        # Desglose por endpoint — fallback_rate y denied_rate
        self.stdout.write("\n  Desglose por endpoint:")
        self.stdout.write(f"  {'endpoint':<45} {'db':>5} {'fall':>5} {'deny':>5} "
                          f"{'fall%':>6} {'deny%':>6}")
        self.stdout.write("  " + "-" * 76)

        by_endpoint = defaultdict(lambda: {"db": 0, "fallback": 0, "denied": 0})
        for e in events:
            path = (e.get("endpoint") or e.get("path") or "unknown")[:44]
            ev = e["event"]
            if ev == "RBAC_ALLOWED_DB":
                by_endpoint[path]["db"] += 1
            elif ev == "RBAC_FALLBACK_ALLOWED":
                by_endpoint[path]["fallback"] += 1
            elif ev == "RBAC_DENIED":
                by_endpoint[path]["denied"] += 1

        for path, c in sorted(by_endpoint.items()):
            allowed = c["db"] + c["fallback"]
            total_ep = allowed + c["denied"]
            fallback_r = c["fallback"] / allowed * 100 if allowed else 0
            denied_r = c["denied"] / total_ep * 100 if total_ep else 0
            flags = (" ⚠FALLBACK" if fallback_r > 0 else "") + \
                    (" ⚠DENIED" if denied_r > 50 else "")
            self.stdout.write(
                f"  {path:<45} {c['db']:>5} {c['fallback']:>5} {c['denied']:>5} "
                f"{fallback_r:>5.0f}% {denied_r:>5.0f}%{flags}"
            )

        self.stdout.write("=" * 60 + "\n")
