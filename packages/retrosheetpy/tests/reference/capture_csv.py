"""Capture the Retrosheet ``plays.csv`` rows for the fixture games (needs network).

Run from the repository root:
    uv run --package retrosheetpy python \
        packages/retrosheetpy/tests/reference/capture_csv.py CACHE_DIR
Downloads each season's official ``<year>csvs.zip`` through ``retrosheetpy.Client``
and keeps only the rows of the games that exist in ``tests/fixtures/events``.
"""

import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from retrosheetpy import Client, Product, resolve

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "fixtures" / "events"
OUT = HERE / "retrosheet_csv"


def main(cache_dir: str) -> None:
    client = Client(cache_dir)
    OUT.mkdir(exist_ok=True)
    manifest: dict[str, object] = {"files": {}}
    for evt in sorted(FIXTURES.glob("*.evt")):
        match = re.search(rb"^id,([A-Z0-9]{3}(\d{4})\d{4}\d)", evt.read_bytes(), re.M)
        assert match, evt
        game_id, year = match.group(1).decode(), int(match.group(2))
        art = client.download(resolve(Product.YEARLY_CSV, year))
        with zipfile.ZipFile(art.local_path) as zf:
            with zf.open(f"{year}plays.csv") as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
                rows = [r for r in reader if r["gid"] == game_id]
        status: dict[str, object] = {"game_id": game_id, "rows": len(rows)}
        if rows:
            with open(OUT / f"{evt.stem}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            status.update(source_url=art.source_url, source_sha256=art.sha256)
        manifest["files"][evt.name] = status  # type: ignore[index]
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["files"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
