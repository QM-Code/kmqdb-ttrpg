#!/usr/bin/env python3
"""Local WSGI viewer for generated creature images."""

from __future__ import annotations

import argparse
import hashlib
import html
import mimetypes
import posixpath
import subprocess
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from wsgiref.simple_server import make_server


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "assets" / "generated"
THUMBS = GENERATED / ".thumbs"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_DIRNAME = "images"
LANE_PATTERNS = (
    ("Bestiary Light", ("bestiary-light", "bestiary-spectral", "godel")),
    ("Silhouette Light", ("silhouette-light", "silhouette-spectral", "kierkegaard")),
    ("Bestiary Dark", ("bestiary-dark",)),
    ("CRPG Dark", ("crpg-dark", "crpg-advancing", "poincare")),
)
SKIP_NAME_PARTS = ("reference", "context", "rejected")
PAGE_SIZE = 100


@dataclass(frozen=True)
class Creature:
    book: str
    slug: str
    name: str
    directory: Path
    images: tuple[Path | None, Path | None, Path | None, Path | None]
    extras: tuple[Path, ...]


def title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-"))


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def image_url(path: Path) -> str:
    return "/asset/" + urllib.parse.quote(rel(path), safe="")


def thumb_path(path: Path) -> Path:
    digest = hashlib.sha256(rel(path).encode("utf-8")).hexdigest()[:18]
    return THUMBS / f"{path.stem}-{digest}.png"


def thumb_url(path: Path) -> str:
    version = str(path.stat().st_mtime_ns)
    return "/thumb/" + urllib.parse.quote(rel(path), safe="") + "?" + urllib.parse.urlencode({"v": version})


def is_display_image(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in IMAGE_SUFFIXES and not any(part in name for part in SKIP_NAME_PARTS)


def creature_images(creature_dir: Path) -> list[Path]:
    image_dir = creature_dir / IMAGE_DIRNAME
    roots = [image_dir, creature_dir] if image_dir.exists() else [creature_dir]
    images: list[Path] = []
    for root in roots:
        images.extend(path for path in root.iterdir() if path.is_file() and is_display_image(path))
    return sorted(images)


def scan_creatures() -> list[Creature]:
    creatures: list[Creature] = []
    if not GENERATED.exists():
        return creatures

    for book_dir in sorted(path for path in GENERATED.iterdir() if path.is_dir() and path.name.startswith("Bestiary ")):
        for creature_dir in sorted(path for path in book_dir.iterdir() if path.is_dir() and not path.name.startswith(".")):
            all_images = creature_images(creature_dir)
            if not all_images:
                continue

            selected: list[Path | None] = []
            used: set[Path] = set()
            for _, patterns in LANE_PATTERNS:
                matches = [path for path in all_images if any(pattern in path.name.lower() for pattern in patterns)]
                choice = matches[0] if matches else None
                selected.append(choice)
                if choice:
                    used.add(choice)

            extras = tuple(path for path in all_images if path not in used)
            creatures.append(
                Creature(
                    book=book_dir.name,
                    slug=creature_dir.name,
                    name=title_from_slug(creature_dir.name),
                    directory=creature_dir,
                    images=tuple(selected),  # type: ignore[arg-type]
                    extras=extras,
                )
            )
    return creatures


def scan_books() -> list[str]:
    if not GENERATED.exists():
        return []
    return sorted(
        path.name
        for path in GENERATED.iterdir()
        if path.is_dir() and path.name.startswith("Bestiary ")
    )


def ensure_thumbnail(path: Path) -> Path:
    THUMBS.mkdir(parents=True, exist_ok=True)
    out = thumb_path(path)
    if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
        return out

    tmp = out.with_suffix(".tmp.png")
    try:
        subprocess.run(
            ["sips", "-s", "format", "png", "-Z", "220", str(path), "--out", str(tmp)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tmp.replace(out)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        return path
    return out


def ensure_all_thumbnails(creatures: list[Creature]) -> None:
    for creature in creatures:
        for image in [*creature.images, *creature.extras]:
            if image:
                ensure_thumbnail(image)


def response(
    start_response,
    status: str,
    body: bytes,
    content_type: str,
    extra_headers: list[tuple[str, str]] | None = None,
) -> list[bytes]:
    headers = [("Content-Type", content_type), ("Content-Length", str(len(body)))]
    if extra_headers:
        headers.extend(extra_headers)
    start_response(status, headers)
    return [body]


def safe_repo_path(encoded: str) -> Path | None:
    decoded = urllib.parse.unquote(encoded)
    normalized = posixpath.normpath(decoded).lstrip("/")
    path = (ROOT / normalized).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError:
        return None
    return path


def serve_file(start_response, path: Path) -> list[bytes]:
    if not path.exists() or not path.is_file():
        return response(start_response, "404 Not Found", b"Not found", "text/plain; charset=utf-8")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return response(start_response, "200 OK", path.read_bytes(), content_type)


def first_value(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key, [])
    return values[0] if values else ""


def page_href(path: str, book: str, page: int) -> str:
    return path + "?" + urllib.parse.urlencode({"book": book, "page": page})


def render_scanned_page(query_string: str) -> bytes:
    params = urllib.parse.parse_qs(query_string, keep_blank_values=True)
    books = scan_books()
    creatures = scan_creatures()
    requested_book = first_value(params, "book")
    selected_book = requested_book if requested_book in books else (books[0] if books else "")

    try:
        requested_page = int(first_value(params, "page") or "1")
    except ValueError:
        requested_page = 1

    filtered = [creature for creature in creatures if creature.book == selected_book] if selected_book else creatures
    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(requested_page, 1), total_pages)
    start = (page - 1) * PAGE_SIZE
    page_creatures = filtered[start : start + PAGE_SIZE]

    return render_page(
        page_creatures,
        datetime.now().astimezone(),
        books,
        selected_book,
        page,
        total_pages,
        len(filtered),
    )


def render_page(
    creatures: list[Creature],
    scanned_at: datetime,
    books: list[str],
    selected_book: str,
    page: int,
    total_pages: int,
    total_creatures: int,
) -> bytes:
    rows = []
    total_images = 0
    for creature in creatures:
        cells = [
            f"<th><span>{html.escape(creature.name)}</span><small>{html.escape(creature.book)}</small></th>"
        ]
        for lane, image in zip((label for label, _ in LANE_PATTERNS), creature.images):
            if image:
                total_images += 1
                cells.append(render_image_cell(lane, image))
            else:
                cells.append(f'<td class="empty"><span>{html.escape(lane)}</span><em>missing</em></td>')
        if creature.extras:
            extras = " ".join(
                f'<button type="button" data-full="{html.escape(image_url(path))}" '
                f'data-title="{html.escape(creature.name + " / " + path.name)}">{html.escape(path.name)}</button>'
                for path in creature.extras
            )
            cells.append(f'<td class="extras">{extras}</td>')
        else:
            cells.append('<td class="extras muted">none</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    if not rows:
        rows.append('<tr><td class="emptyState" colspan="6">No generated images found for this book.</td></tr>')

    book_options = "\n".join(
        f'<option value="{html.escape(book)}"{" selected" if book == selected_book else ""}>{html.escape(book)}</option>'
        for book in books
    )
    first_item = ((page - 1) * PAGE_SIZE + 1) if total_creatures else 0
    last_item = min(page * PAGE_SIZE, total_creatures)
    page_summary = f"{first_item}-{last_item} of {total_creatures}" if total_creatures else "0 of 0"
    prev_href = html.escape(page_href("/", selected_book, page - 1))
    next_href = html.escape(page_href("/", selected_book, page + 1))
    refresh_href = html.escape(page_href("/refresh", selected_book, page))
    prev_class = "pageButton" if page > 1 else "pageButton disabled"
    next_class = "pageButton" if page < total_pages else "pageButton disabled"
    scanned_label = html.escape(scanned_at.strftime("%Y-%m-%d %H:%M:%S %Z"))
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KMQDB Generated Creature Images</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #101214;
      --panel: #171b1f;
      --line: #2c333a;
      --text: #f2f5f7;
      --muted: #a9b2ba;
      --accent: #8fc7ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
    header {{ position: sticky; top: 0; z-index: 2; background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); padding: 14px 18px; }}
    .headerRow {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; }}
    h1 {{ margin: 0; font-size: 18px; font-weight: 650; }}
    header p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
    .scanTime {{ display: block; margin-top: 3px; color: var(--muted); font-size: 12px; }}
    .controls {{ display: flex; align-items: end; justify-content: flex-end; flex-wrap: wrap; gap: 10px; }}
    .field {{ display: grid; gap: 4px; }}
    .field label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; }}
    select {{ min-width: 160px; border: 1px solid var(--line); color: var(--text); background: #20262c; border-radius: 6px; padding: 7px 9px; font: inherit; }}
    .refresh, .pageButton {{ border: 1px solid var(--line); color: var(--text); background: #20262c; border-radius: 6px; padding: 8px 11px; cursor: pointer; font: inherit; text-decoration: none; line-height: 1.2; }}
    .refresh:hover, .pageButton:hover {{ border-color: var(--accent); color: var(--accent); }}
    .disabled {{ opacity: .42; pointer-events: none; }}
    .pageStatus {{ color: var(--muted); font-size: 12px; min-width: 96px; text-align: center; }}
    main {{ padding: 18px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; background: var(--panel); border: 1px solid var(--line); }}
    col.name {{ width: 180px; }}
    col.image {{ width: 170px; }}
    col.extras {{ width: auto; }}
    th, td {{ border-bottom: 1px solid var(--line); border-right: 1px solid var(--line); padding: 10px; vertical-align: top; }}
    thead th {{ position: sticky; top: 62px; z-index: 1; background: #20262c; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    tbody th {{ text-align: left; font-size: 15px; font-weight: 650; }}
    tbody th small {{ display: block; margin-top: 4px; color: var(--muted); font-size: 12px; font-weight: 500; }}
    figure {{ margin: 0; }}
    .thumb {{ width: 150px; height: 112px; padding: 0; border: 1px solid var(--line); background: #0b0d0f; cursor: zoom-in; display: grid; place-items: center; overflow: hidden; }}
    .thumb img {{ max-width: 150px; max-height: 112px; display: block; }}
    figcaption {{ margin-top: 6px; color: var(--muted); font-size: 11px; line-height: 1.25; word-break: break-word; }}
    .empty {{ color: var(--muted); text-align: center; }}
    .emptyState {{ color: var(--muted); text-align: center; padding: 34px; }}
    .empty span {{ display: block; font-size: 12px; margin-bottom: 8px; }}
    .empty em {{ font-size: 13px; }}
    .extras {{ font-size: 12px; }}
    .extras button {{ margin: 0 6px 6px 0; border: 1px solid var(--line); color: var(--accent); background: #11161b; padding: 5px 7px; border-radius: 6px; cursor: zoom-in; max-width: 240px; overflow-wrap: anywhere; }}
    .muted {{ color: var(--muted); }}
    #viewer {{ display: none; position: fixed; inset: 0; z-index: 10; background: rgba(0,0,0,.86); padding: 28px; }}
    #viewer.open {{ display: grid; grid-template-rows: auto 1fr; gap: 12px; }}
    #viewerBar {{ display: flex; align-items: center; gap: 12px; color: white; }}
    #viewerTitle {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    #close {{ border: 1px solid rgba(255,255,255,.35); background: rgba(255,255,255,.12); color: white; border-radius: 6px; padding: 7px 10px; cursor: pointer; }}
    #viewer img {{ place-self: center; max-width: calc(100vw - 56px); max-height: calc(100vh - 92px); object-fit: contain; box-shadow: 0 12px 60px rgba(0,0,0,.55); }}
  </style>
</head>
<body>
  <header>
    <div class="headerRow">
      <div>
        <h1>KMQDB Generated Creature Images</h1>
        <p>{total_creatures} creatures in {html.escape(selected_book or "all books")}, showing {page_summary}. Click any thumbnail or extra image name to enlarge.</p>
        <span class="scanTime">Last scan: {scanned_label}</span>
      </div>
      <div class="controls">
        <form class="field" method="get" action="/">
          <label for="book">Book</label>
          <input type="hidden" name="page" value="1">
          <select id="book" name="book" onchange="this.form.submit()">
            {book_options}
          </select>
        </form>
        <a class="{prev_class}" href="{prev_href}" aria-label="Previous page">Prev</a>
        <span class="pageStatus">Page {page} / {total_pages}</span>
        <a class="{next_class}" href="{next_href}" aria-label="Next page">Next</a>
        <a class="refresh" href="{refresh_href}">Refresh</a>
      </div>
    </div>
  </header>
  <main>
    <table>
      <colgroup>
        <col class="name">
        <col class="image"><col class="image"><col class="image"><col class="image">
        <col class="extras">
      </colgroup>
      <thead>
        <tr><th>Creature</th><th>Bestiary Light</th><th>Silhouette Light</th><th>Bestiary Dark</th><th>CRPG Dark</th><th>Extras</th></tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </main>
  <div id="viewer" role="dialog" aria-modal="true" aria-label="Full size image viewer">
    <div id="viewerBar"><div id="viewerTitle"></div><button id="close" type="button">Close</button></div>
    <img id="viewerImg" alt="">
  </div>
  <script>
    const viewer = document.getElementById('viewer');
    const viewerImg = document.getElementById('viewerImg');
    const viewerTitle = document.getElementById('viewerTitle');
    function openViewer(url, title) {{
      viewerImg.src = url;
      viewerImg.alt = title;
      viewerTitle.textContent = title;
      viewer.classList.add('open');
    }}
    function closeViewer() {{
      viewer.classList.remove('open');
      viewerImg.removeAttribute('src');
    }}
    document.querySelectorAll('[data-full]').forEach((target) => {{
      target.addEventListener('click', (event) => {{
        event.preventDefault();
        event.stopPropagation();
        openViewer(target.dataset.full, target.dataset.title || target.dataset.full);
      }});
    }});
    viewer.addEventListener('click', (event) => {{
      if (event.target === viewer || event.target.id === 'close') closeViewer();
    }});
    document.addEventListener('keydown', (event) => {{
      if (event.key === 'Escape') closeViewer();
    }});
  </script>
</body>
</html>"""
    return body.encode("utf-8")


def render_image_cell(lane: str, image: Path) -> str:
    name = image.name
    return f"""<td>
      <figure>
        <button class="thumb" type="button" data-full="{html.escape(image_url(image))}" data-title="{html.escape(name)}">
          <img src="{html.escape(thumb_url(image))}" alt="{html.escape(name)}">
        </button>
        <figcaption>{html.escape(name)}</figcaption>
      </figure>
    </td>"""


def make_app():
    def app(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        query_string = environ.get("QUERY_STRING", "")
        if path in {"/", "/refresh"}:
            return response(
                start_response,
                "200 OK",
                render_scanned_page(query_string),
                "text/html; charset=utf-8",
                [("Cache-Control", "no-store")],
            )
        if path.startswith("/asset/"):
            image = safe_repo_path(path.removeprefix("/asset/"))
            if not image or image.suffix.lower() not in IMAGE_SUFFIXES:
                return response(start_response, "404 Not Found", b"Not found", "text/plain; charset=utf-8")
            return serve_file(start_response, image)
        if path.startswith("/thumb/"):
            image = safe_repo_path(path.removeprefix("/thumb/"))
            if not image or image.suffix.lower() not in IMAGE_SUFFIXES:
                return response(start_response, "404 Not Found", b"Not found", "text/plain; charset=utf-8")
            return serve_file(start_response, ensure_thumbnail(image))
        return response(start_response, "404 Not Found", b"Not found", "text/plain; charset=utf-8")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve generated creature images locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app = make_app()
    with make_server(args.host, args.port, app) as server:
        print(f"Serving generated creature images at http://{args.host}:{args.port}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
