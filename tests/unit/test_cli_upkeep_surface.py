"""The upkeep commands share one surface: `--dry-run` on ingest (shows the command, loads
nothing) and `--json` on the read-only reports, without changing how old invocations behave."""

import json

import pytest

from mlb_baseball import cli


def test_ingest_dry_run_prints_the_plan_and_never_calls_the_connector(monkeypatch, capsys):
    connector = cli.CONNECTORS["statcast"]

    def boom(*a, **k):
        raise AssertionError("dry run must not load anything")

    for name in ("bootstrap", "update"):
        monkeypatch.setattr(connector, name, boom)
    cli.main(["ingest", "statcast", "--mode", "update", "--dry-run"])
    assert "would run: mlb ingest statcast --mode update" in capsys.readouterr().out


def test_ingest_dry_run_still_rejects_invalid_combinations(monkeypatch):
    with pytest.raises(SystemExit):
        cli.main(["ingest", "statcast", "--start-year", "2020", "--dry-run"])


def test_ingest_without_dry_run_still_loads(monkeypatch, capsys):
    connector = cli.CONNECTORS["statcast"]
    monkeypatch.setattr(connector, "update", lambda: {"raw.x": 1})
    monkeypatch.setattr("mlb_baseball.ingest.table_totals", lambda loaded: {"raw.x": 5})
    cli.main(["ingest", "statcast", "--mode", "update"])
    assert "raw.x: 1 loaded, 5 in table" in capsys.readouterr().out


def test_ingest_json_prints_loaded_counts(monkeypatch, capsys):
    connector = cli.CONNECTORS["statcast"]
    monkeypatch.setattr(connector, "update", lambda: {"raw.x": 1})
    monkeypatch.setattr("mlb_baseball.ingest.table_totals", lambda loaded: {"raw.x": 5})
    cli.main(["ingest", "statcast", "--mode", "update", "--json"])
    assert json.loads(capsys.readouterr().out) == {"raw.x": {"loaded": 1, "in_table": 5}}


def test_doctor_json_lists_each_check(monkeypatch, capsys):
    from mlb_baseball import doctor
    from mlb_baseball.health import Check

    monkeypatch.setattr(doctor, "run", lambda: [Check("a", True, "fine"), Check("b", False, "bad")])
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["doctor", "--json"])
    assert exit_info.value.code == 1
    data = json.loads(capsys.readouterr().out)
    assert [c["name"] for c in data["checks"]] == ["a", "b"]
    assert data["checks"][1]["ok"] is False


def test_refresh_with_dry_run_leaves_the_download_cache_alone(monkeypatch, capsys):
    def boom(source):
        raise AssertionError("dry run must not move downloads")

    monkeypatch.setattr(cli.manifest, "supersede", boom)
    cli.main(["ingest", "retrosheet", "--mode", "bootstrap", "--refresh", "--dry-run"])
    out = capsys.readouterr().out
    assert "would set aside" in out
    assert "--refresh" in out


def test_dry_run_shows_stage_and_year_flags_and_honours_json(monkeypatch, capsys):
    cli.main(
        ["ingest", "mlb_api", "--stage", "analytics", "--start-year", "1950", "--dry-run", "--json"]
    )
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert "--stage analytics" in data["command"] and "--start-year 1950" in data["command"]
