"""Real-Postgres rehearsal for immutable, calendar-safe game-win experiments."""

# ruff: noqa: E501

import json
from pathlib import Path

import pytest

from mlb_baseball import audit
from mlb_baseball.db import get_connection
from mlb_baseball.model import experiment


def _reset(conn):
    conn.rollback()
    with conn.cursor() as cur:
        # Snapshot evidence deliberately rejects row-by-row updates/deletes.
        # TRUNCATE is restricted to this isolated mlb_test fixture cleanup.
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
        # Several unrelated integration tests intentionally drop dynamic raw
        # tables. This rehearsal owns the minimum schedule fixture it needs.
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
                # Games 2 and 3 are an ordered doubleheader.  Their distinct
                # MLB keys must survive the same-date/game-number ordering.
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
                # The first game of each development season deliberately has
                # no prior record. It stays in the snapshot but is excluded
                # from the common Log5 comparison. The 2018 row is a resolved
                # future row used to prove it never enters an earlier fold.
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
        cur.execute(
            "UPDATE gold.game_feature SET day_night = 'day', temp_f = 72 "
            "WHERE mlb_game_pk = '201602'"
        )
        # Two schedule observations for one game preserve a small schedule
        # history fixture. The other doubleheader game has its own MLB key.
        cur.executemany(
            """
            INSERT INTO raw.mlb_schedule
                (game_id, _season, game_date, game_type, status, home_id, away_id, game_num, venue_id)
            VALUES (%s, '2016', '2016-04-02', 'R', %s, '1', '2', %s, NULL)
            """,
            [
                ("experiment-201602", "Postponed", "1"),
                ("experiment-201602", "Final", "1"),
                ("experiment-201603", "Final", "2"),
            ],
        )
    conn.commit()


def test_snapshot_is_content_addressed_and_survives_mutable_feature_changes(db_conn):
    _reset(db_conn)
    _seed(db_conn)

    snapshot_id = experiment.create_snapshot(db_conn)
    db_conn.commit()
    assert experiment.create_snapshot(db_conn) == snapshot_id
    db_conn.commit()
    assert db_conn.execute("SELECT count(*) FROM meta.experiment_snapshot").fetchone() == (1,)
    assert db_conn.execute(
        "SELECT count(*) FROM gold.game_feature_snapshot WHERE snapshot_id = %s", (snapshot_id,)
    ).fetchone() == (25,)

    before = db_conn.execute(
        "SELECT feature_json->>'home_wins' FROM gold.game_feature_snapshot "
        "WHERE snapshot_id = %s AND mlb_game_pk = '201502'",
        (snapshot_id,),
    ).fetchone()
    db_conn.execute("UPDATE gold.game_feature SET home_wins = 999 WHERE mlb_game_pk = '201502'")
    db_conn.commit()
    after = db_conn.execute(
        "SELECT feature_json->>'home_wins' FROM gold.game_feature_snapshot "
        "WHERE snapshot_id = %s AND mlb_game_pk = '201502'",
        (snapshot_id,),
    ).fetchone()
    assert before == after == ("0.0",)
    result = db_conn.execute(
        "UPDATE gold.game_feature_snapshot SET home_win = false "
        "WHERE snapshot_id = %s AND mlb_game_pk = '201502'",
        (snapshot_id,),
    )
    db_conn.commit()
    assert result.rowcount == 0
    assert db_conn.execute(
        "SELECT home_win FROM gold.game_feature_snapshot "
        "WHERE snapshot_id = %s AND mlb_game_pk = '201502'",
        (snapshot_id,),
    ).fetchone() == (True,)
    snapshot_finding = next(
        finding for finding in audit.run() if finding.name == "experiment snapshots"
    )
    assert snapshot_finding.status == "PASS"
    assert "not mutable" in snapshot_finding.detail
    assert experiment.snapshot_integrity(db_conn) == {
        "snapshots": 1,
        "row_hash_mismatches": 0,
        "selection_hash_mismatches": 0,
        "row_count_mismatches": 0,
    }
    assert db_conn.execute(
        "SELECT count(*) FROM raw.mlb_schedule WHERE game_id = 'experiment-201602'"
    ).fetchone() == (2,)
    assert db_conn.execute(
        "SELECT day_night, temp_f FROM gold.game_feature WHERE mlb_game_pk = '201602'"
    ).fetchone() == ("day", 72)
    assert db_conn.execute(
        "SELECT day_night, temp_f FROM gold.game_feature WHERE mlb_game_pk = '201601'"
    ).fetchone() == (None, None)
    _reset(db_conn)


@pytest.mark.parametrize("model_family", experiment.SUPPORTED_MODELS)
def test_all_supported_models_share_calendar_rehearsal_rows(db_conn, tmp_path, model_family):
    _reset(db_conn)
    _seed(db_conn)
    snapshot_id = experiment.create_snapshot(db_conn)
    config = experiment.ExperimentConfig(
        snapshot_id=snapshot_id,
        model_family=model_family,
        fold_years=(2016, 2017),
        artifact_dir=tmp_path / model_family,
    )

    first = experiment.run(db_conn, config)
    db_conn.commit()
    second = experiment.run(db_conn, config)
    db_conn.commit()

    assert first["status"] == "success"
    assert not first["reused"]
    assert second["reused"]
    assert first["aggregate"] == second["aggregate"]
    assert first["aggregate"]["rows"] == 14
    assert set(first["folds"]) == {"season-2016", "season-2017"}
    for metrics in first["folds"].values():
        assert metrics["coverage"]["common_rows"] == 22
        assert metrics["coverage"]["excluded_opening_or_missing_rate_rows"] == 3
        assert metrics["rows"] == 7
        assert 0 <= metrics["brier"] <= 1
        assert metrics["log_loss"] > 0
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT train_through_season, test_season, artifact_uri, artifact_sha256 "
            "FROM meta.experiment_fold WHERE experiment_id = %s ORDER BY test_season",
            (first["experiment_id"],),
        )
        rows = cur.fetchall()
    assert [(row[0], row[1]) for row in rows] == [(2015, 2016), (2016, 2017)]
    for _train, _test, artifact_uri, artifact_sha in rows:
        path = Path(artifact_uri)
        assert path.exists()
        assert path.name == f"{artifact_sha}.json"
    stored_aggregate = db_conn.execute(
        "SELECT metrics_json->>'rows' FROM meta.experiment WHERE experiment_id = %s",
        (first["experiment_id"],),
    ).fetchone()
    assert stored_aggregate == ("14",)
    snapshot_rows = experiment._snapshot_rows(db_conn, snapshot_id)
    assert {
        (row.mlb_game_pk, row.game_number)
        for row in snapshot_rows
        if row.game_date.isoformat() == "2016-04-02"
    } >= {
        ("201602", 1),
        ("201603", 2),
    }
    assert any(row.mlb_game_pk == "201801" for row in snapshot_rows)
    fold = experiment.folds((2017,))[0]
    train_keys = {
        row.game_instance_key
        for row in experiment._common_rows(snapshot_rows)
        if row.season <= fold.train_through_season
    }
    test_keys = {
        row.game_instance_key
        for row in experiment._common_rows(snapshot_rows)
        if row.season == fold.test_season
    }
    assert train_keys.isdisjoint(test_keys)
    assert "mlb:201801" not in train_keys | test_keys
    _reset(db_conn)


def test_failed_experiment_is_recorded_without_corrupting_success(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)
    snapshot_id = experiment.create_snapshot(db_conn)
    good = experiment.ExperimentConfig(
        snapshot_id, "home_rate", fold_years=(2016,), artifact_dir=tmp_path
    )
    success = experiment.run(db_conn, good)
    db_conn.commit()
    bad = experiment.ExperimentConfig(
        snapshot_id,
        "logistic",
        fold_years=(2016,),
        parameters={"C": -1.0},
        artifact_dir=tmp_path,
    )
    # Regression: run through with get_connection() as conn: to exercise
    # the real CLI execution path. When an exception propagates through
    # Connection.__exit__, psycopg3 calls rollback(). _finalize_failed_run
    # must commit the 'failed' row before raising, so it survives.
    with pytest.raises(ValueError, match="range"):
        with get_connection() as conn:
            experiment.run(conn, bad)
    # Deliberately no manual commit here.

    statuses = db_conn.execute("SELECT status FROM meta.experiment ORDER BY started_at").fetchall()
    assert {status[0] for status in statuses} == {"success", "failed"}
    assert db_conn.execute(
        "SELECT count(*) FROM meta.experiment_fold WHERE experiment_id = %s",
        (success["experiment_id"],),
    ).fetchone() == (1,)
    _reset(db_conn)


def test_rejects_malformed_snapshot_contract_before_fitting(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)
    snapshot_id = experiment.create_snapshot(db_conn)
    with pytest.raises(experiment.ExperimentError, match="feature set"):
        experiment.run(
            db_conn,
            experiment.ExperimentConfig(
                snapshot_id,
                "home_rate",
                fold_years=(2016,),
                feature_set_version="unapproved_v0",
                artifact_dir=tmp_path,
            ),
        )
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment.run(
            db_conn,
            experiment.ExperimentConfig(
                snapshot_id,
                "logistic",
                fold_years=(2016,),
                parameters={"mistyped_parameter": 1},
                artifact_dir=tmp_path,
            ),
        )
    _reset(db_conn)


def test_failed_run_can_resume_same_declared_configuration(db_conn, tmp_path):
    _reset(db_conn)
    _seed(db_conn)
    snapshot_id = experiment.create_snapshot(db_conn)
    config = experiment.ExperimentConfig(
        snapshot_id, "home_rate", fold_years=(2016,), artifact_dir=tmp_path
    )
    experiment_id = experiment._experiment_id(config)
    fold_plan = [{"name": "season-2016", "train_through_season": 2015, "test_season": 2016}]
    db_conn.execute(
        """
        INSERT INTO meta.experiment (
            experiment_id, snapshot_id, target, source_profile, fold_plan_json,
            model_family, parameters_json, seed, calibration, status, error
        ) VALUES (%s, %s, 'home_win', %s, %s, 'home_rate', '{}', 0, 'none', 'failed', 'simulated')
        """,
        (experiment_id, snapshot_id, config.source_profile, json.dumps(fold_plan)),
    )
    db_conn.commit()

    resumed = experiment.run(db_conn, config)
    db_conn.commit()

    assert resumed["status"] == "success"
    assert not resumed["reused"]
    assert db_conn.execute(
        "SELECT status, error FROM meta.experiment WHERE experiment_id = %s", (experiment_id,)
    ).fetchone() == ("success", None)
    _reset(db_conn)


def test_row_sha256_uniqueness_across_targets(db_conn):
    _reset(db_conn)
    _seed(db_conn)

    hw_id = experiment.create_snapshot(db_conn, target="home_win")
    db_conn.commit()
    rd_id = experiment.create_snapshot(db_conn, target="run_differential")
    db_conn.commit()

    assert hw_id != rd_id
    assert hw_id.startswith(f"{experiment.FEATURE_SET_VERSION}:home_win:")
    assert rd_id.startswith(f"{experiment.FEATURE_SET_VERSION}:run_differential:")

    # Both snapshot IDs independently reuse their existing database record
    assert experiment.create_snapshot(db_conn, target="home_win") == hw_id
    assert experiment.create_snapshot(db_conn, target="run_differential") == rd_id

    with db_conn.cursor() as cur:
        cur.execute("SELECT target, row_sha256 FROM meta.experiment_snapshot ORDER BY target")
        records = cur.fetchall()
    assert len(records) == 2
    assert records[0][0] == "home_win"
    assert records[1][0] == "run_differential"
    # Content hash is identical because underlying rows are identical
    assert records[0][1] == records[1][1]

    # Rejection of unregistered target
    with pytest.raises(experiment.ExperimentError, match="unsupported target"):
        experiment.create_snapshot(db_conn, target="unknown_target")

    _reset(db_conn)


@pytest.mark.parametrize(
    "model_family",
    experiment.TARGET_REGISTRY["run_differential"].valid_model_families,
)
def test_run_differential_models_share_calendar_rehearsal_rows(db_conn, tmp_path, model_family):
    _reset(db_conn)
    _seed(db_conn)
    snapshot_id = experiment.create_snapshot(db_conn, target="run_differential")
    config = experiment.ExperimentConfig(
        snapshot_id=snapshot_id,
        model_family=model_family,
        target="run_differential",
        fold_years=(2016, 2017),
        artifact_dir=tmp_path / model_family,
    )

    first = experiment.run(db_conn, config)
    db_conn.commit()
    second = experiment.run(db_conn, config)
    db_conn.commit()

    assert first["status"] == "success"
    assert not first["reused"]
    assert second["reused"]
    assert first["aggregate"] == second["aggregate"]
    assert first["aggregate"]["rows"] == 14
    assert set(first["folds"]) == {"season-2016", "season-2017"}
    for metrics in first["folds"].values():
        assert metrics["coverage"]["common_rows"] == 22
        assert metrics["coverage"]["excluded_opening_or_missing_rate_rows"] == 3
        assert metrics["rows"] == 7
        assert metrics["mae"] >= 0
        assert metrics["rmse"] >= 0
        assert "mae_95ci" in metrics
        assert "rmse_95ci" in metrics
        assert "calibration" in metrics

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT train_through_season, test_season, artifact_uri, artifact_sha256 "
            "FROM meta.experiment_fold WHERE experiment_id = %s ORDER BY test_season",
            (first["experiment_id"],),
        )
        rows = cur.fetchall()
    assert [(row[0], row[1]) for row in rows] == [(2015, 2016), (2016, 2017)]
    for _train, _test, artifact_uri, artifact_sha in rows:
        path = Path(artifact_uri)
        assert path.exists()
        assert path.name == f"{artifact_sha}.json"
        content = json.loads(path.read_text())
        assert len(content["predictions"]) == 7
        for pred in content["predictions"]:
            assert "prediction" in pred
            assert "actual_run_differential" in pred

    # Compare reports all folds and models
    comparison = experiment.compare(db_conn, snapshot_id)
    assert any(row["model"] == model_family for row in comparison)

    _reset(db_conn)


def test_first_game_of_season_null_zero_empirical_behavior(db_conn):
    _reset(db_conn)
    _seed(db_conn)

    # In our database schema / rebuild query, check the opening games for each season
    # (e.g. 201501, 201601, 201701)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT mlb_game_pk, home_wins, home_losses, away_wins, away_losses,
                   home_runs_for, home_runs_allowed, away_runs_for, away_runs_allowed
            FROM gold.game_feature
            WHERE mlb_game_pk IN ('201501', '201601', '201701')
            ORDER BY mlb_game_pk
            """
        )
        rows = cur.fetchall()
    for row in rows:
        _pk, hw, hl, aw, al, hrf, hra, arf, ara = row
        # Empirical finding: All 8 entering run/win columns are NULL (not 0) on opening games
        assert hw is None, f"expected NULL home_wins, got {hw}"
        assert hl is None, f"expected NULL home_losses, got {hl}"
        assert aw is None, f"expected NULL away_wins, got {aw}"
        assert al is None, f"expected NULL away_losses, got {al}"
        assert hrf is None, f"expected NULL home_runs_for, got {hrf}"
        assert hra is None, f"expected NULL home_runs_allowed, got {hra}"
        assert arf is None, f"expected NULL away_runs_for, got {arf}"
        assert ara is None, f"expected NULL away_runs_allowed, got {ara}"

    # Snapshot rows accurately retain these NULL values
    snapshot_id = experiment.create_snapshot(db_conn, target="run_differential")
    snapshot_rows = experiment._snapshot_rows(db_conn, snapshot_id)
    opening_rows = [r for r in snapshot_rows if r.mlb_game_pk in {"201501", "201601", "201701"}]
    assert len(opening_rows) == 3
    for r in opening_rows:
        assert r.values["home_wins"] is None
        assert r.values["home_runs_for"] is None

    # And common-row filtering cleanly excludes them for both targets
    hw_eligible = experiment._common_rows(snapshot_rows, experiment.TARGET_REGISTRY["home_win"])
    rd_eligible = experiment._common_rows(
        snapshot_rows, experiment.TARGET_REGISTRY["run_differential"]
    )
    assert len(hw_eligible) == 22
    assert len(rd_eligible) == 22
    assert all(r.mlb_game_pk not in {"201501", "201601", "201701"} for r in hw_eligible)
    assert all(r.mlb_game_pk not in {"201501", "201601", "201701"} for r in rd_eligible)

    _reset(db_conn)
