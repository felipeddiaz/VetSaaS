from django.db import migrations


def sync_org_settings_defaults(apps, schema_editor):
    OrganizationSettings = apps.get_model('organizations', 'OrganizationSettings')
    if not OrganizationSettings.objects.exists():
        return
    OrganizationSettings.objects.update(
        auto_create_medical_record=False,
        auto_create_invoice_on_done=False,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0006_alter_organizationsettings_auto_create_invoice_on_done_and_more'),
    ]

    operations = [
        migrations.RunPython(sync_org_settings_defaults, noop),
    ]
