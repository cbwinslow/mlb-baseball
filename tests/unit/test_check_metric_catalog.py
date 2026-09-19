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
check_validated_test_refs = check_metric_catalog.check_validated_test_refs

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


# --- check_validated_test_refs (Decision 3) -----------------------------


def _validated_entry(**overrides) -> MetricEntry:
    fields = {"status": "validated", "test_ref": "test_something.py"}
    fields.update(overrides)
    return _entry(**fields)


def test_check_validated_test_refs_ignores_non_validated_entries(tmp_path):
    # No file on disk at all -- would error if status were validated.
    entries = [_entry(status="implemented-untested", test_ref=None)]
    errors, warnings = check_validated_test_refs(entries, repo_root=tmp_path)
    assert errors == []
    assert warnings == []


def test_check_validated_test_refs_errors_on_missing_file(tmp_path):
    entries = [_validated_entry(name="missing_test", test_ref="tests/does_not_exist.py")]
    errors, warnings = check_validated_test_refs(entries, repo_root=tmp_path)
    assert len(errors) == 1
    assert "missing_test" in errors[0]
    assert warnings == []


def test_check_validated_test_refs_rejects_path_escaping_repo_root(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside_file = tmp_path / "outside_test.py"
    outside_file.write_text("source_url = 'real'\n")  # would pass every other check
    entries = [_validated_entry(name="escapes_repo", test_ref="../outside_test.py")]
    errors, warnings = check_validated_test_refs(entries, repo_root=repo_root)
    assert len(errors) == 1
    assert "escapes_repo" in errors[0]
    assert warnings == []


def test_check_validated_test_refs_rejects_absolute_path(tmp_path):
    outside_file = tmp_path / "outside_test.py"
    outside_file.write_text("source_url = 'real'\n")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    entries = [_validated_entry(name="absolute_escape", test_ref=str(outside_file))]
    errors, warnings = check_validated_test_refs(entries, repo_root=repo_root)
    assert len(errors) == 1
    assert "absolute_escape" in errors[0]
    assert warnings == []


def test_check_validated_test_refs_no_warning_for_external_fixture_test(tmp_path):
    test_file = tmp_path / "test_tieout.py"
    test_file.write_text(
        "def test_matches_baseball_reference():\n"
        "    # source_url: https://www.baseball-reference.com/players/j/judgeaa01.shtml\n"
        "    expected = 0.311  # Baseball-Reference, 2022 season page\n"
        "    assert compute() == expected\n"
    )
    entries = [_validated_entry(name="real_tieout", test_ref="test_tieout.py")]
    errors, warnings = check_validated_test_refs(entries, repo_root=tmp_path)
    assert errors == []
    assert warnings == []


def test_check_validated_test_refs_flags_self_referential_test(tmp_path):
    test_file = tmp_path / "test_self.py"
    test_file.write_text(
        "def test_matches_its_own_math():\n"
        "    expected = compute_formula(1, 2)\n"
        "    assert compute_formula(1, 2) == expected\n"
    )
    entries = [_validated_entry(name="self_referential", test_ref="test_self.py")]
    errors, warnings = check_validated_test_refs(entries, repo_root=tmp_path)
    assert errors == []
    assert len(warnings) == 1
    assert "self_referential" in warnings[0]


def test_check_validated_test_refs_strips_function_suffix_from_test_ref(tmp_path):
    test_file = tmp_path / "test_tieout.py"
    test_file.write_text("# Retrosheet source_url cited above\n")
    entries = [
        _validated_entry(
            name="real_tieout", test_ref="test_tieout.py::test_matches_baseball_reference"
        )
    ]
    errors, warnings = check_validated_test_refs(entries, repo_root=tmp_path)
    assert errors == []
    assert warnings == []
