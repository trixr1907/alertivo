from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test observation to the local Distill webhook.")
    parser.add_argument("--url", default="http://127.0.0.1:8787/webhook/distill")
    parser.add_argument("--token", default="")
    parser.add_argument("--shop", default="alternate")
    parser.add_argument("--title", default="MSI GeForce RTX 5070 Ti Gaming Trio OC")
    parser.add_argument("--price", default="1039,00 €")
    parser.add_argument("--in-stock", default="Auf Lager", dest="in_stock")
    parser.add_argument("--product-hint", default="rtx-5070-ti", dest="product_hint")
    parser.add_argument("--offer-url", default="https://example.com/product", dest="offer_url")
    args = parser.parse_args()

    payload = {
        "shop": args.shop,
        "source": "shop",
        "scope": "shop_search",
        "title": args.title,
        "url": args.offer_url,
        "price": args.price,
        "in_stock": args.in_stock,
        "product_hint": args.product_hint,
    }

    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["X-Webhook-Token"] = args.token

    request = urllib.request.Request(
        args.url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"))
        raise SystemExit(exc.code) from exc


if __name__ == "__main__":
    main()
