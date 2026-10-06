"""docs/sources/ must stay complete: every source the coverage registry knows has a page
that names it, and every page names at least one registry source (no orphan page)."""

from pathlib import Path

from mlb_baseball.coverage import DATASETS

PAGES = sorted(Path("docs/sources").glob("*.md"))


def _text(path: Path) -> str:
    return path.read_text()


def test_every_registry_source_is_named_on_a_source_page():
    pages = "\n".join(_text(p) for p in PAGES)
    missing = sorted(
        {
            d.source
            for d in DATASETS
            if f"`{d.source}`" not in pages and f"--source {d.source}" not in pages
        }
    )
    assert not missing, f"no docs/sources page names these coverage sources: {missing}"


def test_every_source_page_names_a_coverage_source():
    sources = {d.source for d in DATASETS}
    orphans = [
        p.name
        for p in PAGES
        if not any(f"--source {s}" in _text(p) or f"`{s}`" in _text(p) for s in sources)
    ]
    assert not orphans, f"source pages that name no coverage source: {orphans}"
