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

The KMQDB Pathfinder and Starfinder source/product records are owned by the
private `karmak` Library at these current human/browser table routes:

```text
https://lib.kmqdb.com/karmak/games/ttrpg/pf1e/.api/sqlite/table/sources
https://lib.kmqdb.com/karmak/games/ttrpg/pf2e/.api/sqlite/table/sources
https://lib.kmqdb.com/karmak/games/ttrpg/pf2er/.api/sqlite/table/sources
https://lib.kmqdb.com/karmak/games/ttrpg/sf1e/.api/sqlite/table/sources
https://lib.kmqdb.com/karmak/games/ttrpg/sf2e/.api/sqlite/table/sources
```

Production requires an authenticated Library session and returns 403 to an
anonymous request. `paizo_image_inventory.py` does not perform Core SSO or
accept browser-session material. The command examples below therefore use an
operator-supplied authorized endpoint, such as a bounded loopback service or
test fixture; do not paste a production session cookie into a command or
tracked file. The future production machine path is a Core-authenticated,
owner-approved immutable Library export whose transferred bytes are metered
once and cached by TTRPG, not anonymous access to these browser routes.

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
  --source-api-url "$AUTHORIZED_PF1E_SOURCES_URL" \
  --verify-image-urls \
  --out data/inventory/pf1e_source_image_inventory.csv
```

Use `--source-category` and `--source-brand` when scraping another ruleset:

```sh
python3 scripts/paizo_image_inventory.py \
  --source-api-url "$AUTHORIZED_PF2E_SOURCES_URL" \
  --source-category "Pathfinder 2E" \
  --source-brand "Pathfinder 2E" \
  --verify-image-urls \
  --out data/inventory/pf2e_source_image_inventory.csv
```

A full PF1E source scrape found `785` source rows with URLs and produced `770`
verified image rows:

| Output | Count | Local Size |
| --- | ---: | ---: |
| CSV image rows | 770 | 310.3 KB |
| Thumbnail files | 770 | 40 MB |
| Full-size files | 770 | 136 MB |
| Combined image files | 1,540 | 175 MB |

The source-derived inventory CSV is:

```text
data/inventory/pf1e_source_image_inventory.csv
```

The downloaded image binaries are local-only and ignored by Git:

```text
data/images/pf1e-source/thumbnails/
data/images/pf1e-source/full-size/
```

A full PF2E source scrape found `347` source rows with URLs and produced `457`
verified image rows:

| Output | Count | Local Size |
| --- | ---: | ---: |
| CSV image rows | 457 | 184.1 KB |
| Thumbnail files | 457 | 25 MB |
| Full-size files | 457 | 234 MB |
| Combined image files | 914 | 259 MB |

The PF2E source-derived inventory CSV is:

```text
data/inventory/pf2e_source_image_inventory.csv
```

The downloaded PF2E image binaries are local-only and ignored by Git:

```text
data/images/pf2e-source/thumbnails/
data/images/pf2e-source/full-size/
```

A full PF2E Remaster source scrape found `344` source rows with URLs and
produced `450` verified image rows:

| Output | Count | Local Size |
| --- | ---: | ---: |
| CSV image rows | 450 | 189.1 KB |
| Thumbnail files | 450 | 25 MB |
| Full-size files | 450 | 230 MB |
| Combined image files | 900 | 255 MB |

The PF2E Remaster source-derived inventory CSV is:

```text
data/inventory/pf2er_source_image_inventory.csv
```

The downloaded PF2E Remaster image binaries are local-only and ignored by Git:

```text
data/images/pf2er-source/thumbnails/
data/images/pf2er-source/full-size/
```

A full SF1E source scrape found `283` source rows with URLs and produced `284`
verified image rows. Those rows point to `271` unique thumbnail URLs and `271`
unique full-size URLs:

| Output | Count | Local Size |
| --- | ---: | ---: |
| CSV image rows | 284 | 111.5 KB |
| Unique thumbnail files | 271 | 17 MB |
| Unique full-size files | 271 | 149 MB |
| Combined unique image files | 542 | 166 MB |

The SF1E source-derived inventory CSV is:

```text
data/inventory/sf1e_source_image_inventory.csv
```

The downloaded SF1E image binaries are local-only and ignored by Git:

```text
data/images/sf1e-source/thumbnails/
data/images/sf1e-source/full-size/
```

A full SF2E source scrape found `47` source rows with URLs and produced `59`
verified image rows:

| Output | Count | Local Size |
| --- | ---: | ---: |
| CSV image rows | 59 | 23.7 KB |
| Thumbnail files | 59 | 2.9 MB |
| Full-size files | 59 | 35 MB |
| Combined image files | 118 | 37 MB |

The SF2E source-derived inventory CSV is:

```text
data/inventory/sf2e_source_image_inventory.csv
```

The downloaded SF2E image binaries are local-only and ignored by Git:

```text
data/images/sf2e-source/thumbnails/
data/images/sf2e-source/full-size/
```

## Notes

- `Image Records` means one product image row in the CSV. A product can have more than one image.
- `Thumbnail Files` are the `thumbnail_url` entries in the CSV.
- `Full-Size Files` are the `full_size_url` entries in the CSV.
- Some source rows can share the same image URL; file counts can therefore be
  lower than CSV image rows when duplicate assets are reused.
- `--verify-image-urls` checks both thumbnail and full-size image URLs and skips
  rows where either URL is missing or does not return image content.
- Sizes may change if Paizo updates or recompresses CDN assets.
