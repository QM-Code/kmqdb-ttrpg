# KMQDB TTRPG

KMQDB TTRPG is the standalone TTRPG browser, rules-source, semantic-publication,
and PF2E Remaster compiler service for KMQDB. It is independent of the KMQDB
monorepo and installs beside the separately owned Core host and Gladiator game
service.

The repository also maintains Paizo Store image inventories for these game
lines:

- Pathfinder 1E
- Pathfinder 2E
- Pathfinder 2E Remaster
- Starfinder 1E
- Starfinder 2E

## Application Distribution

The application package is `kmqdb-ttrpg==0.1.0a1`. It installs the PEP 420
`subdomains.ttrpg` service/compiler namespace and the `kmqdb_ttrpg_wsgi`
entrypoint. Its only runtime dependencies are:

- `cryptography>=41.0.7`
- `kmqdb-ttrpg-semantic-contracts==1.0.0`

Build and verify the exact application wheel with:

```sh
PYTHONDONTWRITEBYTECODE=1 python tests/product_gate.py all --quiet
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tests.test_ttrpg_application_wheel
python scripts/build_ttrpg_application_wheel.py --output-dir dist/application
sha256sum dist/application/kmqdb_ttrpg-0.1.0a1-py3-none-any.whl
```

The expected application-wheel SHA-256 is
`2a5ed3eee81bbdb3ab2587fb60c4fa7613eb6c5688292a70883244019496fc58`.

The portable product gate runs 176 cases and records 17 exact environmental
skips for source-cache integration. To run the complete 193-case gate without
skips, provide the operational cache explicitly:

```sh
KMQDB_TTRPG_TEST_CACHE_DB=/absolute/path/to/cache.db \
  PYTHONDONTWRITEBYTECODE=1 \
  python tests/product_gate.py all --require-live-cache --quiet
```

Production caches must be provisioned with
`scripts/sync_library_cache.py --download-assets`. The standalone WSGI
entrypoint therefore needs no Core or S3 Python dependency; an explicitly
composed deployment may inject the narrow asset-stream port for body-null
cache rows.

## Current Contents

```text
.
├── application_distribution/
├── subdomains/ttrpg/
│   ├── @static/
│   ├── pf2er_compiler/
│   ├── backend.py
│   └── ttrpg_auth.py
├── kmqdb_ttrpg_wsgi.py
├── kmqdbttrpg.service.example
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
    ├── build_item_catalog.py
    ├── build_ttrpg_application_wheel.py
    ├── paizo_image_inventory.py
    └── sync_library_cache.py
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

## Semantic Contract Package

This repository also publishes the provider-owned, source-free semantic wire
contracts consumed by the standalone Gladiator service. The dependency-free
package installs four modules into the PEP 420 `subdomains.ttrpg` namespace:

- `semantic_assets`
- `semantic_catalog`
- `semantic_packages`
- `semantic_transport`

Build and verify the current release with:

```sh
PYTHONDONTWRITEBYTECODE=1 python tests/test_ttrpg_semantic_contract_wheel.py -v
python scripts/build_ttrpg_semantic_contract_wheel.py --output-dir dist
sha256sum dist/kmqdb_ttrpg_semantic_contracts-1.0.0-py3-none-any.whl
```

Version 1.0.0 is exactly
`kmqdb_ttrpg_semantic_contracts-1.0.0-py3-none-any.whl`, SHA-256
`7fa658b9a1e4a1148942040b318c758ebf2c49bccf27f91577ecb56e007f6e99`.
The `semantic-contracts-v1.0.0` tag publishes that tested wheel as a GitHub
Release asset; the release job reuses the verified CI artifact and does not
rebuild it.
