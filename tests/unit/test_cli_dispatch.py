"""Pure dispatch-logic tests — connectors are faked out, no network/DB involved."""

import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

from mlb_baseball import cli, model, progress_table
from mlb_baseball.source_profiles import SourceProfileError, require_sources


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


def test_public_safe_profile_rejects_a_restricted_connector(monkeypatch):
    connector = _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"mlb_api": connector})

    try:
        cli.main(["ingest", "mlb_api", "--profile", "public_safe"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected public_safe to reject mlb_api")

    connector.bootstrap.assert_not_called()


def test_public_safe_profile_permits_retrosheet():
    require_sources("public_safe", ["retrosheet"], purpose="test")


def test_local_research_permits_a_restricted_connector():
    require_sources("local_research", ["mlb_api"], purpose="test")


def test_source_profile_failure_names_the_forbidden_source():
    try:
        require_sources("public_safe", ["bref"], purpose="test")
    except SourceProfileError as exc:
        assert "bref" in str(exc)
    else:
        raise AssertionError("expected public_safe to reject bref")


def test_ingest_mode_backfill_calls_backfill_history(monkeypatch, capsys):
    connector = _fake_connector()
    connector.backfill_history.return_value = {"raw.fake_price": 3}
    monkeypatch.setattr(cli, "CONNECTORS", {"fake": connector})

    cli.main(["ingest", "fake", "--mode", "backfill"])

    connector.backfill_history.assert_called_once()
    connector.bootstrap.assert_not_called()
    connector.update.assert_not_called()
    assert "raw.fake_price: 3 rows" in capsys.readouterr().out


def test_ingest_mode_backfill_on_a_connector_without_it_exits_cleanly(monkeypatch, capsys):
    # Not every connector implements backfill_history() (only polymarket.py/
    # kalshi.py so far, see ADR-047) — must fail clearly, not with an
    # AttributeError.
    connector = _fake_connector()
    del connector.backfill_history  # MagicMock would otherwise auto-create one
    monkeypatch.setattr(cli, "CONNECTORS", {"fake": connector})

    try:
        cli.main(["ingest", "fake", "--mode", "backfill"])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit(1) — no backfill_history() to run")

    assert "has no backfill_history()" in capsys.readouterr().out


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


def test_predict_command_calls_model_run(monkeypatch, capsys):
    monkeypatch.setattr(cli.model, "run", lambda: {"gold.game_feature": 1})

    cli.main(["predict"])

    assert "gold.game_feature: 1 rows" in capsys.readouterr().out


def test_metrics_command_passes_source_and_window(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cli.operational_metrics,
        "print_report",
        lambda source, window: captured.update(source=source, window=window),
    )

    cli.main(["metrics", "--source", "mlb_api", "--window-minutes", "10"])

    assert captured == {"source": "mlb_api", "window": 10}


def test_features_command_calls_model_feature_stage(monkeypatch, capsys):
    monkeypatch.setattr(cli.model, "run_features", lambda: {"gold.game_feature": 1})

    cli.main(["features"])

    assert "gold.game_feature: 1 rows" in capsys.readouterr().out


def test_predict_keeps_feature_stage_and_prediction_writes_separate(monkeypatch):
    """The compatibility command still reports feature and prediction results."""
    conn = MagicMock()
    conn.__enter__.return_value = conn

    @contextmanager
    def tracked_run(_conn, _source, _mode, **_kwargs):
        result = {}
        yield result

    monkeypatch.setattr(model, "get_connection", lambda: conn)
    monkeypatch.setattr(model, "track_run", tracked_run)
    monkeypatch.setattr(
        model,
        "build_feature_stage",
        lambda _conn: {"gold.game_feature": 10, "gold.game_feature (starters updated)": 4},
    )
    monkeypatch.setattr(model.market, "record", lambda _conn: 1)
    monkeypatch.setattr(model, "backfill_outcomes", lambda _conn: 2)
    monkeypatch.setattr(model.log5, "predict", lambda _conn: 3)
    monkeypatch.setattr(model.elo, "predict", lambda _conn: 4)
    monkeypatch.setattr(model.gbm, "predict", lambda _conn: 5)

    assert model.run() == {
        "gold.game_feature": 10,
        "gold.game_feature (starters updated)": 4,
        "gold.prediction (log5)": 3,
        "gold.prediction (elo)": 4,
        "gold.prediction (gbm)": 5,
        "gold.prediction (market)": 1,
        "gold.prediction (outcomes backfilled)": 2,
    }
    conn.commit.assert_called_once()


def test_train_command_calls_model_train_and_reports_metrics(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.model,
        "train",
        lambda: {
            "train_rows": 100,
            "validation_rows": 20,
            "gbm": {"log_loss": 0.6, "brier": 0.2},
            "log5": {"log_loss": 0.9, "brier": 0.25},
            "elo": {"log_loss": 0.65, "brier": 0.21},
            "saved": True,
        },
    )

    cli.main(["train"])

    out = capsys.readouterr().out
    assert "train rows: 100" in out
    assert "validation rows: 20" in out
    assert "gbm: log_loss=0.6000" in out
    assert "saved: new model beat both baselines" in out


def test_evaluate_command_reports_common_game_metrics(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.model,
        "evaluate",
        lambda models, season, cutoff, bootstrap_samples: {
            "season": season,
            "cutoff": cutoff,
            "common_games": 12,
            "coverage": {version: 15 for version in models},
            "models": {
                version: {
                    "games": 12,
                    "log_loss": 0.6,
                    "log_loss_95ci": (0.5, 0.7),
                    "brier": 0.2,
                    "brier_95ci": (0.15, 0.25),
                    "accuracy": 0.58,
                }
                for version in models
            },
        },
    )

    cli.main(
        [
            "evaluate",
            "--season",
            "2026",
            "--models",
            "gbm-v1",
            "elo-v1",
            "--bootstrap-samples",
            "10",
        ]
    )

    out = capsys.readouterr().out
    assert "12 common games" in out
    assert "gbm-v1: coverage=15" in out


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
    assert "[broken] FAILED" in capsys.readouterr().out


def test_concurrency_groups_keeps_same_server_connectors_together():
    # retrosheet_event/retrosheet_box hit the same external server
    # (retrosheet.org) as the rest of the retrosheet_* family — must land
    # in one group, not split across concurrent ones (ADR-005/ADR-031).
    names = ["mlb_api", "retrosheet_event", "statcast", "retrosheet_box", "kalshi"]

    groups = cli._concurrency_groups(names)

    retrosheet_group = next(g for g in groups if "retrosheet_event" in g)
    assert set(retrosheet_group) == {"retrosheet_event", "retrosheet_box"}
    # Everything else not in a known same-server group gets its own
    # singleton group — mlb_api/statcast/kalshi hit different servers.
    assert ["mlb_api"] in groups
    assert ["statcast"] in groups
    assert ["kalshi"] in groups


def test_concurrency_groups_defaults_unknown_names_to_singleton_groups():
    # A name this list doesn't know about (a new connector, or — as in
    # every other test in this file — a test double) must still work,
    # not crash or get silently dropped.
    groups = cli._concurrency_groups(["one", "two"])

    assert sorted(groups) == [["one"], ["two"]]


def test_bootstrap_runs_different_groups_concurrently(monkeypatch, capsys):
    # Real concurrency check, not just a grouping-logic check: two
    # connectors with no known same-server relationship must actually
    # overlap in wall-clock time, not run one-after-another. Each records
    # its own (start, end) into a shared, thread-safe list (list.append is
    # atomic under the GIL) so this asserts real overlap, not just that
    # both got called.
    monkeypatch.setattr(cli, "_SAME_SERVER_GROUPS", [])
    spans: list[tuple[float, float]] = []
    lock = threading.Lock()

    def _slow_bootstrap():
        start = time.monotonic()
        time.sleep(0.2)
        end = time.monotonic()
        with lock:
            spans.append((start, end))
        return {"raw.fake": 1}

    one, two = MagicMock(), MagicMock()
    one.bootstrap.side_effect = _slow_bootstrap
    two.bootstrap.side_effect = _slow_bootstrap
    monkeypatch.setattr(cli, "CONNECTORS", {"one": one, "two": two})

    started = time.monotonic()
    cli.main(["bootstrap"])
    total = time.monotonic() - started

    # Sequential would take >= 0.4s (two 0.2s sleeps back to back);
    # concurrent finishes in roughly one sleep's worth of time. A generous
    # 0.35s bound comfortably distinguishes the two without being flaky.
    assert total < 0.35
    (s1, e1), (s2, e2) = spans
    assert s1 < e2 and s2 < e1  # the two [start, end] intervals overlap


def test_bootstrap_runs_same_server_connectors_sequentially(monkeypatch):
    # The other half of the same check: connectors sharing a known server
    # must NOT overlap, even though they're grouped with something that
    # otherwise would run concurrently.
    monkeypatch.setattr(cli, "_SAME_SERVER_GROUPS", [frozenset({"one", "two"})])
    spans: list[tuple[float, float]] = []
    lock = threading.Lock()

    def _slow_bootstrap():
        start = time.monotonic()
        time.sleep(0.1)
        end = time.monotonic()
        with lock:
            spans.append((start, end))
        return {"raw.fake": 1}

    one, two = MagicMock(), MagicMock()
    one.bootstrap.side_effect = _slow_bootstrap
    two.bootstrap.side_effect = _slow_bootstrap
    monkeypatch.setattr(cli, "CONNECTORS", {"one": one, "two": two})

    cli.main(["bootstrap"])

    (s1, e1), (s2, e2) = spans
    assert e1 <= s2 or e2 <= s1  # no overlap — ran one after the other


def test_status_defaults_to_populated_only_and_has_data_strategy(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        progress_table,
        "print_status_table",
        lambda **kwargs: captured.update(kwargs),
    )

    cli.main(["status"])

    assert captured["populated_only"] is True
    assert captured["strategy"] is None  # print_status_table's own default (HasDataStrategy)
    assert captured["watch"] is None


def test_status_all_flag_disables_populated_only(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        progress_table,
        "print_status_table",
        lambda **kwargs: captured.update(kwargs),
    )

    cli.main(["status", "--all", "--watch", "5"])

    assert captured["populated_only"] is False
    assert captured["watch"] == 5


def test_status_run_status_flag_selects_run_status_strategy(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        progress_table,
        "print_status_table",
        lambda **kwargs: captured.update(kwargs),
    )

    cli.main(["status", "--run-status"])

    assert isinstance(captured["strategy"], progress_table.RunStatusStrategy)


def test_status_season_coverage_flag_selects_exact_coverage_strategy(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        progress_table,
        "print_status_table",
        lambda **kwargs: captured.update(kwargs),
    )

    cli.main(["status", "--season-coverage"])

    assert isinstance(captured["strategy"], progress_table.SeasonCoverageStrategy)
