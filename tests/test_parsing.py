from decimal import Decimal

from gpu_alerts.parsing import parse_price


def test_parse_price_with_thousands_and_dash_cents() -> None:
    assert parse_price("€ 1.039,-*") == Decimal("1039.00")


def test_parse_price_with_standard_decimal() -> None:
    assert parse_price("899,99 €") == Decimal("899.99")
