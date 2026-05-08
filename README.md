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

To download image files locally, use:

```sh
python3 scripts/paizo_image_inventory.py --download
```

Downloaded images are intentionally ignored by Git because they can become
large. The CSV inventory is the source of truth for image URLs.

## Notes

- The repository currently stores image URLs and supporting metadata, not the
  downloaded image binaries.
- Digital products are identified with conservative title and URL markers such
  as `PDF`, `Foundry VTT`, `soundtrack`, `download`, and `code`.
- Raw HTML files under `data/raw-paizo-pages/` are retained as inspection
  samples from the original scrape.
