# Agent Notes

## Repository Ownership

- This repository owns the standalone TTRPG browser/API service, TTRPG browser
  assets, semantic publication pipeline, source/cache tooling, item catalog,
  and `subdomains.ttrpg.pf2er_compiler`.
- `QM-Code/kmqdb-gladiator` owns game runtime, encounters, persistence, player
  clients, and Gladiator browser assets. Do not add Game routes or imports here.
- `QM-Code/kmqdb` owns the generic Core server, database browser, shared
  browser assets, identity authority, and reusable infrastructure contracts.
  Do not copy `kmqdbweb` modules or Core private state.
- Core's generic subscription foundation will eventually grant TTRPG service
  eligibility through the same service-scoped entitlement used by Library and
  Gladiator. TTRPG still owns its plan-to-capability map, service usage, and
  local authorization; do not add payment-provider or Library billing schemas
  here.
- A subscription does not authorize Library data. The next Library-backed
  refresh must use Core's separate generic resource-grant protocol: Library
  authorizes and meters the exact transfer, while TTRPG verifies and durably
  caches the immutable generation. Cache hits create no new transfer cost;
  revocation blocks only future retrieval.
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
  body-null asset row. Build/update the source cache with
  `scripts/sync_library_cache.py`, then use
  `scripts/materialize_cache_assets.py` to prove and fill every exact binary
  binding before deployment. AWS credentials are operator inputs to the
  materializer and must never be installed on the TTRPG host.
- Build a deployment semantic repository from reviewed package/asset bundles
  with `scripts/build_semantic_repository.py`. Deploy only the resulting
  digest-named immutable repository; never bundle provider source trees or
  Game runtime data as semantic publication state.
- The sealed alpha-1 cache is pre-protocol operator-seeded evidence, not a
  live Library integration. TTRPG carries no Library browser session, bucket
  permission, or permanent cross-service credential. Before its next refresh,
  implement and record the exact grant, immutable receipt, and delivered-byte
  accounting defined by `QM-Code/kmqdb` in
  `AGENTS/service-resource-grants.md`.
- The WSGI entrypoint is `kmqdb_ttrpg_wsgi:application`; the example systemd
  unit is `kmqdbttrpg.service.example`.

## Production Deployment

- `infrastructure/aws/` owns the dedicated `ttrpg.kmqdb.com` CloudFormation,
  nginx, systemd-hardening, backup, and operational acceptance contract.
- Create the stack with `PublishDns=false`, install and validate sealed
  artifacts through the EIP, then publish the exact Route 53 record in a
  separately inspected update. Do not combine DNS cutover with host creation.
- Persistent databases and semantic repositories live under
  `/var/lib/kmqdb/ttrpg` on the retained encrypted data volume. Application
  wheels, nginx, TLS, and systemd configuration are reproducible host state.
- The data volume uses the shared `BackupEnabled=true` DLM policy: 7 daily,
  8 weekly, and 12 monthly snapshots. Do not attach the backup tag to the
  replaceable root volume.
- The instance has no IAM role or AWS credential. Only SSH from the current
  operator `/32` and public HTTP/HTTPS are permitted.

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
