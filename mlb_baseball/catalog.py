"""The per-metric YAML catalog: schema, loader, and `meta.metric` sync
(metric-catalog, ADR-291; see openspec/changes/metric-catalog/).

Every statistic/metric this project implements gets exactly one small,
schema-validated YAML file under `mlb_baseball/metrics/<name>.yaml` (see
`mlb_baseball/metrics/README.md` for the field-by-field schema doc, which
must stay in sync with `MetricEntry` below). This module:

- validates every entry (`load_all`) -- pydantic, not jsonschema: pydantic
  was already resolved transitively (sqlmesh's own dependency, a project
  dev-extra), so promoting it to a base dependency adds nothing new to
  `uv.lock`; `jsonschema` is not present anywhere in the lock today and
  would pull in several new packages (attrs, referencing, rpds-py, ...) for
  the same job.
- rebuilds PostgreSQL `meta.metric` from the validated entries (`load`) --
  same idempotent TRUNCATE + insert-in-one-transaction pattern as every
  other gold/meta loader in this project (see
  `conform.py::_build_team_aliases`).
- generates each entry's `source_permalink`: a version-pinned GitHub blob
  URL built from `formula`'s file path and the git commit the build ran
  against -- never hand-written in the YAML, never pointing at a moving
  branch (design.md Decision 7).
- renders the `visibility: public` subset as a Markdown docs page
  (`generate_docs_page`), wired to `mlb catalog docs`.

This is documentation-only tooling. It never computes, stores, or changes
any metric's actual value (see the change's spec, "This change does not
alter computed values").
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

import psycopg
import yaml
from pydantic import BaseModel, ValidationError, model_validator

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.sql import read_sql

METRICS_DIR = Path(__file__).resolve().parent / "metrics"

# Pinned to this project's own GitHub repository -- source_permalink always
# points back at cbwinslow/mlb-baseball, regardless of any fork/remote the
# build happens to run from.
_REPO_BLOB_BASE = "https://github.com/cbwinslow/mlb-baseball/blob"

# Sort order for the public docs page (design.md Decision 5): validated
# entries first, then implemented-untested, then published. negative-result
# and archived entries are internal-facing record-keeping, not something a
# public reader should see promoted above an actually-live metric, so they
# sort last if a `public` entry is ever tagged that way.
_STATUS_SORT_ORDER = {
    "validated": 0,
    "implemented-untested": 1,
    "published": 2,
    "negative-result": 3,
    "archived": 4,
}

Layer = Literal["gold", "feat", "model"]
Complexity = Literal["arithmetic", "complex"]
Implementation = Literal["sql", "sqlmesh", "python"]
Status = Literal["published", "validated", "implemented-untested", "negative-result", "archived"]
Visibility = Literal["public", "internal"]


class MetricEntry(BaseModel):
    """One `mlb_baseball/metrics/<name>.yaml` entry.

    Field meanings are documented, field-for-field, in
    `mlb_baseball/metrics/README.md` -- keep that file in sync with this
    model rather than duplicating the explanation here.
    """

    name: str
    definition: str
    formula: str
    citation: str
    data_source: str
    grain: str
    layer: Layer
    complexity: Complexity
    implementation: Implementation
    status: Status
    visibility: Visibility
    test_ref: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _validated_requires_test_ref(self) -> MetricEntry:
        if self.status == "validated" and not self.test_ref:
            raise ValueError(
                "status: validated requires test_ref naming the tie-out test "
                "(spec: 'validated SHALL NOT be set without a linked, "
                "currently-passing test')"
            )
        return self


class CatalogError(ValueError):
    """A metric YAML file failed schema validation.

    Always names the offending file and the specific missing/invalid
    field(s) -- never a bare pydantic stack trace (tasks.md 2.1/2.4).
    """


def _load_one(path: Path) -> MetricEntry:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CatalogError(f"{path}: not valid YAML -- {exc}") from exc
    if not isinstance(raw, dict):
        raise CatalogError(f"{path}: expected a YAML mapping of fields, got {type(raw).__name__}")
    try:
        return MetricEntry.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or '(entry)'}: {err['msg']}"
            for err in exc.errors()
        )
        raise CatalogError(f"{path}: invalid metric entry -- {problems}") from exc


def load_all(directory: Path = METRICS_DIR) -> list[MetricEntry]:
    """Read and validate every `*.yaml` metric entry under `directory`.

    Raises `CatalogError` naming the file and the specific missing/invalid
    field on the first entry that fails validation.
    """
    return [_load_one(path) for path in sorted(directory.glob("*.yaml"))]


def _git_commit_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parent,
    )
    return result.stdout.strip()


def _source_permalink(formula: str, commit_sha: str) -> str:
    """Build a version-pinned GitHub blob URL from `formula` + `commit_sha`.

    `formula` may carry a `::function_name` suffix (e.g.
    `mlb_baseball/model/framing.py::compute`) -- that suffix names a symbol
    inside the file, not a path segment, so it is stripped before building
    the URL: the permalink points at the file, never at a nonexistent path.
    """
    file_path = formula.split("::", 1)[0]
    return f"{_REPO_BLOB_BASE}/{commit_sha}/{file_path}"


def load(
    conn: psycopg.Connection,
    *,
    directory: Path = METRICS_DIR,
    commit_sha: str | None = None,
) -> int:
    """Validate every metric YAML and rebuild `meta.metric` from it.

    Idempotent full-rebuild (same pattern as every other gold/meta loader in
    this project -- see `conform.py::_build_team_aliases`): TRUNCATE
    `meta.metric`, then insert every validated entry, all in one transaction.
    Returns the resulting row count.

    `commit_sha` defaults to the real `git rev-parse HEAD` of this checkout;
    a caller may pass a fixed value (tests do, to assert the generated
    `source_permalink` embeds an exact, known sha rather than a moving one).
    """
    entries = load_all(directory)
    sha = commit_sha if commit_sha is not None else _git_commit_sha()
    upsert_sql = read_sql("meta_metric_upsert.sql")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("TRUNCATE meta.metric")
        for entry in entries:
            cur.execute(
                upsert_sql,
                {
                    "name": entry.name,
                    "definition": entry.definition,
                    "formula": entry.formula,
                    "citation": entry.citation,
                    "data_source": entry.data_source,
                    "grain": entry.grain,
                    "layer": entry.layer,
                    "complexity": entry.complexity,
                    "implementation": entry.implementation,
                    "status": entry.status,
                    "visibility": entry.visibility,
                    "test_ref": entry.test_ref,
                    "notes": entry.notes,
                    "source_permalink": _source_permalink(entry.formula, sha),
                },
            )
        cur.execute("SELECT count(*) FROM meta.metric")
        (count,) = fetch_one(cur)
    return count


def build() -> int:
    """`mlb catalog build` entry point: opens and owns its own connection."""
    with get_connection() as conn:
        return load(conn)


def generate_docs_page(conn: psycopg.Connection) -> str:
    """Render every `visibility: public` `meta.metric` row as Markdown.

    Sorted `validated` before `implemented-untested` before `published`
    (design.md Decision 5). The public docs page and `meta.metric` are two
    views of the same source of truth -- this function only reads
    `meta.metric`, it never re-reads the YAML directly, so the two views
    cannot drift apart from each other (they can only both drift from the
    YAML together, which `mlb catalog build` fixes).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, definition, citation, data_source, grain, layer, "
            "status, source_permalink, notes "
            "FROM meta.metric WHERE visibility = 'public'"
        )
        rows = cur.fetchall()
    rows.sort(key=lambda row: _STATUS_SORT_ORDER.get(row[6], len(_STATUS_SORT_ORDER)))

    lines = [
        "# Metric catalog",
        "",
        "Every publicly-visible statistic this project implements, generated "
        "from `meta.metric` (`mlb catalog docs`) -- see "
        "`openspec/changes/metric-catalog/` for how this catalog is built and "
        "maintained. An internal (non-public) entry never appears here.",
        "",
    ]
    for name, definition, citation, data_source, grain, layer, status, permalink, notes in rows:
        lines.append(f"## {name}")
        lines.append("")
        lines.append(definition.strip())
        lines.append("")
        lines.append(f"- **Status:** {status}")
        lines.append(f"- **Citation:** {citation}")
        lines.append(f"- **Data source:** {data_source}")
        lines.append(f"- **Grain:** {grain}")
        lines.append(f"- **Layer:** {layer}")
        lines.append(f"- **Source:** [{permalink}]({permalink})")
        if notes:
            lines.append(f"- **Notes:** {notes.strip()}")
        lines.append("")
    return "\n".join(lines)


def write_docs_page(conn: psycopg.Connection, path: Path) -> Path:
    """Generate the public docs page and write it to `path`. Returns `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_docs_page(conn), encoding="utf-8")
    return path
