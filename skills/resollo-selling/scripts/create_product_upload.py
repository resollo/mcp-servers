#!/usr/bin/env python3
"""Create an inactive Resollo draft listing from 1-5 photos.

Encodes the images and POSTs them to Resollo's agent API in this process,
so the image bytes never pass through the AI agent's context. Prints only
the small JSON response (product_id, suggested fields, activation_url, ...).

Usage:
    RESOLLO_API_KEY=... python3 create_product_upload.py photo1.jpg [photo2.jpg ...]
        [--price 120] [--quantity 1] [--business] [--no-offers]

Standard library only (no 'requests'). The API key is read from the
RESOLLO_API_KEY environment variable and is never printed.
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = os.environ.get("RESOLLO_API_URL", "https://www.resollo.com/api/agent/v1/products")
ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGES = 5
MAX_BYTES = 5 * 1024 * 1024


def load_image(path: str) -> dict:
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type not in ALLOWED_TYPES:
        raise ValueError(f"{path}: unsupported type {mime_type!r} (use JPEG, PNG or WebP)")
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        raise ValueError(f"{path}: {size / 1e6:.1f} MB is over the 5 MB limit; resize or compress it first")
    with open(path, "rb") as f:
        return {"mime_type": mime_type, "data": base64.b64encode(f.read()).decode("ascii")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an inactive Resollo draft listing from photos.")
    parser.add_argument("images", nargs="+", help=f"1-{MAX_IMAGES} photos of the same item")
    parser.add_argument("--price", type=float, help="fixed price override (default: Resollo's AI suggestion)")
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--business", action="store_true", help="mark as a business listing")
    parser.add_argument("--no-offers", action="store_true", help="disable Make-an-Offer on the listing")
    args = parser.parse_args()

    api_key = os.environ.get("RESOLLO_API_KEY")
    if not api_key:
        print(json.dumps({"error": "RESOLLO_API_KEY environment variable is not set"}))
        return 2
    if len(args.images) > MAX_IMAGES:
        print(json.dumps({"error": f"at most {MAX_IMAGES} images per listing"}))
        return 2

    try:
        body = {
            "images": [load_image(p) for p in args.images],
            "quantity": args.quantity,
            "is_business_listing": args.business,
            "offers_enabled": not args.no_offers,
        }
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    if args.price is not None:
        body["price"] = args.price

    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            print(json.dumps(json.load(resp), ensure_ascii=False))
            return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        print(json.dumps({"error": f"HTTP {exc.code}", "detail": detail}, ensure_ascii=False))
        return 1
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"network error: {exc.reason}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
