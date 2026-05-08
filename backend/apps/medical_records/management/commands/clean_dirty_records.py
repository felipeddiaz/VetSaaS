from django.core.management.base import BaseCommand
from apps.medical_records.models import MedicalRecord
from apps.core.sanitize import sanitize_text


class Command(BaseCommand):
    help = "Limpia registros médicos creados antes de activar bleach (uso único)"

    def handle(self, *args, **kwargs):
        count = 0
        for record in MedicalRecord.objects.iterator():
            changed = False
            for field in ['diagnosis', 'treatment', 'notes']:
                val = getattr(record, field) or ''
                clean = sanitize_text(val, max_length=5000)
                if clean != val:
                    setattr(record, field, clean)
                    changed = True
            if changed:
                record.save(update_fields=['diagnosis', 'treatment', 'notes'])
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Limpiados: {count} registros"))
