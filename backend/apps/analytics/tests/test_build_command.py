"""
Tests for the build_daily_metrics management command.

Covers: argument parsing (--date / --from --to / --org / --force) and
that the command refuses to snapshot today.
"""
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.analytics.models import DailyOrgMetrics
from apps.organizations.models import Organization
from apps.users.models import User


class BuildDailyMetricsCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Cmd Org", timezone="UTC")

    def test_default_picks_yesterday(self):
        out = StringIO()
        call_command('build_daily_metrics', stdout=out)
        # Should produce one snapshot for yesterday.
        self.assertEqual(DailyOrgMetrics.objects.filter(organization=self.org).count(), 1)
        snap = DailyOrgMetrics.objects.get(organization=self.org)
        from apps.core.datetime_utils import org_today_local
        self.assertEqual(snap.date, org_today_local(self.org) - timedelta(days=1))

    def test_explicit_date(self):
        out = StringIO()
        call_command('build_daily_metrics', '--date=2026-05-01', stdout=out)
        self.assertTrue(
            DailyOrgMetrics.objects.filter(organization=self.org, date=date(2026, 5, 1)).exists()
        )

    def test_range_builds_multiple_days(self):
        out = StringIO()
        call_command('build_daily_metrics', '--from=2026-05-01', '--to=2026-05-03', stdout=out)
        self.assertEqual(
            DailyOrgMetrics.objects.filter(organization=self.org).count(), 3
        )

    def test_today_is_skipped_with_warning(self):
        from apps.core.datetime_utils import org_today_local
        today = org_today_local(self.org)
        out = StringIO()
        call_command('build_daily_metrics', f'--date={today.isoformat()}', stdout=out)
        self.assertIn('skipped today', out.getvalue())

    def test_invalid_org_raises(self):
        with self.assertRaises(CommandError):
            call_command('build_daily_metrics', '--org=999999')

    def test_date_and_range_mutually_exclusive(self):
        with self.assertRaises(CommandError):
            call_command('build_daily_metrics', '--date=2026-05-01', '--from=2026-05-01', '--to=2026-05-02')
