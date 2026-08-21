"""Regression coverage for mlb_baseball.model.log5's DB-facing pieces
(predict/backfill_outcomes) -- the pure formula itself is unit-tested in
tests/unit/test_log5_formula.py.

Undecided games are seeded via raw.mlb_schedule, not core.game directly --
core.game only ever holds completed games (conform.py's _build_games
excludes status = 'Scheduled', see migration 0014), so that's the only
path an undecided game can realistically take in production.
"""

from decimal import Decimal

import pytest

from mlb_baseball import model
from mlb_baseball.model import features, log5


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def _ensure_mlb_schedule_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS raw.mlb_schedule ("
            "game_id text, _season text, game_date text, game_type text, "
            "status text, home_id text, away_id text, game_num text, "
            "venue_id text)"
        )
        for column in (
            "game_id",
            "_season",
            "game_date",
            "game_type",
            "status",
            "home_id",
            "away_id",
            "game_num",
            "venue_id",
        ):
            cur.execute(f"ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS {column} text")
    db_conn.commit()


def _reset(db_conn):
    # Called automatically before and after every test here by the _clean
    # autouse fixture below -- a prior test (in this file or
    # test_model_features.py, which shares this natural key) failing
    # before reaching its own cleanup would otherwise leave ATL/NYA rows
    # behind and collide with the next test's _seed_teams insert. Same
    # defensive-reset pattern as test_conform.py's _reset_dynamic_tables().
    #
    # raw.mlb_schedule is DROPped, not DELETEd (issue #9 item 5) -- see
    # test_model_features.py's identical _reset for the full explanation.
    # _ensure_mlb_schedule_table above already recreates it fresh on
    # demand, unconditionally re-running its ALTER ADD COLUMN block
    # either way, so this is safe.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _clean(db_conn):
    # Issue #9 item 5: an autouse fixture's teardown runs regardless of
    # pass/fail, unlike the per-test trailing _reset(db_conn) call this
    # replaces, which never ran if a test failed partway through -- see
    # test_model_offense.py's identical fixture for the full explanation.
    _reset(db_conn)
    yield
    _reset(db_conn)


def test_predict_skips_decided_games_and_season_openers(db_conn):
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            # G1: season opener for both -- no win_pct yet, must be skipped.
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            # G2: decided already (has a score) -- must be skipped, only
            # upcoming games get predictions from predict().
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # G3: not yet decided, sourced from raw.mlb_schedule -- the only
        # one that should get a prediction.
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999001', '2024', '2024-04-03', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    inserted = log5.predict(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT mlb_game_pk, home_win_prob, model_version, actual_home_win FROM gold.prediction"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    mlb_game_pk, home_win_prob, model_version, actual = rows[0]
    assert mlb_game_pk == "999001"
    assert model_version == "log5-v2"
    assert actual is None
    # ATL entered 2-0, NYA 0-2 -- log5(1.0, 0.0) is exactly 1, not merely
    # "greater than 0.5" (verified separately in tests/unit/test_log5_formula.py).
    assert home_win_prob == Decimal("1")
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT p.model_id, r.run_type, r.status FROM gold.prediction p "
            "JOIN meta.model_run r ON r.run_id = p.model_run_id "
            "WHERE p.mlb_game_pk = '999001'"
        )
        _model_id, run_type, status = cur.fetchone()
    assert (run_type, status) == ("predict", "success")


def test_predict_handles_two_undefeated_teams_without_aborting_the_whole_run(db_conn):
    # Real bug found via PR review: predict()'s raw SQL formula (a
    # standalone INSERT ... SELECT, can't call back into probability()
    # per row) excludes the (0,0) winless-vs-winless degenerate case, but
    # never excluded the mirror-image (1,1) undefeated-vs-undefeated case
    # -- both divide 0/0. An undefeated-vs-undefeated matchup on the same
    # day as any other still-undecided game would abort the entire INSERT
    # (a single division error kills every row in one SELECT), silently
    # blocking every other game's prediction in the same run, not just
    # this one game's.
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        # A third team (BOS) each play a win against, so ATL and NYA enter
        # their own head-to-head 1-0 each -- both undefeated
        # (home_win_pct == away_win_pct == 1.0), without a loss against
        # each other muddying either record.
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('BOS', 'Boston', 'Red Sox', 1908, 2025, 111) "
            "RETURNING id"
        )
        (bos,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(bos)s, 5, 0, 'regular'), "
            "('G2', 2024, '2024-04-02', %(nya)s, %(bos)s, 5, 0, 'regular')",
            {"atl": atl, "nya": nya, "bos": bos},
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999002', '2024', '2024-04-03', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    inserted = log5.predict(db_conn)
    db_conn.commit()

    # The undefeated-vs-undefeated game itself is correctly excluded (no
    # sensible log5 answer, same as the pre-existing winless-vs-winless
    # exclusion) -- the point of this test is that the INSERT completes at
    # all instead of raising and aborting.
    assert inserted == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction WHERE mlb_game_pk = '999002'")
        (count,) = cur.fetchone()
    assert count == 0


def test_backfill_outcomes_fills_in_actual_result_once_game_is_final(db_conn):
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999002', '2024', '2024-04-02', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    log5.predict(db_conn)
    db_conn.commit()

    # Game 999002 now finishes, 4-2 to the away team (NYA wins) -- conform
    # would normally land this in core.game with game_pk backfilled to the
    # same value raw.mlb_schedule always had for it; simulated directly
    # here rather than re-running the full conform pipeline in a test.
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, game_pk) "
            "VALUES ('G2', 2024, '2024-04-02', %s, %s, 2, 4, 'regular', '999002')",
            (atl, nya),
        )
        cur.execute("UPDATE raw.mlb_schedule SET status = 'Final' WHERE game_id = '999002'")
    db_conn.commit()

    # The normal production ordering is conform → features → outcome backfill.
    # Rebuilding replaces the scheduled row with the matching completed-game
    # instance key before outcome resolution runs.
    features.build(db_conn)
    db_conn.commit()

    updated = model.backfill_outcomes(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT actual_home_win FROM gold.prediction WHERE mlb_game_pk = '999002'")
        (actual,) = cur.fetchone()
    assert actual is False  # home team (ATL) lost, 2-4


def test_rerunning_predict_before_game_day_preserves_prediction_history(db_conn):
    # gold.prediction is deliberately history-preserving (migration 0013)
    # -- re-running predict() for the same still-undecided game before it's
    # played should add another row, not overwrite/skip the first one.
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999003', '2024', '2024-04-02', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    first = log5.predict(db_conn)
    db_conn.commit()
    second = log5.predict(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction")
        (count,) = cur.fetchone()
    assert count == 2
