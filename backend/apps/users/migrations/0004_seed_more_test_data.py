from datetime import date, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.hashers import make_password
from django.db import migrations


def _get_or_create_staff(User, db_alias, organization, role, username_prefix, first_name, last_name, specialty=""):
    existing = User.objects.using(db_alias).filter(
        organization=organization,
        role=role,
        is_active=True,
    ).order_by("id").first()
    if existing:
        return existing

    username = f"{username_prefix}_org_{organization.id}"
    user, _ = User.objects.using(db_alias).get_or_create(
        username=username,
        defaults={
            "email": f"{username}@test.com",
            "password": make_password("123456"),
            "first_name": first_name,
            "last_name": last_name,
            "organization": organization,
            "role": role,
            "specialty": specialty,
            "is_active": True,
        },
    )
    return user


def seed_more_test_data(apps, schema_editor):
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

    orgs = list(Organization.objects.using(db_alias).all().order_by("id"))
    if not orgs:
        org, _ = Organization.objects.using(db_alias).get_or_create(name="VetSaaS Seed Org")
        orgs = [org]

    today = date.today()

    for org in orgs:
        admin = _get_or_create_staff(
            User,
            db_alias,
            org,
            "ADMIN",
            "seed_admin",
            "Admin",
            "Org",
        )
        vet = _get_or_create_staff(
            User,
            db_alias,
            org,
            "VET",
            "seed_vet",
            "Laura",
            "Quintero",
            "Medicina interna",
        )

        owner_specs = [
            ("Ana Torres", "3001000101"),
            ("Luis Gomez", "3001000102"),
            ("Marta Velez", "3001000103"),
            ("Carlos Pena", "3001000104"),
            ("Diana Ruiz", "3001000105"),
        ]

        owners = []
        for idx, (name, phone) in enumerate(owner_specs, start=1):
            owner, _ = Owner.objects.using(db_alias).get_or_create(
                organization=org,
                name=f"{name} {org.id}",
                defaults={"phone": phone},
            )
            if not owner.phone:
                owner.phone = phone
                owner.save(update_fields=["phone"])
            owners.append(owner)

        pet_specs = [
            ("Luna", "Felino", "Siames", "female", "Blanco", 0),
            ("Rocky", "Canino", "Bulldog", "male", "Cafe", 1),
            ("Nala", "Felino", "Criollo", "female", "Negro", 2),
            ("Bruno", "Canino", "Golden", "male", "Dorado", 3),
            ("Mia", "Canino", "Poodle", "female", "Blanco", 4),
            ("Simba", "Felino", "Persa", "male", "Gris", 0),
            ("Toby", "Canino", "Labrador", "male", "Miel", 1),
            ("Kira", "Canino", "Pastor", "female", "Negro", 2),
        ]

        pets = []
        for idx, (name, species, breed, sex, color, owner_idx) in enumerate(pet_specs, start=1):
            pet, _ = Pet.objects.using(db_alias).get_or_create(
                organization=org,
                owner=owners[owner_idx],
                name=f"{name} {org.id}",
                defaults={
                    "species": species,
                    "breed": breed,
                    "birth_date": today - timedelta(days=365 * (idx + 1)),
                    "sex": sex,
                    "color": color,
                },
            )
            pets.append(pet)

        product_specs = [
            ("Seed Antibiotico 50mg", "medication", True, Decimal("9500.00"), Decimal("100.00"), Decimal("15.00")),
            ("Seed Antipulgas Pipeta", "medication", True, Decimal("18500.00"), Decimal("60.00"), Decimal("10.00")),
            ("Seed Alimento Premium Adulto", "food", False, Decimal("22000.00"), Decimal("70.00"), Decimal("12.00")),
            ("Seed Shampoo Dermico", "other", False, Decimal("14000.00"), Decimal("50.00"), Decimal("8.00")),
            ("Seed Collar Antiparasitario", "accessory", False, Decimal("30000.00"), Decimal("25.00"), Decimal("6.00")),
        ]

        products = []
        for name, category, requires_rx, unit_price, stock, min_stock in product_specs:
            product, _ = Product.objects.using(db_alias).get_or_create(
                organization=org,
                name=f"{name} {org.id}",
                defaults={
                    "description": "Producto de prueba para escenarios de consulta y facturacion",
                    "unit": "unidad",
                    "stock": stock,
                    "min_stock": min_stock,
                    "category": category,
                    "requires_prescription": requires_rx,
                    "is_active": True,
                },
            )
            products.append((product, unit_price))

        service_specs = [
            ("Consulta general", Decimal("60000.00")),
            ("Control postoperatorio", Decimal("45000.00")),
            ("Vacunacion", Decimal("35000.00")),
            ("Desparasitacion", Decimal("28000.00")),
        ]

        services = []
        for name, base_price in service_specs:
            service, _ = Service.objects.using(db_alias).get_or_create(
                organization=org,
                name=f"{name} {org.id}",
                defaults={
                    "description": "Servicio de prueba",
                    "base_price": base_price,
                    "is_active": True,
                },
            )
            services.append((service, base_price))

        medical_records = []
        for i, pet in enumerate(pets[:6]):
            appointment_date = today - timedelta(days=(i + 1) * 3)
            appointment, _ = Appointment.objects.using(db_alias).get_or_create(
                organization=org,
                pet=pet,
                veterinarian=vet,
                date=appointment_date,
                start_time=time(9 + (i % 4), 0),
                defaults={
                    "end_time": time(9 + (i % 4), 30),
                    "reason": f"Consulta de control #{i + 1}",
                    "notes": "Generada por seed",
                    "status": "done",
                },
            )

            mr, _ = MedicalRecord.objects.using(db_alias).get_or_create(
                organization=org,
                pet=pet,
                appointment=appointment,
                defaults={
                    "veterinarian": vet,
                    "diagnosis": f"Revision general de {pet.name}",
                    "treatment": "Manejo sintomatico y control en 15 dias",
                    "notes": f"seed_record_org_{org.id}_{i + 1}",
                    "weight": Decimal(str(4.5 + i)),
                },
            )
            medical_records.append(mr)

        walkin_pet = pets[6]
        walkin_record, _ = MedicalRecord.objects.using(db_alias).get_or_create(
            organization=org,
            pet=walkin_pet,
            notes=f"seed_walkin_org_{org.id}",
            defaults={
                "veterinarian": vet,
                "diagnosis": "Vacunacion anual",
                "treatment": "Aplicacion de vacuna multivalente",
                "weight": Decimal("22.00"),
            },
        )
        medical_records.append(walkin_record)

        for i, record in enumerate(medical_records):
            if record.appointment_id:
                invoice, _ = Invoice.objects.using(db_alias).get_or_create(
                    appointment_id=record.appointment_id,
                    defaults={
                        "organization": org,
                        "medical_record": record,
                        "owner": record.pet.owner,
                        "pet": record.pet,
                        "created_by": admin,
                        "status": "draft",
                        "invoice_type": "consultation",
                        "tax_rate": Decimal("0.1900"),
                        "notes": "Factura seed de consulta",
                    },
                )
            else:
                invoice, _ = Invoice.objects.using(db_alias).get_or_create(
                    organization=org,
                    medical_record=record,
                    invoice_type="direct_sale",
                    owner=record.pet.owner,
                    pet=record.pet,
                    defaults={
                        "created_by": admin,
                        "status": "draft",
                        "tax_rate": Decimal("0.1900"),
                        "notes": "Factura seed de venta directa",
                    },
                )

            service, service_price = services[i % len(services)]
            product, product_price = products[i % len(products)]

            InvoiceItem.objects.using(db_alias).get_or_create(
                invoice=invoice,
                description=service.name,
                defaults={
                    "service": service,
                    "quantity": Decimal("1.00"),
                    "unit_price": service_price,
                    "subtotal": service_price,
                },
            )

            # Buscar el item existente y actualizarlo a usar presentation en lugar de product
            item, created = InvoiceItem.objects.using(db_alias).get_or_create(
                invoice=invoice,
                description=product.name,
                defaults={
                    "presentation": product.presentation,
                    "quantity": Decimal("1.00"),
                    "unit_price": product_price,
                    "subtotal": product_price,
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

            if i % 2 == 0:
                rx_product, _ = products[0]
                prescription, _ = Prescription.objects.using(db_alias).get_or_create(
                    organization=org,
                    medical_record=record,
                    defaults={
                        "veterinarian": vet,
                        "pet": record.pet,
                        "notes": "Tratamiento por 7 dias",
                    },
                )

                PrescriptionItem.objects.using(db_alias).get_or_create(
                    prescription=prescription,
                    product=rx_product,
                    defaults={
                        "dose": "1 dosis cada 12 horas",
                        "duration": "7 dias",
                        "quantity": Decimal("14.00"),
                        "instructions": "Suministrar despues de la comida",
                    },
                )


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

    operations = [
        migrations.RunPython(seed_more_test_data, migrations.RunPython.noop),
    ]
