# Image Inventory

Generated from `data/inventory/paizo_digital_image_inventory.csv`. The project currently stores image URLs, not downloaded image binaries. Disk-space values below are calculated from CDN `Content-Length` headers and represent the estimated local storage required if the thumbnail and full-size image sets were downloaded.

| Game | Products | Image Records | Thumbnail Files | Thumbnail Size | Full-Size Files | Full-Size Size | Combined Size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pathfinder 1E | 58 | 58 | 58 | 2.8 MB | 58 | 9.2 MB | 12.0 MB |
| Pathfinder 2E | 28 | 111 | 111 | 3.5 MB | 111 | 130.5 MB | 134.0 MB |
| Pathfinder 2E Remaster | 59 | 187 | 187 | 7.7 MB | 187 | 215.5 MB | 223.2 MB |
| Starfinder 1E | 2 | 2 | 2 | 77.7 KB | 2 | 547.5 KB | 625.2 KB |
| Starfinder 2E | 10 | 29 | 29 | 860.6 KB | 29 | 25.6 MB | 26.5 MB |

## Totals

- Products: `157`
- Image records: `387`
- Thumbnail files: `387` (14.9 MB)
- Full-size files: `387` (381.4 MB)
- Combined estimated image storage: `396.3 MB`

## Source URL Image Lookup

The KMQDB Pathfinder 1E database exposes source/product records through:

```text
https://kmqdb.com/api/ttrpg/pf1e/sqlite/table/sources
```

Rows in that table include Paizo source URLs and existing image metadata in
these columns:

```text
id, type, name, abbr, parent, seq, lmin, lmax, date, sku, isbn, pages, url, description, image, credits, toc
```

For source rows that have a `url`, the inventory script can now fetch the
source product page, extract thumbnail and full-size CDN image URLs, and verify
that those URLs return image content before writing them to an inventory CSV.

Example command:

```sh
python3 scripts/paizo_image_inventory.py \
  --source-api-url https://kmqdb.com/api/ttrpg/pf1e/sqlite/table/sources \
  --verify-image-urls \
  --out data/inventory/pf1e_source_image_inventory.csv
```

A sample verification run against the first three PF1E source URLs produced
three verified image rows:

| Source ID | Name | SKU | Image Status |
| --- | --- | --- | --- |
| `ap-rotr-1` | Rise of the Runelords #1: Burnt Offerings | `PZO9001E` | verified |
| `ap-rotr-2` | Rise of the Runelords #2: The Skinsaw Murders | `PZO9002E` | verified |
| `ap-rotr-3` | Rise of the Runelords #3: The Hook Mountain Massacre | `PZO9003E` | verified |

## Notes

- `Image Records` means one product image row in the CSV. A product can have more than one image.
- `Thumbnail Files` are the `thumbnail_url` entries in the CSV.
- `Full-Size Files` are the `full_size_url` entries in the CSV.
- `--verify-image-urls` checks both thumbnail and full-size image URLs and skips
  rows where either URL is missing or does not return image content.
- Sizes may change if Paizo updates or recompresses CDN assets.
