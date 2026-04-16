from datetime import date, datetime, time, timedelta
from decimal import Decimal
from random import Random

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem, Service
from apps.billing.services import confirm_invoice as confirm_invoice_service
from apps.core.datetime_utils import local_date_time_to_utc
from apps.inventory.models import Product, Presentation, StockMovement, MedicalRecordProduct
from apps.medical_records.models import MedicalRecord
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.users.models import User


FIRST_NAMES = [
    "Sofia", "Valentina", "Camila", "Regina", "Lucia", "Renata", "Mariana", "Ximena", "Aitana", "Elena",
    "Diego", "Mateo", "Santiago", "Sebastian", "Leonardo", "Emiliano", "Gael", "Javier", "Daniel", "Andres",
    "Fernanda", "Paula", "Montserrat", "Natalia", "Daniela", "Carla", "Adriana", "Alicia", "Jimena", "Patricia",
]

LAST_NAMES = [
    "Garcia", "Lopez", "Martinez", "Hernandez", "Gonzalez", "Perez", "Sanchez", "Ramirez", "Torres", "Flores",
    "Rivera", "Gomez", "Diaz", "Vargas", "Castro", "Mendoza", "Ortega", "Cruz", "Morales", "Ruiz",
]

PET_NAMES = [
    "Luna", "Max", "Nala", "Rocky", "Mia", "Toby", "Kira", "Canela", "Bruno", "Coco", "Simba", "Lola",
    "Milo", "Zeus", "Nina", "Bongo", "Moka", "Duna", "Paco", "Greta", "Tina", "Rocco", "Kiwi", "Leia",
    "Gala", "Maya", "Rita", "Polo", "Chispa", "Milo", "Nero", "Sasha", "Loki", "Runa", "Nube", "Pinta",
]

PRODUCT_CATALOG = [
    ("Antibiotico AmoxiVet", "medication", True, "tablet", Decimal("380.00"), Decimal("180.00"), Decimal("26.00"), Decimal("8.00")),
    ("Antiinflamatorio Carprovet", "medication", True, "tablet", Decimal("420.00"), Decimal("210.00"), Decimal("20.00"), Decimal("7.00")),
    ("Antiparasitario EndoCare", "medication", True, "capsule", Decimal("260.00"), Decimal("130.00"), Decimal("30.00"), Decimal("10.00")),
    ("Pipeta Antipulgas TotalShield", "medication", True, "piece", Decimal("310.00"), Decimal("150.00"), Decimal("24.00"), Decimal("8.00")),
    ("Vacuna Triple Felina", "medication", True, "vial", Decimal("520.00"), Decimal("260.00"), Decimal("20.00"), Decimal("6.00")),
    ("Vacuna Quintupla Canina", "medication", True, "vial", Decimal("610.00"), Decimal("300.00"), Decimal("18.00"), Decimal("5.00")),
    ("Shampoo Dermatologico Avena", "other", False, "bottle", Decimal("230.00"), Decimal("110.00"), Decimal("40.00"), Decimal("12.00")),
    ("Limpiador Otico Balance", "other", False, "bottle", Decimal("190.00"), Decimal("95.00"), Decimal("36.00"), Decimal("10.00")),
    ("Suplemento Articular FlexiPet", "medication", False, "capsule", Decimal("540.00"), Decimal("260.00"), Decimal("22.00"), Decimal("8.00")),
    ("Alimento Canino Premium Adulto", "food", False, "bag", Decimal("1280.00"), Decimal("650.00"), Decimal("32.00"), Decimal("10.00")),
    ("Alimento Felino Esterilizado", "food", False, "bag", Decimal("1180.00"), Decimal("580.00"), Decimal("28.00"), Decimal("9.00")),
    ("Arena Aglomerante Ultra", "other", False, "bag", Decimal("320.00"), Decimal("150.00"), Decimal("40.00"), Decimal("12.00")),
    ("Collar Ajustable Confort", "accessory", False, "piece", Decimal("170.00"), Decimal("80.00"), Decimal("35.00"), Decimal("10.00")),
    ("Arnes Paseo Seguro", "accessory", False, "piece", Decimal("360.00"), Decimal("170.00"), Decimal("20.00"), Decimal("6.00")),
    ("Juguete Mordedera Resistente", "accessory", False, "piece", Decimal("220.00"), Decimal("100.00"), Decimal("26.00"), Decimal("8.00")),
    ("Snack Dental DailyCare", "food", False, "bag", Decimal("190.00"), Decimal("90.00"), Decimal("38.00"), Decimal("12.00")),
]

SERVICE_CATALOG = [
    ("Consulta general", Decimal("450.00")),
    ("Consulta de seguimiento", Decimal("380.00")),
    ("Consulta de urgencia", Decimal("1200.00")),
    ("Vacunacion", Decimal("490.00")),
    ("Desparasitacion", Decimal("280.00")),
    ("Limpieza dental", Decimal("1400.00")),
    ("Radiografia simple", Decimal("950.00")),
    ("Ultrasonido", Decimal("1100.00")),
    ("Curacion", Decimal("350.00")),
    ("Prueba sanguinea", Decimal("640.00")),
]


class Command(BaseCommand):
    help = "Genera datos demo realistas (MXN) de forma manual"

    def add_arguments(self, parser):
        parser.add_argument("--org", default="Clinica Vet Norte", help="Nombre de organización demo")
        parser.add_argument("--password", default="123456", help="Password para usuarios demo")
        parser.add_argument("--seed", type=int, default=2406, help="Semilla de aleatoriedad")
        parser.add_argument("--reset", action="store_true", help="Borra datos demo existentes de la organización")

        parser.add_argument("--owners", type=int, default=40)
        parser.add_argument("--pets", type=int, default=90)
        parser.add_argument("--products", type=int, default=45)
        parser.add_argument("--appointments", type=int, default=140)
        parser.add_argument("--records", type=int, default=95)
        parser.add_argument("--invoices", type=int, default=110)

    def handle(self, *args, **options):
        rnd = Random(options["seed"])

        org, _ = Organization.objects.get_or_create(
            name=options["org"],
            defaults={"timezone": "America/Mexico_City", "tax_rate": Decimal("0.1600")},
        )
        if org.timezone == "UTC":
            org.timezone = "America/Mexico_City"
        if org.tax_rate == Decimal("0.0000"):
            org.tax_rate = Decimal("0.1600")
        org.save(update_fields=["timezone", "tax_rate"])

        if options["reset"]:
            self._reset_org_data(org)

        admin = self._upsert_user(
            username="demo_admin",
            email="admin.demo@vetsaas.mx",
            first_name="Aurora",
            last_name="Salazar",
            organization=org,
            role="ADMIN",
            password=options["password"],
            is_staff=True,
            is_superuser=True,
        )
        vets = [
            self._upsert_user(
                username="demo_vet_aurora",
                email="vet.aurora@vetsaas.mx",
                first_name="Aurora",
                last_name="Montes",
                organization=org,
                role="VET",
                specialty="Medicina interna",
                password=options["password"],
            ),
            self._upsert_user(
                username="demo_vet_bruno",
                email="vet.bruno@vetsaas.mx",
                first_name="Bruno",
                last_name="Rivas",
                organization=org,
                role="VET",
                specialty="Cirugia de tejidos blandos",
                password=options["password"],
            ),
        ]
        self._upsert_user(
            username="demo_assistant",
            email="asistente.demo@vetsaas.mx",
            first_name="Camila",
            last_name="Paredes",
            organization=org,
            role="ASSISTANT",
            password=options["password"],
        )

        owners = self._create_owners(org, options["owners"], rnd)
        pets = self._create_pets(org, owners, options["pets"], rnd)
        services = self._create_services(org)
        presentations = self._create_inventory(org, options["products"], rnd)

        appointments = self._create_appointments(org, pets, vets, options["appointments"], rnd)
        medical_records = self._create_medical_records(org, appointments, pets, vets, options["records"], rnd)
        self._create_prescriptions(org, medical_records, presentations, vets, rnd)
        self._create_invoices(
            org=org,
            admin=admin,
            services=services,
            presentations=presentations,
            appointments=appointments,
            medical_records=medical_records,
            max_invoices=options["invoices"],
            rnd=rnd,
        )

        self.stdout.write("Seed manual completado.")
        self.stdout.write(f"Organización: {org.name}")
        self.stdout.write("Usuarios demo: demo_admin, demo_vet_aurora, demo_vet_bruno, demo_assistant")
        self.stdout.write(f"Password: {options['password']}")

    def _reset_org_data(self, org):
        PrescriptionItem.objects.filter(prescription__organization=org).delete()
        Prescription.objects.filter(organization=org).delete()
        InvoiceItem.objects.filter(invoice__organization=org).delete()
        Invoice.objects.filter(organization=org).delete()
        MedicalRecordProduct.objects.filter(medical_record__organization=org).delete()
        StockMovement.objects.filter(organization=org).delete()
        MedicalRecord.objects.filter(organization=org).delete()
        Appointment.objects.filter(organization=org).delete()
        Pet.objects.filter(organization=org).delete()
        Owner.objects.filter(organization=org).delete()
        Presentation.objects.filter(organization=org).delete()
        Product.objects.filter(organization=org).delete()
        Service.objects.filter(organization=org).delete()
        User.objects.filter(organization=org, username__startswith="demo_").delete()

    def _upsert_user(
        self,
        username,
        email,
        first_name,
        last_name,
        organization,
        role,
        password,
        specialty="",
        is_staff=False,
        is_superuser=False,
    ):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "organization": organization,
                "role": role,
                "specialty": specialty,
                "is_active": True,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
            },
        )
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.organization = organization
        user.role = role
        user.specialty = specialty
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.is_active = True
        user.set_password(password)
        user.save()
        return user

    def _create_owners(self, org, count, rnd):
        owners = []
        names = [f"{fn} {ln}" for fn in FIRST_NAMES for ln in LAST_NAMES]
        rnd.shuffle(names)

        for idx in range(count):
            full_name = names[idx % len(names)]
            phone = f"55{rnd.randint(20000000, 99999999)}"
            owner, _ = Owner.objects.get_or_create(
                organization=org,
                name=full_name,
                defaults={"phone": phone},
            )
            if owner.phone != phone:
                owner.phone = phone
                owner.save(update_fields=["phone"])
            owners.append(owner)
        return owners

    def _create_pets(self, org, owners, count, rnd):
        pets = []
        species_map = [
            ("Canino", ["Mestizo", "Labrador", "Poodle", "Pastor Aleman", "Bulldog"], "male"),
            ("Felino", ["Criollo", "Siames", "Persa", "Maine Coon"], "female"),
        ]
        colors = ["Negro", "Blanco", "Cafe", "Miel", "Atigrado", "Gris", "Tricolor"]

        for _ in range(count):
            owner = rnd.choice(owners)
            name = rnd.choice(PET_NAMES)
            species, breeds, default_sex = rnd.choice(species_map)
            breed = rnd.choice(breeds)
            sex = rnd.choice([default_sex, "male", "female", "unknown"])
            birth_date = date.today() - timedelta(days=rnd.randint(180, 3650))
            color = rnd.choice(colors)

            pet = Pet.objects.create(
                organization=org,
                owner=owner,
                name=name,
                species=species,
                breed=breed,
                birth_date=birth_date,
                sex=sex,
                color=color,
            )
            pets.append(pet)
        return pets

    def _create_services(self, org):
        services = []
        for name, price in SERVICE_CATALOG:
            service, _ = Service.objects.get_or_create(
                organization=org,
                name=name,
                defaults={"description": f"Servicio veterinario: {name}", "base_price": price, "is_active": True},
            )
            if service.base_price != price:
                service.base_price = price
                service.save(update_fields=["base_price"])
            services.append(service)
        return services

    def _create_inventory(self, org, count, rnd):
        presentations = []
        shuffled_catalog = PRODUCT_CATALOG[:]
        rnd.shuffle(shuffled_catalog)

        for idx in range(count):
            (
                product_name,
                category,
                requires_prescription,
                base_unit,
                sale_price,
                cost_estimate,
                stock,
                min_stock,
            ) = shuffled_catalog[idx % len(shuffled_catalog)]

            internal_code = f"DEMO-{category[:3].upper()}-{idx + 1:04d}"
            product, _ = Product.objects.get_or_create(
                organization=org,
                internal_code=internal_code,
                defaults={
                    "name": product_name,
                    "description": f"Costo estimado de compra: ${cost_estimate} MXN",
                    "is_active": True,
                    "category": category,
                    "requires_prescription": requires_prescription,
                },
            )

            product.name = product_name
            product.description = f"Costo estimado de compra: ${cost_estimate} MXN"
            product.category = category
            product.requires_prescription = requires_prescription
            product.is_active = True
            product.save()

            presentation, _ = Presentation.objects.get_or_create(
                organization=org,
                product=product,
                defaults={
                    "name": product_name,
                    "base_unit": base_unit,
                    "quantity": Decimal("1.00"),
                    "sale_price": sale_price,
                    "stock": stock,
                    "min_stock": min_stock,
                },
            )
            presentation.name = product_name
            presentation.base_unit = base_unit
            presentation.quantity = Decimal("1.00")
            presentation.sale_price = sale_price
            presentation.stock = stock + Decimal(rnd.randint(0, 20))
            presentation.min_stock = min_stock
            presentation.save()
            presentations.append(presentation)

        return presentations

    def _create_appointments(self, org, pets, vets, count, rnd):
        appointments = []
        slots = [time(9, 0), time(9, 30), time(10, 0), time(10, 30), time(11, 0), time(12, 0), time(16, 0)]
        reasons = [
            "Revision general", "Control de piel", "Vomito recurrente", "Control postoperatorio",
            "Vacunacion", "Desparasitacion", "Dolor articular", "Chequeo preventivo",
        ]

        for _ in range(count):
            pet = rnd.choice(pets)
            vet = rnd.choice(vets)
            appt_date = date.today() + timedelta(days=rnd.randint(-60, 20))
            start = rnd.choice(slots)
            end = (datetime.combine(date.today(), start) + timedelta(minutes=30)).time()
            if appt_date < date.today():
                status = rnd.choices(["done", "canceled", "scheduled"], weights=[75, 15, 10], k=1)[0]
            elif appt_date == date.today():
                status = rnd.choices(["scheduled", "done", "canceled"], weights=[70, 20, 10], k=1)[0]
            else:
                status = rnd.choices(["scheduled", "canceled"], weights=[92, 8], k=1)[0]

            start_dt = local_date_time_to_utc(org, appt_date, start)
            end_dt = local_date_time_to_utc(org, appt_date, end)

            appointment = Appointment.objects.create(
                organization=org,
                pet=pet,
                veterinarian=vet,
                date=appt_date,
                start_time=start,
                end_time=end,
                start_datetime=start_dt,
                end_datetime=end_dt,
                timezone_at_creation=org.timezone,
                reason=rnd.choice(reasons),
                notes="Consulta demo generada por seeder manual",
                status=status,
            )
            appointments.append(appointment)
        return appointments

    def _create_medical_records(self, org, appointments, pets, vets, target_count, rnd):
        records = []

        done_appointments = [a for a in appointments if a.status == "done"]
        rnd.shuffle(done_appointments)
        diagnostic_pool = [
            "Gastritis leve", "Dermatitis alergica", "Otitis externa", "Gingivitis",
            "Parasitosis intestinal", "Control de peso", "Evaluacion preoperatoria", "Conjuntivitis",
        ]
        treatment_pool = [
            "Tratamiento por siete dias y control en dos semanas",
            "Cambio de dieta y seguimiento clinico",
            "Medicacion antiinflamatoria y reposo relativo",
            "Limpieza local y tratamiento topico",
        ]

        for appointment in done_appointments[:target_count]:
            record = MedicalRecord.objects.create(
                organization=org,
                pet=appointment.pet,
                veterinarian=appointment.veterinarian,
                appointment=appointment,
                diagnosis=rnd.choice(diagnostic_pool),
                treatment=rnd.choice(treatment_pool),
                notes="Nota clinica demo",
                weight=Decimal(str(rnd.randint(3, 36))) + Decimal("0.50"),
            )
            records.append(record)

        remaining = max(0, target_count - len(records))
        for _ in range(remaining):
            pet = rnd.choice(pets)
            vet = rnd.choice(vets)
            record = MedicalRecord.objects.create(
                organization=org,
                pet=pet,
                veterinarian=vet,
                diagnosis=rnd.choice(diagnostic_pool),
                treatment=rnd.choice(treatment_pool),
                notes="Consulta walk-in demo",
                weight=Decimal(str(rnd.randint(3, 36))) + Decimal("0.20"),
            )
            records.append(record)
        return records

    def _create_prescriptions(self, org, records, presentations, vets, rnd):
        for record in records:
            if rnd.random() > 0.35:
                continue

            product = rnd.choice([p for p in presentations if p.product.requires_prescription]) if any(
                p.product.requires_prescription for p in presentations
            ) else rnd.choice(presentations)

            prescription = Prescription.objects.create(
                organization=org,
                medical_record=record,
                veterinarian=record.veterinarian or rnd.choice(vets),
                pet=record.pet,
                notes="Administrar posterior a alimento",
            )
            PrescriptionItem.objects.create(
                prescription=prescription,
                product=product.product,
                dose="Una dosis cada doce horas",
                duration="Siete dias",
                quantity=Decimal("14.00"),
                instructions="Completar tratamiento",
            )

    def _create_invoices(self, org, admin, services, presentations, appointments, medical_records, max_invoices, rnd):
        created_count = 0
        done_appts = [a for a in appointments if a.status == "done"]

        for appointment in done_appts:
            if created_count >= max_invoices:
                break
            medical_record = next((r for r in medical_records if r.appointment_id == appointment.id), None)
            invoice, created = Invoice.objects.get_or_create(
                appointment=appointment,
                defaults={
                    "organization": org,
                    "invoice_type": "consultation",
                    "medical_record": medical_record,
                    "owner": appointment.pet.owner,
                    "pet": appointment.pet,
                    "created_by": admin,
                    "status": "draft",
                    "tax_rate": org.tax_rate,
                    "notes": "Factura de consulta generada por seed manual",
                },
            )
            if created:
                self._add_invoice_items(invoice, services, presentations, rnd, direct_sale=False)
                self._advance_invoice_status(invoice, admin, rnd)
                created_count += 1

        walkin_records = [r for r in medical_records if not r.appointment_id]
        for record in walkin_records:
            if created_count >= max_invoices:
                break
            invoice, created = Invoice.objects.get_or_create(
                organization=org,
                medical_record=record,
                owner=record.pet.owner,
                pet=record.pet,
                invoice_type="direct_sale",
                defaults={
                    "created_by": admin,
                    "status": "draft",
                    "tax_rate": org.tax_rate,
                    "notes": "Venta directa generada por seed manual",
                },
            )
            if created:
                self._add_invoice_items(invoice, services, presentations, rnd, direct_sale=True)
                self._advance_invoice_status(invoice, admin, rnd)
                created_count += 1

    def _add_invoice_items(self, invoice, services, presentations, rnd, direct_sale):
        service = rnd.choice(services)
        qty = Decimal(rnd.choice(["1.00", "1.00", "2.00"]))
        InvoiceItem.objects.create(
            invoice=invoice,
            service=service,
            description=service.name,
            quantity=qty,
            unit_price=service.base_price,
        )

        lines = rnd.randint(1, 2) if direct_sale else rnd.randint(0, 1)
        for _ in range(lines):
            presentation = rnd.choice(presentations)
            if presentation.stock <= 0:
                continue
            qty = Decimal(rnd.choice(["1.00", "1.00", "2.00", "3.00"]))
            if qty > presentation.stock:
                qty = Decimal("1.00")

            InvoiceItem.objects.create(
                invoice=invoice,
                presentation=presentation,
                product=presentation.product,
                description=presentation.product.name,
                quantity=qty,
                unit_price=presentation.sale_price,
            )

    def _advance_invoice_status(self, invoice, admin, rnd):
        target = rnd.choices(["draft", "confirmed", "paid"], weights=[40, 35, 25], k=1)[0]
        if target in ("confirmed", "paid"):
            try:
                confirm_invoice_service(invoice, admin)
                invoice.refresh_from_db()
            except Exception:
                return

        if target == "paid" and invoice.status == "confirmed":
            invoice.status = "paid"
            invoice.payment_method = rnd.choice(["cash", "card", "transfer"])
            invoice.paid_at = timezone.now() - timedelta(days=rnd.randint(0, 25))
            invoice.save(update_fields=["status", "payment_method", "paid_at", "updated_at"])
