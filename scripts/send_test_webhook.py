from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from gpu_alerts.config import load_config


def _resolve_runtime_defaults(args: argparse.Namespace) -> tuple[str, str, str, str, str, str]:
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    config = load_config(config_path)
    webhook_url = args.url or f"http://{config.webhook.host}:{config.webhook.port}{config.webhook.path}"
    token = args.token or (config.webhook.token or "")

    selected_source = None
    if args.tracker_id:
        for source in config.sources:
            if source.tracker_id == args.tracker_id:
                selected_source = source
                break
    elif args.product_hint:
        for source in config.sources:
            if source.tracker_id == args.product_hint:
                selected_source = source
                break
    elif config.sources:
        selected_source = config.sources[0]

    shop = args.shop or (selected_source.shop if selected_source else "manual")
    source_name = args.source_name or (selected_source.source if selected_source else "shop")
    scope = args.scope or (selected_source.scope if selected_source else "shop_search")
    product_hint = args.product_hint or (selected_source.tracker_id if selected_source else args.tracker_id or "demo-tracker")
    return webhook_url, token, shop, source_name, scope, product_hint


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test observation to the local Distill webhook.")
    parser.add_argument("--config", default="system.json")
    parser.add_argument("--url", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--tracker-id", default="", dest="tracker_id")
    parser.add_argument("--shop", default="")
    parser.add_argument("--source", default="", dest="source_name")
    parser.add_argument("--scope", default="")
    parser.add_argument("--title", default="Alertivo Testangebot")
    parser.add_argument("--price", default="499,00 EUR")
    parser.add_argument("--in-stock", default="Auf Lager", dest="in_stock")
    parser.add_argument("--product-hint", default="", dest="product_hint")
    parser.add_argument("--offer-url", default="https://example.com/product", dest="offer_url")
    args = parser.parse_args()

    webhook_url, token, shop, source_name, scope, product_hint = _resolve_runtime_defaults(args)

    payload = {
        "shop": shop,
        "source": source_name,
        "scope": scope,
        "title": args.title,
        "url": args.offer_url,
        "price": args.price,
        "in_stock": args.in_stock,
        "product_hint": product_hint,
    }

    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Webhook-Token"] = token

    request = urllib.request.Request(
        webhook_url,
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
