"""Declared table schemas for migrated sources, stored as JSON next to this module.

``schemas/<source>.json`` maps table -> ``{"columns": {name: kind}, "key": [...]}``. The
file is the declaration (reviewed, committed); ``infer.py`` only proposes it. A column the
file does not list is landed as text and reported, never dropped.
"""

import json
from pathlib import Path

from mlb_baseball.market_store import Column, MarketTable

_DIR = Path(__file__).parent / "schemas"


def load(source: str, *, prefix: tuple[str, str] | None = None) -> dict[str, MarketTable]:
    """``{table name: spec}`` for ``source``. ``prefix=("raw.lahman_", "raw.x_lahman_")``
    renames tables (parity and rehearsal runs use scratch names)."""
    raw = json.loads((_DIR / f"{source}.json").read_text())
    specs = {}
    for table, body in raw.items():
        name = table.replace(*prefix) if prefix else table
        specs[table] = MarketTable(
            name=name,
            reject=name + "_reject",
            columns=tuple(Column(c, kind) for c, kind in body["columns"].items()),
            key=tuple(body.get("key", ())),
        )
    return specs


def write(source: str, tables: dict[str, dict]) -> Path:
    path = _DIR / f"{source}.json"
    path.write_text(json.dumps(tables, indent=1, sort_keys=False) + "\n")
    return path
