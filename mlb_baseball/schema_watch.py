"""Source schema drift check (openspec/changes/source-inventory, source-schema-drift).

A snapshot is `{name: type}`: field names and JSON types for an API response, or file
names for a publisher's file list. `check` fetches one sample per dataset, compares it
with the saved snapshot and reports added, removed and changed names. It never touches
the database. A source that cannot be reached is `unchecked`, never `unchanged`. A drift
stays reported on every run until it is accepted, so it cannot be missed once.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlb_baseball.manifest import DOWNLOADS_ROOT

logger = logging.getLogger(__name__)

SAMPLE_ROWS = 20  # rows merged from a list response so sparse fields are seen
MAX_DEPTH = 5
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    return "object"


def _walk(obj: dict, prefix: str, depth: int, out: dict[str, str]) -> None:
    for key, value in obj.items():
        name = f"{prefix}{key}"
        kind = _type_name(value)
        if out.get(name) in (None, "null"):
            out[name] = kind
        if isinstance(value, dict) and depth < MAX_DEPTH:
            _walk(value, f"{name}.", depth + 1, out)
        elif isinstance(value, list) and depth < MAX_DEPTH:
            for item in value[:SAMPLE_ROWS]:
                if isinstance(item, dict):
                    _walk(item, f"{name}[].", depth + 1, out)


def fields_of(sample: Any) -> dict[str, str]:
    """Field name -> JSON type for a response (dict, or list of dicts merged)."""
    out: dict[str, str] = {}
    if isinstance(sample, dict):
        _walk(sample, "", 1, out)
    elif isinstance(sample, list):
        for row in sample[:SAMPLE_ROWS]:
            if isinstance(row, dict):
                _walk(row, "", 1, out)
    return out


@dataclass(frozen=True)
class Drift:
    added: dict[str, str] = field(default_factory=dict)
    removed: dict[str, str] = field(default_factory=dict)
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def any(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def compare(old: dict[str, str], new: dict[str, str]) -> Drift:
    """A null in either sample says nothing about the type, so it is never a change."""
    changed = {
        k: (old[k], new[k])
        for k in old.keys() & new.keys()
        if old[k] != new[k] and "null" not in (old[k], new[k])
    }
    return Drift(
        added={k: new[k] for k in new.keys() - old.keys()},
        removed={k: old[k] for k in old.keys() - new.keys()},
        changed=changed,
    )


class SnapshotStore:
    """One small JSON file per dataset: `<root>/<source>/<dataset>.json`."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _path(self, source: str, dataset: str) -> Path:
        for part in (source, dataset):
            if not _SAFE.match(part) or part.startswith("."):
                raise ValueError(f"unsafe snapshot name: {part!r}")
        return self.root / source / f"{dataset}.json"

    def load(self, source: str, dataset: str) -> dict[str, str] | None:
        path = self._path(source, dataset)
        return json.loads(path.read_text()) if path.exists() else None

    def save(self, source: str, dataset: str, snapshot: dict[str, str]) -> None:
        path = self._path(source, dataset)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")


@dataclass(frozen=True)
class Dataset:
    """`fetch` returns a sample: a response (dict/list) or a `{file name: type}` map."""

    source: str
    name: str
    fetch: Callable[[], Any]
    kind: str = "fields"  # "fields": fields_of(sample); "names": sample is already a snapshot


@dataclass(frozen=True)
class Finding:
    source: str
    dataset: str
    status: str  # new | unchanged | drift | unchecked
    drift: Drift = field(default_factory=Drift)
    error: str = ""


def _fetch_with_retries(dataset: Dataset, attempts: int, pause: float) -> Any:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return dataset.fetch()
        except Exception as exc:  # any failure to read the source means unchecked
            last = exc
            logger.warning(
                "schema-watch %s/%s attempt %d: %s", dataset.source, dataset.name, attempt, exc
            )
            if attempt < attempts:
                time.sleep(pause)
    assert last is not None
    raise last


def check(
    datasets: list[Dataset],
    store: SnapshotStore,
    *,
    accept: bool = False,
    attempts: int = 3,
    pause: float = 5.0,
) -> list[Finding]:
    findings = []
    for ds in datasets:
        try:
            sample = _fetch_with_retries(ds, attempts, pause)
        except Exception as exc:
            findings.append(Finding(ds.source, ds.name, "unchecked", error=str(exc)))
            continue
        new = dict(sample) if ds.kind == "names" else fields_of(sample)
        old = store.load(ds.source, ds.name)
        if old is None:
            store.save(ds.source, ds.name, new)
            findings.append(Finding(ds.source, ds.name, "new"))
            continue
        drift = compare(old, new)
        if not drift.any:
            findings.append(Finding(ds.source, ds.name, "unchanged"))
            continue
        if accept:
            store.save(ds.source, ds.name, new)
        findings.append(Finding(ds.source, ds.name, "drift", drift))
    return findings


SNAPSHOT_DIR = DOWNLOADS_ROOT / "schema_snapshots"
EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_UNCHECKED = 2


def record(conn, findings: list[Finding]) -> None:
    """Replace the latest result per dataset in meta.schema_finding. Writes nothing to raw."""
    with conn.cursor() as cur:
        for f in findings:
            cur.execute(
                """
                INSERT INTO meta.schema_finding
                    (source, dataset, status, added, removed, changed, error, checked_at)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, now())
                ON CONFLICT (source, dataset) DO UPDATE SET
                    status = EXCLUDED.status, added = EXCLUDED.added,
                    removed = EXCLUDED.removed, changed = EXCLUDED.changed,
                    error = EXCLUDED.error, checked_at = EXCLUDED.checked_at
                WHERE meta.schema_finding.status <> 'drift' OR EXCLUDED.status <> 'unchecked'
                """,
                (
                    f.source,
                    f.dataset,
                    f.status,
                    json.dumps(f.drift.added),
                    json.dumps(f.drift.removed),
                    json.dumps({k: list(v) for k, v in f.drift.changed.items()}),
                    f.error,
                ),
            )
    conn.commit()


def exit_code(findings: list[Finding]) -> int:
    """1 when anything drifted, else 2 when anything could not be checked, else 0."""
    if any(f.status == "drift" for f in findings):
        return EXIT_DRIFT
    if any(f.status == "unchecked" for f in findings):
        return EXIT_UNCHECKED
    return EXIT_OK


def to_dict(f: Finding) -> dict:
    return {
        "source": f.source,
        "dataset": f.dataset,
        "status": f.status,
        "added": f.drift.added,
        "removed": f.drift.removed,
        "changed": {k: list(v) for k, v in f.drift.changed.items()},
        "error": f.error,
    }


def render(findings: list[Finding]) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    lines = ["schema-watch: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))]
    for f in findings:
        if f.status == "drift":
            lines.append(f"DRIFT {f.source}/{f.dataset}")
            lines += [f"  added {k}: {v}" for k, v in sorted(f.drift.added.items())]
            lines += [f"  removed {k}: {v}" for k, v in sorted(f.drift.removed.items())]
            lines += [f"  changed {k}: {a} -> {b}" for k, (a, b) in sorted(f.drift.changed.items())]
        elif f.status == "unchecked":
            lines.append(f"UNCHECKED {f.source}/{f.dataset}: {f.error}")
    return "\n".join(lines)


def run(
    source: str | None = None,
    *,
    accept: bool = False,
    as_json: bool = False,
    tolerate_unchecked: bool = False,
    store_dir: Path | str = SNAPSHOT_DIR,
    datasets: list[Dataset] | None = None,
) -> int:
    """Sample every dataset (or one source), compare, record, print; return the exit code."""
    from mlb_baseball.db import get_connection

    if datasets is None:
        from mlb_baseball.schema_sources import all_datasets

        datasets = all_datasets()
    if source:
        datasets = [d for d in datasets if d.source == source]
        if not datasets:
            print(f"schema-watch: no datasets for source {source!r}")
            return EXIT_UNCHECKED
    findings = check(datasets, SnapshotStore(store_dir), accept=accept)
    with get_connection() as conn:
        record(conn, findings)
    if as_json:
        print(json.dumps([to_dict(f) for f in findings], indent=1))
    else:
        print(render(findings))
    code = exit_code(findings)
    return EXIT_OK if tolerate_unchecked and code == EXIT_UNCHECKED else code
