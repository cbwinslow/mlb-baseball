"""Pure dispatch-logic tests — connectors are faked out, no network/DB involved."""

import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from mlb_baseball import audit, backup, cli, field_census, model, progress_table, report
from mlb_baseball.model import experiment, feature_select, feature_select_stepwise
from mlb_baseball.source_profiles import SourceProfileError, require_sources


def _fake_connector():
    connector = MagicMock()
    connector.bootstrap.return_value = {"raw.fake": 1}
    connector.update.return_value = {"raw.fake": 2}
    return connector


def test_cli_help_lists_core_commands_and_start_here_docs(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Core commands" in out
    assert "openspec/project.md" in out
    assert "docs/ARCHITECTURE.md" in out


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
    calls = []
    monkeypatch.setattr(cli.migrate, "main", lambda skip=None: calls.append(skip))

    cli.main(["migrate"])

    assert calls == [set()]


def test_migrate_command_parses_repeated_skip_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.migrate, "main", lambda skip=None: calls.append(skip))

    cli.main(["migrate", "--skip", "0040_core_game_pk_unique.sql", "--skip", "0045_x.sql"])

    assert calls == [{"0040_core_game_pk_unique.sql", "0045_x.sql"}]


def test_preflight_reports_plan_without_running_connectors(monkeypatch, capsys):
    connector = _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"fake": connector})
    monkeypatch.setattr(
        "mlb_baseball.preflight.run",
        lambda settings, sources, with_conform: (
            [],
            ["mlb migrate", "mlb ingest fake --mode bootstrap"],
        ),
    )

    cli.main(["preflight", "--sources", "fake"])

    connector.bootstrap.assert_not_called()
    output = capsys.readouterr().out
    assert "Planned commands (not run):" in output
    assert "mlb ingest fake --mode bootstrap" in output


def test_conform_command_calls_conform_run(monkeypatch, capsys):
    monkeypatch.setattr(cli.conform, "run", lambda: {"core.team": 1})

    cli.main(["conform"])

    assert "core.team: 1 rows" in capsys.readouterr().out


def test_report_command_calls_report_run(monkeypatch, capsys):
    monkeypatch.setattr(report, "run", lambda: {"gold.team_season": 1})

    cli.main(["report"])

    assert "gold.team_season: 1 rows" in capsys.readouterr().out


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


def test_field_census_command_is_read_only_dispatch(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        field_census,
        "print_report",
        lambda **kwargs: captured.update(kwargs),
    )

    cli.main(["field-census", "--exact"])

    assert captured == {"exact": True, "output_json": None, "output_markdown": None}


def test_audit_command_passes_scope_and_exits_cleanly(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        audit,
        "print_report",
        lambda scope: captured.setdefault("scope", scope) or True,
    )

    cli.main(["audit", "--scope", "database"])

    assert captured == {"scope": "database"}


def test_features_command_calls_model_feature_stage(monkeypatch, capsys):
    monkeypatch.setattr(cli.model, "run_features", lambda: {"gold.game_feature": 1})

    cli.main(["features"])

    assert "gold.game_feature: 1 rows" in capsys.readouterr().out


def test_experiment_snapshot_command_creates_and_prints_snapshot(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        experiment, "create_snapshot", lambda _conn, target="home_win": "snapshot-1"
    )

    cli.main(["experiment", "snapshot"])

    assert "snapshot: snapshot-1" in capsys.readouterr().out
    conn.commit.assert_called_once()


def test_experiment_run_command_parses_all_its_own_arguments(monkeypatch, capsys):
    # Regression test: experiment_run's --seed argument was accidentally
    # deleted from the argparse subparser in 442f47e (while --seed was being
    # added to the new select-features subparser), which crashed every real
    # `mlb experiment run` invocation with AttributeError: 'Namespace' object
    # has no attribute 'seed' -- undetected because no test exercised this
    # subcommand's CLI dispatch at all, only experiment.run() directly.
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    captured_config = {}

    def fake_run(_conn, config):
        captured_config["config"] = config
        return {
            "experiment_id": "exp-1",
            "reused": False,
            "folds": {"season-2016": {"log_loss": 0.6, "brier": 0.2}},
        }

    monkeypatch.setattr(experiment, "run", fake_run)

    cli.main(
        [
            "experiment",
            "run",
            "--snapshot",
            "snap-1",
            "--model",
            "home_rate",
            "--target",
            "home_win",
            "--seed",
            "7",
            "--fold-years",
            "2016",
            "2017",
        ]
    )

    config = captured_config["config"]
    assert config.snapshot_id == "snap-1"
    assert config.model_family == "home_rate"
    assert config.target == "home_win"
    assert config.seed == 7
    assert config.fold_years == (2016, 2017)
    assert "experiment: exp-1 (ran)" in capsys.readouterr().out


def test_experiment_run_command_prints_regression_metrics(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)

    def fake_run(_conn, config):
        return {
            "experiment_id": "exp-reg-1",
            "reused": False,
            "folds": {"season-2021": {"mae": 1.4567, "rmse": 2.1234}},
        }

    monkeypatch.setattr(experiment, "run", fake_run)

    cli.main(
        [
            "experiment",
            "run",
            "--snapshot",
            "snap-1",
            "--model",
            "ridge",
            "--target",
            "run_differential",
            "--seed",
            "42",
            "--fold-years",
            "2021",
        ]
    )

    out = capsys.readouterr().out
    assert "experiment: exp-reg-1 (ran)" in out
    assert "  season-2021: mae=1.4567 rmse=2.1234" in out
    conn.commit.assert_called_once()


def test_experiment_compare_command_parses_arguments_and_prints_metrics(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)

    rows = [
        {"model": "home_rate", "fold": "season-2020", "log_loss": 0.61234, "brier": 0.21234},
        {"model": "ridge", "fold": "season-2020", "mae": 1.54321, "rmse": 2.12345},
    ]
    monkeypatch.setattr(
        experiment,
        "compare",
        lambda _conn, snapshot: rows if snapshot == "snap-1" else [],
    )

    cli.main(["experiment", "compare", "--snapshot", "snap-1"])

    out = capsys.readouterr().out
    assert "home_rate season-2020: log_loss=0.6123 brier=0.2123" in out
    assert "ridge season-2020: mae=1.5432 rmse=2.1235" in out


def test_experiment_select_features_command_parses_all_its_own_arguments(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    captured_args = {}

    def fake_select(conn_arg, snapshot, n_repeats=10, seed=42, fold_years=None):
        captured_args["snapshot"] = snapshot
        captured_args["n_repeats"] = n_repeats
        captured_args["seed"] = seed
        captured_args["fold_years"] = fold_years
        return {
            "selection_id": "sel-1",
            "reused": False,
            "total_folds_evaluated": 5,
            "features": {
                "elo_diff": {
                    "stage1_survived_folds": 4,
                    "stage2_survived_folds": 3,
                    "both_stages_survived_folds": 3,
                }
            },
        }

    monkeypatch.setattr(feature_select, "select_features", fake_select)

    cli.main(
        [
            "experiment",
            "select-features",
            "--snapshot",
            "snap-1",
            "--n-repeats",
            "7",
            "--seed",
            "99",
            "--fold-years",
            "2018",
            "2019",
        ]
    )

    assert captured_args["snapshot"] == "snap-1"
    assert captured_args["n_repeats"] == 7
    assert captured_args["seed"] == 99
    assert captured_args["fold_years"] == (2018, 2019)
    conn.commit.assert_called_once()
    out = capsys.readouterr().out
    assert "feature_selection: sel-1 (ran)" in out
    assert "  elo_diff: stage1: 4/5  stage2: 3/5  both: 3/5" in out


def test_experiment_select_features_stepwise_command_parses_all_its_own_arguments(
    monkeypatch, capsys
):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    captured_args = {}

    def fake_stepwise(conn_arg, snapshot, seed=42, fold_years=None, min_survival_fraction=0.75):
        captured_args["snapshot"] = snapshot
        captured_args["seed"] = seed
        captured_args["fold_years"] = fold_years
        captured_args["min_survival_fraction"] = min_survival_fraction
        return {
            "selection_id": "step-1",
            "reused": True,
            "total_folds_evaluated": 4,
            "candidate_features": ["f1", "f2"],
            "features": {
                "f1": {
                    "selected_folds": 3,
                    "selection_fraction": 0.75,
                }
            },
        }

    monkeypatch.setattr(feature_select_stepwise, "select_features_stepwise", fake_stepwise)

    cli.main(
        [
            "experiment",
            "select-features-stepwise",
            "--snapshot",
            "snap-2",
            "--seed",
            "101",
            "--fold-years",
            "2020",
            "--min-survival-fraction",
            "0.5",
        ]
    )

    assert captured_args["snapshot"] == "snap-2"
    assert captured_args["seed"] == 101
    assert captured_args["fold_years"] == (2020,)
    assert captured_args["min_survival_fraction"] == 0.5
    conn.commit.assert_called_once()
    out = capsys.readouterr().out
    assert "feature_selection_stepwise: step-1 (reused)" in out
    assert "candidates (2): f1, f2" in out
    assert "  f1: selected 3/4 folds (75%)" in out


def test_format_metrics_line_classification_and_regression():
    class_metrics = {"log_loss": 0.54321, "brier": 0.18765}
    assert cli._format_metrics_line(class_metrics) == "log_loss=0.5432 brier=0.1877"

    reg_metrics = {"mae": 1.23456, "rmse": 2.34567}
    assert cli._format_metrics_line(reg_metrics) == "mae=1.2346 rmse=2.3457"

    assert cli._format_metrics_line({}) == ""


def test_feature_select_has_no_health_check():
    assert not hasattr(feature_select, "health_check")


def test_predict_keeps_feature_stage_and_prediction_writes_separate(monkeypatch):
    """The compatibility command still reports feature and prediction results."""
    conn = MagicMock()
    conn.__enter__.return_value = conn
    tracked: dict = {}

    @contextmanager
    def tracked_run(_conn, _source, _mode, **_kwargs):
        result = {}
        yield result
        tracked.update(result)

    monkeypatch.setattr(model, "get_connection", lambda: conn)
    monkeypatch.setattr(model, "track_run", tracked_run)
    monkeypatch.setattr(
        model,
        "build_feature_stage",
        lambda _conn: {"gold.game_feature": 10, "gold.game_feature (starters updated)": 4},
    )
    # A single-key stand-in for the real 20-key dict (one per enrichment
    # module) is enough here -- this test only proves run() merges
    # whatever enrich_feature_stage() returns into its own result, not
    # every module's own row count; the real dict's exact shape is
    # tests/integration/test_model_enrich_stage.py's job to verify.
    monkeypatch.setattr(
        model,
        "enrich_feature_stage",
        lambda _conn: {"gold.game_feature (park_factor)": 6},
    )
    monkeypatch.setattr(model.elo, "compute_ratings", lambda _conn: 10)
    # diff.compute() must run after elo.compute_ratings() (real bug found
    # and fixed in PR review, CodeAnt: elo_diff was permanently NULL in
    # production because it used to be computed from inside
    # enrich_feature_stage(), which runs before Elo ratings are written --
    # see mlb_baseball/model/__init__.py's own docstrings for the full
    # explanation). Mocked separately here since it's its own call in
    # run(), not part of enrich_feature_stage()'s returned dict anymore.
    monkeypatch.setattr(model.diff, "compute", lambda _conn: 7)
    monkeypatch.setattr(model.market, "record", lambda _conn: 1)
    monkeypatch.setattr(model, "backfill_outcomes", lambda _conn: 2)
    monkeypatch.setattr(model.log5, "predict", lambda _conn: 3)
    monkeypatch.setattr(model.elo, "predict", lambda _conn: 4)
    monkeypatch.setattr(model.gbm, "predict", lambda _conn: 5)
    monkeypatch.setattr(model.sim_predict, "predict", lambda _conn: 8)

    assert model.run() == {
        "gold.game_feature": 10,
        "gold.game_feature (starters updated)": 4,
        "gold.game_feature (park_factor)": 6,
        "gold.game_feature (diff)": 7,
        "gold.prediction (log5)": 3,
        "gold.prediction (elo)": 4,
        "gold.prediction (gbm)": 5,
        "gold.prediction (markov)": 8,
        "gold.prediction (market)": 1,
        "gold.prediction (outcomes backfilled)": 2,
        "gold.game_feature (Elo ratings)": 10,
    }
    conn.commit.assert_called_once()
    # A regression that dropped enrich_counts (or backfilled) from
    # result["rows"] would still pass the assertion above -- that dict
    # never includes result["rows"] at all, it's a separate value handed
    # to track_run's own tracking, not part of run()'s return value.
    # diff_count is deliberately excluded from this total, matching
    # elo_rows' own established exclusion: both diff.compute() and
    # elo.compute_ratings() touch every row on every run, not just
    # newly-written ones (PR review, Kilo -- see run()'s own comment).
    # feature_counts(10) + enrich_counts(6) + log5(3) + elo(4) + gbm(5) +
    # markov(8) + market(1) + backfilled(2) = 39.
    assert tracked["rows"] == 39


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


def test_update_skip_excludes_the_named_connector(monkeypatch, capsys):
    # `mlb update --skip mlb_api` is how scripts/mlb_daily_update.sh avoids
    # the daily run fighting the every-5-min mlb_api_update cron for the
    # mlb_api ingestion lock (spec 2026-08-28, Phase 0.2).
    one, two = _fake_connector(), _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"one": one, "two": two})

    cli.main(["update", "--skip", "two"])

    one.update.assert_called_once()
    two.update.assert_not_called()


def test_update_skip_is_repeatable(monkeypatch, capsys):
    one, two, three = _fake_connector(), _fake_connector(), _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"one": one, "two": two, "three": three})

    cli.main(["update", "--skip", "two", "--skip", "three"])

    one.update.assert_called_once()
    two.update.assert_not_called()
    three.update.assert_not_called()


def test_update_skip_unknown_connector_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cli, "CONNECTORS", {"one": _fake_connector()})
    with pytest.raises(SystemExit) as exc:
        cli.main(["update", "--skip", "nope"])
    assert exc.value.code == 2
    assert "no known connector" in capsys.readouterr().out


def test_update_skipping_every_connector_is_a_clean_no_op(monkeypatch, capsys):
    # --skip covering every connector leaves `groups` empty;
    # ThreadPoolExecutor(max_workers=0) would raise ValueError. Must be a
    # controlled no-op instead (codex/coderabbit review, PR #85).
    one = _fake_connector()
    monkeypatch.setattr(cli, "CONNECTORS", {"one": one})

    cli.main(["update", "--skip", "one"])

    one.update.assert_not_called()
    assert "nothing to do" in capsys.readouterr().out


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
    # concurrent finishes in roughly one sleep's worth of time.
    assert total < 0.6
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


def test_backup_keep_flag_rotates_after_a_successful_full_backup(monkeypatch, tmp_path, capsys):
    dump_path = tmp_path / "mlb_20260101T000000Z.sql"
    monkeypatch.setattr(backup, "backup", lambda *a, **k: dump_path)
    deleted = [tmp_path / "mlb_20251201T000000Z.sql"]
    rotate_mock = MagicMock(return_value=deleted)
    monkeypatch.setattr(backup, "rotate_backups", rotate_mock)

    cli.main(["backup", "--output-dir", str(tmp_path), "--keep", "3"])

    rotate_mock.assert_called_once()
    assert rotate_mock.call_args.kwargs["keep"] == 3
    assert "Rotated 1 old backup(s)" in capsys.readouterr().out


def test_backup_without_keep_flag_does_not_rotate(monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "backup", lambda *a, **k: tmp_path / "mlb_20260101T000000Z.sql")
    rotate_mock = MagicMock()
    monkeypatch.setattr(backup, "rotate_backups", rotate_mock)

    cli.main(["backup", "--output-dir", str(tmp_path)])

    rotate_mock.assert_not_called()


def test_backup_schema_only_with_keep_flag_does_not_rotate(monkeypatch, tmp_path):
    # --keep exists to bound the automated full-backup cron's disk usage --
    # applying it to an ad-hoc --schema-only dump would be a no-op at best
    # (nothing schema-only matches rotate_backups' full-backup pattern
    # anyway) and confusing at worst, so the CLI skips the call outright.
    monkeypatch.setattr(
        backup, "backup", lambda *a, **k: tmp_path / "mlb_schema_20260101T000000Z.sql"
    )
    rotate_mock = MagicMock()
    monkeypatch.setattr(backup, "rotate_backups", rotate_mock)

    cli.main(["backup", "--output-dir", str(tmp_path), "--schema-only", "--keep", "3"])

    rotate_mock.assert_not_called()


def test_backup_scoped_with_keep_flag_does_not_rotate(monkeypatch, tmp_path):
    # Same reasoning as the --schema-only case: a --schema-scoped dump
    # can't restore the whole database, so --keep must not treat it as a
    # rotatable full backup either.
    monkeypatch.setattr(
        backup, "backup", lambda *a, **k: tmp_path / "mlb_scoped_20260101T000000Z.sql"
    )
    rotate_mock = MagicMock()
    monkeypatch.setattr(backup, "rotate_backups", rotate_mock)

    cli.main(["backup", "--output-dir", str(tmp_path), "--schema", "raw", "--keep", "3"])

    rotate_mock.assert_not_called()


def test_backup_keep_zero_is_rejected_before_running_pg_dump(monkeypatch, tmp_path):
    # keep=0 would delete every full backup rotate_backups() itself already
    # rejects (ValueError) -- but that check happening only inside
    # rotate_backups() means a real, possibly multi-GB backup() call would
    # run to completion first, for nothing, before the error surfaces.
    backup_mock = MagicMock()
    monkeypatch.setattr(backup, "backup", backup_mock)

    try:
        cli.main(["backup", "--output-dir", str(tmp_path), "--keep", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected --keep 0 to be rejected")

    backup_mock.assert_not_called()


# Regression coverage for the calculator-style subcommands added alongside
# BULLPEN-BRIDGE-01/LINEUP-PROTECT-01/SWING-TEMPO-01/SPRAY-HEATMAP-01: these
# went straight through cli.main() with only their underlying engine classes
# unit-tested, so a missing `import dataclasses` in cli.py's --json branches
# shipped undetected. See CLAUDE.md Testing: every new subcommand needs a
# dispatch-level test through real argparse.


def test_lineup_protect_command_parses_all_its_own_arguments(capsys):
    cli.main(
        ["lineup-protect", "--woba", "0.340", "--zone", "48.0", "--fstrike", "62.0", "--pa", "150"]
    )
    assert "PII Score" in capsys.readouterr().out


def test_lineup_protect_command_json_output(capsys):
    cli.main(["lineup-protect", "--json"])
    out = capsys.readouterr().out
    assert '"pii_score"' in out
    assert '"protection_tier"' in out


def test_bullpen_bridge_command_parses_all_its_own_arguments(capsys):
    cli.main(
        [
            "bullpen-bridge",
            "--hold",
            "70.0",
            "--leverage",
            "55.0",
            "--inherited",
            "25.0",
            "--innings",
            "90.0",
        ]
    )
    assert (
        "BRIDGE_SEQUENCING" in capsys.readouterr().out or "BRIDGE_CHAIN" in capsys.readouterr().out
    )


def test_bullpen_bridge_command_json_output_matches_its_own_defaults(capsys):
    # Regression test: the --inherited default (30.0, printed in its own
    # --help text) must equal the formula's own anchor, or a neutral/default
    # bullpen reads as near-elite (bsei_score) while being tagged "average"
    # (bridge_tier) at the same time -- see ADR-256 fix.
    cli.main(["bullpen-bridge", "--json"])
    out = capsys.readouterr().out
    assert '"bsei_score": 100.0' in out
    assert '"bridge_tier": "AVERAGE_BRIDGE_SEQUENCING"' in out


def test_swing_tempo_command_parses_all_its_own_arguments(capsys):
    cli.main(
        [
            "swing-tempo",
            "--std",
            "2.0",
            "--consistency",
            "95.0",
            "--contact",
            "80.0",
            "--swings",
            "250",
        ]
    )
    assert "STCI Score" in capsys.readouterr().out


def test_swing_tempo_command_json_output(capsys):
    cli.main(["swing-tempo", "--json"])
    out = capsys.readouterr().out
    assert '"stci_score"' in out
    assert '"tempo_tier"' in out


def test_spray_heatmap_command_parses_all_its_own_arguments(capsys):
    cli.main(["spray-heatmap", "--title", "Test Chart", "--batter", "Test Batter", "--hand", "R"])
    assert "Generated Vector SVG Spray Chart Heatmap" in capsys.readouterr().out


# Regression coverage for the ~130 calculator-style subcommands (pure-Python
# scoring engines with no DB/network I/O) added across the recent package
# batch. None of these had any dispatch-level test before this pass, which is
# exactly the gap that let a missing `import dataclasses` in cli.py ship
# undetected (see the lineup-protect/bullpen-bridge/swing-tempo tests above).
# Each of these runs through real argparse via cli.main() with its own bare
# defaults and asserts it doesn't crash and produces output -- a deliberately
# lighter check than a full-argument test, sized to their number.
CALCULATOR_STYLE_COMMANDS = [
    "active-spin",
    "aging",
    "air-trap",
    "ambush",
    "arm",
    "arm-accuracy",
    "arm-align",
    "arm-slot",
    "arsenal",
    "attack-9x9",
    "babip",
    "barrel-grid",
    "blast-angle",
    "block",
    "block-suppress",
    "break-diamond",
    "break-plot",
    "bullpen",
    "bullpen-opt",
    "bunt",
    "bunt-charge",
    "bvp",
    "carry",
    "catcher-pop",
    "catch-prob",
    "catch-xchg",
    "chase-recog",
    "cluster",
    "clutch",
    "contact-depth",
    "count",
    "damage",
    "decision",
    "dp-footwork",
    "entropy",
    "exp-resist",
    "extension",
    "ext-perceive",
    "fatigue",
    "fatigue-drop",
    "first-pitch-ambush",
    "first-step",
    "flight-3d",
    "flow-mix",
    "foul-attrition",
    "fstrike",
    "gyro-spin",
    "haa",
    "heat-check",
    "heatmap",
    "hedge",
    "hexbin",
    "high-heat",
    "iffb",
    "intent-leak",
    "la-ev-contour",
    "lead-snap",
    "leverage",
    "low-scoop",
    "matchup-card",
    "neural",
    "nrfi",
    "odds-chart",
    "oppo-gap",
    "oppo-liner",
    "outfield-target",
    "parlay",
    "pivot-dp",
    "platoon",
    "polar-compass",
    "pop-time",
    "pull-air",
    "pull-barrel",
    "pull-gb",
    "pull-slice",
    "putaway",
    "putaway-depth",
    "putaway-exec",
    "radar",
    "re24-heatmap",
    "rel-drift",
    "release-box",
    "research",
    "route-burst",
    "score-flow",
    "separation-plot",
    "serve-api",
    "shift",
    "shop",
    "slash-oppo",
    "slot-sag",
    "spin",
    "spin-align",
    "spin-clock",
    "spin-polar",
    "spray",
    "spray-iso",
    "spray-rose",
    "ssw",
    "ssw-latent",
    "steal",
    "stuff",
    "sub",
    "sweetspot",
    "travel",
    "tto",
    "tunnel",
    "tunnel-box",
    "tunnel-decision",
    "two-strike",
    "umpire",
    "vaa",
    "vaa-toz",
    "velo-delta",
    "velo-drift",
    "visual",
    "wall",
    "wall-block",
    "wall-crash",
    "wall-leap",
    "weather",
    "wpa",
    "wpa-replay",
    "xslg",
    "zone-isometric",
    "zone-surface",
    "zone-swing",
    "zone-whiff",
]


@pytest.mark.parametrize("cmd", CALCULATOR_STYLE_COMMANDS)
def test_calculator_style_command_runs_with_bare_defaults(cmd, capsys):
    cli.main([cmd])
    assert capsys.readouterr().out.strip()


# Dispatch coverage for the remaining subcommands that touch the database,
# call a heavy multi-phase pipeline, or are destructive. These are mocked at
# the same seam the existing predict/conform/migrate tests use (the real
# function each handler calls), never by faking SQL results through a real
# connection -- see CLAUDE.md's DATABASE_URL safety rule. A bare
# `cli.main([cmd])` was deliberately NOT used to probe these (one such probe,
# run outside pytest, hit real production `mlb` via `mlb doctor` before this
# file existed -- harmless since doctor.py is read-only, but the wrong way to
# find that out). Every command below is exercised only inside pytest, whose
# conftest.py already redirects DATABASE_URL to a disposable per-run test
# database before any test module is imported.


def test_calibrate_command_pure_calculation_path_touches_no_db(capsys):
    # --prob takes the pure-Python HFA adjustment path; the DB-reading branch
    # (bare `mlb calibrate`) is covered separately below with a mock.
    cli.main(["calibrate", "--prob", "0.55"])
    out = capsys.readouterr().out
    assert "HOME FIELD ADVANTAGE RECALIBRATION" in out


def test_calibrate_command_db_path_handles_no_predictions_found(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = MagicMock()
    cur.__enter__.return_value = cur
    cur.fetchall.return_value = []
    conn.cursor.return_value = cur
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)

    cli.main(["calibrate"])

    assert "No completed evaluated predictions found" in capsys.readouterr().out


def _fake_daily_briefing_report(**overrides):
    from mlb_baseball.daily import DailyBriefingReport
    from mlb_baseball.model.portfolio import PortfolioAllocationPlan

    defaults = dict(
        target_date="2026-08-25",
        health_status=[],
        matchups=[],
        pitcher_props=[],
        portfolio_plan=PortfolioAllocationPlan(
            total_bankroll_usd=10000.0,
            total_allocated_usd=0.0,
            total_exposure_pct=0.0,
            expected_portfolio_growth_rate=0.0,
            recommendations=[],
        ),
        generated_at="2026-08-25T00:00:00Z",
    )
    defaults.update(overrides)
    return DailyBriefingReport(**defaults)


def test_daily_command_renders_an_empty_briefing(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        "mlb_baseball.daily.generate_daily_briefing",
        lambda **kwargs: _fake_daily_briefing_report(),
    )

    cli.main(["daily", "--json"])

    out = capsys.readouterr().out
    assert '"target_date": "2026-08-25"' in out


def test_export_command_relation_dispatch(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    calls = []
    monkeypatch.setattr(
        "mlb_baseball.export.export_relation",
        lambda c, relation, format, out_path, season: (
            calls.append((relation, format, out_path, season)) or ("gold.game_export.csv", 42)
        ),
    )

    cli.main(
        ["export", "gold.game_export", "--season", "2024", "--format", "csv", "--out", "test.csv"]
    )

    assert calls == [("gold.game_export", "csv", "test.csv", 2024)]
    out = capsys.readouterr().out
    assert "Exported 42 rows to gold.game_export.csv" in out


def test_export_command_profile_dispatch(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    calls = []
    monkeypatch.setattr(
        "mlb_baseball.export.export_bundle",
        lambda c, profile, out_dir, make_zip: (
            calls.append((profile, out_dir, make_zip)) or "export_bundle.zip"
        ),
    )

    cli.main(["export", "--profile", "public_safe", "--out", "bundle_dir", "--zip"])

    assert calls == [("public_safe", "bundle_dir", True)]
    out = capsys.readouterr().out
    assert "Exported public_safe bundle to export_bundle.zip" in out


def test_export_command_preset_dispatch(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    calls = []
    monkeypatch.setattr(
        "mlb_baseball.export.export_backbone_bundle",
        lambda c, out_dir: calls.append(out_dir) or "backbone_bundle",
    )

    cli.main(["export", "--preset", "backbone", "--out", "bundle_dir"])

    assert calls == ["bundle_dir"]
    out = capsys.readouterr().out
    assert "Exported backbone preset bundle to backbone_bundle" in out


def test_export_command_preset_publish_dispatch(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        "mlb_baseball.export.export_backbone_bundle", lambda c, out_dir: "backbone_bundle"
    )
    publish_calls = []
    monkeypatch.setattr(
        "mlb_baseball.publish.publish_backbone_bundle",
        lambda bundle_dir, tag: (
            publish_calls.append((bundle_dir, tag)) or "https://hf.co/commit/abc"
        ),
    )

    cli.main(["export", "--preset", "backbone", "--publish", "hf", "--tag", "v0.1.0"])

    assert publish_calls == [("backbone_bundle", "v0.1.0")]
    out = capsys.readouterr().out
    assert "Published to Hugging Face (revision=v0.1.0): https://hf.co/commit/abc" in out


def test_export_command_preset_publish_passes_custom_repo_id(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        "mlb_baseball.export.export_backbone_bundle", lambda c, out_dir: "backbone_bundle"
    )
    publish_calls = []
    monkeypatch.setattr(
        "mlb_baseball.publish.publish_backbone_bundle",
        lambda bundle_dir, **kwargs: (
            publish_calls.append((bundle_dir, kwargs)) or "https://hf.co/commit/abc"
        ),
    )

    cli.main(
        [
            "export",
            "--preset",
            "backbone",
            "--publish",
            "hf",
            "--tag",
            "v0.1.0",
            "--repo-id",
            "someorg/mlb-research",
        ]
    )

    assert publish_calls == [
        ("backbone_bundle", {"tag": "v0.1.0", "repo_id": "someorg/mlb-research"})
    ]


def test_export_command_publish_without_tag_errors(capsys):
    with pytest.raises(SystemExit):
        cli.main(["export", "--preset", "backbone", "--publish", "hf"])


def test_export_command_publish_without_preset_errors(capsys):
    with pytest.raises(SystemExit):
        cli.main(["export", "--publish", "hf", "--tag", "v0.1.0"])


def test_export_command_preset_zip_errors(capsys):
    with pytest.raises(SystemExit):
        cli.main(["export", "--preset", "backbone", "--zip"])


def test_export_command_missing_args_exits(capsys):
    with pytest.raises(SystemExit):
        cli.main(["export"])


def test_serve_command_daily_grid_mart(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr("mlb_baseball.serve.fetch_daily_betting_grid", lambda game_date, conn: [])

    cli.main(["serve", "daily-grid"])

    assert "Serving Mart: serve.daily-grid (0 rows)" in capsys.readouterr().out


def test_season_sim_command_falls_back_to_synthetic_schedule(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr("mlb_baseball.model.season.load_schedule_from_db", lambda season, conn: [])

    cli.main(["season-sim", "--sims", "10"])

    assert "Monte Carlo Simulation" in capsys.readouterr().out


def test_player_id_command_parses_all_its_own_arguments(monkeypatch, capsys):
    monkeypatch.setattr(
        "mlb_baseball.player.print_crosswalk",
        lambda id_type, id_value: print(f"looked up {id_type}={id_value}"),
    )

    cli.main(["player-id", "mlbam", "660271"])

    assert "looked up mlbam=660271" in capsys.readouterr().out


def test_kelly_command_handles_no_market_alpha_found(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        "mlb_baseball.serve.fetch_prediction_market_alpha", lambda min_edge, conn: []
    )

    cli.main(["kelly"])

    assert capsys.readouterr().out.strip()


def test_drift_command_parses_all_its_own_arguments(monkeypatch, capsys):
    from types import SimpleNamespace

    from mlb_baseball.model.drift import DriftSeverity

    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    fake_report = SimpleNamespace(
        model_version="gbm-v1",
        total_evaluated_games=0,
        overall_brier_score=0.0,
        overall_ece=0.0,
        current_status=DriftSeverity.HEALTHY,
        alerts=[],
        windows=[],
    )
    monkeypatch.setattr(
        "mlb_baseball.model.drift.ModelDriftMonitor.evaluate_model_from_db",
        lambda self, model_version, conn: fake_report,
    )

    cli.main(["drift", "--window", "20", "--step", "5"])

    assert "MODEL CALIBRATION MONITOR" in capsys.readouterr().out


def test_backtest_command_parses_all_its_own_arguments(monkeypatch, capsys):
    from types import SimpleNamespace

    fake_summary = SimpleNamespace(
        start_date="2024-04-01",
        end_date="2024-04-30",
        model_version="gbm-v1",
        initial_bankroll_usd=10000.0,
        final_bankroll_usd=10000.0,
        total_wagers=0,
        winning_wagers=0,
        losing_wagers=0,
        win_rate_pct=0.0,
        total_wagered_usd=0.0,
        total_pnl_usd=0.0,
        roi_pct=0.0,
        annualized_sharpe_ratio=0.0,
        max_drawdown_pct=0.0,
        mean_clv_pct=0.0,
        brier_score=0.0,
        wager_history=[],
    )
    monkeypatch.setattr(
        "mlb_baseball.model.backtest.WalkForwardBacktester.run_backtest",
        lambda self, start_date, end_date, model_version, initial_bankroll: fake_summary,
    )

    cli.main(["backtest", "--start-date", "2024-04-01", "--end-date", "2024-04-30"])

    assert "HISTORICAL WALK-FORWARD BACKTEST SUMMARY" in capsys.readouterr().out


def test_ros_command_parses_all_its_own_arguments(monkeypatch, capsys):
    from types import SimpleNamespace

    fake_report = SimpleNamespace(
        season=2024,
        as_of_date="2024-08-01",
        simulations_count=10,
        team_projections=[],
    )
    monkeypatch.setattr(
        "mlb_baseball.model.ros.RestOfSeasonSimulator.simulate_ros",
        lambda self, season, as_of_date, n_sims: fake_report,
    )

    cli.main(["ros", "--sims", "10"])

    assert "REST-OF-SEASON" in capsys.readouterr().out


def test_backfill_game_identities_command_parses_all_its_own_arguments(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        "mlb_baseball.model.identity.backfill_game_instance_keys",
        lambda conn, batch_size: {"core.game": 0},
    )

    cli.main(["backfill-game-identities", "--batch-size", "500"])

    assert "core.game=0" in capsys.readouterr().out


def test_repair_runs_command_reports_no_stale_runs(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr("mlb_baseball.ingest.reap_stale_runs", lambda conn: [])

    cli.main(["repair-runs"])

    assert "no stale ingestion runs found" in capsys.readouterr().out


def test_inventory_command_parses_all_its_own_arguments(monkeypatch, capsys):
    monkeypatch.setattr("mlb_baseball.inventory.tables", lambda **kwargs: [])
    monkeypatch.setattr("mlb_baseball.inventory.last_runs", lambda: [])

    cli.main(["inventory"])

    assert "Last run per source:" in capsys.readouterr().out


def test_schema_command_calls_schema_inventory_print_report(monkeypatch, capsys):
    monkeypatch.setattr(
        "mlb_baseball.schema_inventory.print_report",
        lambda **kwargs: print("schema report"),
    )

    cli.main(["schema"])

    assert "schema report" in capsys.readouterr().out


def test_simulate_command_handles_no_transition_data(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        "mlb_baseball.model.markov.estimate_outcome_distribution", lambda conn, seasons: {}
    )

    try:
        cli.main(["simulate"])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit(1) with no transition data")

    assert "No Retrosheet transition data" in capsys.readouterr().out


def test_live_command_handles_no_transition_data(monkeypatch, capsys):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    monkeypatch.setattr("mlb_baseball.db.get_connection", lambda: conn)
    monkeypatch.setattr(
        "mlb_baseball.model.markov.estimate_outcome_distribution", lambda conn, seasons: {}
    )

    try:
        cli.main(["live"])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit(1) with no transition data")

    assert "No Retrosheet transition data" in capsys.readouterr().out


def test_props_command_with_bare_defaults_prints_usage_hint(capsys):
    # Neither --game-pk nor --pitcher-k given -> the safe, DB-free branch.
    cli.main(["props"])

    assert "Please provide --game-pk or --pitcher-k" in capsys.readouterr().out


def test_stack_command_with_bare_defaults_reports_no_trained_model(monkeypatch, capsys):
    from pathlib import Path

    monkeypatch.setattr("mlb_baseball.model.stack.MODEL_PATH", Path("/nonexistent/stack.json"))

    cli.main(["stack"])

    assert "No trained stack model found" in capsys.readouterr().out


def test_doctor_command_reports_all_checks_passed(monkeypatch, capsys):
    monkeypatch.setattr("mlb_baseball.doctor.run", lambda: [])

    cli.main(["doctor"])

    assert "0/0 checks passed" in capsys.readouterr().out


def test_pipeline_command_parses_all_its_own_arguments(monkeypatch, capsys):
    from mlb_baseball.pipeline import MasterPipelineReport

    fake_report = MasterPipelineReport(
        run_id="pipeline_test",
        target_date="2026-08-25",
        overall_success=True,
        total_duration_seconds=0.01,
        phases=[],
        alerts=[],
    )
    monkeypatch.setattr(
        "mlb_baseball.pipeline.MasterDailyPipeline.execute_daily_cycle",
        lambda self, target_date, n_sims, bankroll_usd: fake_report,
    )

    cli.main(["pipeline", "--skip-doctor", "--json"])

    assert '"run_id": "pipeline_test"' in capsys.readouterr().out


def test_daemon_command_parses_all_its_own_arguments(monkeypatch, capsys):
    from mlb_baseball.daemon import DaemonRunSummary

    fake_summary = DaemonRunSummary(
        execution_timestamp="2026-08-25",
        pipeline_status="SUCCESS",
        pipeline_duration_s=0.01,
        cache_warming_time_ms=0.0,
        visual_assets_baked=2,
        alerts=[],
    )
    monkeypatch.setattr(
        "mlb_baseball.daemon.DailyAutomationDaemon.execute_daily_cycle",
        lambda self, date_str, skip_doctor: fake_summary,
    )

    cli.main(["daemon", "--skip-doctor", "--json"])

    assert '"pipeline_status": "SUCCESS"' in capsys.readouterr().out


def test_restore_command_refuses_without_yes_flag(tmp_path, capsys):
    dump_file = tmp_path / "backup.dump"
    dump_file.write_text("fake dump content")

    try:
        cli.main(["restore", str(dump_file)])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected --yes to be required")

    assert "without --yes" in capsys.readouterr().err


def test_restore_command_with_yes_calls_backup_restore_not_real_pg_restore(
    monkeypatch, tmp_path, capsys
):
    dump_file = tmp_path / "backup.dump"
    dump_file.write_text("fake dump content")
    calls = []
    monkeypatch.setattr(
        cli.backup,
        "restore",
        lambda database_url, dump_path, confirm: calls.append((dump_path, confirm)),
    )
    monkeypatch.setattr(cli.backup, "dbname", lambda database_url: "mlb_test_fake")

    cli.main(["restore", str(dump_file), "--yes"])

    assert calls == [(dump_file, True)]
    assert "Restore complete." in capsys.readouterr().out
