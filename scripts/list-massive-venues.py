from __future__ import annotations

import argparse
import os
from collections import defaultdict

import requests


DEFAULT_VENUES = ("XCME", "XCBT", "XCEC", "XNYM")
PRODUCTS_URL = "https://api.massive.com/futures/v1/products"


def load_local_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List Massive futures products by trading venue.")
    parser.add_argument(
        "--venue",
        dest="venues",
        action="append",
        help="Trading venue to query. Can be passed more than once. Defaults to common CME venues.",
    )
    parser.add_argument("--limit", type=int, default=1000, help="Massive API page size.")
    parser.add_argument("--max-pages", type=int, default=25, help="Safety cap per venue.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds.")
    return parser.parse_args()


def require_api_key() -> str:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set MASSIVE_API_KEY before running this manual script.")
    return api_key


def fetch_products(venue: str, *, api_key: str, limit: int, max_pages: int, timeout: float) -> list[dict]:
    products: list[dict] = []
    url: str | None = PRODUCTS_URL
    params: dict[str, object] = {
        "limit": max(1, min(int(limit or 1000), 1000)),
        "trading_venue": venue,
        "apiKey": api_key,
    }
    page = 0

    while url and page < max_pages:
        page += 1
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("results") or []
        if not isinstance(batch, list) or not batch:
            break
        products.extend(item for item in batch if isinstance(item, dict))
        next_url = payload.get("next_url")
        url = str(next_url).strip() if next_url else None
        params = {"apiKey": api_key}

    return products


def summarize(products: list[dict]) -> dict[str, list[str]]:
    by_class: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for product in products:
        code = str(product.get("product_code") or "").strip()
        if not code:
            continue
        key = (
            str(product.get("asset_class") or "?").strip(),
            str(product.get("asset_sub_class") or "?").strip(),
            str(product.get("sector") or "").strip(),
        )
        by_class[key].append(code)

    summary: dict[str, list[str]] = {}
    for (asset_class, asset_sub_class, sector), codes in by_class.items():
        label = f"{asset_class} / {asset_sub_class}" + (f" / {sector}" if sector else "")
        summary[label] = sorted(set(codes))
    return summary


def main() -> None:
    load_local_env()
    args = parse_args()
    api_key = require_api_key()
    venues = tuple(args.venues or DEFAULT_VENUES)

    for venue in venues:
        print(f"\n{'=' * 50}")
        print(f"  {venue}")
        print(f"{'=' * 50}")

        products = fetch_products(
            venue,
            api_key=api_key,
            limit=args.limit,
            max_pages=max(int(args.max_pages or 25), 1),
            timeout=max(float(args.timeout or 15.0), 1.0),
        )
        unique_codes = sorted({str(item.get("product_code") or "").strip() for item in products if item.get("product_code")})
        print(f"  Total unique products: {len(unique_codes)}")

        for label, codes in sorted(summarize(products).items()):
            shown = ", ".join(codes[:40])
            suffix = " ..." if len(codes) > 40 else ""
            print(f"\n  [{label}]  ({len(codes)} products)")
            print(f"    {shown}{suffix}")


if __name__ == "__main__":
    main()
