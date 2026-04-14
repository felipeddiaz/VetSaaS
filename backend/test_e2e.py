#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import django
import requests
import json
from decimal import Decimal

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.billing.models import Invoice, InvoiceItem, InvoiceAuditLog
from apps.inventory.models import StockMovement, Presentation, Product
from apps.users.models import User
from apps.organizations.models import Organization
from apps.patients.models import Owner, Pet

BASE_URL = "http://localhost:8000/api"
RESULTS = []

def log_result(test_name, status, details=""):
    print(f"\n[{status}] {test_name}")
    if details:
        print(f"     {details}")
    RESULTS.append((test_name, status, details))

def get_admin_token():
    """Obtiene token de autenticación del admin"""
    response = requests.post(f"{BASE_URL}/token/", json={
        "username": "seed_admin",
        "password": "123456"
    })
    if response.status_code == 200:
        return response.json().get("access")
    else:
        print(f"ERROR: No se pudo obtener token: {response.text}")
        return None

def get_vet_token():
    """Obtiene token de autenticación del VET"""
    response = requests.post(f"{BASE_URL}/token/", json={
        "username": "seed_vet",
        "password": "123456"
    })
    if response.status_code == 200:
        return response.json().get("access")
    else:
        print(f"ERROR: No se pudo obtener token VET: {response.text}")
        return None

# ==================== PRUEBAS ====================
print("\n" + "="*60)
print("PRUEBAS END-TO-END - PLAN DE REESTRUCTURACIÓN")
print("="*60)

ADMIN_TOKEN = get_admin_token()
VET_TOKEN = get_vet_token()

if not ADMIN_TOKEN or not VET_TOKEN:
    print("ERROR: No se obtuvieron tokens de autenticación")
    exit(1)

admin_headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
vet_headers = {"Authorization": f"Bearer {VET_TOKEN}"}

# Obtener owner y pet para las pruebas
org = Organization.objects.first()
owner = Owner.objects.filter(organization=org).first()
pet = Pet.objects.filter(organization=org).first()

if not owner or not pet:
    print("ERROR: No hay owner o pet en la base de datos")
    exit(1)

print(f"\nDatos de prueba: Owner={owner.name}, Pet={pet.name}")

# ==================== CASO A ====================
print("\n\n--- CASO A: direct_sale + presentacion + confirmar ---")
try:
    # Crear factura
    invoice_data = {
        "invoice_type": "direct_sale",
        "status": "draft",
        "owner_id": owner.id,
        "pet_id": pet.id,
    }

    resp = requests.post(f"{BASE_URL}/billing/invoices/",
                        json=invoice_data,
                        headers=admin_headers)

    if resp.status_code != 201:
        log_result("A) Crear factura", "FALLO", f"Status {resp.status_code}: {resp.text}")
    else:
        invoice_id = resp.json()["id"]
        print(f"   Factura creada: ID {invoice_id}")

        # Obtener una presentación con stock
        pres_with_stock = Presentation.objects.filter(stock__gt=0).first()
        if not pres_with_stock:
            log_result("A) Presentación con stock", "FALLO", "No hay presentaciones con stock")
        else:
            initial_stock = pres_with_stock.stock
            print(f"   Presentación: {pres_with_stock.name}, stock inicial: {initial_stock}")

            # Agregar ítem
            item_data = {
                "presentation_id": pres_with_stock.id,
                "quantity": 1,
                "unit_price": 5000
            }
            resp = requests.post(f"{BASE_URL}/billing/invoices/{invoice_id}/items/",
                               json=item_data,
                               headers=admin_headers)

            if resp.status_code != 201:
                log_result("A) Agregar ítem", "FALLO", f"Status {resp.status_code}: {resp.text}")
            else:
                item_id = resp.json()["id"]
                print(f"   Ítem agregado: ID {item_id}")

                # Confirmar factura
                resp = requests.patch(f"{BASE_URL}/billing/invoices/{invoice_id}/confirm/",
                                     headers=admin_headers)

                if resp.status_code != 200:
                    log_result("A) Confirmar factura", "FALLO", f"Status {resp.status_code}: {resp.text}")
                else:
                    # Verificar estado y stock
                    invoice = Invoice.objects.get(id=invoice_id)
                    new_stock = Presentation.objects.get(id=pres_with_stock.id).stock

                    if invoice.status == "confirmed" and new_stock < initial_stock:
                        log_result("A) Confirmar factura + stock", "OK",
                                  f"Status: {invoice.status}, Stock bajó de {initial_stock} a {new_stock}")
                    else:
                        log_result("A) Confirmar factura + stock", "FALLO",
                                  f"Status: {invoice.status}, Stock: {new_stock}")
except Exception as e:
    log_result("A) Caso completo", "FALLO", str(e))

# ==================== CASO B ====================
print("\n\n--- CASO B: Item sin stock --> error 400 ---")
try:
    # Crear factura
    invoice_data = {
        "invoice_type": "direct_sale",
        "status": "draft",
        "owner_id": owner.id,
        "pet_id": pet.id,
    }
    resp = requests.post(f"{BASE_URL}/billing/invoices/",
                        json=invoice_data,
                        headers=admin_headers)
    invoice_id = resp.json()["id"]

    # Buscar presentación sin stock
    pres_no_stock = Presentation.objects.filter(stock=0).first()
    if not pres_no_stock:
        log_result("B) Presentación sin stock", "FALLO", "No hay presentaciones sin stock")
    else:
        print(f"   Presentación sin stock: {pres_no_stock.name}, stock: {pres_no_stock.stock}")

        # Agregar ítem
        item_data = {
            "presentation_id": pres_no_stock.id,
            "quantity": 1,
            "unit_price": 5000
        }
        resp = requests.post(f"{BASE_URL}/billing/invoices/{invoice_id}/items/",
                           json=item_data,
                           headers=admin_headers)

        if resp.status_code != 201:
            log_result("B) Agregar ítem sin stock", "FALLO", f"Status {resp.status_code}: {resp.text}")
        else:
            item_id = resp.json()["id"]

            # Intentar confirmar
            resp = requests.patch(f"{BASE_URL}/billing/invoices/{invoice_id}/confirm/",
                                 headers=admin_headers)

            if resp.status_code == 400 and "disponible" in resp.text.lower():
                invoice = Invoice.objects.get(id=invoice_id)
                if invoice.status == "draft":
                    log_result("B) Error 400 sin stock", "OK",
                              f"Error: {resp.json().get('detail', 'disponible')}")
                else:
                    log_result("B) Error 400 sin stock", "FALLO", f"Factura pasó a: {invoice.status}")
            else:
                log_result("B) Error 400 sin stock", "FALLO",
                          f"Status: {resp.status_code}, esperaba 400")
except Exception as e:
    log_result("B) Caso completo", "FALLO", str(e))

# ==================== CASO C ====================
print("\n\n--- CASO C: Item con service Y presentation --> error 400 ---")
try:
    invoice_data = {
        "invoice_type": "direct_sale",
        "status": "draft",
        "owner_id": owner.id,
        "pet_id": pet.id,
    }
    resp = requests.post(f"{BASE_URL}/billing/invoices/",
                        json=invoice_data,
                        headers=admin_headers)
    invoice_id = resp.json()["id"]

    # Obtener un service y una presentación
    from apps.billing.models import Service
    service = Service.objects.first()
    pres = Presentation.objects.first()

    if not service or not pres:
        log_result("C) Service/Presentation disponibles", "FALLO", "Datos no disponibles")
    else:
        item_data = {
            "service_id": service.id,
            "presentation_id": pres.id,
            "quantity": 1,
            "unit_price": 5000
        }
        resp = requests.post(f"{BASE_URL}/billing/invoices/{invoice_id}/items/",
                           json=item_data,
                           headers=admin_headers)

        if resp.status_code == 400 and ("xor" in resp.text.lower() or "either" in resp.text.lower()):
            log_result("C) Error XOR", "OK", resp.json().get('detail', 'XOR error'))
        else:
            log_result("C) Error XOR", "FALLO",
                      f"Status {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    log_result("C) Caso completo", "FALLO", str(e))

# ==================== CASO E ====================
print("\n\n--- CASO E: Cancelar factura confirmed --> stock restaurado ---")
try:
    # Crear y confirmar una factura
    invoice_data = {
        "invoice_type": "direct_sale",
        "status": "draft",
        "owner_id": owner.id,
        "pet_id": pet.id,
    }
    resp = requests.post(f"{BASE_URL}/billing/invoices/",
                        json=invoice_data,
                        headers=admin_headers)
    invoice_id = resp.json()["id"]

    pres = Presentation.objects.filter(stock__gt=0).first()
    initial_stock = pres.stock

    # Agregar ítem
    item_data = {"presentation_id": pres.id, "quantity": 1, "unit_price": 5000}
    resp = requests.post(f"{BASE_URL}/billing/invoices/{invoice_id}/items/",
                       json=item_data, headers=admin_headers)

    # Confirmar
    resp = requests.patch(f"{BASE_URL}/billing/invoices/{invoice_id}/confirm/",
                         headers=admin_headers)

    stock_after_confirm = Presentation.objects.get(id=pres.id).stock
    print(f"   Stock después de confirmar: {stock_after_confirm} (era {initial_stock})")

    # Cancelar
    resp = requests.patch(f"{BASE_URL}/billing/invoices/{invoice_id}/cancel/",
                         headers=admin_headers)

    if resp.status_code != 200:
        log_result("E) Cancelar factura", "FALLO", f"Status {resp.status_code}: {resp.text}")
    else:
        invoice = Invoice.objects.get(id=invoice_id)
        final_stock = Presentation.objects.get(id=pres.id).stock

        if invoice.status == "cancelled" and final_stock == initial_stock:
            log_result("E) Cancelar + restaurar stock", "OK",
                      f"Status: {invoice.status}, Stock restaurado a {final_stock}")
        else:
            log_result("E) Cancelar + restaurar stock", "FALLO",
                      f"Status: {invoice.status}, Stock: {final_stock} (esperaba {initial_stock})")
except Exception as e:
    log_result("E) Caso completo", "FALLO", str(e))

# ==================== CASO F ====================
print("\n\n--- CASO F: VET intenta pagar --> 403 ---")
try:
    # Crear una factura draft
    invoice_data = {
        "invoice_type": "direct_sale",
        "status": "draft",
        "owner_id": owner.id,
        "pet_id": pet.id,
    }
    resp = requests.post(f"{BASE_URL}/billing/invoices/",
                        json=invoice_data,
                        headers=admin_headers)
    invoice_id = resp.json()["id"]

    # Confirmar como admin
    requests.patch(f"{BASE_URL}/billing/invoices/{invoice_id}/confirm/",
                  headers=admin_headers)

    # Intentar pagar como VET
    resp = requests.patch(f"{BASE_URL}/billing/invoices/{invoice_id}/pay/",
                         headers=vet_headers)

    if resp.status_code == 403:
        log_result("F) VET paga → 403", "OK", "Acceso denegado correctamente")
    else:
        log_result("F) VET paga → 403", "FALLO", f"Status {resp.status_code}, esperaba 403")
except Exception as e:
    log_result("F) Caso completo", "FALLO", str(e))

# ==================== CASO G ====================
print("\n\n--- CASO G: Confirmar consultation --> stock no cambia ---")
try:
    # Crear factura consultation
    invoice_data = {
        "invoice_type": "consultation",
        "status": "draft",
        "owner_id": owner.id,
        "pet_id": pet.id,
    }
    resp = requests.post(f"{BASE_URL}/billing/invoices/",
                        json=invoice_data,
                        headers=admin_headers)
    invoice_id = resp.json()["id"]

    pres = Presentation.objects.filter(stock__gt=0).first()
    initial_stock = pres.stock

    # Agregar ítem
    item_data = {"presentation_id": pres.id, "quantity": 1, "unit_price": 5000}
    resp = requests.post(f"{BASE_URL}/billing/invoices/{invoice_id}/items/",
                       json=item_data, headers=admin_headers)

    # Confirmar
    resp = requests.patch(f"{BASE_URL}/billing/invoices/{invoice_id}/confirm/",
                         headers=admin_headers)

    if resp.status_code != 200:
        log_result("G) Confirmar consultation", "FALLO", f"Status {resp.status_code}")
    else:
        invoice = Invoice.objects.get(id=invoice_id)
        final_stock = Presentation.objects.get(id=pres.id).stock

        if invoice.status == "confirmed" and final_stock == initial_stock:
            log_result("G) Consultation stock no cambia", "OK",
                      f"Status: {invoice.status}, Stock: {final_stock} (sin cambios)")
        else:
            log_result("G) Consultation stock no cambia", "FALLO",
                      f"Stock cambió: {initial_stock} → {final_stock}")
except Exception as e:
    log_result("G) Caso completo", "FALLO", str(e))

# ==================== RESUMEN ====================
print("\n\n" + "="*60)
print("RESUMEN FINAL")
print("="*60)

passed = sum(1 for _, status, _ in RESULTS if status == "OK")
failed = sum(1 for _, status, _ in RESULTS if status == "FALLO")

print(f"\nCasos pasados: {passed}")
print(f"Casos fallidos: {failed}")
print(f"Total: {len(RESULTS)}")

if failed > 0:
    print("\nFALLOS:")
    for name, status, details in RESULTS:
        if status == "FALLO":
            print(f"  - {name}: {details}")
