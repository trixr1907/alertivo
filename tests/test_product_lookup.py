from __future__ import annotations

import asyncio

import aiohttp
from aiohttp import web

import gpu_alerts.product_lookup as lookup_module
from gpu_alerts.product_lookup import ProductLookupError, lookup_product


async def _start_server(handler_map):  # type: ignore[no-untyped-def]
    app = web.Application()
    for path, handler in handler_map.items():
        app.router.add_get(path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server else []
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


def test_lookup_product_prefers_google_books_for_isbn(monkeypatch) -> None:
    async def _case() -> None:
        async def google_handler(request: web.Request) -> web.Response:
            return web.json_response(
                {
                    "items": [
                        {
                            "volumeInfo": {
                                "title": "Clean Code",
                                "authors": ["Robert C. Martin"],
                                "industryIdentifiers": [
                                    {"type": "ISBN_13", "identifier": "9780132350884"},
                                ],
                                "imageLinks": {"thumbnail": "https://example.com/clean-code.jpg"},
                            }
                        }
                    ]
                }
            )

        async def upc_handler(request: web.Request) -> web.Response:
            return web.json_response({"items": []})

        runner, base_url = await _start_server(
            {
                "/google": google_handler,
                "/lookup": upc_handler,
                "/search": upc_handler,
            }
        )
        monkeypatch.setattr(lookup_module, "GOOGLE_BOOKS_API_URL", f"{base_url}/google")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_LOOKUP_URL", f"{base_url}/lookup")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_SEARCH_URL", f"{base_url}/search")
        try:
            async with aiohttp.ClientSession() as session:
                result = await lookup_product(session, "9780132350884")
                assert result.title == "Clean Code"
                assert result.identifier_value == "9780132350884"
                assert result.source == "google_books"
        finally:
            await runner.cleanup()

    asyncio.run(_case())


def test_lookup_product_uses_upcitemdb_for_generic_barcode(monkeypatch) -> None:
    async def _case() -> None:
        async def google_handler(request: web.Request) -> web.Response:
            return web.json_response({"items": []})

        async def upc_handler(request: web.Request) -> web.Response:
            return web.json_response(
                {
                    "items": [
                        {
                            "title": "Valve Steam Deck OLED 1TB",
                            "brand": "Valve",
                            "upc": "0195949037349",
                            "images": ["https://example.com/steamdeck.png"],
                        }
                    ]
                }
            )

        runner, base_url = await _start_server(
            {
                "/google": google_handler,
                "/lookup": upc_handler,
                "/search": upc_handler,
            }
        )
        monkeypatch.setattr(lookup_module, "GOOGLE_BOOKS_API_URL", f"{base_url}/google")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_LOOKUP_URL", f"{base_url}/lookup")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_SEARCH_URL", f"{base_url}/search")
        try:
            async with aiohttp.ClientSession() as session:
                result = await lookup_product(session, "0195949037349")
                assert result.title == "Valve Steam Deck OLED 1TB"
                assert result.brand == "Valve"
                assert result.identifier_type == "upc"
                assert result.source == "upcitemdb"
        finally:
            await runner.cleanup()

    asyncio.run(_case())


def test_lookup_product_raises_no_match(monkeypatch) -> None:
    async def _case() -> None:
        async def empty_handler(request: web.Request) -> web.Response:
            return web.json_response({"items": []})

        runner, base_url = await _start_server(
            {
                "/google": empty_handler,
                "/lookup": empty_handler,
                "/search": empty_handler,
            }
        )
        monkeypatch.setattr(lookup_module, "GOOGLE_BOOKS_API_URL", f"{base_url}/google")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_LOOKUP_URL", f"{base_url}/lookup")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_SEARCH_URL", f"{base_url}/search")
        try:
            async with aiohttp.ClientSession() as session:
                try:
                    await lookup_product(session, "Unbekanntes Produkt")
                except ProductLookupError as exc:
                    assert exc.code == "lookup_no_match"
                    assert exc.status == 404
                else:
                    raise AssertionError("lookup_product should have raised ProductLookupError")
        finally:
            await runner.cleanup()

    asyncio.run(_case())


def test_lookup_product_surfaces_upcitemdb_rate_limit(monkeypatch) -> None:
    async def _case() -> None:
        async def google_handler(request: web.Request) -> web.Response:
            return web.json_response({"items": []})

        async def rate_limited_handler(request: web.Request) -> web.Response:
            return web.json_response({"code": "TOO_MANY_REQUESTS"}, status=429)

        runner, base_url = await _start_server(
            {
                "/google": google_handler,
                "/lookup": rate_limited_handler,
                "/search": rate_limited_handler,
            }
        )
        monkeypatch.setattr(lookup_module, "GOOGLE_BOOKS_API_URL", f"{base_url}/google")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_LOOKUP_URL", f"{base_url}/lookup")
        monkeypatch.setattr(lookup_module, "UPCITEMDB_SEARCH_URL", f"{base_url}/search")
        try:
            async with aiohttp.ClientSession() as session:
                try:
                    await lookup_product(session, "Nintendo Switch OLED")
                except ProductLookupError as exc:
                    assert exc.code == "lookup_rate_limited"
                    assert exc.status == 429
                else:
                    raise AssertionError("lookup_product should have raised ProductLookupError")
        finally:
            await runner.cleanup()

    asyncio.run(_case())
