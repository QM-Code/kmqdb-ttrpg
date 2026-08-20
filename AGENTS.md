# Agent Notes

## Repository Ownership

- This repository owns the standalone TTRPG browser/API service, TTRPG browser
  assets, semantic publication pipeline, source/cache tooling, item catalog,
  and `subdomains.ttrpg.pf2er_compiler`.
- `QM-Code/kmqdb-gladiator` owns game runtime, encounters, persistence, player
  clients, and Gladiator browser assets. Do not add Game routes or imports here.
- The KMQDB monorepo owns the generic Core server, database browser, shared
  browser assets, and deployment composition. Do not copy `kmqdbweb` modules.
- Normal files use mode `644` and directories use mode `755`. Keep cache,
  authentication, and semantic-repository state out of Git.

## GitHub Access

- Use SSH for GitHub verification, fetches, and pushes.
- The working remote should be `git@github.com:QM-Code/kmqdb-ttrpg.git`.
- Do not rely on the HTTPS remote for verification or pushing from agent
  environments; it can fail with an interactive credential prompt such as
  `could not read Username for 'https://github.com': Device not configured`.
- A quick SSH verification command is:

```sh
ssh -T git@github.com
```

GitHub returns a success message and exits nonzero because it does not provide
shell access; treat the authenticated greeting as a successful verification.

## Semantic Contract Distribution

- The provider-owned public wire contract consists only of
  `semantic_assets.py`, `semantic_catalog.py`, `semantic_packages.py`, and
  `semantic_transport.py`.
- `semantic_contract_distribution/` owns the dependency-free deterministic
  wheel backend and its exact source manifest. The distribution uses the PEP
  420 `subdomains.ttrpg` namespace and must not add namespace `__init__.py`
  files or provider/compiler implementation dependencies.
- Build only with
  `python scripts/build_ttrpg_semantic_contract_wheel.py --output-dir <dir>`.
  Version 1.0.0 must produce
  `kmqdb_ttrpg_semantic_contracts-1.0.0-py3-none-any.whl` at SHA-256
  `7fa658b9a1e4a1148942040b318c758ebf2c49bccf27f91577ecb56e007f6e99`.
- Run the focused release gate with
  `PYTHONDONTWRITEBYTECODE=1 python tests/test_ttrpg_semantic_contract_wheel.py -v`.
- The exact tag `semantic-contracts-v1.0.0` may release only the wheel artifact
  already produced by the successful test/build job. The release job must
  download and verify that artifact and must never rebuild it.
- A contract-module or wheel-byte change requires a new explicit distribution
  version, manifest digests, expected wheel digest, test fixtures, tag, and
  release workflow identity. Do not silently replace the 1.0.0 artifact.

## Application Distribution

- The application distribution is distinct from the semantic-contract
  distribution. Version `0.1.0a1` builds as
  `kmqdb_ttrpg-0.1.0a1-py3-none-any.whl` with SHA-256
  `2a5ed3eee81bbdb3ab2587fb60c4fa7613eb6c5688292a70883244019496fc58`.
- `application_distribution/source-manifest.json` is the exact wheel source
  authority. Build only with
  `python scripts/build_ttrpg_application_wheel.py --output-dir <dir>`.
- The application wheel must contain the TTRPG service/compiler and four
  TTRPG-owned static files, but must not duplicate the four semantic-contract
  modules. It depends on their exact `1.0.0` distribution instead.
- The application may import only the standard library, `cryptography`, and
  the exact semantic-contract namespace. Reject imports of `kmqdbweb`,
  Gladiator, and the retired local `rules_engine` package.
- `backend.create_application(asset_streamer=...)` is the sole optional
  object-storage integration. The default application fails closed for a
  body-null asset row. Initial deployments must provision caches with
  `scripts/sync_library_cache.py --download-assets`.
- The WSGI entrypoint is `kmqdb_ttrpg_wsgi:application`; the example systemd
  unit is `kmqdbttrpg.service.example`.

## Verification

- Portable retained product gate:
  `PYTHONDONTWRITEBYTECODE=1 python tests/product_gate.py all --quiet`.
- Full live-cache gate: set `KMQDB_TTRPG_TEST_CACHE_DB` to an absolute cache
  path and add `--require-live-cache`; this must run 193 tests with zero skips.
- Application release boundary:
  `PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tests.test_ttrpg_application_wheel`.
- Semantic contract boundary:
  `PYTHONDONTWRITEBYTECODE=1 python tests/test_ttrpg_semantic_contract_wheel.py -v`.
- Browser JavaScript must pass `node --check subdomains/ttrpg/@static/app.js`.
- Run verification from outside the monorepo and prove installed module origins
  before publishing. Do not count a test that imports the monorepo as
  standalone evidence.
