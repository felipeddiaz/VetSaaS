"""
Cron-safety tests for build_daily_metrics:

- Per-org advisory lock prevents overlapping runs (Railway can spawn
  duplicates on deploy / restart). Tested by holding the lock from a
  second connection and asserting the command logs LOCK_BUSY and skips
  the org.
- Per-org failure isolation: a runtime exception during one org's build
  does not abort the rest of the run.
- Hash function for lock keys is deterministic and fits PG bigint.
- TZ drift: command picks "yesterday in org-local TZ", not server TZ.
"""
from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.analytics.models import DailyOrgMetrics
from apps.core.datetime_utils import org_today_local
from apps.core.db_locks import (
    LockUnavailable, advisory_lock, hash_lock_key, try_advisory_lock,
)
from apps.organizations.models import Organization


class HashKeyTests(TransactionTestCase):
    def test_hash_is_deterministic(self):
        self.assertEqual(
            hash_lock_key('a', 'b', 1),
            hash_lock_key('a', 'b', 1),
        )

    def test_hash_fits_signed_bigint(self):
        n = hash_lock_key('analytics', 'build', 'org', 12345)
        self.assertGreaterEqual(n, 0)
        self.assertLess(n, 2 ** 63)

    def test_hash_distinguishes_inputs(self):
        self.assertNotEqual(
            hash_lock_key('analytics', 'build', 'org', 1),
            hash_lock_key('analytics', 'build', 'org', 2),
        )


class AdvisoryLockTests(TransactionTestCase):
    def test_acquire_and_release(self):
        key = hash_lock_key('test', 'lock', 'a')
        self.assertTrue(try_advisory_lock(key))
        # Release so the next test or session can acquire.
        from apps.core.db_locks import release_advisory_lock
        release_advisory_lock(key)

    def test_context_manager_acquires_and_releases(self):
        key = hash_lock_key('test', 'lock', 'b')
        with advisory_lock(key) as acquired:
            self.assertTrue(acquired)
        # After exit the lock is released — acquire again must succeed.
        with advisory_lock(key) as acquired2:
            self.assertTrue(acquired2)


class CommandLockSkipsBusyOrgTests(TransactionTestCase):
    def setUp(self):
        # TransactionTestCase wipes between tests so create here.
        self.org = Organization.objects.create(name="Lock Org", timezone="UTC")

    def test_busy_lock_skips_org(self):
        """When the lock is held externally, the command logs LOCK_BUSY
        and continues without producing a snapshot for that org."""
        lock_key = hash_lock_key('analytics', 'build_daily_metrics', 'org', self.org.pk)

        # Hold the lock from a second DB connection so it persists across
        # the call_command's own connection.
        other = connections.create_connection('default')
        try:
            with other.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(%s)", [lock_key])

            out = StringIO()
            call_command('build_daily_metrics', '--date=2026-05-01', stdout=out)
            self.assertIn('lock busy', out.getvalue().lower())
            # No snapshot should have been built for the busy org.
            self.assertFalse(
                DailyOrgMetrics.objects.filter(organization=self.org).exists()
            )
        finally:
            with other.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock_all()")
            other.close()


class CommandFailureIsolationTests(TransactionTestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="ISO A", timezone="UTC")
        self.org_b = Organization.objects.create(name="ISO B", timezone="UTC")

    def test_failure_in_one_org_does_not_block_others(self):
        """If apply_snapshot raises for one org, the command continues
        with the rest and exits 2."""
        from apps.analytics import services as analytics_services

        original = analytics_services.apply_snapshot

        def selective_fail(org, *args, **kwargs):
            if org.pk == self.org_a.pk:
                raise RuntimeError("simulated boom for org A")
            return original(org, *args, **kwargs)

        with patch(
            'apps.analytics.management.commands.build_daily_metrics.apply_snapshot',
            side_effect=selective_fail,
        ):
            out = StringIO()
            try:
                call_command('build_daily_metrics', '--date=2026-05-01', stdout=out)
            except SystemExit as exc:
                self.assertEqual(exc.code, 2,
                                 "Run with at least one failing org must exit 2")
            else:
                self.fail("Command should have exited non-zero")

        # Org B should have a snapshot; org A should not.
        self.assertTrue(
            DailyOrgMetrics.objects.filter(organization=self.org_b).exists(),
            "Failure in org A must not block org B",
        )
        self.assertFalse(
            DailyOrgMetrics.objects.filter(organization=self.org_a).exists()
        )


class MidnightBoundaryTests(TransactionTestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Midnight A", timezone="UTC")
        self.org_b = Organization.objects.create(name="Midnight B", timezone="UTC")

    def test_midnight_boundary_deterministic(self):
        from apps.analytics.services import apply_snapshot
        from zoneinfo import ZoneInfo

        utc_tz = ZoneInfo('UTC')
        mock_now_before = datetime(2026, 5, 16, 23, 59, 50, tzinfo=utc_tz)
        mock_now_after = datetime(2026, 5, 17, 0, 0, 10, tzinfo=utc_tz)

        bucket_date = org_today_local(self.org_a, now=mock_now_before) - timedelta(days=1)

        snap_a_before = apply_snapshot(self.org_a, bucket_date, now=mock_now_before)
        snap_b_before = apply_snapshot(self.org_b, bucket_date, now=mock_now_before)

        self.assertIsNotNone(snap_a_before)
        self.assertIsNotNone(snap_b_before)

        snap_a_after = apply_snapshot(self.org_a, bucket_date, now=mock_now_after)
        snap_b_after = apply_snapshot(self.org_b, bucket_date, now=mock_now_after)

        self.assertEqual(snap_a_before.pk, snap_a_after.pk)
        self.assertEqual(snap_b_before.pk, snap_b_after.pk)

        value_fields = [
            'revenue_paid', 'revenue_accrual', 'invoices_paid_count',
            'appointments_total', 'appointments_done', 'appointments_no_show',
            'medical_records_closed', 'excluded_anchor_missing',
        ]
        for field in value_fields:
            self.assertEqual(
                getattr(snap_a_before, field),
                getattr(snap_a_after, field),
                f"Field {field} differs between midnight-before and midnight-after for org A",
            )
            self.assertEqual(
                getattr(snap_b_before, field),
                getattr(snap_b_after, field),
                f"Field {field} differs between midnight-before and midnight-after for org B",
            )

        self.assertEqual(snap_a_before.built_at, snap_a_after.built_at)
        self.assertEqual(snap_b_before.built_at, snap_b_after.built_at)
