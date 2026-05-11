"""
build_daily_metrics — populate or rebuild DailyOrgMetrics rows.

Usage:
  python manage.py build_daily_metrics --date=2026-05-08
  python manage.py build_daily_metrics --from=2026-05-01 --to=2026-05-07
  python manage.py build_daily_metrics --date=2026-05-08 --org=12
  python manage.py build_daily_metrics --date=2026-05-08 --force

Defaults:
  --date     yesterday in each org's local timezone
  --org      all organizations
  --force    rebuild frozen rows (default: skip)

Today's date is rejected by the underlying service. Today belongs to live
aggregates, not snapshots.

Production safety guarantees:
- Per-org PostgreSQL advisory lock prevents concurrent runs for the same
  organization (Railway can duplicate jobs, restart deploys, overlap
  executions). Lock contention → that org is skipped with a warning;
  the job continues with the next org.
- Per-org try/except isolation: a failure on one org does not abort the
  remaining orgs. Failures are logged with stacktrace and counted in
  the run summary. Exit code is non-zero if any org failed.
- Structured event logs (DASH_BUILD_STARTED / _COMPLETED / _FAILED /
  _LOCK_BUSY) for cron monitoring.
- Idempotency is provided by the underlying apply_snapshot service: same
  inputs → same numbers → no built_at advance. Repeating this command
  is always safe.
"""
import logging
import sys
import time
import traceback
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from apps.analytics.services import TODAY_REJECTED, apply_snapshot
from apps.core.datetime_utils import org_today_local
from apps.core.db_locks import advisory_lock, hash_lock_key
from apps.organizations.models import Organization


logger = logging.getLogger('analytics.events')


class Command(BaseCommand):
    help = "Build / rebuild DailyOrgMetrics rows for one or more (org, date) pairs."

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, default=None,
                            help='Single date YYYY-MM-DD. Defaults to yesterday per org.')
        parser.add_argument('--from', dest='date_from', type=str, default=None,
                            help='Range start YYYY-MM-DD.')
        parser.add_argument('--to', dest='date_to', type=str, default=None,
                            help='Range end YYYY-MM-DD inclusive.')
        parser.add_argument('--org', type=int, default=None,
                            help='Restrict to a single organization id.')
        parser.add_argument('--force', action='store_true',
                            help='Rebuild rows whose lifecycle_state is frozen.')

    def handle(self, *args, **opts):
        if opts['date'] and (opts['date_from'] or opts['date_to']):
            raise CommandError("Use --date OR --from/--to, not both.")

        orgs = (
            Organization.objects.filter(pk=opts['org'])
            if opts['org']
            else Organization.objects.all()
        )
        if opts['org'] and not orgs.exists():
            raise CommandError(f"Organization {opts['org']} not found.")

        run_started = time.monotonic()
        run_summary = {
            'orgs_processed': 0,
            'orgs_locked_busy': 0,
            'orgs_failed': 0,
            'snapshots_built': 0,
            'snapshots_skipped_today': 0,
        }

        logger.info(
            "DASH_BUILD_RUN_STARTED",
            extra={
                'org_count': orgs.count(),
                'date': opts['date'],
                'from': opts['date_from'],
                'to': opts['date_to'],
                'force': opts['force'],
            },
        )

        for org in orgs:
            self._process_org(org, opts, run_summary)

        run_summary['duration_seconds'] = round(time.monotonic() - run_started, 2)
        logger.info("DASH_BUILD_RUN_COMPLETED", extra=run_summary)

        self.stdout.write(self.style.SUCCESS(
            f"Run summary: {run_summary}"
        ))

        # Non-zero exit if any org failed — cron alert can wire on this.
        if run_summary['orgs_failed'] > 0:
            sys.exit(2)

    def _process_org(self, org, opts, run_summary):
        lock_key = hash_lock_key('analytics', 'build_daily_metrics', 'org', org.pk)
        org_started = time.monotonic()
        try:
            with advisory_lock(lock_key, on_busy='skip') as acquired:
                if not acquired:
                    run_summary['orgs_locked_busy'] += 1
                    logger.warning(
                        "DASH_BUILD_LOCK_BUSY",
                        extra={'organization_id': org.pk},
                    )
                    self.stdout.write(self.style.WARNING(
                        f"  org={org.pk} skipped — advisory lock busy"
                    ))
                    return
                dates = self._dates_for(org, opts)
                logger.info(
                    "DASH_BUILD_ORG_STARTED",
                    extra={'organization_id': org.pk, 'days': len(dates)},
                )
                for d in dates:
                    self._build_one(org, d, opts, run_summary)
        except Exception:
            run_summary['orgs_failed'] += 1
            logger.exception(
                "DASH_BUILD_ORG_FAILED",
                extra={
                    'organization_id': org.pk,
                    'duration_seconds': round(time.monotonic() - org_started, 2),
                },
            )
            self.stdout.write(self.style.ERROR(
                f"  org={org.pk} FAILED:\n{traceback.format_exc()}"
            ))
            return

        run_summary['orgs_processed'] += 1
        logger.info(
            "DASH_BUILD_ORG_COMPLETED",
            extra={
                'organization_id': org.pk,
                'duration_seconds': round(time.monotonic() - org_started, 2),
            },
        )

    def _build_one(self, org, d, opts, run_summary):
        try:
            snap = apply_snapshot(org, d, force=opts['force'])
            run_summary['snapshots_built'] += 1
            self.stdout.write(self.style.SUCCESS(
                f"  org={org.pk} date={d.isoformat()} "
                f"lifecycle={snap.lifecycle_state} "
                f"excluded={snap.excluded_anchor_missing}"
            ))
        except TODAY_REJECTED as e:
            run_summary['snapshots_skipped_today'] += 1
            self.stdout.write(self.style.WARNING(
                f"  skipped today: {e}"
            ))

    def _dates_for(self, org, opts):
        if opts['date']:
            return [self._parse(opts['date'])]
        if opts['date_from'] or opts['date_to']:
            start = self._parse(opts['date_from']) if opts['date_from'] else None
            end = self._parse(opts['date_to']) if opts['date_to'] else None
            if not (start and end):
                raise CommandError("--from and --to must both be supplied.")
            if start > end:
                raise CommandError("--from must be <= --to.")
            days = (end - start).days
            return [start + timedelta(days=i) for i in range(days + 1)]
        # Default: yesterday per org-local TZ.
        today = org_today_local(org)
        return [today - timedelta(days=1)]

    def _parse(self, s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date()
        except ValueError as exc:
            raise CommandError(f"Invalid date {s!r}: expected YYYY-MM-DD.") from exc
