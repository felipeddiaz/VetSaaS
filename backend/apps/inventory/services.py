import logging

from django.db.models import F
from django.core.exceptions import ValidationError

from .models import Presentation, StockMovement

logger = logging.getLogger(__name__)


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

    NOTA: usa Presentation.all_objects.filter(pk=...).update() intencionalmente.
    Razón: update() garantiza atomicidad en stock (sin race conditions).
    Es seguro porque pk viene de un objeto ya validado y conocido por la llamada.
    """
    org_id = getattr(organization, 'pk', organization)
    user_id = getattr(created_by, 'pk', None)

    if movement_type == 'out':
        presentation.refresh_from_db()
        if presentation.stock < quantity:
            logger.warning(
                "Stock insuficiente | organization_id=%s user_id=%s presentation=%s solicitado=%s disponible=%s",
                org_id, user_id, presentation.pk, quantity, presentation.stock,
            )
            raise ValidationError(
                f"Stock insuficiente para '{presentation.product.name}'. "
                f"Disponible: {presentation.stock}, solicitado: {quantity}."
            )
        # ⚠️ Uses all_objects intentionally to bypass tenant + soft delete filters.
        # This is required for atomic stock updates using F() expressions.
        # Do NOT replace with objects — will silently update 0 rows outside request context.
        Presentation.all_objects.filter(pk=presentation.pk).update(stock=F('stock') - quantity)

    elif movement_type == 'in':
        # ⚠️ Uses all_objects intentionally — see comment above.
        Presentation.all_objects.filter(pk=presentation.pk).update(stock=F('stock') + quantity)

    elif movement_type == 'adjustment':
        # ⚠️ Uses all_objects intentionally — see comment above.
        Presentation.all_objects.filter(pk=presentation.pk).update(stock=quantity)

    else:
        logger.error(
            "movement_type desconocido: %s | organization_id=%s user_id=%s presentation=%s",
            movement_type, org_id, user_id, presentation.pk,
        )
        raise ValidationError(f"Tipo de movimiento inválido: {movement_type}")

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

    logger.info(
        "StockMovement | type=%s qty=%s presentation=%s organization_id=%s user_id=%s reason=%r",
        movement_type, quantity, presentation.pk, org_id, user_id, reason,
    )
