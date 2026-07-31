"""Regression coverage for mlb_baseball.model.features -- gold.game_feature's
point-in-time window-function build (ADR-032).

Cleanup uses targeted DELETE, not TRUNCATE CASCADE -- core.game cascades
into core.play/core.pitch, which migration 0011 partitioned into 150+
pieces each; TRUNCATE CASCADE against them was confirmed to hang 10+
minutes even when empty (see issue #2). DELETE has no such cost here since
these tests never touch core.play/core.pitch at all.
"""

from decimal import Decimal

from mlb_baseball.model import features


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
    # raw.mlb_schedule only exists once some connector run has created it
    # (load_dataframe creates raw tables from whatever a real load
    # contains) -- not a given in a fresh mlb_test. Created here with just
    # the columns features.py's upcoming-games query actually reads.
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (exists,) = cur.fetchone()
        if not exists:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule ("
                "game_id text, _season text, game_date text, game_type text, "
                "status text, home_id text, away_id text, game_num text, "
                "venue_id text)"
            )
    db_conn.commit()


def _reset(db_conn):
    # Called at both the start and end of every test here -- a prior test
    # in this file (or test_model_log5.py, which shares this natural key)
    # failing before reaching its own cleanup would otherwise leave
    # ATL/NYA rows behind and collide with the next test's _seed_teams
    # insert. Same defensive-reset pattern as test_conform.py's
    # _reset_dynamic_tables().
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (schedule_exists,) = cur.fetchone()
        if schedule_exists:
            cur.execute("DELETE FROM raw.mlb_schedule")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_build_computes_point_in_time_win_pct_and_pythagenpat(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular'), "
            "('G3', 2024, '2024-04-03', %(atl)s, %(nya)s, 1, 4, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    count = features.build(db_conn)
    db_conn.commit()
    assert count == 3

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_win_pct, f.away_win_pct, "
            "f.home_run_diff, f.away_run_diff, f.home_win "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: first game of the season for both teams -- nothing prior to
    # compute from, every rolling stat is honestly NULL, not zero.
    assert rows["G1"] == (None, None, None, None, True)

    # G2: entering it, ATL is 1-0 (won G1), NYA is 0-1.
    g2 = rows["G2"]
    assert g2[0] == Decimal("1.00000000000000000000")
    assert g2[1] == Decimal("0E-20")  # 0, Postgres's numeric zero representation
    assert g2[2] == Decimal("2")  # ATL's run diff before G2: 5-3
    assert g2[3] == Decimal("-2")
    assert g2[4] is True

    # G3: entering it, ATL is 2-0, NYA is 0-2.
    g3 = rows["G3"]
    assert g3[0] == Decimal("1.00000000000000000000")
    assert g3[1] == Decimal("0E-20")
    assert g3[2] == Decimal("3")  # (5-3) + (2-1)
    assert g3[3] == Decimal("-3")
    assert g3[4] is False  # ATL lost G3, 1-4

    _reset(db_conn)


def test_pythagenpat_home_and_away_sum_to_one(db_conn):
    # Same run total (RS+RA) on both sides of a game means the same
    # scoring-environment exponent applies to both teams -- home_pyth_wpct
    # and away_pyth_wpct should be exact complements, not just close.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_pyth_wpct, f.away_pyth_wpct FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G2'"
        )
        home_pyth, away_pyth = cur.fetchone()

    assert home_pyth + away_pyth == Decimal("1.00000000000000000000")
    assert Decimal("0.71") < home_pyth < Decimal("0.72")

    _reset(db_conn)


def test_build_resolves_venue_id_for_completed_and_upcoming_games(db_conn):
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, mlb_venue_id) "
            "VALUES ('ATL03', 'Truist Park', 4705) RETURNING id"
        )
        (venue_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular', %s)",
            (atl, nya, venue_id),
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, "
            "game_num, venue_id) "
            "VALUES ('999005', '2024', '2024-04-02', 'R', 'Scheduled', '144', '147', '1', '4705')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT venue_id FROM gold.game_feature WHERE game_id IS NOT NULL")
        assert cur.fetchone() == (venue_id,)
        cur.execute("SELECT venue_id FROM gold.game_feature WHERE mlb_game_pk = '999005'")
        assert cur.fetchone() == (venue_id,)

    _reset(db_conn)


def test_build_computes_rest_days_across_the_season_boundary(db_conn):
    # Rest is NOT season-partitioned, unlike win_pct/pyth_wpct -- a team's
    # rest entering next season's opener is real and should reflect the
    # actual offseason gap, not reset to NULL at the season boundary.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular'), "
            "('G3', 2024, '2024-04-06', %(atl)s, %(nya)s, 4, 2, 'regular'), "
            "('G4', 2025, '2025-03-28', %(atl)s, %(nya)s, 1, 0, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_rest, f.away_rest "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None)  # first game ever for both -- no prior game to measure from
    assert rows["G2"] == (1, 1)  # 2024-04-02 minus 2024-04-01
    assert rows["G3"] == (4, 4)  # 2024-04-06 minus 2024-04-02
    assert rows["G4"] == (356, 356)  # 2025-03-28 minus 2024-04-06 -- real offseason gap, not NULL

    _reset(db_conn)


def test_rerunning_build_truncates_instead_of_duplicating(db_conn):
    _reset(db_conn)
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
    db_conn.commit()

    first = features.build(db_conn)
    db_conn.commit()
    second = features.build(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.game_feature")
        (count,) = cur.fetchone()
    assert count == 1

    _reset(db_conn)


def test_health_check_flags_empty_table():
    check = next(c for c in features.health_check() if c.name == "gold.game_feature")
    # Whatever state the DB happens to be in at test time, this must not
    # raise -- the real assertion is that health_check() returns cleanly
    # and names the right table.
    assert check.name == "gold.game_feature"


def test_build_includes_upcoming_game_from_raw_mlb_schedule(db_conn):
    # The real reason this branch exists: core.game only ever holds
    # completed games (conform.py's _build_games excludes status =
    # 'Scheduled'), so an upcoming game has to come from raw.mlb_schedule
    # directly or mlb predict has nothing to ever predict (see migration
    # 0014). Uses the exact same fixture shape as
    # test_build_computes_point_in_time_win_pct_and_pythagenpat (ATL 2-0
    # entering) so the win_pct/run_diff/pyth_wpct values are already
    # hand-verified by that test -- this one is about game_id/mlb_game_pk
    # identity and sourcing, not re-deriving the math.
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999001', '2024', '2024-04-03', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    count = features.build(db_conn)
    db_conn.commit()
    assert count == 3

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT game_id, mlb_game_pk, home_win_pct, away_win_pct, home_win "
            "FROM gold.game_feature WHERE mlb_game_pk = '999001'"
        )
        row = cur.fetchone()

    assert row is not None
    game_id, mlb_game_pk, home_win_pct, away_win_pct, home_win = row
    assert game_id is None  # not in core.game -- never played
    assert mlb_game_pk == "999001"
    assert home_win_pct == Decimal("1.00000000000000000000")  # ATL entered 2-0
    assert away_win_pct == Decimal("0E-20")
    assert home_win is None  # undecided

    _reset(db_conn)


def test_build_degrades_gracefully_without_raw_mlb_schedule(db_conn):
    # A fresh clone that's run mlb migrate + mlb conform but never mlb
    # ingest mlb_api has no raw.mlb_schedule table at all yet -- must still
    # build features for whatever completed games exist in core.game, not
    # crash the entire rebuild over a table it doesn't strictly need.
    # Explicitly dropped here (not just asserted absent) so this test's
    # precondition doesn't depend on running before any other test in this
    # file that creates the table via _ensure_mlb_schedule_table.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
    db_conn.commit()

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
    db_conn.commit()

    count = features.build(db_conn)
    db_conn.commit()

    assert count == 1

    _reset(db_conn)
