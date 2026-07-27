from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from reports.services import (
    br_date,
    coerce_date,
    month_last_day,
    percent,
    percent_int,
    prettify_value,
    shift_month,
)


class ReportServiceTests(SimpleTestCase):
    def test_percentage_helpers_handle_zero_and_round_consistently(self):
        self.assertEqual(percent(1, 3), Decimal("33.3"))
        self.assertEqual(percent_int(2, 3), 67)
        self.assertEqual(percent(10, 0), Decimal("0.00"))

    def test_month_helpers_cross_year_boundaries(self):
        self.assertEqual(shift_month(date(2026, 1, 15), -1), date(2025, 12, 1))
        self.assertEqual(month_last_day(date(2024, 2, 1)), date(2024, 2, 29))

    def test_display_helpers_are_defensive(self):
        self.assertEqual(coerce_date("invalida"), None)
        self.assertEqual(br_date("2026-07-21"), "21/07/2026")
        self.assertEqual(prettify_value({"ativo": True, "itens": ["A", "B"]}), "ativo: Sim, itens: A, B")
