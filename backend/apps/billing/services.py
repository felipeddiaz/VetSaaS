from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

from apps.inventory.services import apply_stock_movement
from apps.inventory.models import Presentation
from apps.billing.money import money, discount_amount, line_subtotal
from .models import Invoice, InvoiceAuditLog, InvoiceItem


VALID_PAYMENT_METHODS = {'cash', 'card', 'transfer', 'other'}


def apply_invoice_item_quantity_delta(item, delta):
    """
    Mutación atómica de InvoiceItem.quantity usando F('quantity') + delta.

    Convención del proyecto: TODA mutación numérica contable en InvoiceItem
    DEBE usar F() (paralelo a apply_stock_movement para Presentation.stock),
    incluso cuando el caller posee select_for_update() sobre el InvoiceItem.

    ⚠️ CONTRATO:
      - El caller DEBE poseer select_for_update() sobre el item.
      - El caller DEBE estar dentro de transaction.atomic().
      - delta puede ser negativo (decremento), pero el resultado no puede ser <= 0.
        Si el caller necesita borrar el item, debe llamar item.delete() ANTES
        de invocar este helper (proyectar item.quantity + delta primero).

    Recomputa subtotal del item + totales de la factura. Usa los mismos helpers
    que InvoiceItem.save() (money, discount_amount, line_subtotal) para no
    divergir del cálculo canónico.

    Returns:
        Decimal — la nueva cantidad después del delta.
    """
    projected = item.quantity + delta
    if projected <= 0:
        raise ValidationError(
            f"La cantidad resultante ({projected}) no es positiva. "
            f"Llama item.delete() antes de invocar apply_invoice_item_quantity_delta."
        )

    InvoiceItem.all_objects.filter(pk=item.pk).update(quantity=F('quantity') + delta)
    item.refresh_from_db(fields=['quantity'])

    gross = money(item.quantity * item.unit_price)
    disc = discount_amount(gross, item.discount_type, item.discount_value)
    new_subtotal = line_subtotal(item.quantity, item.unit_price, disc)
    InvoiceItem.all_objects.filter(pk=item.pk).update(subtotal=new_subtotal)

    item.invoice.recalculate_totals()
    item.refresh_from_db(fields=['subtotal'])
    return item.quantity


def _lock_presentations(presentation_ids):
    if not presentation_ids:
        return {}
    return {
        p.pk: p
        for p in Presentation.objects.select_for_update().filter(
            pk__in=sorted(set(presentation_ids))
        )
    }


# ---------------------------------------------------------------------------
# Funciones internas — asumen invoice YA lockeada con select_for_update().
# Sin @transaction.atomic propio; el caller maneja la transacción.
# ---------------------------------------------------------------------------

def _confirm_locked_invoice(invoice, user):
    """
    Confirma una factura que YA está lockeada con select_for_update().
    Solo direct_sale descuenta stock.
    Orden estricto: validar → validar stock → descontar → cambiar estado.
    """
    if invoice.status != 'draft':
        raise ValidationError("Solo se pueden confirmar facturas en borrador.")

    active_items = InvoiceItem.all_objects.filter(invoice=invoice, is_active=True)

    if not active_items.exists():
        raise ValidationError("No se puede confirmar una factura sin ítems.")

    if invoice.invoice_type == 'direct_sale':
        items_with_presentation = [
            item for item in active_items.select_related('presentation__product')
            if item.presentation_id
        ]

        for item in active_items:
            if item.quantity <= 0:
                raise ValidationError(
                    f"Cantidad inválida en ítem '{item.description}'."
                )

        presentation_ids = [i.presentation_id for i in items_with_presentation]
        locked = _lock_presentations(presentation_ids)

        errors = []
        for item in items_with_presentation:
            p = locked[item.presentation_id]
            if p.stock < item.quantity:
                errors.append(
                    f"'{p.product.name}': disponible {p.stock}, requerido {item.quantity}."
                )
        if errors:
            raise ValidationError(errors)

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

    invoice.status = 'confirmed'
    invoice.confirmed_at = timezone.now()
    invoice.confirmed_at_source = 'service'
    invoice.save(update_fields=[
        'status', 'confirmed_at', 'confirmed_at_source', 'updated_at',
    ])
    _log_status_change(invoice, previous='draft', new='confirmed', user=user)


def _pay_locked_invoice(invoice, user, payment_method):
    """
    Marca una factura YA lockeada como pagada.
    Authoritative writer del anchor `paid_at`.
    """
    if payment_method not in VALID_PAYMENT_METHODS:
        raise ValidationError(
            f'Método de pago inválido. Opciones: {sorted(VALID_PAYMENT_METHODS)}'
        )
    if invoice.status == 'paid':
        raise ValidationError('La factura ya fue pagada.')
    if invoice.status != 'confirmed':
        raise ValidationError(
            'Solo se pueden pagar facturas confirmadas. Confirma la factura primero.'
        )
    previous_status = invoice.status
    invoice.status = 'paid'
    invoice.payment_method = payment_method
    invoice.paid_at = timezone.now()
    invoice.paid_at_source = 'service'
    invoice.save(update_fields=[
        'status', 'payment_method', 'paid_at', 'paid_at_source', 'updated_at',
    ])
    _log_status_change(invoice, previous=previous_status, new='paid', user=user)
    return invoice


# ---------------------------------------------------------------------------
# Wrappers públicos — con @transaction.atomic y lock propio.
# ---------------------------------------------------------------------------

@transaction.atomic
def confirm_invoice(invoice, user):
    """Confirma una factura. Lock + validación + transición atómica."""
    invoice = Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)
    _confirm_locked_invoice(invoice, user)


@transaction.atomic
def cancel_invoice(invoice, user, notes=''):
    """
    Cancela una factura. Si estaba confirmed, revierte el stock.
    Facturas paid no se pueden cancelar directamente.
    """
    invoice = Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)

    if invoice.status == 'paid':
        raise ValidationError("Las facturas pagadas no se pueden cancelar directamente.")
    if invoice.status == 'cancelled':
        raise ValidationError("La factura ya está cancelada.")

    previous_status = invoice.status

    if previous_status == 'confirmed' and invoice.invoice_type == 'direct_sale':
        items = list(
            InvoiceItem.all_objects
            .filter(invoice=invoice, is_active=True)
            .select_related('presentation__product')
        )
        locked_presentations = _lock_presentations(
            item.presentation_id for item in items if item.presentation_id
        )
        for item in items:
            if item.presentation_id:
                try:
                    apply_stock_movement(
                        presentation=locked_presentations[item.presentation_id],
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
    invoice.cancelled_at = timezone.now()
    invoice.cancelled_at_source = 'service'
    invoice.save(update_fields=[
        'status', 'cancelled_at', 'cancelled_at_source', 'updated_at',
    ])
    _log_status_change(invoice, previous=previous_status, new='cancelled', user=user, notes=notes)


@transaction.atomic
def pay_invoice(invoice, user, payment_method):
    """
    Marca una factura como pagada. Authoritative writer del anchor `paid_at`.

    Llamado por billing/views.py::pay_invoice y por cualquier flujo futuro
    (webhook de pasarela de pagos, conciliación batch, mgmt commands).
    No editar `paid_at` desde otro lugar — el contrato analítico depende de
    que este sea el único writer.
    """
    if payment_method not in VALID_PAYMENT_METHODS:
        raise ValidationError(
            f'Método de pago inválido. Opciones: {sorted(VALID_PAYMENT_METHODS)}'
        )
    invoice = Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)
    return _pay_locked_invoice(invoice, user, payment_method)


# ---------------------------------------------------------------------------
# Direct sale — pay atómico (confirmar + pagar en una sola transacción)
# ---------------------------------------------------------------------------

@transaction.atomic
def pay_direct_sale(invoice, user, payment_method):
    """
    Paga una venta directa confirmando y cobrando en una sola transacción.

    UX: draft → paid (un solo paso para el cajero).
    Interno: draft → confirmed → paid (máquina de estados completa).

    Analytics: confirmed_at y paid_at tendrán valores casi idénticos (ms de
    diferencia). Para métricas de accrual vs cash, esto significa que en
    direct_sale ambas curvas coinciden — comportamiento esperado y distinto
    al de consultation donde puede haber horas/días entre confirmación y pago.
    Ver docs/dashboard-metrics-contract.md §3.1.2 (revenue_accrual).

    Un solo select_for_update() — sin re-locks internos.
    """
    if payment_method not in VALID_PAYMENT_METHODS:
        raise ValidationError(
            f'Método de pago inválido. Opciones: {sorted(VALID_PAYMENT_METHODS)}'
        )

    invoice = Invoice.objects.for_organization(invoice.organization).select_for_update().get(pk=invoice.pk)

    if invoice.invoice_type != 'direct_sale':
        raise ValidationError(
            'La acción direct-pay solo está disponible para ventas directas.'
        )
    if invoice.status == 'paid':
        raise ValidationError('La factura ya fue pagada.')
    if invoice.status != 'draft':
        raise ValidationError(
            'Solo se pueden cobrar directamente facturas en borrador.'
        )

    # TODO (v2): direct_sale con liquidación instantánea eventualmente necesitará
    # un mecanismo de refund/void distinto de cancel_invoice(). Este último solo
    # aplica a confirmed (no a paid). Ver ADR pendiente sobre refunds.

    _confirm_locked_invoice(invoice, user)
    return _pay_locked_invoice(invoice, user, payment_method)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _log_status_change(invoice, previous, new, user, notes=''):
    InvoiceAuditLog.objects.create(
        invoice=invoice,
        previous_status=previous,
        new_status=new,
        changed_by=user,
        notes=notes,
    )


@transaction.atomic
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
    from apps.medical_records.models import MedicalRecord

    medical_record = MedicalRecord.objects.for_organization(
        medical_record.organization
    ).select_for_update().get(pk=medical_record.pk)
    org = medical_record.organization

    if medical_record.appointment_id:
        invoice = Invoice.objects.select_for_update().filter(
            appointment=medical_record.appointment,
            organization=org,
        ).first()
        if invoice:
            if invoice.medical_record_id is None:
                invoice.medical_record = medical_record
                invoice.save(update_fields=['medical_record'])
            return invoice

    invoice, _ = Invoice.objects.get_or_create(
        medical_record=medical_record,
        defaults={
            'owner': medical_record.pet.owner,
            'pet': medical_record.pet,
            'organization': org,
            'status': 'draft',
            'invoice_type': 'consultation',
            'tax_rate': org.tax_rate,
        }
    )
    return Invoice.objects.for_organization(org).select_for_update().get(pk=invoice.pk)
