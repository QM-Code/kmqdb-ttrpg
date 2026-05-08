#!/usr/bin/env python3
"""
Build an inventory of Paizo digital product images.

This script starts from the requested Paizo category pages, finds product cards,
keeps products that look digital, then opens each product page to collect
thumbnail and full-size image URLs.
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE = "https://store.paizo.com"

CATEGORIES = {
    "Pathfinder 1E": "https://store.paizo.com/pathfinder-1e/",
    "Pathfinder 2E": "https://store.paizo.com/pathfinder/pathfinder-second-edition/",
    "Pathfinder 2E Remaster": "https://store.paizo.com/pathfinder-2e-remaster/",
    "Starfinder 1E": "https://store.paizo.com/starfinder/starfinder-first-edition/",
    # Paizo's public SF2 products are listed under the main Starfinder shelf.
    "Starfinder 2E": "https://store.paizo.com/starfinder/",
}

DIGITAL_MARKERS = (
    "pdf",
    "foundry vtt",
    "fantasy grounds",
    "roll20",
    "demiplane",
    "alchemy",
    "official soundtrack",
    "soundtrack",
    "digital",
    "download",
    "code",
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 PaizoImageInventory/1.0",
}


def fetch(url: str, pause: float) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
    if pause:
        time.sleep(pause)
    return data.decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def absolutize(url: str) -> str:
    return urllib.parse.urljoin(BASE, html.unescape(url))


def page_url(base_url: str, page: int) -> str:
    if page == 1:
        return base_url
    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query)
    query["page"] = [str(page)]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def max_page(document: str) -> int:
    pages = [1]
    for match in re.finditer(r"[?&]page(?:=|&#x3D;)(\d+)", document):
        pages.append(int(match.group(1)))
    return max(pages)


def product_cards(document: str) -> list[dict[str, str]]:
    cards = []
    chunks = re.split(r'<article\b(?=[\s\S]{0,120}\bclass="[^"]*\bcard\b)', document)[1:]
    for chunk in chunks:
        title_match = re.search(
            r'<h3 class="card-title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>',
            chunk,
            re.S,
        )
        if not title_match:
            continue
        brand_match = re.search(
            r'<p class="card-text product-brandname"[^>]*>(.*?)</p>', chunk, re.S
        )
        image_match = re.search(r'<img\s+src="([^"]+)"', chunk, re.S)
        product_id_match = re.search(r"product_id(?:=|&#x3D;)(\d+)", chunk)
        cards.append(
            {
                "title": clean_text(title_match.group(2)),
                "product_url": absolutize(title_match.group(1)),
                "brand": clean_text(brand_match.group(1)) if brand_match else "",
                "listing_thumbnail_url": absolutize(image_match.group(1))
                if image_match
                else "",
                "product_id": product_id_match.group(1) if product_id_match else "",
            }
        )
    return cards


def is_digital(card: dict[str, str], category_name: str) -> bool:
    text = f"{card['title']} {card['product_url']}".lower()
    if category_name == "Starfinder 2E" and card["brand"] != "Starfinder 2E":
        return False
    return any(marker in text for marker in DIGITAL_MARKERS)


def extract_sku(document: str) -> str:
    patterns = [
        r'"mainSku":"([^"]+)"',
        r'data-product-sku="([^"]+)"',
        r'<dt[^>]*>\s*SKU:\s*</dt>\s*<dd[^>]*>(.*?)</dd>',
    ]
    for pattern in patterns:
        match = re.search(pattern, document, re.S)
        if match:
            return clean_text(match.group(1))
    return ""


def image_rows(card: dict[str, str], category_name: str, document: str) -> list[dict[str, str]]:
    rows = []
    sku = extract_sku(document)
    gallery_urls = []
    for pattern in (
        r'data-image-gallery-zoom-image-url="([^"]+)"',
        r'<figure[^>]+data-zoom-image="([^"]+)"',
    ):
        for match in re.finditer(pattern, document):
            url = re.sub(
                r"/images/stencil/[^/]+/",
                "/images/stencil/original/",
                absolutize(match.group(1)),
            )
            if url not in gallery_urls:
                gallery_urls.append(url)
    if not gallery_urls:
        for match in re.finditer(r'<meta property="og:image" content="([^"]+)"', document):
            url = absolutize(match.group(1))
            if url not in gallery_urls:
                gallery_urls.append(url)

    for index, full_url in enumerate(gallery_urls, start=1):
        thumb_url = re.sub(r"/images/stencil/[^/]+/", "/images/stencil/320w/", full_url)
        rows.append(
            {
                "category": category_name,
                "brand": card["brand"],
                "product_id": card["product_id"],
                "sku": sku,
                "title": card["title"],
                "product_url": card["product_url"],
                "image_number": index,
                "thumbnail_url": thumb_url,
                "full_size_url": full_url,
            }
        )
    if not rows and card["listing_thumbnail_url"]:
        rows.append(
            {
                "category": category_name,
                "brand": card["brand"],
                "product_id": card["product_id"],
                "sku": sku,
                "title": card["title"],
                "product_url": card["product_url"],
                "image_number": 1,
                "thumbnail_url": card["listing_thumbnail_url"],
                "full_size_url": re.sub(
                    r"/images/stencil/[^/]+/",
                    "/images/stencil/1280x1280/",
                    card["listing_thumbnail_url"],
                ),
            }
        )
    return rows


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return value[:120] or "image"


def download(url: str, target: Path, pause: float) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as response:
        target.write_bytes(response.read())
    if pause:
        time.sleep(pause)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="paizo_digital_image_inventory.csv")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--image-dir", default="paizo_images")
    parser.add_argument("--limit-products", type=int, default=0)
    parser.add_argument("--pause", type=float, default=0.5)
    args = parser.parse_args()

    seen_products = set()
    rows = []

    for category_name, category_url in CATEGORIES.items():
        first_page = fetch(category_url, args.pause)
        total_pages = max_page(first_page)
        for page in range(1, total_pages + 1):
            document = first_page if page == 1 else fetch(page_url(category_url, page), args.pause)
            cards = product_cards(document)
            print(f"{category_name}: page {page}/{total_pages}, {len(cards)} products")
            for card in cards:
                if card["product_url"] in seen_products:
                    continue
                if not is_digital(card, category_name):
                    continue
                seen_products.add(card["product_url"])
                try:
                    product_doc = fetch(card["product_url"], args.pause)
                except urllib.error.URLError as exc:
                    print(f"  skipped {card['product_url']}: {exc}")
                    continue
                rows.extend(image_rows(card, category_name, product_doc))
                if args.limit_products and len(seen_products) >= args.limit_products:
                    break
            if args.limit_products and len(seen_products) >= args.limit_products:
                break
        if args.limit_products and len(seen_products) >= args.limit_products:
            break

    fieldnames = [
        "category",
        "brand",
        "product_id",
        "sku",
        "title",
        "product_url",
        "image_number",
        "thumbnail_url",
        "full_size_url",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if args.download:
        root = Path(args.image_dir)
        for row in rows:
            stem = safe_name(row["sku"] or row["title"])
            ext = os.path.splitext(urllib.parse.urlparse(row["full_size_url"]).path)[1] or ".jpg"
            base = f"{stem}_{row['image_number']:02d}{ext}"
            download(row["thumbnail_url"], root / "thumbnails" / base, args.pause)
            download(row["full_size_url"], root / "full-size" / base, args.pause)

    print(f"Wrote {len(rows)} image rows to {args.out}")


if __name__ == "__main__":
    main()
