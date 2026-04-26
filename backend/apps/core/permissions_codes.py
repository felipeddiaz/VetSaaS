"""
core/permissions_codes.py — Fuente única de verdad de permisos RBAC
====================================================================

REGLAS:
  - Este archivo es la única fuente de verdad para permisos.
  - Formato: "resource.action"
  - PERMISSIONS define los permisos estáticos por rol.
  - El seed valida que PERMISSION_CODES == set de todos los permisos en PERMISSIONS.
  - Nunca modificar PERMISSIONS sin actualizar PERMISSION_CODES primero.
  - Wildcard global es "*.*", no "*".
"""

# ---------------------------------------------------------------------------
# Catálogo de permisos válidos
# ---------------------------------------------------------------------------
PERMISSION_CODES = [
    # Citas
    "appointment.list",
    "appointment.retrieve",
    "appointment.create",
    "appointment.update",
    "appointment.destroy",

    # Historial clínico
    "medicalrecord.list",
    "medicalrecord.retrieve",
    "medicalrecord.create",
    "medicalrecord.update",
    "medicalrecord.close",

    # Facturas
    "invoice.list",
    "invoice.retrieve",
    "invoice.create",
    "invoice.confirm",
    "invoice.pay",
    "invoice.cancel",

    # Servicios (catálogo de facturación — Configuración)
    "service.list",
    "service.retrieve",
    "service.create",
    "service.update",
    "service.destroy",

    # Pacientes (mascotas)
    "patient.list",
    "patient.retrieve",
    "patient.create",
    "patient.update",
    "patient.destroy",

    # Propietarios
    "owner.list",
    "owner.retrieve",
    "owner.create",
    "owner.update",
    "owner.destroy",

    # Inventario
    "inventory.list",
    "inventory.retrieve",
    "inventory.update",

    # Recetas
    "prescription.list",
    "prescription.retrieve",
    "prescription.create",
    "prescription.destroy",

    # Equipo (gestión de usuarios internos)
    "staff.list",
    "staff.create",
    "staff.destroy",

    # Dashboard
    "dashboard.view",
]

# ---------------------------------------------------------------------------
# Permisos estáticos por rol (fallback cuando no hay roles en DB)
# ---------------------------------------------------------------------------
PERMISSIONS = {
    # Superadmin de plataforma
    "ADMIN_SAAS": ["*.*"],

    # Administrador de clínica
    "ADMIN": ["*.*"],

    # Veterinario
    "VET": [
        "appointment.list", "appointment.retrieve", "appointment.create",
        "appointment.update", "appointment.destroy",
        "medicalrecord.list", "medicalrecord.retrieve", "medicalrecord.create",
        "medicalrecord.update", "medicalrecord.close",
        "prescription.list", "prescription.retrieve", "prescription.create",
        "prescription.destroy",
        "patient.list", "patient.retrieve", "patient.create",
        "patient.update", "patient.destroy",
        "owner.list", "owner.retrieve", "owner.create",
        "owner.update", "owner.destroy",
        "inventory.list", "inventory.retrieve",
        "invoice.list", "invoice.retrieve", "invoice.create",
        "invoice.confirm", "invoice.pay", "invoice.cancel",
        "service.list", "service.retrieve",
        "staff.list",
        "dashboard.view",
    ],

    # Asistente / Recepcionista
    "ASSISTANT": [
        "appointment.list", "appointment.retrieve", "appointment.create",
        "appointment.update", "appointment.destroy",
        "medicalrecord.list", "medicalrecord.retrieve",
        "prescription.list", "prescription.retrieve",
        "patient.list", "patient.retrieve", "patient.create",
        "patient.update", "patient.destroy",
        "owner.list", "owner.retrieve", "owner.create",
        "owner.update", "owner.destroy",
        "inventory.list", "inventory.retrieve",
        "invoice.list", "invoice.retrieve", "invoice.create",
        "invoice.confirm", "invoice.pay", "invoice.cancel",
        "service.list", "service.retrieve",
        "staff.list",
        "dashboard.view",
    ],
}
