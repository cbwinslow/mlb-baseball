"""Unit coverage for scripts/check_metric_catalog.py's pure logic -- not a
package, so loaded directly by path (same pattern as
tests/unit/test_lint_sql_ownership.py)."""

import importlib.util
from pathlib import Path

import pytest

from mlb_baseball.catalog import MetricEntry

_SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "check_metric_catalog.py"
_spec = importlib.util.spec_from_file_location("check_metric_catalog", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
check_metric_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_metric_catalog)

find_gaps = check_metric_catalog.find_gaps
lint_visibility = check_metric_catalog.lint_visibility

_BASE_FIELDS = {
    "name": "some_metric",
    "definition": "A metric.",
    "formula": "mlb_baseball/model/framing.py",
    "citation": "project-derived",
    "data_source": "raw.statcast",
    "grain": "player-season",
    "layer": "model",
    "complexity": "complex",
    "implementation": "python",
    "status": "implemented-untested",
    "visibility": "internal",
}


def _entry(**overrides) -> MetricEntry:
    fields = dict(_BASE_FIELDS)
    fields.update(overrides)
    return MetricEntry.model_validate(fields)


# --- find_gaps ---------------------------------------------------------


def test_find_gaps_reports_uncovered_file(tmp_path):
    covered = tmp_path / "covered.py"
    covered.touch()
    uncovered = tmp_path / "uncovered.py"
    uncovered.touch()
    entries = [_entry(formula="covered.py")]
    gaps = find_gaps([covered, uncovered], entries, repo_root=tmp_path)
    assert gaps == ["uncovered.py"]


def test_find_gaps_strips_function_suffix_from_formula(tmp_path):
    covered = tmp_path / "framing.py"
    covered.touch()
    entries = [_entry(formula="framing.py::compute")]
    gaps = find_gaps([covered], entries, repo_root=tmp_path)
    assert gaps == []


def test_find_gaps_empty_when_all_covered(tmp_path):
    a = tmp_path / "a.py"
    a.touch()
    entries = [_entry(formula="a.py")]
    assert find_gaps([a], entries, repo_root=tmp_path) == []


# --- lint_visibility (Decision 2) --------------------------------------


def test_lint_visibility_no_flag_for_correctly_tagged_public_entry():
    entries = [_entry(citation="FanGraphs, Guts! constants", visibility="public")]
    assert lint_visibility(entries) == []


def test_lint_visibility_no_flag_for_correctly_tagged_internal_entry():
    entries = [_entry(citation="project-derived", visibility="internal")]
    assert lint_visibility(entries) == []


def test_lint_visibility_flags_public_citation_marked_internal():
    entries = [
        _entry(name="mismatch_1", citation="Baseball-Reference bulk export", visibility="internal")
    ]
    warnings = lint_visibility(entries)
    assert len(warnings) == 1
    assert "mismatch_1" in warnings[0]


def test_lint_visibility_flags_no_public_citation_marked_public():
    entries = [_entry(name="mismatch_2", citation="project-derived", visibility="public")]
    warnings = lint_visibility(entries)
    assert len(warnings) == 1
    assert "mismatch_2" in warnings[0]


@pytest.mark.parametrize(
    "marker",
    ["FanGraphs", "Baseball-Reference", "Tango", "Retrosheet", "Lahman", "Baseball Prospectus"],
)
def test_lint_visibility_recognizes_each_allow_list_marker(marker):
    entries = [_entry(citation=f"{marker}, some year", visibility="public")]
    assert lint_visibility(entries) == []
