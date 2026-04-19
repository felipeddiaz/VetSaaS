from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_seed_test_data"),
        ("patients", "0004_pet_birth_date_pet_color_pet_sex_alter_pet_breed"),
        ("appointments", "0001_initial"),
        ("medical_records", "0003_alter_medicalrecord_options_and_more"),
        ("inventory", "0002_product_category_product_requires_prescription"),
        ("billing", "0003_invoice_invoice_type_invoice_medical_record"),
        ("prescriptions", "0001_initial"),
    ]

    operations = []
