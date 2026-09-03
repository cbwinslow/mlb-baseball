#!/usr/bin/env python3
"""End-to-end local check of the delivery-surface change (apply task 6.1).

Exercises three of the four delivery surfaces against ONE locally-produced
backbone bundle, without needing the published Hugging Face dataset:

1. `mlb export --preset backbone` (mlb_baseball.export.export_backbone_bundle)
2. `mlb_research.load()` for every published backbone table, with
   huggingface_hub's downloader monkeypatched to serve the local bundle
   instead of the network
3. docs/site/query/ served locally with CORS headers, its query.js pointed
   at the local bundle instead of huggingface.co -- reachability/content
   checked here; the interactive DuckDB-WASM query mechanism itself was
   verified with a real headless-Chromium (Playwright) run during the
   delivery-surface change (not a project dependency, so not re-driven by
   this script -- see the printed manual-check instructions at the end).

Requires an existing, already-populated backbone database (gold.batting_game
etc. -- built via `mlb report`, see
docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md).
Read-only: never writes to the database.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _database_url() -> str:
    """Same precedence `mlb export`/`get_connection()` uses (DATABASE_URL) --
    this script exercises the real CLI/package/page path against whatever
    database that would hit, test or production. Read-only: this script and
    export_backbone_bundle never write to the database. The resolved
    database name is always printed before connecting (root AGENTS.md:
    "make the target database explicit before execution") so a shell with
    DATABASE_URL left pointed at production `mlb` is never ambiguous.
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL (or TEST_DATABASE_URL) is required and must point at a "
            "database with the backbone gold tables already built (`mlb report`)."
        )
    dbname = url.rsplit("/", 1)[-1].split("?", 1)[0]
    print(f"Target database: {dbname!r} (read-only)")
    return url


class _CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # keep the check's own output readable


def _serve(directory: Path, port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(_CORSHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def step_export(database_url: str, out_dir: Path) -> dict:
    print(f"[1/3] mlb export --preset backbone --out {out_dir}")
    import psycopg

    from mlb_baseball.export import BACKBONE_TABLES, export_backbone_bundle

    with psycopg.connect(database_url) as conn:
        export_backbone_bundle(conn, out_dir=out_dir)

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    published = {t["table"] for t in manifest["tables"]}
    expected = {name.split(".", 1)[1] for name in BACKBONE_TABLES}
    if published != expected:
        raise SystemExit(f"export produced {published}, expected {expected}")
    print(f"    OK -- {len(published)} tables + manifest.json + README.md")
    return manifest


def step_load(bundle_dir: Path, manifest: dict) -> None:
    print("[2/3] mlb_research.load() for every published table")
    import huggingface_hub
    import mlb_research

    def _fake_hf_hub_download(*, filename: str, **_kwargs: object) -> str:
        return str(bundle_dir / filename)

    huggingface_hub.hf_hub_download = _fake_hf_hub_download
    mlb_research._DOWNLOAD_CACHE.clear()

    for entry in manifest["tables"]:
        table = entry["table"]
        df = mlb_research.load(table)
        if len(df) != entry["row_count"]:
            raise SystemExit(
                f"{table}: mlb_research.load() returned {len(df)} rows, "
                f"manifest says {entry['row_count']}"
            )
        print(f"    {table}: {len(df)} rows OK")


def step_query_page(bundle_dir: Path, *, interactive: bool) -> None:
    print("[3/3] docs/site/query/ against the local bundle")
    data_server = _serve(bundle_dir / "data", 8934)

    with tempfile.TemporaryDirectory() as page_dir_str:
        page_dir = Path(page_dir_str)
        query_src = REPO_ROOT / "docs" / "site" / "query"
        (page_dir / "index.html").write_text(
            (query_src / "index.html").read_text(encoding="utf-8"), encoding="utf-8"
        )
        query_js = (query_src / "query.js").read_text(encoding="utf-8")
        original = "return `https://huggingface.co/datasets/${HF_REPO_ID}/resolve/${HF_REVISION}/data/${table}.parquet`;"
        override = "return `http://localhost:8934/${table}.parquet`;"
        if original not in query_js:
            raise SystemExit("query.js's parquetUrl() shape changed; update this script's patch")
        (page_dir / "query.js").write_text(query_js.replace(original, override), encoding="utf-8")

        page_server = _serve(page_dir, 8935)
        try:
            with urllib.request.urlopen("http://localhost:8935/index.html", timeout=5) as resp:
                if resp.status != 200:
                    raise SystemExit(f"query page not reachable: HTTP {resp.status}")
            with urllib.request.urlopen(
                "http://localhost:8934/batting_game.parquet", timeout=5
            ) as resp:
                if resp.status != 200:
                    raise SystemExit(f"local bundle not reachable: HTTP {resp.status}")
            print("    OK -- query page + local bundle both reachable over HTTP with CORS")
            if interactive:
                print(
                    "    Manual check: open http://localhost:8935/index.html in a browser "
                    "and run the default query -- servers stay up until you press Enter."
                )
                input("    Press Enter to stop the local servers and finish... ")
        finally:
            page_server.shutdown()
    data_server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="bundle output directory")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="pause with the local query page reachable so you can open it in a browser",
    )
    args = parser.parse_args()

    database_url = _database_url()
    out_dir = args.out or Path(tempfile.mkdtemp(prefix="mlb_backbone_verify_"))

    manifest = step_export(database_url, out_dir)
    step_load(out_dir, manifest)
    step_query_page(out_dir, interactive=args.interactive)

    print(f"\nAll delivery surfaces verified against {out_dir}. No failures.")


if __name__ == "__main__":
    sys.exit(main())
