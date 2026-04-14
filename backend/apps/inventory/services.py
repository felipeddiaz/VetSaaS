from django.db.models import F
from django.core.exceptions import ValidationError
from .models import Presentation, StockMovement


def apply_stock_movement(
    presentation,
    quantity,
    movement_type,
    organization,
    reason='',
    created_by=None,
    medical_record=None,
    invoice=None,
):
    """
    Único punto de entrada para todos los cambios de stock.
    Nadie debe actualizar Presentation.stock directamente fuera de esta función.

    Lanza ValidationError si un movimiento 'out' dejaría stock negativo.
    """
    if movement_type == 'out':
        presentation.refresh_from_db()
        if presentation.stock < quantity:
            raise ValidationError(
                f"Stock insuficiente para '{presentation.product.name}'. "
                f"Disponible: {presentation.stock}, solicitado: {quantity}."
            )
        Presentation.objects.filter(pk=presentation.pk).update(stock=F('stock') - quantity)
    elif movement_type == 'in':
        Presentation.objects.filter(pk=presentation.pk).update(stock=F('stock') + quantity)
    elif movement_type == 'adjustment':
        Presentation.objects.filter(pk=presentation.pk).update(stock=quantity)

    StockMovement.objects.create(
        presentation=presentation,
        organization=organization,
        movement_type=movement_type,
        quantity=quantity,
        reason=reason,
        created_by=created_by,
        medical_record=medical_record,
        invoice=invoice,
    )
