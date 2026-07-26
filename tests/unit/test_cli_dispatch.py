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
