from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.db import migrations


def backfill_appointment_datetimes(apps, schema_editor):
    Appointment = apps.get_model('appointments', 'Appointment')
    Organization = apps.get_model('organizations', 'Organization')

    org_tz = {
        org.id: (org.timezone or 'UTC')
        for org in Organization.objects.all().only('id', 'timezone')
    }

    for appt in Appointment.objects.all().iterator():
        tz_name = appt.timezone_at_creation or org_tz.get(appt.organization_id, 'UTC')
        tz = ZoneInfo(tz_name)

        if appt.date and appt.start_time:
            start_local = datetime.combine(appt.date, appt.start_time).replace(tzinfo=tz)
            appt.start_datetime = start_local.astimezone(dt_timezone.utc)
        if appt.date and appt.end_time:
            end_local = datetime.combine(appt.date, appt.end_time).replace(tzinfo=tz)
            appt.end_datetime = end_local.astimezone(dt_timezone.utc)

        if not appt.timezone_at_creation:
            appt.timezone_at_creation = tz_name

        appt.save(update_fields=['start_datetime', 'end_datetime', 'timezone_at_creation'])


class Migration(migrations.Migration):
    dependencies = [
        ('organizations', '0002_organization_timezone_and_more'),
        ('appointments', '0002_appointment_end_datetime_appointment_start_datetime_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_appointment_datetimes, migrations.RunPython.noop),
    ]
