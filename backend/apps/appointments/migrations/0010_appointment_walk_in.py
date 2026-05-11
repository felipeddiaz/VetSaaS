"""
Capa 2 — Appointment.walk_in authoritative flag.

Adds:
- Appointment.walk_in BooleanField(default=False, editable=False, db_index=True)

Backfill heuristic: an appointment is considered a walk-in if and only if it
has NO 'scheduled' transition in its AppointmentStatusChange history AND its
current status is in ('in_progress', 'done', 'canceled', 'no_show'). The
walk-in creation flow always starts the appointment directly at 'in_progress'.

Heuristic limitations:
- An appointment created at 'in_progress' but later reverted does not get
  flagged. Acceptable; reversions are rare.
- Older data without AppointmentStatusChange rows (pre-migration 0008)
  cannot be classified. Defaults to False (conservative).

Going forward, walk_in is set by appointments/views.py::walk_in directly
on creation. The heuristic is never re-applied.
"""

from django.db import migrations, models


def backfill_walk_in(apps, schema_editor):
    Appointment = apps.get_model('appointments', 'Appointment')
    AppointmentStatusChange = apps.get_model('appointments', 'AppointmentStatusChange')

    candidate_statuses = ('in_progress', 'done', 'canceled', 'no_show')
    candidate_ids = list(
        Appointment.objects.filter(status__in=candidate_statuses).values_list('pk', flat=True)
    )
    if not candidate_ids:
        return

    appts_with_scheduled_transition = set(
        AppointmentStatusChange.objects.filter(
            appointment_id__in=candidate_ids,
            from_status='scheduled',
        ).values_list('appointment_id', flat=True)
    )

    walk_in_ids = [
        pk for pk in candidate_ids if pk not in appts_with_scheduled_transition
    ]
    if walk_in_ids:
        Appointment.objects.filter(pk__in=walk_in_ids).update(walk_in=True)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0009_add_public_id_to_exposed_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='walk_in',
            field=models.BooleanField(db_index=True, default=False, editable=False),
        ),
        migrations.RunPython(backfill_walk_in, reverse_noop),
    ]
