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


def test_exit_code_drift_beats_unchecked_beats_ok():
    from mlb_baseball.schema_watch import Finding, exit_code

    assert exit_code([Finding("s", "a", "unchanged"), Finding("s", "b", "new")]) == 0
    assert exit_code([Finding("s", "a", "unchecked")]) == 2
    drift = Finding("s", "a", "drift", compare({}, {"x": "int"}))
    assert exit_code([Finding("s", "b", "unchecked"), drift]) == 1


def test_render_lists_each_drifted_field_and_each_unchecked_dataset():
    from mlb_baseball.schema_watch import Finding, render

    drift = Finding("s", "a", "drift", compare({"o": "str", "c": "int"}, {"n": "int", "c": "str"}))
    text = render([drift, Finding("s", "b", "unchecked", error="down")])
    assert "DRIFT s/a" in text
    assert "added n: int" in text
    assert "removed o: str" in text
    assert "changed c: int -> str" in text
    assert "UNCHECKED s/b: down" in text


def test_fields_inside_lists_of_objects_are_seen():
    sample = {"dates": [{"games": [{"gamePk": 1, "status": {"code": "F"}}]}], "total": 1}
    fields = fields_of(sample)
    assert fields["dates[].games"] == "list"
    assert fields["dates[].games[].gamePk"] == "int"
    assert fields["dates[].games[].status.code"] == "str"


def test_a_renamed_nested_field_is_drift(tmp_path):
    store = SnapshotStore(tmp_path)
    check([_ds({"dates": [{"games": [{"gamePk": 1}]}]})], store)
    (finding,) = check([_ds({"dates": [{"games": [{"game_pk": 1}]}]})], store)
    assert finding.status == "drift"
    assert "dates[].games[].gamePk" in finding.drift.removed


def test_a_failing_dataset_is_retried_the_stated_number_of_times(tmp_path):
    calls = []
    check([_ds(ConnectionError("x"), calls)], SnapshotStore(tmp_path), attempts=3, pause=0)
    assert len(calls) == 3


def test_unknown_source_is_not_reported_as_success(capsys):
    from mlb_baseball import schema_watch

    assert schema_watch.run("nonexistent", datasets=[_ds({"a": 1})]) == 2
    assert "no datasets" in capsys.readouterr().out


def test_tolerate_unchecked_turns_exit_2_into_0_but_keeps_drift(tmp_path, monkeypatch):
    import contextlib

    from mlb_baseball import schema_watch

    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: contextlib.nullcontext())
    monkeypatch.setattr(schema_watch, "record", lambda conn, findings: None)
    down = [_ds(ConnectionError("down"))]
    kw = {"store_dir": tmp_path, "datasets": down}
    monkeypatch.setattr(
        schema_watch,
        "check",
        lambda *a, **k: [schema_watch.Finding("s", "d", "unchecked", error="down")],
    )
    assert schema_watch.run(**kw) == 2
    assert schema_watch.run(tolerate_unchecked=True, **kw) == 0
    drift = schema_watch.Finding("s", "d", "drift", compare({}, {"x": "int"}))
    monkeypatch.setattr(schema_watch, "check", lambda *a, **k: [drift])
    assert schema_watch.run(tolerate_unchecked=True, **kw) == 1
