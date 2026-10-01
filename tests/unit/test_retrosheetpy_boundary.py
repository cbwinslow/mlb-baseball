"""Boundary contract: how mlb_baseball could consume retrosheetpy (task 6.2).

The consumer side only needs (a) Artifact metadata for provenance and (b) a
stream of plain parsed records. This test plays the consumer using the public
API alone, and pins that neither package imports the other.
"""

import dataclasses
import re
from datetime import UTC, datetime
from pathlib import Path

import retrosheetpy
from retrosheetpy import Artifact, PlayRecord, Product, read_event_file

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "packages/retrosheetpy/tests/fixtures/events/regular_2007.evt"


def _provenance_row(artifact: Artifact) -> dict[str, object]:
    """What a raw-layer loader would store beside rows: source identity + hash."""
    return {
        "source_url": artifact.source_url,
        "sha256": artifact.sha256,
        "size": artifact.size,
        "retrieved_at": artifact.retrieved_at,
    }


def test_consumer_can_build_rows_from_artifact_and_record_stream():
    artifact = Artifact(
        source_url="https://www.retrosheet.org/events/2000seve.zip",
        product=Product.EVENTS_DECADE,
        season=None,
        group="2000s",
        local_path=FIXTURE,
        sha256="0" * 64,
        size=FIXTURE.stat().st_size,
        retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    # Metadata survives a JSON round trip, so it can be stored as text.
    assert Artifact.from_json(artifact.to_json()) == artifact
    provenance = _provenance_row(artifact)

    rows = [
        {
            **dataclasses.asdict(rec),  # records are plain frozen dataclasses
            "record_type": type(rec).__name__,
            "artifact_sha256": provenance["sha256"],
        }
        for rec in read_event_file(artifact.local_path)
    ]
    assert rows, "fixture produced no records"
    plays = [r for r in rows if r["record_type"] == "PlayRecord"]
    assert plays
    # Every row traces back to a source file, line, and the artifact hash.
    assert all(r["source"] and r["line_no"] > 0 for r in rows)
    assert {r["artifact_sha256"] for r in rows} == {"0" * 64}
    assert all(
        isinstance(rec, PlayRecord) for rec in read_event_file(FIXTURE) if "event" in dir(rec)
    )


def test_retrosheetpy_does_not_import_mlb_baseball():
    pattern = re.compile(r"^\s*(?:from|import)\s+(mlb_baseball|pandas|psycopg2?)\b", re.M)
    for path in (REPO / "packages/retrosheetpy/src").rglob("*.py"):
        assert not pattern.search(path.read_text()), path


def test_mlb_baseball_has_no_production_dependency_on_retrosheetpy():
    """6.1: this slice adds no connector switch or production import."""
    for path in (REPO / "mlb_baseball").rglob("*.py"):
        assert "retrosheetpy" not in path.read_text(), path
    assert retrosheetpy.__version__
