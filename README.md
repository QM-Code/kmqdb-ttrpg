# KMQDB TTRPG

KMQDB TTRPG is the standalone TTRPG browser, rules-source, semantic-publication,
and PF2E Remaster compiler service for KMQDB. It is independent of
`QM-Code/kmqdb` and installs beside the separately owned Core host and
Gladiator game service.

Future paid access will consume Core's generic service-scoped subscription
entitlement after Library proves that platform. TTRPG will own its plans'
local compiler, catalog, and browser capabilities, but will not create a
separate payment customer or service-specific billing implementation.

Subscription eligibility is not source-data authority. Core account `ttrpg`
is an active reader of the `karmak` Library scoped to `games/ttrpg`. TTRPG
exchanges its Core-owned machine credential for a short-lived
Library-audience identity assertion, then Library applies that membership and
scope. The first authenticated `pf2er` refresh completed on 2026-08-25 and
atomically activated 140 sources, 1,977 sections, and 6,097 approved binary
assets. Ordinary TTRPG operation uses only that local cache and has no live
Library dependency; revocation affects only future refreshes. Library
attributes storage and outgoing transfer to its owner regardless of the
receiving system or destination, so there is no TTRPG-specific
transfer-accounting protocol. PF2ER is the first selected ruleset, not the
authorization or service boundary; this service is intended to encode all
TTRPG rulesets.

The repository also maintains Paizo Store image inventories for these game
lines:

- Pathfinder 1E
- Pathfinder 2E
- Pathfinder 2E Remaster
- Starfinder 1E
- Starfinder 2E

## Application Distribution

The application package is `kmqdb-ttrpg==0.1.0a3`. It installs the PEP 420
`subdomains.ttrpg` service/compiler namespace and the `kmqdb_ttrpg_wsgi`
entrypoint. Its only runtime dependencies are:

- `cryptography>=41.0.7`
- `kmqdb-ttrpg-semantic-contracts==1.0.0`

Build and verify the exact application wheel with:

```sh
PYTHONDONTWRITEBYTECODE=1 python tests/product_gate.py all --quiet
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tests.test_ttrpg_application_wheel
python scripts/build_ttrpg_application_wheel.py --output-dir dist/application
sha256sum dist/application/kmqdb_ttrpg-0.1.0a3-py3-none-any.whl
```

The expected application-wheel SHA-256 is
`e2d97f8e63899bdd8fb19140887efe2099c738de51048a8549149277763f1301`.

The portable product gate runs 182 cases and records 17 exact environmental
skips for source-cache integration. To run the complete 199-case gate without
skips, provide the operational cache explicitly:

```sh
KMQDB_TTRPG_TEST_CACHE_DB=/absolute/path/to/cache.db \
  PYTHONDONTWRITEBYTECODE=1 \
  python tests/product_gate.py all --require-live-cache --quiet
```

Production caches must be provisioned with
`scripts/sync_library_cache.py --download-assets`. This caches the complete
structured publication plus only the explicit Library `source-assets` set:
canonical covers, semantic icons, and book-local resource images used by
TTRPG. It does **not** copy original PDFs, high-resolution source material, or
every page image. Library S3 remains authoritative for the complete source and
media corpus.

The active cache file is deployed as `0640 root:www-data`. The synchronizer
creates a new cache with mode `0640` and preserves an existing cache's exact
mode and ownership across its atomic replacement.

Every cache records its exact owner-qualified Library dataset separately from
the selected ruleset. The runtime accepts any valid Library owner slug, binds
the bookshelf receipt to that recorded dataset, and still requires the
current runtime ruleset. This keeps `karmak` out of the reusable TTRPG cache
consumer while preventing a cache for another ruleset from being mounted by
mistake.

The bounded local cache lets TTRPG serve its browser, compiler, and catalog
while Library is unreachable. The standalone WSGI entrypoint therefore needs
no Core or S3 Python dependency; an explicitly composed deployment may still
inject the narrow asset-stream port for body-null cache rows. If measured
local-volume or snapshot cost later becomes material, the reproducible media
cache may move to a TTRPG-owned S3 bucket excluded from nightly backups without
changing Library authority or the verified-generation contract.

Executable presentation is a reviewed service artifact rather than imported
tenant content. A refresh with a non-empty renderer requires exactly one
Library interface script and one digest-sealed renderer bundle, caches both as
same-origin assets, and rejects dynamic code evaluation. The production CSP
does not permit `unsafe-eval`.

The synchronizer is ruleset-neutral. A production refresh reads a
service-bound Core machine credential from a mode-0600 file, exchanges it for
a short-lived Library assertion as needed, and selects one child below the
member scope `games/ttrpg`:

```sh
python3 scripts/sync_library_cache.py \
  --origin https://lib.kmqdb.com \
  --core-origin https://kmqdb.com \
  --machine-credential-file /etc/kmqdb/ttrpg-library.credential \
  --library-slug karmak \
  --ruleset pf2er \
  --download-assets
```

The credential must belong to a Core account subscribed to Library; Library
must separately grant that account a reader membership whose scope includes
the selected path. Changing `--ruleset` selects another published child such
as a future Starfinder or other TTRPG ruleset without changing the identity,
membership, or cache protocol.

For the first refresh only, the Library owner can create a reader invitation
scoped exactly to `games/ttrpg`. Store that one-use token in a separate
mode-0600 file and add `--library-invitation-file /absolute/path/to/file`.
The synchronizer exchanges its Core credential, accepts the invitation as the
authenticated Core account, verifies the returned role and scope, and then
continues with the normal refresh. Remove the consumed invitation file after a
successful run; subsequent refreshes use the persisted Library membership.

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

The source records now belong to the private `karmak` Library at
`lib.kmqdb.com`. Its current human/browser table route is, for example:

```text
https://lib.kmqdb.com/karmak/games/ttrpg/pf1e/.api/sqlite/table/sources
```

Library rejects an unauthenticated request to that route. The inventory script
does not perform Core SSO or accept a browser cookie, so do not point it at the
production URL and expect an anonymous scrape. Its `--source-api-url` mode is
for an explicitly authorized local/operator endpoint. The future production
machine flow uses the Core account `ttrpg`, a short-lived Library-audience
identity assertion, Library reader membership scoped to `games/ttrpg`, and
immutable generation verification. It does not reuse the browser API or a
Library-local service credential. Never put a Library browser session or Core
machine credential in source control or shell history.

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

## Legacy roster publication operator

The operator-only `scripts/build_pf2er_legacy_roster_publication.py` reconnects
an explicitly reviewed source-era Gladiator roster to current private TTRPG
source evidence and emits a canonical public semantic bundle. It does not join
the application wheel or add an authenticated catalog route. The resulting
catalog is served through the existing anonymous, immutable envelope, package,
and asset APIs.

The current reviewed publication has catalog digest
`e2454af265fdacfc410b15ca05073c5b60bc8bf2b92073e360130c88110442b4`:
six packages, 101 entities, and an exact 931-reference presentation closure for
all 94 roster creature identities. Each creature carries its authenticated
Library source-node packet and closure manifest, the sealed SourceNodeView v20
renderer and CSS, source media, action glyphs, and x128/x512 roster portraits.
The complete closure is 87,575,546 bytes and has no unavailable or omitted
presentation asset. TTRPG passes these Library-owned presentation components
through as content-addressed semantic assets; it does not replace them with a
re-derived stat-block renderer. Ninety-one reconnected creatures are
intentionally persistence-only and carry a runtime blocker; Hadrosaurid,
Viper, and Xulgath use their reviewed executable packages. The private
evidence and migration-binding artifacts remain operator inputs and are never
published by the HTTP service.
