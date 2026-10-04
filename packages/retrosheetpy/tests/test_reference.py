"""Differential checks against Chadwick (captured) and Retrosheet's plays.csv (captured)."""

import csv
import hashlib
import json
from pathlib import Path

import pytest
from chadwick_reference import ChadwickReference
from retrosheetpy import read_event_file
from retrosheetpy.validation import compare_chadwick, compare_plays_csv

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "events"
CHADWICK = HERE / "reference" / "chadwick"
PLAYS_CSV = HERE / "reference" / "retrosheet_csv"
# Known, understood disagreements between the event text and the CSV (the CSV
# normalises some hit locations, e.g. 3L -> 3+, 56D -> 56+). Anything else is a failure.
EXPECTED_CSV_DIFFS = {"postseason": {"loc": 2}, "auto_runner_pr": {"loc": 2}}
NAMES = sorted(p.stem for p in FIXTURES.glob("*.evt"))


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_fixture_set_is_not_empty():
    assert len(NAMES) == 10


def test_captured_chadwick_matches_current_fixtures():
    manifest = json.loads((CHADWICK / "MANIFEST.json").read_text())
    assert manifest["chadwick_version"] == "0.10.0"
    for name in NAMES:
        digest = hashlib.sha256((FIXTURES / f"{name}.evt").read_bytes()).hexdigest()
        assert manifest["files"][f"{name}.evt"]["fixture_sha256"] == digest, (
            f"{name}: fixture changed; re-run tests/reference/capture.py"
        )


@pytest.mark.parametrize("name", NAMES)
def test_captured_chadwick_has_all_164_columns(name):
    manifest = json.loads((CHADWICK / "MANIFEST.json").read_text())
    assert (manifest["fields"], manifest["extended"]) == ("0-96", "0-66")
    rows = read_rows(CHADWICK / f"{name}.csv")
    assert len(rows[0]) == 97 + 67 and len(set(rows[0])) == 164


@pytest.mark.parametrize("directory", [CHADWICK, PLAYS_CSV])
def test_captured_csvs_match_manifest_hashes(directory):
    files = json.loads((directory / "MANIFEST.json").read_text())["files"]
    for name, entry in files.items():
        csv_path = directory / f"{Path(name).stem}.csv"
        if "csv_sha256" not in entry:
            assert not csv_path.exists(), f"{csv_path.name} has no recorded hash"
            continue
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        assert digest == entry["csv_sha256"], f"{csv_path.name} was edited by hand"


@pytest.mark.parametrize("name", NAMES)
def test_parser_agrees_with_captured_chadwick(name):
    records = read_event_file(FIXTURES / f"{name}.evt")
    result = compare_chadwick(records, read_rows(CHADWICK / f"{name}.csv"), version="0.10.0")
    assert result.games_misaligned == 0 and result.games == 1
    assert result.plays_compared > 30
    assert {"EVENT_CD", "H_CD", "BUNT_FL"} <= result.fields.keys()
    assert all(f.compared > 0 for f in result.fields.values())
    assert result.mismatches == 0, result.to_dict()["fields"]


@pytest.mark.parametrize("name", NAMES)
def test_parser_agrees_with_captured_plays_csv(name):
    records = read_event_file(FIXTURES / f"{name}.evt")
    result = compare_plays_csv(records, read_rows(PLAYS_CSV / f"{name}.csv"))
    assert result.games_misaligned == 0 and result.games == 1
    found = {k: v.mismatches for k, v in result.fields.items() if v.mismatches}
    assert found == EXPECTED_CSV_DIFFS.get(name, {}), result.to_dict()["fields"]


@pytest.mark.parametrize("name", NAMES)
def test_live_chadwick_reproduces_captured_rows(name):
    live = ChadwickReference.find()
    if live is None:
        pytest.skip("cwevent is not on PATH (reference tests use the captured output)")
    manifest = json.loads((CHADWICK / "MANIFEST.json").read_text())
    if live.version != manifest["chadwick_version"]:
        pytest.skip(f"cwevent {live.version} differs from captured {manifest['chadwick_version']}")
    year = manifest["files"][f"{name}.evt"]["year"]
    assert live.events(FIXTURES / f"{name}.evt", year) == read_rows(CHADWICK / f"{name}.csv")
