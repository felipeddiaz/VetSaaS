from django.db import transaction
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

from apps.inventory.services import apply_stock_movement
from apps.inventory.models import Presentation
from .models import Invoice, InvoiceAuditLog, InvoiceItem


@transaction.atomic
def confirm_invoice(invoice, user):
    """
    Confirma una factura. Solo direct_sale descuenta stock.
    Orden estricto: lock → validar → validar stock → descontar → cambiar estado.
    """
    # Re-fetch con lock para prevenir confirmaciones concurrentes (doble-submit)
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != 'draft':
        raise ValidationError("Solo se pueden confirmar facturas en borrador.")

    # ⚠️ all_objects: servicio crítico — no depender del contexto de tenant.
    # Regla: services de facturación siempre usan all_objects + filtros explícitos.
    active_items = InvoiceItem.all_objects.filter(invoice=invoice, is_active=True)

    if not active_items.exists():
        raise ValidationError("No se puede confirmar una factura sin ítems.")

    if invoice.invoice_type == 'direct_sale':
        items_with_presentation = [
            item for item in active_items.select_related('presentation__product')
            if item.presentation_id
        ]

        # Validación defensiva: cantidades válidas
        for item in active_items:
            if item.quantity <= 0:
                raise ValidationError(
                    f"Cantidad inválida en ítem '{item.description}'."
                )

        # 1. Lock de escritura en todas las presentaciones involucradas
        presentation_ids = [i.presentation_id for i in items_with_presentation]
        locked = {
            p.pk: p
            for p in Presentation.objects.select_for_update().filter(pk__in=presentation_ids)
        }

        # 2. Validar stock de TODOS los ítems antes de mover ninguno
        errors = []
        for item in items_with_presentation:
            p = locked[item.presentation_id]
            if p.stock < item.quantity:
                errors.append(
                    f"'{p.product.name}': disponible {p.stock}, requerido {item.quantity}."
                )
        if errors:
            raise ValidationError(errors)

        # 3. Descontar stock de cada ítem con referencia a la factura
        for item in items_with_presentation:
            try:
                apply_stock_movement(
                    presentation=locked[item.presentation_id],
                    quantity=item.quantity,
                    movement_type='out',
                    organization=invoice.organization,
                    reason=f'Venta directa — Factura #{invoice.pk}',
                    created_by=user,
                    invoice=invoice,
                )
            except Exception as e:
                logger.error(
                    f"Error aplicando movimiento de stock en factura {invoice.pk}: {str(e)}"
                )
                raise

    # 4. Cambiar estado AL FINAL (si cualquier cosa falló arriba, esto no se ejecuta)
    invoice.status = 'confirmed'
    invoice.save(update_fields=['status', 'updated_at'])
    _log_status_change(invoice, previous='draft', new='confirmed', user=user)


@transaction.atomic
def cancel_invoice(invoice, user, notes=''):
    """
    Cancela una factura. Si estaba confirmed, revierte el stock.
    Facturas paid no se pueden cancelar directamente.
    """
    if invoice.status == 'paid':
        raise ValidationError("Las facturas pagadas no se pueden cancelar directamente.")
    if invoice.status == 'cancelled':
        raise ValidationError("La factura ya está cancelada.")

    previous_status = invoice.status

    if previous_status == 'confirmed' and invoice.invoice_type == 'direct_sale':
        # ⚠️ all_objects: mismo criterio que confirm_invoice.
        for item in InvoiceItem.all_objects.filter(invoice=invoice, is_active=True).select_related('presentation__product'):
            if item.presentation_id:
                try:
                    apply_stock_movement(
                        presentation=item.presentation,
                        quantity=item.quantity,
                        movement_type='in',
                        organization=invoice.organization,
                        reason=f'Reversión por cancelación — Factura #{invoice.pk}',
                        created_by=user,
                        invoice=invoice,
                    )
                except Exception as e:
                    logger.error(
                        f"Error revirtiendo stock en factura {invoice.pk}: {str(e)}"
                    )
                    raise

    invoice.status = 'cancelled'
    invoice.save(update_fields=['status', 'updated_at'])
    _log_status_change(invoice, previous=previous_status, new='cancelled', user=user, notes=notes)


def _log_status_change(invoice, previous, new, user, notes=''):
    InvoiceAuditLog.objects.create(
        invoice=invoice,
        previous_status=previous,
        new_status=new,
        changed_by=user,
        notes=notes,
    )


def get_or_create_invoice_for_medical_record(medical_record):
    """
    Fuente única de verdad para obtener o crear la Invoice de una consulta.
    
    Reglas:
    1) Si la consulta tiene cita, busca la factura vinculada a la cita primero
       (con filtro multi-tenant explícito: misma organización)
    2) Si la factura de cita existe, la linkea al medical_record
    3) Fallback: crea factura nueva vinculada al medical_record
    
    Usado por _sync_invoice_item en medical_records/views.py e inventory/views.py.
    """
    org = medical_record.organization

    # 1) Si hay cita, buscar factura vinculada a la cita
    if medical_record.appointment_id:
        invoice = Invoice.objects.filter(
            appointment=medical_record.appointment,
            organization=org,
        ).first()
        if invoice:
            # Linkear si no estaba vinculada al medical_record
            if invoice.medical_record_id is None:
                invoice.medical_record = medical_record
                invoice.save(update_fields=['medical_record'])
            return invoice

    # 2) Fallback: factura nueva vinculada al medical_record
    invoice, _ = Invoice.objects.get_or_create(
        medical_record=medical_record,
        defaults={
            'owner': medical_record.pet.owner,
            'pet': medical_record.pet,
            'organization': org,
            'status': 'draft',
            'invoice_type': 'consultation',
        }
    )
    return invoice
