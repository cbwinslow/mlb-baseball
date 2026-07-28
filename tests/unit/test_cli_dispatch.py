"""Pure dispatch-logic tests — connectors are faked out, no network/DB involved."""

from unittest.mock import MagicMock

from mlb_baseball import cli


def _fake_connector():
    connector = MagicMock()
    connector.bootstrap.return_value = {"raw.fake": 1}
    connector.update.return_value = {"raw.fake": 2}
    return connector


def test_ingest_defaults_to_bootstrap(monkeypatch, capsys):
    connector = _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"fake": connector})

    cli.main(["ingest", "fake"])

    connector.bootstrap.assert_called_once()
    connector.update.assert_not_called()
    assert "raw.fake: 1 rows" in capsys.readouterr().out


def test_ingest_mode_update_calls_update_not_bootstrap(monkeypatch, capsys):
    connector = _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"fake": connector})

    cli.main(["ingest", "fake", "--mode", "update"])

    connector.update.assert_called_once()
    connector.bootstrap.assert_not_called()
    assert "raw.fake: 2 rows" in capsys.readouterr().out


def test_migrate_command_calls_migrate_main(monkeypatch):
    called = {"count": 0}
    monkeypatch.setattr(
        cli.migrate, "main", lambda: called.__setitem__("count", called["count"] + 1)
    )

    cli.main(["migrate"])

    assert called["count"] == 1


def test_conform_command_calls_conform_run(monkeypatch, capsys):
    monkeypatch.setattr(cli.conform, "run", lambda: {"core.team": 1})

    cli.main(["conform"])

    assert "core.team: 1 rows" in capsys.readouterr().out


def test_bootstrap_command_calls_every_connectors_bootstrap(monkeypatch, capsys):
    one, two = _fake_connector(), _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"one": one, "two": two})

    cli.main(["bootstrap"])

    one.bootstrap.assert_called_once()
    two.bootstrap.assert_called_once()
    one.update.assert_not_called()
    out = capsys.readouterr().out
    assert "=== one (bootstrap) ===" in out
    assert "=== two (bootstrap) ===" in out


def test_update_command_calls_every_connectors_update(monkeypatch, capsys):
    one, two = _fake_connector(), _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"one": one, "two": two})

    cli.main(["update"])

    one.update.assert_called_once()
    two.update.assert_called_once()
    one.bootstrap.assert_not_called()


def test_bootstrap_command_continues_past_a_failing_connector(monkeypatch, capsys):
    broken = MagicMock()
    broken.bootstrap.side_effect = RuntimeError("simulated failure")
    fine = _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"broken": broken, "fine": fine})

    try:
        cli.main(["bootstrap"])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit(1) — a connector failed")

    fine.bootstrap.assert_called_once()
    assert "broken: FAILED" in capsys.readouterr().out
