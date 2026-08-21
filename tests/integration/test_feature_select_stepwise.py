"""Integration tests for forward-stepwise feature selection against real Postgres (mlb_test)."""

# ruff: noqa: E501

from pathlib import Path

import pytest

from mlb_baseball import cli
from mlb_baseball.db import get_connection
from mlb_baseball.model import experiment, feature_select_stepwise


def _reset(conn):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('meta.feature_selection_stepwise')")
        if cur.fetchone()[0] is not None:
            cur.execute("TRUNCATE meta.feature_selection_stepwise CASCADE")
        cur.execute("TRUNCATE meta.feature_selection CASCADE")
        cur.execute("TRUNCATE meta.experiment_snapshot CASCADE")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if cur.fetchone()[0] is not None:
            cur.execute("DELETE FROM raw.mlb_schedule WHERE game_id LIKE 'experiment-%'")
    conn.commit()


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.mlb_schedule (
                game_id text, _season text, game_date text, game_type text,
                status text, home_id text, away_id text, game_num text, venue_id text
            )
            """
        )
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('AAA', 'Alpha', 'Aces', 1900, 2030), ('BBB', 'Beta', 'Bats', 1900, 2030) "
            "RETURNING id"
        )
        home, away = [row[0] for row in cur.fetchall()]
        for season, game_count in ((2015, 8), (2016, 8), (2017, 8), (2018, 1)):
            for number in range(1, game_count + 1):
                pk = str(season * 100 + number)
                home_win = number % 2 == 0
                home_score, away_score = (5, 3) if home_win else (2, 4)
                game_date = f"{season}-04-02" if number in (2, 3) else f"{season}-04-{number:02d}"
                game_number = number - 1 if number in (2, 3) else number
                cur.execute(
                    "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, game_number, "
                    "home_team_id, away_team_id, home_score, away_score, game_type) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'regular') RETURNING id",
                    (
                        f"G{pk}",
                        pk,
                        season,
                        game_date,
                        game_number,
                        home,
                        away,
                        home_score,
                        away_score,
                    ),
                )
                (game_id,) = cur.fetchone()
                prior = 7 if season == 2018 else (None if number == 1 else number - 1)
                rate = None if prior is None else 0.5
                cur.execute(
                    "INSERT INTO gold.game_feature (game_id, mlb_game_pk, game_instance_key, season, "
                    "game_date, game_number, feature_cutoff_at, home_team_id, away_team_id, home_win, "
                    "home_wins, home_losses, away_wins, away_losses, home_runs_for, home_runs_allowed, "
                    "away_runs_for, away_runs_allowed, home_rest, away_rest, home_field, home_win_pct, "
                    "away_win_pct) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, true, %s, %s)",
                    (
                        game_id,
                        pk,
                        f"mlb:{pk}",
                        season,
                        game_date,
                        game_number,
                        f"{game_date}T{12 + number:02d}:00:00Z",
                        home,
                        away,
                        home_win,
                        prior // 2 if prior is not None else None,
                        prior - (prior // 2) if prior is not None else None,
                        prior - (prior // 2) if prior is not None else None,
                        prior // 2 if prior is not None else None,
                        prior * 4 if prior is not None else None,
                        prior * 4 if prior is not None else None,
                        prior * 4 if prior is not None else None,
                        prior * 4 if prior is not None else None,
                        1,
                        1,
                        rate,
                        rate,
                    ),
                )
    conn.commit()


def test_select_features_stepwise_classification_end_to_end_and_idempotent(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    artifact_dir = tmp_path / "artifacts_stepwise"
    result1 = feature_select_stepwise.select_features_stepwise(
        db_conn,
        snapshot_id,
        seed=42,
        fold_years=(2016, 2017, 2018),
        min_survival_fraction=0.30,
        artifact_dir=artifact_dir,
    )
    db_conn.commit()

    assert result1["status"] == "success"
    assert result1["reused"] is False
    assert result1["target"] == "home_win"
    assert result1["total_folds_evaluated"] == 2
    assert len(result1["candidate_features"]) >= 1

    # Verify fold results and empty-inner-data skip path
    folds_res = result1["folds"]
    assert "season-2016" in folds_res
    assert folds_res["season-2016"]["skipped"] is True
    assert folds_res["season-2016"]["reason"] == "insufficient inner-split data"

    assert "season-2017" in folds_res
    assert folds_res["season-2017"]["skipped"] is False
    assert "selected" in folds_res["season-2017"]
    assert len(folds_res["season-2017"]["trace"]) >= 1

    assert "season-2018" in folds_res
    assert folds_res["season-2018"]["skipped"] is False
    assert "selected" in folds_res["season-2018"]
    assert len(folds_res["season-2018"]["trace"]) >= 1

    # Verify database persistence
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT selection_id, status, error, artifact_uri, artifact_sha256 FROM meta.feature_selection_stepwise WHERE selection_id = %s",
            (result1["selection_id"],),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[1] == "success"
        assert row[2] is None
        assert row[3] is not None
        assert Path(row[3]).exists()

    # Rerun idempotency test
    result2 = feature_select_stepwise.select_features_stepwise(
        db_conn,
        snapshot_id,
        seed=42,
        fold_years=(2016, 2017, 2018),
        min_survival_fraction=0.30,
        artifact_dir=artifact_dir,
    )
    assert result2["status"] == "success"
    assert result2["reused"] is True
    assert result2["selection_id"] == result1["selection_id"]

    # Verify no duplicate rows in meta.feature_selection_stepwise
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM meta.feature_selection_stepwise")
        assert cur.fetchone()[0] == 1


def test_select_features_stepwise_regression_end_to_end(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="run_differential")
    db_conn.commit()

    artifact_dir = tmp_path / "artifacts_stepwise"
    result = feature_select_stepwise.select_features_stepwise(
        db_conn,
        snapshot_id,
        seed=42,
        fold_years=(2016, 2017, 2018),
        min_survival_fraction=0.30,
        artifact_dir=artifact_dir,
    )
    db_conn.commit()

    assert result["status"] == "success"
    assert result["reused"] is False
    assert result["target"] == "run_differential"
    assert result["method_config"]["probe_estimator"] == "ridge"
    assert result["method_config"]["scoring"] == "mae"
    assert result["total_folds_evaluated"] == 2
    assert len(result["candidate_features"]) >= 1

    folds_res = result["folds"]
    assert folds_res["season-2016"]["skipped"] is True
    assert folds_res["season-2017"]["skipped"] is False
    assert folds_res["season-2018"]["skipped"] is False


def test_empty_candidate_set_raises_on_integration_fixture(db_conn):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    with pytest.raises(
        experiment.ExperimentError,
        match="no candidate features survived stage 1\\+2 at the 70th-percent threshold",
    ):
        feature_select_stepwise.select_features_stepwise(
            db_conn,
            snapshot_id,
            seed=42,
            fold_years=(2016, 2017, 2018),
            min_survival_fraction=0.70,
        )


def test_cli_select_features_stepwise(db_conn, tmp_path, monkeypatch, capsys):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    monkeypatch.setattr(
        "sys.argv",
        [
            "mlb",
            "experiment",
            "select-features-stepwise",
            "--snapshot",
            snapshot_id,
            "--fold-years",
            "2016",
            "2017",
            "2018",
            "--min-survival-fraction",
            "0.30",
            "--seed",
            "42",
        ],
    )
    cli.main()
    captured = capsys.readouterr()
    assert "feature_selection_stepwise:" in captured.out
    assert "candidates" in captured.out
    assert "selected" in captured.out


def test_failed_select_features_stepwise_is_recorded_through_connection_context_manager(
    db_conn, tmp_path, monkeypatch
):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    artifact_dir = tmp_path / "artifacts_stepwise"

    def _exploding_named_matrix(*args, **kwargs):
        raise RuntimeError("simulated calculation error in stepwise search")

    monkeypatch.setattr(feature_select_stepwise, "_named_matrix", _exploding_named_matrix)

    # Regression: run through with get_connection() as conn: to exercise real CLI
    # context-manager exit semantics. _finalize_failed_run must commit before re-raising
    # so the failed status persists.
    with pytest.raises(RuntimeError, match="simulated calculation error"):
        with get_connection() as conn:
            feature_select_stepwise.select_features_stepwise(
                conn,
                snapshot_id,
                seed=42,
                fold_years=(2016, 2017, 2018),
                min_survival_fraction=0.30,
                artifact_dir=artifact_dir,
            )
    # Deliberately no db_conn.commit() here.

    with db_conn.cursor() as cur:
        cur.execute("SELECT status, error FROM meta.feature_selection_stepwise")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "failed"
        assert "simulated calculation error" in (rows[0][1] or "")
    _reset(db_conn)


def test_select_features_stepwise_skips_single_class_inner_training_split(db_conn, tmp_path):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.mlb_schedule (
                game_id text, _season text, game_date text, game_type text,
                status text, home_id text, away_id text, game_num text, venue_id text
            )
            """
        )
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('AAA', 'Alpha', 'Aces', 1900, 2030), ('BBB', 'Beta', 'Bats', 1900, 2030) "
            "RETURNING id"
        )
        home, away = [row[0] for row in cur.fetchall()]
        # 2015: All games are home wins (single class: True only)
        # 2016: Mixed wins and losses
        # 2017: Mixed wins and losses
        for season, game_count in ((2015, 8), (2016, 8), (2017, 8)):
            for number in range(1, game_count + 1):
                pk = str(season * 100 + number)
                home_win = True if season == 2015 else (number % 2 == 0)
                home_score, away_score = (5, 3) if home_win else (2, 4)
                game_date = f"{season}-04-{number:02d}"
                game_number = number
                cur.execute(
                    "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, game_number, "
                    "home_team_id, away_team_id, home_score, away_score, game_type) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'regular') RETURNING id",
                    (
                        f"G{pk}",
                        pk,
                        season,
                        game_date,
                        game_number,
                        home,
                        away,
                        home_score,
                        away_score,
                    ),
                )
                (game_id,) = cur.fetchone()
                rate = 0.5
                cur.execute(
                    "INSERT INTO gold.game_feature (game_id, mlb_game_pk, game_instance_key, season, "
                    "game_date, game_number, feature_cutoff_at, home_team_id, away_team_id, home_win, "
                    "home_wins, home_losses, away_wins, away_losses, home_runs_for, home_runs_allowed, "
                    "away_runs_for, away_runs_allowed, home_rest, away_rest, home_field, home_win_pct, "
                    "away_win_pct) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, true, %s, %s)",
                    (
                        game_id,
                        pk,
                        f"mlb:{pk}",
                        season,
                        game_date,
                        game_number,
                        f"{game_date}T12:00:00Z",
                        home,
                        away,
                        home_win,
                        2,
                        2,
                        2,
                        2,
                        8,
                        8,
                        8,
                        8,
                        1,
                        1,
                        rate,
                        rate,
                    ),
                )
    db_conn.commit()

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    artifact_dir = tmp_path / "artifacts_single_class"
    result = feature_select_stepwise.select_features_stepwise(
        db_conn,
        snapshot_id,
        seed=42,
        fold_years=(2017, 2018),
        min_survival_fraction=0.0,
        artifact_dir=artifact_dir,
    )
    db_conn.commit()

    assert result["status"] == "success"
    # season-2017's inner train is season 2015 (all home_win=True) -> skipped with reason
    assert result["folds"]["season-2017"]["skipped"] is True
    assert result["folds"]["season-2017"]["reason"] == "single-class inner-training split"
    # season-2018's inner train is seasons 2015+2016 (has both True and False) -> evaluated
    assert result["folds"]["season-2018"]["skipped"] is False
    _reset(db_conn)
