# Dedicated TTRPG host

This directory owns the repeatable AWS and host configuration for the
standalone `https://ttrpg.kmqdb.com` service. TTRPG consumes Core identity only
through the public HTTPS SSO/JWKS boundary and owns no Core or Gladiator code,
database, credential, or route.

## Production boundary

- AWS account: `322573371496`, region `us-east-1`
- CloudFormation stack: `kmqdb-ttrpg-production`
- Instance: `t3.small`, standard CPU credits, Ubuntu 24.04 amd64
- Existing unassociated Elastic IP: `52.207.82.158` (`eipalloc-52e89067`)
- Authoritative Route 53 zone: `Z0482932K097XLOBF5D0`
- Root storage: encrypted 16 GiB gp3, deleted with the instance
- State storage: encrypted 20 GiB gp3, retained across replacement/deletion
- Persistent mount: `/var/lib/kmqdb`
- Persistent state backups: shared DLM policy `policy-0706342b11f31a6d9`
- Application listener: `127.0.0.1:8012`; nginx alone exposes 80/443
- SSH: port 22 from the deployment-time operator `/32` only
- No instance profile or AWS credential is installed on the host.

The initial stack is created with `PublishDns=false`. This associates the EIP
and permits direct Host-header validation without changing the live wildcard
route. A separately reviewed update to `PublishDns=true` creates the exact A
record only after the installed service passes its direct-host gate.
`ttrpg.kmqdb.com.bootstrap.nginx` is the DNS-disabled HTTP configuration; it
rejects every other Host header. The TLS configuration replaces it only after
the certificate is issued.

The audited `ttrpg-shell.html` deployment file and the verified application
wheel's four exact TTRPG static files are installed into the release directory.
The shell is host composition and is deliberately not a wheel payload. Shared
workspace and menu assets remain Core-owned and are loaded over public HTTPS
from `kmqdb.com`; they are not copied into this repository or the TTRPG
artifact. The browser therefore has an explicit Core-static service dependency
in addition to Core SSO, while the TTRPG Python process remains
Core-independent.

## Sealed deployment artifacts

| Artifact | SHA-256 |
| --- | --- |
| `kmqdb_ttrpg-0.1.0a2-py3-none-any.whl` | `c51140de437d986829878ca91040fc55110d2456c8f562929caba6a21d50e1f5` |
| `kmqdb_ttrpg_semantic_contracts-1.0.0-py3-none-any.whl` | `7fa658b9a1e4a1148942040b318c758ebf2c49bccf27f91577ecb56e007f6e99` |
| `kmqdb-ttrpg-runtime-0.1.0a1.tar.gz` | `8de4b6d9ec51f71a981c8e2dd6789cad19c0ce21e1456c9ecd6e6227ef765828` |
| `cryptography-41.0.7-cp37-abi3-manylinux_2_28_x86_64.whl` | `43f2552a2378b44869fe8827aa19e69512e3245a219104438692385b0ee119d1` |
| `cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` | `c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf` |
| `pycparser-3.0-py3-none-any.whl` | `b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992` |
| `gunicorn-23.0.0-py3-none-any.whl` | `ec400d38950de4dfd418cff8328b2c8faed0edb0d517d3394e457c317908ca4d` |
| `packaging-26.3-py3-none-any.whl` | `d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c` |

The runtime artifact contains only exact deployment state:

- schema-3 cache: SHA-256 `abb170fb8fe73a45ca165a63706f66d85aa0b71c4cc4e5a6c8be7ac25359fffd`;
- 6,096 embedded binary assets, 364,481,680 body bytes, zero body-null rows;
- schema-1 item catalog: SHA-256 `4847f712ccf7c5f3297a7b7e21bf4e2406bb160b050c4db754d93c8f5d78394e`;
- item catalog digest `53e360e054a9f9fdd57e7f42841f015c9418e58e3b4095370862554355a9bf4e`;
- semantic repository catalog digest `84e19dfa52236397ca7e837795908b11b72fe08d3b34ddabde2fda13bbabf6de`.

The binary cache was initially materialized locally from exact approved
`s3://kmqdb` bindings. AWS credentials were never copied into the artifact or
server. The active cache was subsequently replaced through the authenticated
Library membership flow and now contains 6,097 approved binary assets with no
body-null rows. It remains a local cache, not a live object-store mount. The
portable product gate runs 181 cases with 17 exact cache-dependent skips; the
complete live-cache gate runs 198 cases with zero skips.

Subsequent refreshes use the generic Core-account and Library-membership
boundary. The Core account `ttrpg` exchanges its service-bound machine
credential for a short-lived Library-audience assertion. Library then verifies
that identity and its active `reader` membership in the owner library
`karmak`, scoped to `games/ttrpg`. The synchronizer selects one ruleset child;
PF2ER is the first, not a special identity or storage boundary. Library is
authoritative for delivered-byte accounting and charges the library owner.
TTRPG verifies the immutable generation and caches its structured publication
plus bounded direct-use media on the retained volume. Normal browser/compiler
requests use that local cache and incur no cross-service transfer. Revocation
prevents another fetch but does not invalidate already cached bytes.
The cache metadata binds the exact owner-qualified Library dataset to the
bookshelf receipt, while the runtime independently requires the selected
ruleset. A Library owner is therefore an input to a refresh, not a hard-coded
application identity.

## Infrastructure workflow

Validate the template and create a non-executing change set:

```bash
python -m unittest -v tests.infrastructure.test_ttrpg_server_template
aws cloudformation validate-template \
  --region us-east-1 \
  --template-body file://infrastructure/aws/ttrpg-server.yaml

operator_ip=$(curl -fsS https://checkip.amazonaws.com | tr -d '\r\n')
aws cloudformation create-change-set \
  --region us-east-1 \
  --stack-name kmqdb-ttrpg-production \
  --change-set-name REPLACE_WITH_UNIQUE_NAME \
  --change-set-type CREATE \
  --template-body file://infrastructure/aws/ttrpg-server.yaml \
  --parameters \
    ParameterKey=OperatorCidr,ParameterValue="$operator_ip/32" \
    ParameterKey=PublishDns,ParameterValue=false \
  --tags \
    Key=Service,Value=ttrpg.kmqdb.com \
    Key=ManagedBy,Value=cloudformation \
    Key=Environment,Value=production
```

Do not use the empty duplicate `kmqdb.com` hosted zone. Do not publish DNS in
the initial stack, clone the shared host security group, or copy its AWS
credentials.

## Runtime layout

- releases: `/srv/kmqdb-ttrpg/releases/`
- current release symlink: `/srv/kmqdb-ttrpg/current`
- virtual environment symlink: `/srv/kmqdb-ttrpg/venv`
- browser shell: `/srv/kmqdb-ttrpg/current/ttrpg-shell.html`
- TTRPG static assets: `/srv/kmqdb-ttrpg/current/@static/`
- cache: `/var/lib/kmqdb/ttrpg/cache/cache.db`
- item catalog: `/var/lib/kmqdb/ttrpg/cache/item-catalog.db`
- browser auth: `/var/lib/kmqdb/ttrpg/ttrpg-auth.db`
- semantic repositories: `/var/lib/kmqdb/ttrpg/semantic-repositories/`

Cache and catalog files are root-owned, group-readable by `www-data`, and not
application-writable. The semantic repository retains its authenticated exact
755/644 modes. Only browser authentication state is mutable by the service.
The root-owned mode-600 `/etc/kmqdb/ttrpg.env` contains the shared multi-worker
scope secret and no AWS credential.

## DNS, TLS, and identity

After the direct-host gate, update only `PublishDns=true`, inspect that the
change set creates one A record, and execute it. Obtain the new certificate
with Certbot's nginx authenticator, install `ttrpg.kmqdb.com.nginx`, and require
a successful renewal dry run. Unknown HTTP hosts and TLS SNI names fail closed.

Core already registers the exact TTRPG callback
`https://ttrpg.kmqdb.com/.api/auth/sso/callback`. No Core auth database or
signing key belongs on the TTRPG host.

## Required acceptance

- CloudFormation and EC2 termination protection are enabled; drift is
  `IN_SYNC` with zero drifted resources.
- The data volume has `BackupEnabled=true`; the shared 7-daily, 8-weekly,
  12-monthly DLM policy is enabled.
- IMDSv1 returns 401; only 22/80/443 are externally reachable.
- Cache and catalog SQLite `quick_check` pass, and the cache has zero body-null
  assets.
- `/.api/auth/session` and `/.api/bookshelf` return 200; removed Game,
  encounter, and engine routes remain canonical 404s.
- `/`, `/pf2er/`, and client-side TTRPG routes return the no-store browser
  shell; only the four declared `/.static/` files are served locally.
- The semantic envelope route returns the configured catalog digest.
- SSO start redirects to Core with client `ttrpg` and the exact callback.
- Certbot renewal dry-run and a controlled reboot both recover cleanly.

## Recovery

Application rollback repoints the `current` and `venv` symlinks to an already
verified release. Host replacement reattaches the retained state volume in the
same availability zone. Stack deletion requires an explicit termination-
protection disable and still retains the data volume. Never restore the old
monorepo TTRPG application as a runtime fallback.
