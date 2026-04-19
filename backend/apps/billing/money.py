from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")


def money(v: Decimal) -> Decimal:
    """Redondea a 2 decimales con HALF_UP. Usar en todo valor monetario antes de guardar."""
    return v.quantize(MONEY, rounding=ROUND_HALF_UP)


def line_subtotal(qty: Decimal, price: Decimal, discount: Decimal = Decimal("0")) -> Decimal:
    """Subtotal de un ítem: (qty * price) - descuento ya calculado, redondeado."""
    gross = qty * price
    return money(gross - discount)


def discount_amount(gross: Decimal, discount_type: str, discount_value: Decimal) -> Decimal:
    """Calcula el monto de descuento dado el bruto, tipo y valor."""
    if discount_type == "percentage":
        return money(gross * (discount_value / Decimal("100")))
    if discount_type == "fixed":
        return money(min(discount_value, gross))
    return Decimal("0.00")


def invoice_totals(subtotal: Decimal, tax_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """
    Devuelve (subtotal, tax_amount, total), todos redondeados a 2 decimales.
    Entrada: subtotal ya redondeado, tax_rate en [0, 1].
    """
    subtotal = money(subtotal)
    tax = money(subtotal * tax_rate)
    total = money(subtotal + tax)
    return subtotal, tax, total
