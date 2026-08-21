"""Integration tests for feature-selection stability reports against real Postgres (mlb_test)."""

# ruff: noqa: E501

from pathlib import Path

import pytest

from mlb_baseball import cli
from mlb_baseball.db import get_connection
from mlb_baseball.model import experiment, feature_select


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
        # raw.mlb_schedule is DROPped, not just scoped-DELETEd (issue #9
        # item 5) -- see test_experiment.py's identical _reset for the
        # full explanation. _seed() below already recreates it fresh
        # (CREATE TABLE IF NOT EXISTS) when missing.
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
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


def test_select_features_classification_end_to_end_and_idempotent(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    artifact_dir = tmp_path / "artifacts"
    result1 = feature_select.select_features(
        db_conn,
        snapshot_id,
        n_repeats=5,
        seed=42,
        fold_years=(2016, 2017),
        artifact_dir=artifact_dir,
    )
    db_conn.commit()

    assert result1["status"] == "success"
    assert result1["reused"] is False
    assert result1["target"] == "home_win"
    assert result1["total_folds_evaluated"] == 2
    assert len(result1["features"]) == 11
    for _feat_name, summary in result1["features"].items():
        assert "stage1_survived_folds" in summary
        assert "stage2_survived_folds" in summary
        assert "both_stages_survived_folds" in summary
        assert "stage1_by_fold" in summary
        assert "stage2_by_fold" in summary
        assert "both_by_fold" in summary

    # Verify database persistence
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT selection_id, status, error, artifact_uri, artifact_sha256 FROM meta.feature_selection WHERE selection_id = %s",
            (result1["selection_id"],),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[1] == "success"
        assert row[2] is None
        assert row[3] is not None
        assert Path(row[3]).exists()

    # Rerun idempotency test
    result2 = feature_select.select_features(
        db_conn,
        snapshot_id,
        n_repeats=5,
        seed=42,
        fold_years=(2016, 2017),
        artifact_dir=artifact_dir,
    )
    assert result2["status"] == "success"
    assert result2["reused"] is True
    assert result2["selection_id"] == result1["selection_id"]

    # Verify no duplicate rows
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM meta.feature_selection")
        assert cur.fetchone()[0] == 1


def test_select_features_regression_end_to_end(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="run_differential")
    db_conn.commit()

    artifact_dir = tmp_path / "artifacts"
    result = feature_select.select_features(
        db_conn,
        snapshot_id,
        n_repeats=5,
        seed=42,
        fold_years=(2016, 2017),
        artifact_dir=artifact_dir,
    )
    db_conn.commit()

    assert result["status"] == "success"
    assert result["reused"] is False
    assert result["target"] == "run_differential"
    assert result["method_config"]["stage1_estimator"] == "ridge"
    assert result["method_config"]["stage2_estimator"] == "xgboost_regressor"
    assert result["method_config"]["scoring"] == "neg_mean_absolute_error"
    assert result["total_folds_evaluated"] == 2
    assert len(result["features"]) == 11


def test_cli_select_features(db_conn, tmp_path, monkeypatch, capsys):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    monkeypatch.setattr(
        "sys.argv",
        [
            "mlb",
            "experiment",
            "select-features",
            "--snapshot",
            snapshot_id,
            "--n-repeats",
            "5",
            "--fold-years",
            "2016",
            "2017",
        ],
    )
    cli.main()
    captured = capsys.readouterr()
    assert "feature_selection:" in captured.out
    assert "home_wins: stage1:" in captured.out
    assert "away_wins: stage1:" in captured.out


def test_failed_feature_select_is_recorded_through_connection_context_manager(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()

    artifact_dir = tmp_path / "artifacts"
    # Regression: run through with get_connection() as conn: to exercise real CLI
    # context-manager exit semantics. n_repeats=0 raises ValueError inside permutation_importance,
    # and _finalize_failed_run must commit before re-raising so the failed status persists.
    with pytest.raises(ValueError, match="n_repeats"):
        with get_connection() as conn:
            feature_select.select_features(
                conn,
                snapshot_id,
                n_repeats=0,
                seed=42,
                fold_years=(2016,),
                artifact_dir=artifact_dir,
            )
    # Deliberately no db_conn.commit() here.

    with db_conn.cursor() as cur:
        cur.execute("SELECT status, error FROM meta.feature_selection")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "failed"
        assert "n_repeats" in (rows[0][1] or "")
    _reset(db_conn)
