"""Schema drift check: snapshots are compared by field name and type, an unreachable
source is 'unchecked' (never 'unchanged'), and the check needs no database."""

import pytest

from mlb_baseball.schema_watch import (
    Dataset,
    SnapshotStore,
    check,
    compare,
    fields_of,
)


def test_fields_of_flattens_names_and_json_types():
    sample = {"id": 1, "name": "x", "team": {"id": 2, "w": 0.5}, "tags": [1], "n": None, "ok": True}
    assert fields_of(sample) == {
        "id": "int",
        "name": "str",
        "team": "object",
        "team.id": "int",
        "team.w": "float",
        "tags": "list",
        "n": "null",
        "ok": "bool",
    }


def test_fields_of_list_merges_rows_so_sparse_fields_are_seen():
    assert fields_of([{"a": 1}, {"a": 2, "b": "x"}]) == {"a": "int", "b": "str"}


def test_compare_reports_added_removed_and_changed():
    old = {"a": "int", "b": "str", "c": "int"}
    new = {"a": "int", "b": "int", "d": "str"}
    drift = compare(old, new)
    assert drift.added == {"d": "str"}
    assert drift.removed == {"c": "int"}
    assert drift.changed == {"b": ("str", "int")}
    assert drift.any


def test_compare_ignores_null_samples():
    assert not compare({"a": "null"}, {"a": "str"}).any
    assert not compare({"a": "str"}, {"a": "null"}).any


def _ds(sample, calls=None, name="d"):
    def fetch():
        if calls is not None:
            calls.append(name)
        if isinstance(sample, Exception):
            raise sample
        return sample

    return Dataset(source="s", name=name, fetch=fetch)


def test_first_run_writes_a_baseline_and_reports_it_as_new(tmp_path):
    store = SnapshotStore(tmp_path)
    (finding,) = check([_ds({"a": 1})], store)
    assert finding.status == "new"
    assert store.load("s", "d") == {"a": "int"}


def test_unchanged_rerun_reports_nothing_and_writes_nothing(tmp_path):
    store = SnapshotStore(tmp_path)
    check([_ds({"a": 1})], store)
    before = (tmp_path / "s" / "d.json").stat().st_mtime_ns
    (finding,) = check([_ds({"a": 1})], store)
    assert finding.status == "unchanged"
    assert (tmp_path / "s" / "d.json").stat().st_mtime_ns == before


def test_added_field_is_drift_and_snapshot_is_kept_until_accepted(tmp_path):
    store = SnapshotStore(tmp_path)
    check([_ds({"a": 1})], store)
    (finding,) = check([_ds({"a": 1, "b": "x"})], store)
    assert finding.status == "drift"
    assert finding.drift.added == {"b": "str"}
    assert store.load("s", "d") == {"a": "int"}
    (again,) = check([_ds({"a": 1, "b": "x"})], store)
    assert again.status == "drift"
    (accepted,) = check([_ds({"a": 1, "b": "x"})], store, accept=True)
    assert accepted.status == "drift"
    assert store.load("s", "d") == {"a": "int", "b": "str"}


def test_unreachable_source_is_unchecked_not_unchanged(tmp_path):
    store = SnapshotStore(tmp_path)
    check([_ds({"a": 1})], store)
    (finding,) = check([_ds(ConnectionError("down"))], store, attempts=2, pause=0)
    assert finding.status == "unchecked"
    assert "down" in finding.error
    assert store.load("s", "d") == {"a": "int"}


def test_one_request_per_dataset_when_the_source_answers(tmp_path):
    calls = []
    check([_ds({"a": 1}, calls, "x"), _ds({"b": 1}, calls, "y")], SnapshotStore(tmp_path))
    assert sorted(calls) == ["x", "y"]


def test_a_failing_dataset_does_not_stop_the_others(tmp_path):
    findings = check(
        [_ds(RuntimeError("boom"), name="x"), _ds({"a": 1}, name="y")],
        SnapshotStore(tmp_path),
        attempts=1,
        pause=0,
    )
    assert [f.status for f in findings] == ["unchecked", "new"]


def test_snapshot_names_cannot_escape_the_store(tmp_path):
    with pytest.raises(ValueError):
        SnapshotStore(tmp_path).load("../x", "d")
