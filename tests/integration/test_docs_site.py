"""The MkDocs Material docs site builds, carries the query page through verbatim,
and does not leak the internal schema onto the public data-dictionary page
(mkdocs-docs-site change).

Lives in ``tests/integration/`` because it shells out to ``mkdocs build`` and
reads the generated tree. It is run by the ``docs`` job in ``ci.yml`` (the only
job with the ``docs`` extra installed); the Postgres-backed integration shards
collect it and skip via the ``mkdocs``-missing guard below.

``mkdocs build --strict`` is exercised in that job too; this test adds the
guarantees a strict build alone does not give:

* the hand-written DuckDB-WASM query page is published byte-for-byte, and
* the data-dictionary snippet stays bounded to section 3 of
  ``docs/DATA_DICTIONARY.md`` -- a removed ``[end:backbone]`` marker makes
  ``pymdownx.snippets`` read to end of file, which a strict build does not catch.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_SRC = REPO_ROOT / "docs" / "site-src"

pytestmark = pytest.mark.skipif(
    shutil.which("mkdocs") is None and not (REPO_ROOT / ".venv/bin/mkdocs").exists(),
    reason="mkdocs not installed (docs extra); covered by the CI docs job",
)


@pytest.fixture(scope="module")
def built_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("mkdocs-site")
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"mkdocs build --strict failed:\n{result.stderr}"
    return out


def test_query_page_is_published_byte_for_byte(built_site: Path) -> None:
    for name in ("index.html", "query.js"):
        src = (SITE_SRC / "query" / name).read_bytes()
        published = (built_site / "query" / name).read_bytes()
        assert published == src, (
            f"query/{name} differs from its source -- mkdocs is transforming it "
            "instead of copying it through as a static asset"
        )

    # Belt and braces: the published page must still be the raw hand-written
    # document, not something wrapped in the Material page template.
    index = (built_site / "query" / "index.html").read_text()
    assert index.lstrip().startswith("<!doctype html>")
    assert "md-header" not in index, "Material nav chrome was injected into the query page"
    assert (
        "cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm"
        in (built_site / "query" / "query.js").read_text()
    )


def test_data_dictionary_page_contains_the_backbone_tables(built_site: Path) -> None:
    html = (built_site / "data-dictionary" / "index.html").read_text()
    for table in (
        "gold.batting_game",
        "gold.batting_season",
        "gold.pitching_season",
        "gold.batting_career",
    ):
        assert table in html, f"{table} missing from the data-dictionary page"


def test_data_dictionary_page_does_not_leak_the_internal_schema(built_site: Path) -> None:
    """A dropped ``[end:backbone]`` marker would splice sections 4-6 (raw / serve /
    core) of DATA_DICTIONARY.md onto the public page. Guard the boundary."""
    html = (built_site / "data-dictionary" / "index.html").read_text()
    for internal in (
        "raw.statcast_pitch",
        "Raw Data Landing Tables",
        "Serving Marts",
        "Core Relational Tables",
    ):
        assert internal not in html, (
            f"internal-schema marker {internal!r} leaked onto the public "
            "data-dictionary page -- check the [start:backbone]/[end:backbone] "
            "markers in docs/DATA_DICTIONARY.md"
        )


def test_grain_ladder_diagram_and_formula_math_render(built_site: Path) -> None:
    ladder = (built_site / "grain-ladder" / "index.html").read_text()
    # The diagram is a hand-authored inline SVG (no mermaid/JS runtime): it must
    # ship in the page markup with its grain labels intact.
    assert "<svg" in ladder, "grain-ladder diagram SVG missing"
    for label in ("Game", "Season, per stint", "Season, combined", "Team season", "Career"):
        assert label in ladder, f"grain-ladder diagram is missing the {label!r} node"

    formulas = (built_site / "formulas" / "index.html").read_text()
    assert 'class="arithmatex"' in formulas, "formula math not wrapped by arithmatex"
