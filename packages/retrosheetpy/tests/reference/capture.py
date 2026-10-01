"""Regenerate the captured Chadwick reference output (needs ``cwevent`` on PATH).

Run from the repository root:
    uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/capture.py
"""

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from chadwick_reference import FIELDS, ChadwickReference  # noqa: E402

FIXTURES = HERE.parent / "fixtures" / "events"
OUT = HERE / "chadwick"


def main() -> None:
    ref = ChadwickReference.find()
    if ref is None:
        sys.exit("cwevent not found on PATH")
    OUT.mkdir(exist_ok=True)
    manifest: dict[str, object] = {"chadwick_version": ref.version, "fields": FIELDS, "files": {}}
    for evt in sorted(FIXTURES.glob("*.evt")):
        text = evt.read_bytes()
        year = int(re.search(rb"^id,[A-Z0-9]{3}(\d{4})", text, re.M).group(1))  # type: ignore[union-attr]
        rows = ref.events(evt, year)
        target = OUT / f"{evt.stem}.csv"
        with open(target, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        manifest["files"][evt.name] = {  # type: ignore[index]
            "year": year,
            "rows": len(rows),
            "fixture_sha256": hashlib.sha256(text).hexdigest(),
        }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"captured {len(manifest['files'])} files with Chadwick {ref.version}")  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
