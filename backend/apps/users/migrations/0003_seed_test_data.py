from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_test_data(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    Organization = apps.get_model("organizations", "Organization")
    User = apps.get_model("users", "User")
    Owner = apps.get_model("patients", "Owner")
    Pet = apps.get_model("patients", "Pet")
    Appointment = apps.get_model("appointments", "Appointment")
    MedicalRecord = apps.get_model("medical_records", "MedicalRecord")
    Product = apps.get_model("inventory", "Product")
    Service = apps.get_model("billing", "Service")
    Invoice = apps.get_model("billing", "Invoice")
    InvoiceItem = apps.get_model("billing", "InvoiceItem")
    Prescription = apps.get_model("prescriptions", "Prescription")
    PrescriptionItem = apps.get_model("prescriptions", "PrescriptionItem")

    org, _ = Organization.objects.using(db_alias).get_or_create(
        name="VetSaaS Seed Org"
    )

    admin, _ = User.objects.using(db_alias).get_or_create(
        username="seed_admin",
        defaults={
            "email": "seed_admin@test.com",
            "password": make_password("123456"),
            "first_name": "Admin",
            "last_name": "Seed",
            "organization": org,
            "role": "ADMIN",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )

    vet, _ = User.objects.using(db_alias).get_or_create(
        username="seed_vet",
        defaults={
            "email": "seed_vet@test.com",
            "password": make_password("123456"),
            "first_name": "Valeria",
            "last_name": "Mora",
            "organization": org,
            "role": "VET",
            "specialty": "Medicina general",
            "is_active": True,
        },
    )

    User.objects.using(db_alias).get_or_create(
        username="seed_assistant",
        defaults={
            "email": "seed_assistant@test.com",
            "password": make_password("123456"),
            "first_name": "Camila",
            "last_name": "Rojas",
            "organization": org,
            "role": "ASSISTANT",
            "is_active": True,
        },
    )

    owner, _ = Owner.objects.using(db_alias).get_or_create(
        organization=org,
        name="Juan Perez",
        defaults={"phone": "3001234567"},
    )

    pet, _ = Pet.objects.using(db_alias).get_or_create(
        organization=org,
        owner=owner,
        name="Milo",
        defaults={
            "species": "Canino",
            "breed": "Labrador",
            "birth_date": date(2021, 5, 10),
            "sex": "male",
            "color": "Dorado",
        },
    )

    appointment, _ = Appointment.objects.using(db_alias).get_or_create(
        organization=org,
        pet=pet,
        veterinarian=vet,
        date=date(2026, 1, 15),
        start_time=time(10, 0),
        defaults={
            "end_time": time(10, 30),
            "reason": "Control general",
            "notes": "Paciente estable",
            "status": "done",
        },
    )

    medical_record, _ = MedicalRecord.objects.using(db_alias).get_or_create(
        organization=org,
        pet=pet,
        appointment=appointment,
        defaults={
            "veterinarian": vet,
            "diagnosis": "Chequeo preventivo",
            "treatment": "Vitaminas y seguimiento anual",
            "notes": "Sin hallazgos relevantes",
            "weight": Decimal("18.50"),
        },
    )

    product, _ = Product.objects.using(db_alias).get_or_create(
        organization=org,
        name="Antibiotico Vet 50mg",
        defaults={
            "description": "Uso oral para infecciones comunes",
            "unit": "tableta",
            "stock": Decimal("120.00"),
            "min_stock": Decimal("20.00"),
            "category": "medication",
            "requires_prescription": True,
            "is_active": True,
        },
    )

    Service.objects.using(db_alias).get_or_create(
        organization=org,
        name="Consulta general",
        defaults={
            "description": "Consulta medica veterinaria",
            "base_price": Decimal("60000.00"),
            "is_active": True,
        },
    )

    invoice, _ = Invoice.objects.using(db_alias).get_or_create(
        appointment=appointment,
        defaults={
            "organization": org,
            "medical_record": medical_record,
            "owner": owner,
            "pet": pet,
            "created_by": admin,
            "status": "draft",
            "invoice_type": "consultation",
            "tax_rate": Decimal("0.1900"),
            "notes": "Factura de prueba generada en migracion",
        },
    )

    InvoiceItem.objects.using(db_alias).get_or_create(
        invoice=invoice,
        description="Consulta general",
        defaults={
            "quantity": Decimal("1.00"),
            "unit_price": Decimal("60000.00"),
            "subtotal": Decimal("60000.00"),
        },
    )

    # Buscar el item existente y actualizarlo a usar presentation en lugar de product
    item, created = InvoiceItem.objects.using(db_alias).get_or_create(
        invoice=invoice,
        description="Antibiotico Vet 50mg",
        defaults={
            "presentation": product.presentation,
            "quantity": Decimal("2.00"),
            "unit_price": Decimal("8500.00"),
            "subtotal": Decimal("17000.00"),
        },
    )
    if not created and item.presentation is None:
        item.presentation = product.presentation
        item.product = None
        item.save()

    items = InvoiceItem.objects.using(db_alias).filter(invoice=invoice)
    subtotal = sum((item.subtotal for item in items), Decimal("0.00"))
    tax_amount = (subtotal * invoice.tax_rate).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    Invoice.objects.using(db_alias).filter(pk=invoice.pk).update(
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=subtotal + tax_amount,
    )

    prescription, _ = Prescription.objects.using(db_alias).get_or_create(
        organization=org,
        medical_record=medical_record,
        defaults={
            "veterinarian": vet,
            "pet": pet,
            "notes": "Tomar despues de cada comida",
        },
    )

    PrescriptionItem.objects.using(db_alias).get_or_create(
        prescription=prescription,
        product=product,
        defaults={
            "dose": "1 tableta cada 12 horas",
            "duration": "7 dias",
            "quantity": Decimal("14.00"),
            "instructions": "Administrar con agua",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0001_initial"),
        ("users", "0002_simplify_roles"),
        ("patients", "0004_pet_birth_date_pet_color_pet_sex_alter_pet_breed"),
        ("appointments", "0001_initial"),
        ("medical_records", "0003_alter_medicalrecord_options_and_more"),
        ("inventory", "0002_product_category_product_requires_prescription"),
        ("billing", "0003_invoice_invoice_type_invoice_medical_record"),
        ("prescriptions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_test_data, migrations.RunPython.noop),
    ]
