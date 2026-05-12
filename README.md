# KMQDB TTRPG

KMQDB TTRPG is a working repository for collecting, organizing, and documenting
tabletop roleplaying game product metadata and image assets.

The current project focus is a Paizo Store image inventory for digital products
across these game lines:

- Pathfinder 1E
- Pathfinder 2E
- Pathfinder 2E Remaster
- Starfinder 1E
- Starfinder 2E

## Current Contents

```text
.
├── INVENTORY.md
├── docs/
│   └── IMAGE_GENERATION_WORKFLOW.md
├── data/
│   ├── inventory/
│   │   ├── paizo_digital_image_inventory.csv
│   │   └── paizo_digital_image_inventory_sample.csv
│   └── raw-paizo-pages/
│       ├── pf2.html
│       ├── sample_product.html
│       └── starfinder.html
└── scripts/
    └── paizo_image_inventory.py
```

## Inventory Data

The main inventory file is:

```text
data/inventory/paizo_digital_image_inventory.csv
```

Each row represents one product image and includes:

- game/category
- product brand
- product ID
- SKU
- product title
- product page URL
- image number
- thumbnail URL
- full-size image URL

See `INVENTORY.md` for a summary of image counts and estimated download size by
game line.

## Script

The inventory was generated with:

```sh
python3 scripts/paizo_image_inventory.py --out data/inventory/paizo_digital_image_inventory.csv
```

To create a small test inventory:

```sh
python3 scripts/paizo_image_inventory.py --limit-products 5 --out data/inventory/paizo_digital_image_inventory_sample.csv
```

To inventory images from a KMQDB `sources` API table, such as Pathfinder 1E
source records that already have product URLs:

```sh
python3 scripts/paizo_image_inventory.py \
  --source-api-url https://kmqdb.com/api/ttrpg/pf1e/sqlite/table/sources \
  --verify-image-urls \
  --out data/inventory/pf1e_source_image_inventory.csv
```

`--verify-image-urls` keeps only rows whose thumbnail and full-size URLs return
image content.

To download image files locally, use:

```sh
python3 scripts/paizo_image_inventory.py --download
```

Downloaded images are intentionally ignored by Git because they can become
large. The CSV inventory is the source of truth for image URLs.

When archiving downloaded image folders for transfer, prefer minimal compression
for speed because image files are already compressed:

```sh
zip -r -0 -X archive-name.zip image-folder
```

## Notes

- Repository notes and inventory files may change as the integration shape
  becomes clearer.
- The repository currently stores image URLs and supporting metadata, not the
  downloaded image binaries.
- Generated creature-art workflow notes live in `docs/IMAGE_GENERATION_WORKFLOW.md`.
- Digital products are identified with conservative title and URL markers such
  as `PDF`, `Foundry VTT`, `soundtrack`, `download`, and `code`.
- Raw HTML files under `data/raw-paizo-pages/` are retained as inspection
  samples from the original scrape.
