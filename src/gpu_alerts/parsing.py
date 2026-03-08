from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


PRICE_PATTERN = re.compile(r"(?<![\w])(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2}|,-)?|\d+(?:,\d{2}|,-)?)(?![\w])")
EURO_PRICE_PATTERN = re.compile(
    r"(?<![\w])(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2}|,-)?|\d+(?:,\d{2}|,-)?)\s*(?:€|eur)",
    re.IGNORECASE,
)


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def parse_price(value: str | None, custom_regex: str | None = None) -> Decimal | None:
    if not value:
        return None
    text = normalize_space(value)
    if custom_regex:
        match = re.compile(custom_regex).search(text)
    else:
        match = EURO_PRICE_PATTERN.search(text) or PRICE_PATTERN.search(text)
    if not match:
        return None

    candidate = match.group(1).replace(",-", ",00")
    candidate = candidate.replace(".", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(candidate)
    except InvalidOperation:
        return None


def parse_stock(
    value: str | None,
    stock_in_texts: list[str] | None = None,
    stock_out_texts: list[str] | None = None,
) -> bool | None:
    if not value:
        return None

    normalized = normalize_space(value).lower()
    in_markers = [text.lower() for text in stock_in_texts or []]
    out_markers = [text.lower() for text in stock_out_texts or []]

    if any(marker in normalized for marker in out_markers):
        return False
    if any(marker in normalized for marker in in_markers):
        return True

    fallback_in = ("lagernd", "verfügbar", "available", "sofort", "in stock")
    fallback_out = ("nicht", "ausverkauft", "out of stock", "derzeit nicht", "bald verfügbar")

    if any(marker in normalized for marker in fallback_out):
        return False
    if any(marker in normalized for marker in fallback_in):
        return True
    return None
