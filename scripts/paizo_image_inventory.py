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
import json
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


def fetch_json(url: str, pause: float) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if pause:
        time.sleep(pause)
    return payload


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


def extract_product_id(document: str, fallback_url: str = "") -> str:
    for pattern in (
        r'"productId":(\d+)',
        r'"product_id":(\d+)',
        r"product_id(?:=|&#x3D;)(\d+)",
        r'data-product-id="(\d+)"',
    ):
        match = re.search(pattern, document)
        if match:
            return match.group(1)
    match = re.search(r"/products/(\d+)/", fallback_url)
    return match.group(1) if match else ""


def thumbnail_url(full_url: str) -> str:
    return re.sub(r"/images/stencil/[^/]+/", "/images/stencil/320w/", full_url)


def full_size_url(image_url: str) -> str:
    return re.sub(r"/images/stencil/[^/]+/", "/images/stencil/original/", image_url)


def image_rows_from_urls(
    card: dict[str, str],
    category_name: str,
    sku: str,
    gallery_urls: list[str],
) -> list[dict[str, str]]:
    rows = []
    for index, full_url in enumerate(gallery_urls, start=1):
        rows.append(
            {
                "category": category_name,
                "brand": card["brand"],
                "product_id": card["product_id"],
                "sku": sku,
                "title": card["title"],
                "product_url": card["product_url"],
                "image_number": index,
                "thumbnail_url": thumbnail_url(full_url),
                "full_size_url": full_url,
            }
        )
    return rows


def image_rows(card: dict[str, str], category_name: str, document: str) -> list[dict[str, str]]:
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

    rows = image_rows_from_urls(card, category_name, sku, gallery_urls)
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
                "full_size_url": full_size_url(card["listing_thumbnail_url"]),
            }
        )
    return rows


def source_api_page_url(api_url: str, limit: int, offset: int) -> str:
    parsed = urllib.parse.urlparse(api_url)
    query = urllib.parse.parse_qs(parsed.query)
    query["limit"] = [str(limit)]
    query["offset"] = [str(offset)]
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query, doseq=True))
    )


def source_api_rows(
    api_url: str,
    pause: float,
    page_limit: int = 100,
    max_rows: int = 0,
    require_url: bool = False,
) -> list[dict]:
    rows = []
    offset = 0
    while True:
        payload = fetch_json(source_api_page_url(api_url, page_limit, offset), pause)
        page_rows = payload.get("rows") or []
        rows.extend(row for row in page_rows if not require_url or row.get("url"))
        if max_rows and len(rows) >= max_rows:
            return rows[:max_rows]
        if len(page_rows) < page_limit:
            break
        offset += page_limit
    return rows


def card_from_source(source: dict, category_name: str, brand: str) -> dict[str, str]:
    image = source.get("image") or ""
    return {
        "title": source.get("name") or source.get("id") or "",
        "product_url": source.get("url") or "",
        "brand": brand,
        "listing_thumbnail_url": image,
        "product_id": extract_product_id("", image),
    }


def image_rows_from_source(
    source: dict,
    category_name: str,
    brand: str,
    pause: float,
) -> list[dict[str, str]]:
    url = source.get("url") or ""
    card = card_from_source(source, category_name, brand)
    if not url:
        return []

    document = ""
    if "store.paizo.com" in urllib.parse.urlparse(url).netloc:
        try:
            document = fetch(url, pause)
        except urllib.error.URLError as exc:
            print(f"  could not fetch {url}: {exc}")

    if document:
        card["product_id"] = extract_product_id(document, card["listing_thumbnail_url"])
        rows = image_rows(card, category_name, document)
        if rows:
            if source.get("sku"):
                for row in rows:
                    row["sku"] = row["sku"] or str(source["sku"])
            return rows

    image = source.get("image") or ""
    if not image:
        return []
    full_url = full_size_url(absolutize(image))
    return image_rows_from_urls(
        card,
        category_name,
        str(source.get("sku") or ""),
        [full_url],
    )


def rows_from_source_api(
    api_url: str,
    category_name: str,
    brand: str,
    pause: float,
    limit_sources: int = 0,
) -> list[dict[str, str]]:
    rows = []
    sources = source_api_rows(
        api_url,
        pause,
        max_rows=limit_sources,
        require_url=True,
    )
    for index, source in enumerate(sources, start=1):
        print(f"{category_name}: source {index}/{len(sources)} {source.get('id') or ''}")
        rows.extend(image_rows_from_source(source, category_name, brand, pause))
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


def image_url_exists(url: str, pause: float) -> bool:
    if not url:
        return False
    for method, headers in (
        ("HEAD", {}),
        ("GET", {"Range": "bytes=0-0"}),
    ):
        req = urllib.request.Request(url, headers={**HEADERS, **headers}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                content_type = response.headers.get("Content-Type", "")
                ok = 200 <= response.status < 400 and content_type.lower().startswith("image/")
            if pause:
                time.sleep(pause)
            if ok:
                return True
        except urllib.error.URLError:
            continue
    return False


def verify_image_rows(rows: list[dict[str, str]], pause: float) -> list[dict[str, str]]:
    verified = []
    for row in rows:
        label = f"{row['title']} #{row['image_number']}"
        thumb_ok = image_url_exists(row["thumbnail_url"], pause)
        full_ok = image_url_exists(row["full_size_url"], pause)
        if thumb_ok and full_ok:
            verified.append(row)
        else:
            print(
                f"  missing image skipped for {label}: "
                f"thumbnail={'ok' if thumb_ok else 'missing'}, "
                f"full-size={'ok' if full_ok else 'missing'}"
            )
    return verified


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="paizo_digital_image_inventory.csv")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--image-dir", default="paizo_images")
    parser.add_argument("--limit-products", type=int, default=0)
    parser.add_argument(
        "--source-api-url",
        help="Read product/source rows from a KMQDB sources API table instead of Paizo category pages.",
    )
    parser.add_argument("--source-category", default="Pathfinder 1E")
    parser.add_argument("--source-brand", default="Pathfinder 1E")
    parser.add_argument(
        "--limit-sources",
        type=int,
        default=0,
        help="Limit source API rows with URLs for testing.",
    )
    parser.add_argument(
        "--verify-image-urls",
        action="store_true",
        help="Keep only image rows whose thumbnail and full-size URLs return image content.",
    )
    parser.add_argument("--pause", type=float, default=0.5)
    args = parser.parse_args()

    if args.source_api_url:
        rows = rows_from_source_api(
            args.source_api_url,
            args.source_category,
            args.source_brand,
            args.pause,
            args.limit_sources,
        )
    else:
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

    if args.verify_image_urls:
        rows = verify_image_rows(rows, args.pause)

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
