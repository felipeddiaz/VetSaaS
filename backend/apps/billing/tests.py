from decimal import Decimal
from django.test import TestCase
from apps.billing.money import discount_amount, invoice_totals, line_subtotal, money


class MoneyRoundingTests(TestCase):
    """Aritmética centralizada — billing/money.py"""

    def test_money_rounds_half_up(self):
        self.assertEqual(money(Decimal("0.335")), Decimal("0.34"))
        self.assertEqual(money(Decimal("0.334")), Decimal("0.33"))
        self.assertEqual(money(Decimal("1.005")), Decimal("1.01"))

    def test_line_subtotal_two_decimals(self):
        result = line_subtotal(Decimal("3"), Decimal("1.1111"))
        self.assertEqual(result.as_tuple().exponent, -2)

    def test_line_subtotal_with_percentage_discount(self):
        gross = Decimal("3") * Decimal("10.00")  # 30.00
        disc = discount_amount(gross, "percentage", Decimal("10"))  # 3.00
        result = line_subtotal(Decimal("3"), Decimal("10.00"), disc)
        self.assertEqual(result, Decimal("27.00"))

    def test_line_subtotal_with_fixed_discount(self):
        gross = Decimal("2") * Decimal("5.00")  # 10.00
        disc = discount_amount(gross, "fixed", Decimal("3.00"))
        result = line_subtotal(Decimal("2"), Decimal("5.00"), disc)
        self.assertEqual(result, Decimal("7.00"))

    def test_fixed_discount_capped_at_gross(self):
        gross = Decimal("1") * Decimal("5.00")
        disc = discount_amount(gross, "fixed", Decimal("999.00"))
        self.assertEqual(disc, Decimal("5.00"))

    def test_invoice_totals_two_decimals(self):
        subtotal, tax, total = invoice_totals(Decimal("100.00"), Decimal("0.19"))
        self.assertEqual(subtotal.as_tuple().exponent, -2)
        self.assertEqual(tax.as_tuple().exponent, -2)
        self.assertEqual(total.as_tuple().exponent, -2)

    def test_invoice_totals_values(self):
        subtotal, tax, total = invoice_totals(Decimal("100.00"), Decimal("0.19"))
        self.assertEqual(subtotal, Decimal("100.00"))
        self.assertEqual(tax, Decimal("19.00"))
        self.assertEqual(total, Decimal("119.00"))

    def test_invoice_totals_no_drift_on_multiple_calls(self):
        """El mismo subtotal+tax_rate siempre produce el mismo total."""
        result_a = invoice_totals(Decimal("99.99"), Decimal("0.0800"))
        result_b = invoice_totals(Decimal("99.99"), Decimal("0.0800"))
        self.assertEqual(result_a, result_b)

    def test_invoice_totals_zero_tax(self):
        subtotal, tax, total = invoice_totals(Decimal("50.00"), Decimal("0"))
        self.assertEqual(tax, Decimal("0.00"))
        self.assertEqual(total, Decimal("50.00"))
