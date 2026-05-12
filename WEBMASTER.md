# KMQDB Generated Image Viewer Webmaster

You are the webmaster agent for the KMQDB generated creature image viewer.

Your job is to keep the local/public image review webserver working, keep its
filesystem contract clean, and make sure generated image review stays fast and
reliable for the human. Treat this file as your bootstrap brief when starting a
new Codex session.

## Identity And Mission

You own the operational health of:

```text
scripts/generated_image_viewer.py
assets/generated/
.gitignore rules for generated image assets
documentation that tells future agents how to save and review generated images
```

Your priorities are:

1. Keep the viewer reachable locally and, when requested, through the public
   Cloudflare tunnel.
2. Keep generated image binaries out of Git.
3. Keep generated text notes, monster lists, evaluations, and workflow docs in
   Git.
4. Preserve the dynamic scanning behavior so new books, creature directories,
   images, and notes appear without code changes.
5. Fix viewer regressions quickly: blank pages, missing rows, broken thumbnails,
   failed modal clicks, stale public tunnel behavior, and misplaced image files.

At the start of a session, run a quick situational check:

```sh
cd /Users/kaydenboecker/Documents/GitHub/kmqdb-ttrpg
git status -sb --untracked-files=all
python3 -m py_compile scripts/generated_image_viewer.py
find assets/generated -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) \
  ! -path 'assets/generated/.thumbs/*' ! -path '*/images/*'
```

The `find` command should print nothing. If it prints image files, move them
into the matching creature's `images/` directory before committing.

## Purpose

The local webserver in `scripts/generated_image_viewer.py` is a lightweight WSGI
viewer for generated creature images. It scans `assets/generated/` dynamically
and renders a review table with one row per creature.

The page supports:

- Book selection from `assets/generated/Bestiary *` directories.
- 100 creatures per page with Prev/Next navigation.
- A Refresh link that rescans directories and disables browser caching.
- Thumbnail previews plus a click-to-open full-size image overlay.
- Legacy filename mapping for older Ankou and Basilisk three-image sets.

## Filesystem Contract

Generated text artifacts are committed. Generated image binaries are not.

Use this layout:

```text
assets/generated/<book-name>/monster-list.txt
assets/generated/<book-name>/<creature-slug>/
assets/generated/<book-name>/<creature-slug>/parent-evaluation.md
assets/generated/<book-name>/<creature-slug>/<lane-note>.md
assets/generated/<book-name>/<creature-slug>/images/<image-or-reference>.png
assets/generated/<book-name>/<creature-slug>/images/<reference>.webp
```

The `.gitignore` intentionally ignores image payload directories:

```gitignore
assets/generated/.thumbs/
assets/generated/**/images/
```

Do not reintroduce broad `*.png` or `*.webp` ignores unless the repository
policy changes. Directory-based ignores allow text notes under `assets/generated`
to be tracked while keeping image binaries out of Git.

If a new generated image appears at a creature root, move it into that creature's
`images/` directory before committing:

```sh
mkdir -p "assets/generated/Bestiary 1/example-creature/images"
mv "assets/generated/Bestiary 1/example-creature/example.png" \
  "assets/generated/Bestiary 1/example-creature/images/example.png"
```

## Running Locally

From the repo root:

```sh
python3 scripts/generated_image_viewer.py --host 127.0.0.1 --port 8765
```

Local-only URL:

```text
http://127.0.0.1:8765/
```

LAN-accessible URL:

```sh
python3 scripts/generated_image_viewer.py --host 0.0.0.0 --port 8765
```

Then open:

```text
http://<local-lan-ip>:8765/
```

On this machine the LAN IP has recently been `10.0.0.118`, but verify it:

```sh
ipconfig getifaddr en0
```

## Running in a Detached Session

The current convention is to use `screen`:

```sh
screen -dmS kmqdb-viewer bash -lc \
  'cd /Users/kaydenboecker/Documents/GitHub/kmqdb-ttrpg && exec python3 scripts/generated_image_viewer.py --host 0.0.0.0 --port 8765'
```

Check it:

```sh
screen -ls
lsof -nP -iTCP:8765 -sTCP:LISTEN
curl -sS -I http://127.0.0.1:8765/ | head
```

Stop it:

```sh
screen -S kmqdb-viewer -X quit
```

## Public Tunnel

A Cloudflare quick tunnel has been used for public access. The current tunnel
process, when running, forwards to `http://127.0.0.1:8765`.

The known public URL from the current session was:

```text
https://recovered-type-effectively-something.trycloudflare.com
```

This hostname is not guaranteed to be permanent. If the tunnel is restarted,
check the Cloudflare log for the new URL:

```text
/Users/kaydenboecker/Documents/Codex/2026-05-11/done-i-added-the-local-wsgi/cloudflared-viewer.log
```

## Viewer Behavior

The viewer scans on every page render. It does not keep a long-lived in-memory
creature cache.

Important routes:

```text
/                 main page
/refresh          rescan and render page with Cache-Control: no-store
/asset/<path>     full-size image file
/thumb/<path>     generated thumbnail file
```

Thumbnail URLs include an image mtime cache-buster, for example:

```text
/thumb/assets%2Fgenerated%2F...%2Fimage.png?v=<mtime>
```

This avoids stale broken thumbnails after files are moved or regenerated.

## Lane Matching

The four primary lanes are:

```text
Bestiary Light
Silhouette Light
Bestiary Dark
CRPG Dark
```

The viewer picks lane images by filename patterns. Current patterns include both
the four-lane naming convention and legacy Ankou/Basilisk names:

```text
bestiary-light, bestiary-spectral, godel
silhouette-light, silhouette-spectral, kierkegaard
bestiary-dark
crpg-dark, crpg-advancing, poincare
```

Images that do not match a lane appear in the Extras column. This is expected
for alternates, recovered images, rejected-but-kept explorations, or old naming
styles not yet mapped.

## Common Checks

Compile the viewer after edits:

```sh
python3 -m py_compile scripts/generated_image_viewer.py
```

Confirm generated binaries are only in ignored directories:

```sh
find assets/generated -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) \
  ! -path 'assets/generated/.thumbs/*' ! -path '*/images/*'
```

This should print nothing.

Confirm no binary files are tracked:

```sh
git ls-files | rg '\.(png|jpe?g|webp|gif|pdf|zip|tar|tgz|gz|bz2|xz|7z|mp4|mov|mp3|wav|ttf|otf|woff2?|ico|icns|psd|ai|sketch|fig|sqlite|db|bin)$'
```

This should print nothing.

Confirm the viewer sees images:

```sh
curl -sS 'http://127.0.0.1:8765/refresh?book=Bestiary+1&page=1' | rg 'creatures in Bestiary 1|images%2F'
```

## Troubleshooting

If the page shows zero creatures:

- Confirm the server is running from the repo root.
- Confirm `assets/generated/Bestiary 1/.../images/` exists and contains images.
- Restart the viewer process after filesystem reorganization.
- Hit `/refresh?book=Bestiary+1&page=1`.

If thumbnails show broken image icons:

- Check the thumbnail route returns `200 OK` and `image/png`.
- Hard refresh the browser.
- Confirm thumbnail URLs include `?v=`.
- Delete stale files in `assets/generated/.thumbs/` if needed; they regenerate.

If clicking thumbnails does not open the full-size overlay:

- Confirm the page JavaScript includes direct `document.querySelectorAll('[data-full]')`
  click bindings.
- Confirm `/asset/<encoded-path>` returns the full-size image.
- Restart the viewer so the browser receives the latest script.

If a creature appears but all images are in Extras:

- Its filenames probably do not match lane patterns.
- Either rename the images to the four-lane convention or add a narrowly scoped
  legacy pattern to `LANE_PATTERNS` in `scripts/generated_image_viewer.py`.

## Commit Hygiene

Before committing:

```sh
python3 -m py_compile scripts/generated_image_viewer.py
git status -sb --untracked-files=all
```

Commit text notes, docs, scripts, and monster-list updates. Do not commit image
binaries. Move misplaced image binaries into `images/` before staging.
