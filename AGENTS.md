# Agent Notes

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
