from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import aiohttp


GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"
UPCITEMDB_LOOKUP_URL = "https://api.upcitemdb.com/prod/trial/lookup"
UPCITEMDB_SEARCH_URL = "https://api.upcitemdb.com/prod/trial/search"

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


class ProductLookupError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.hint = hint


@dataclass(slots=True)
class ProductLookupResult:
    title: str
    search_query: str
    brand: str = ""
    image_url: str = ""
    identifier_type: str = ""
    identifier_value: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "search_query": self.search_query,
            "brand": self.brand,
            "image_url": self.image_url,
            "identifier_type": self.identifier_type,
            "identifier_value": self.identifier_value,
            "source": self.source,
        }


def _normalize_query(raw_query: str) -> str:
    return re.sub(r"\s+", " ", (raw_query or "").strip())


def _digits_only(raw_query: str) -> str:
    return re.sub(r"[^0-9]", "", raw_query or "")


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _build_search_query(title: str) -> str:
    words = TOKEN_PATTERN.findall(title or "")
    return " ".join(words[:4]) or title.strip()


def _pick_image(image_links: dict[str, Any] | None) -> str:
    if not isinstance(image_links, dict):
        return ""
    for key in ("thumbnail", "smallThumbnail", "small", "medium", "large"):
        value = image_links.get(key)
        if value:
            return str(value)
    return ""


def _pick_identifier(identifiers: list[dict[str, Any]] | None) -> tuple[str, str]:
    if not isinstance(identifiers, list):
        return "", ""
    for preferred_type in ("ISBN_13", "ISBN_10", "EAN", "GTIN", "UPC"):
        for item in identifiers:
            if str(item.get("type") or "").upper() == preferred_type and item.get("identifier"):
                return preferred_type.lower(), str(item["identifier"]).strip()
    for item in identifiers:
        value = str(item.get("identifier") or "").strip()
        if value:
            return str(item.get("type") or "identifier").strip().lower(), value
    return "", ""


def _score_result(query: str, result: ProductLookupResult) -> int:
    normalized_query = _normalize_title(query)
    normalized_title = _normalize_title(result.title)
    if not normalized_query or not normalized_title:
        return 0
    if normalized_title == normalized_query:
        return 120
    if normalized_query in normalized_title:
        return 95
    query_tokens = [token for token in normalized_query.split() if token]
    title_tokens = set(normalized_title.split())
    overlap = sum(1 for token in query_tokens if token in title_tokens)
    score = overlap * 15
    if result.brand and _normalize_title(result.brand) in normalized_query:
        score += 10
    if result.source == "upcitemdb":
        score += 3
    return score


def _result_from_google_item(item: dict[str, Any]) -> ProductLookupResult | None:
    volume = item.get("volumeInfo", {})
    title = str(volume.get("title") or "").strip()
    if not title:
        return None
    identifier_type, identifier_value = _pick_identifier(volume.get("industryIdentifiers"))
    authors = volume.get("authors", [])
    brand = ""
    if isinstance(authors, list) and authors:
        brand = str(authors[0]).strip()
    elif volume.get("publisher"):
        brand = str(volume.get("publisher") or "").strip()
    return ProductLookupResult(
        title=title,
        search_query=_build_search_query(title),
        brand=brand,
        image_url=_pick_image(volume.get("imageLinks")),
        identifier_type=identifier_type,
        identifier_value=identifier_value,
        source="google_books",
    )


def _result_from_upc_item(item: dict[str, Any]) -> ProductLookupResult | None:
    title = str(item.get("title") or item.get("description") or "").strip()
    if not title:
        return None
    images = item.get("images", [])
    image_url = ""
    if isinstance(images, list) and images:
        image_url = str(images[0] or "").strip()
    identifier_value = str(item.get("upc") or item.get("ean") or item.get("gtin") or "").strip()
    identifier_type = ""
    if item.get("upc"):
        identifier_type = "upc"
    elif item.get("ean"):
        identifier_type = "ean"
    elif item.get("gtin"):
        identifier_type = "gtin"
    return ProductLookupResult(
        title=title,
        search_query=_build_search_query(title),
        brand=str(item.get("brand") or "").strip(),
        image_url=image_url,
        identifier_type=identifier_type,
        identifier_value=identifier_value,
        source="upcitemdb",
    )


async def _read_json_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        payload = await response.json(content_type=None)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _google_books_lookup(session: aiohttp.ClientSession, query: str) -> ProductLookupResult | None:
    async with session.get(
        GOOGLE_BOOKS_API_URL,
        params={"q": query, "maxResults": 5, "printType": "books"},
    ) as response:
        if response.status >= 400:
            raise ProductLookupError(
                "lookup_unavailable",
                "Die Produktsuche für Bücher ist gerade nicht erreichbar. Bitte manuell eintragen.",
                status=response.status,
            )
        payload = await _read_json_response(response)
    items = payload.get("items", [])
    if not isinstance(items, list):
        return None
    for item in items:
        result = _result_from_google_item(item)
        if result is not None:
            return result
    return None


async def _upcitemdb_lookup(session: aiohttp.ClientSession, digits: str) -> ProductLookupResult | None:
    async with session.get(UPCITEMDB_LOOKUP_URL, params={"upc": digits}) as response:
        if response.status == 429:
            raise ProductLookupError(
                "lookup_rate_limited",
                "Limit der kostenlosen EAN-Suche erreicht. Bitte manuell eintragen.",
                status=429,
                hint="Warte kurz oder trage Produktname und Suchbegriffe direkt ein.",
            )
        if response.status >= 400:
            raise ProductLookupError(
                "lookup_unavailable",
                "Die EAN-Suche ist gerade nicht erreichbar. Bitte manuell eintragen.",
                status=response.status,
            )
        payload = await _read_json_response(response)
    items = payload.get("items", [])
    if not isinstance(items, list):
        return None
    for item in items:
        result = _result_from_upc_item(item)
        if result is not None:
            return result
    return None


async def _upcitemdb_search(session: aiohttp.ClientSession, query: str) -> ProductLookupResult | None:
    async with session.get(UPCITEMDB_SEARCH_URL, params={"s": query}) as response:
        if response.status == 429:
            raise ProductLookupError(
                "lookup_rate_limited",
                "Limit der kostenlosen EAN-Suche erreicht. Bitte manuell eintragen.",
                status=429,
                hint="Du kannst den Produktnamen trotzdem direkt in den Tracker eintragen.",
            )
        if response.status >= 400:
            raise ProductLookupError(
                "lookup_unavailable",
                "Die Produktsuche ist gerade nicht erreichbar. Bitte manuell eintragen.",
                status=response.status,
            )
        payload = await _read_json_response(response)
    items = payload.get("items", [])
    if not isinstance(items, list):
        return None
    for item in items:
        result = _result_from_upc_item(item)
        if result is not None:
            return result
    return None


async def lookup_product(session: aiohttp.ClientSession, query: str) -> ProductLookupResult:
    cleaned_query = _normalize_query(query)
    if not cleaned_query:
        raise ProductLookupError("lookup_query_required", "Bitte gib zuerst einen Produktnamen oder Strichcode ein.")

    digits = _digits_only(cleaned_query)
    if digits and len(digits) in {10, 13} and (len(digits) == 10 or digits.startswith(("978", "979"))):
        try:
            result = await _google_books_lookup(session, f"isbn:{digits}")
            if result is not None:
                return result
        except ProductLookupError as exc:
            if exc.status != 404:
                raise
        if len(digits) in {12, 13, 14, 8}:
            result = await _upcitemdb_lookup(session, digits)
            if result is not None:
                return result
        raise ProductLookupError("lookup_no_match", "Kein passendes Produkt gefunden.", status=404)

    if digits and len(digits) in {8, 12, 13, 14}:
        result = await _upcitemdb_lookup(session, digits)
        if result is not None:
            return result
        raise ProductLookupError("lookup_no_match", "Kein passendes Produkt gefunden.", status=404)

    google_task = asyncio.create_task(_google_books_lookup(session, cleaned_query))
    upc_task = asyncio.create_task(_upcitemdb_search(session, cleaned_query))
    google_result, upc_result = await asyncio.gather(google_task, upc_task, return_exceptions=True)

    candidates: list[ProductLookupResult] = []
    rate_limited_error: ProductLookupError | None = None
    for candidate in (google_result, upc_result):
        if isinstance(candidate, ProductLookupResult):
            candidates.append(candidate)
        elif isinstance(candidate, ProductLookupError):
            if candidate.code == "lookup_rate_limited":
                rate_limited_error = candidate
            elif candidate.code != "lookup_no_match":
                raise candidate
        elif isinstance(candidate, Exception):
            raise ProductLookupError(
                "lookup_unavailable",
                "Die Produktsuche ist gerade nicht erreichbar. Bitte manuell eintragen.",
            ) from candidate

    if candidates:
        ranked = sorted(candidates, key=lambda item: _score_result(cleaned_query, item), reverse=True)
        return ranked[0]
    if rate_limited_error is not None:
        raise rate_limited_error
    raise ProductLookupError("lookup_no_match", "Kein passendes Produkt gefunden.", status=404)
