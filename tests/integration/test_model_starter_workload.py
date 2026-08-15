"""Regression coverage for mlb_baseball.model.starter_workload -- starting-pitcher
rest days and trailing 7-day workload outs (PIT-03).

Every value below is hand-computed and checked against exact Decimal/integer
arithmetic in the tests.
"""

from decimal import Decimal

from mlb_baseball.model import features, starter_workload


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, resp_pit_id text, "
                "resp_pit_start_fl text, bat_event_fl text, event_cd text, "
                "event_outs_ct text, _season text)"
            )
        else:
            for column in (
                "game_id",
                "bat_home_id",
                "resp_pit_id",
                "resp_pit_start_fl",
                "bat_event_fl",
                "event_cd",
                "event_outs_ct",
                "_season",
            ):
                cur.execute(
                    f"ALTER TABLE raw.retrosheet_event ADD COLUMN IF NOT EXISTS {column} text"
                )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_gameinfo ("
                "gid text, gametype text, visteam text, hometeam text, _season text)"
            )
        else:
            cur.execute(
                "ALTER TABLE raw.retrosheet_gameinfo "
                "ADD COLUMN IF NOT EXISTS visteam text, "
                "ADD COLUMN IF NOT EXISTS hometeam text, "
                "ADD COLUMN IF NOT EXISTS _season text"
            )
    db_conn.commit()


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


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in (
            "raw.retrosheet_event",
            "raw.retrosheet_gameinfo",
        ):
            cur.execute("SELECT to_regclass(%s)", (table,))
            if cur.fetchone()[0]:
                cur.execute(f"DELETE FROM {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_starter_workload_matches_hand_calculation(db_conn):
    # G1 (2020-04-01): ATL starts startp1 (home, bat_home_id='0'),
    #   NYA starts startp2 (away, bat_home_id='1').
    #   startp1 pitches 17 outs. startp2 pitches 15 outs.
    #   Entering G1: both pitchers have no prior starts -> rest_days = NULL, outs_7d = NULL.
    #
    # G1_MID (2020-04-04): NYA uses startp2 in relief (bat_home_id='0' in a home game for NYA,
    #   resp_pit_start_fl='F'). startp2 pitches 6 relief outs.
    #
    # G2 (2020-04-06, 5 days after G1): ATL starts startp1, NYA starts startp2.
    #   startp1 entering G2:
    #     prior start: G1 (2020-04-01) -> rest_days = 2020-04-06 - 2020-04-01 = 5
    #     trailing 7d workload [03-30 to 04-05]: G1 on 04-01 (17 outs) -> outs_7d = 17
    #   startp2 entering G2:
    #     prior start: G1 (2020-04-01) -> rest_days = 2020-04-06 - 2020-04-01 = 5
    #     trailing 7d workload [03-30 to 04-05]: G1 (15 outs) + G1_MID relief (6 outs) -> 21 outs
    #   In G2, startp1 pitches 18 outs.
    #
    # G3 (2020-04-12, 6 days after G2): ATL starts startp1.
    #   startp1 entering G3:
    #     prior start: G2 (2020-04-06) -> rest_days = 2020-04-12 - 2020-04-06 = 6
    #     trailing 7d workload [04-05 to 04-11]: G2 on 04-06 (18 outs), G1 on 04-01 is 11 days ago
    #     -> outs_7d = 18
    #   In G3, startp1 pitches 21 outs.
    #
    # G4 (2020-04-25, 13 days after G3): ATL starts startp1.
    #   startp1 entering G4:
    #     prior start: G3 (2020-04-12) -> rest_days = 2020-04-25 - 2020-04-12 = 13
    #     trailing 7d workload [04-18 to 04-24]: no appearances in window -> outs_7d = NULL
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G1_MID', 2020, '2020-04-04', %(nya)s, %(atl)s, 4, 2, 'regular'), "
            "('G2', 2020, '2020-04-06', %(atl)s, %(nya)s, 2, 1, 'regular'), "
            "('G3', 2020, '2020-04-12', %(atl)s, %(nya)s, 3, 2, 'regular'), "
            "('G4', 2020, '2020-04-25', %(atl)s, %(nya)s, 6, 4, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) VALUES "
            "('G1', 'regular'), ('G1_MID', 'regular'), ('G2', 'regular'), "
            "('G3', 'regular'), ('G4', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            # G1: startp1 (home) 17 outs, startp2 (away) 15 outs
            "('G1', '0', 'startp1', 'T', 'T', '2', '17', '2020'), "
            "('G1', '1', 'startp2', 'T', 'T', '2', '15', '2020'), "
            # G1_MID: otherp starts for NYA, startp2 pitches 6 relief outs for NYA (bat_home_id='0')
            "('G1_MID', '0', 'otherp', 'T', 'T', '2', '15', '2020'), "
            "('G1_MID', '0', 'startp2', 'F', 'T', '2', '6', '2020'), "
            "('G1_MID', '1', 'otherp2', 'T', 'T', '2', '24', '2020'), "
            # G2: startp1 18 outs, startp2 16 outs
            "('G2', '0', 'startp1', 'T', 'T', '2', '18', '2020'), "
            "('G2', '1', 'startp2', 'T', 'T', '2', '16', '2020'), "
            # G3: startp1 21 outs, startp2 18 outs
            "('G3', '0', 'startp1', 'T', 'T', '2', '21', '2020'), "
            "('G3', '1', 'startp2', 'T', 'T', '2', '18', '2020'), "
            # G4: startp1 20 outs, startp2 18 outs
            "('G4', '0', 'startp1', 'T', 'T', '2', '20', '2020'), "
            "('G4', '1', 'startp2', 'T', 'T', '2', '18', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = starter_workload.compute(db_conn)
    db_conn.commit()

    assert updated == 5
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, "
            "f.home_starter_rest_days, f.home_starter_outs_7d, "
            "f.away_starter_rest_days, f.away_starter_outs_7d "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.game_date, g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: first start for both pitchers -> all NULL
    assert rows["G1"] == (None, None, None, None)

    # G2: 5 days rest for both; startp1 had 17 outs in 7d; startp2 had 15 + 6 relief = 21 outs in 7d
    g2 = rows["G2"]
    assert g2[0] == 5
    assert g2[1] == Decimal("17")
    assert g2[2] == 5
    assert g2[3] == Decimal("21")

    # G3: 6 days rest for startp1; 18 outs in 7d window (G2 only, G1 outside 7d)
    g3 = rows["G3"]
    assert g3[0] == 6
    assert g3[1] == Decimal("18")

    # G4: 13 days rest for startp1; no appearances in trailing 7 days -> outs_7d = NULL
    g4 = rows["G4"]
    assert g4[0] == 13
    assert g4[1] is None

    _reset(db_conn)


def test_compute_starter_workload_doubleheader(db_conn):
    # ADR-042: Day-collapse ensures doubleheaders don't suffer peer-row ambiguity.
    # G1A / G1B on 2020-04-01: startp1 starts both games of a doubleheader.
    #   G1A: first start -> rest_days = NULL, outs_7d = NULL. startp1 pitches 12 outs.
    #   G1B: second start same day -> rest_days = 0 (2020-04-01 - 2020-04-01 = 0), outs_7d = NULL.
    #        startp1 pitches 6 outs.
    # G2 on 2020-04-03 (2 days later): startp1 starts G2.
    #   prior start is G1B (2020-04-01) -> rest_days = 2
    #   trailing 7d window includes 2020-04-01: day total is 12 + 6 = 18 outs -> outs_7d = 18
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, game_number) VALUES "
            "('G1A', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular', 1), "
            "('G1B', 2020, '2020-04-01', %(atl)s, %(nya)s, 4, 2, 'regular', 2), "
            "('G2', 2020, '2020-04-03', %(atl)s, %(nya)s, 2, 1, 'regular', 0)",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) VALUES "
            "('G1A', 'regular'), ('G1B', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            "('G1A', '0', 'startp1', 'T', 'T', '2', '12', '2020'), "
            "('G1A', '1', 'startp2', 'T', 'T', '2', '15', '2020'), "
            "('G1B', '0', 'startp1', 'T', 'T', '2', '6', '2020'), "
            "('G1B', '1', 'startp2', 'T', 'T', '2', '15', '2020'), "
            "('G2', '0', 'startp1', 'T', 'T', '2', '18', '2020'), "
            "('G2', '1', 'startp2', 'T', 'T', '2', '15', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    starter_workload.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_rest_days, f.home_starter_outs_7d "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    assert rows["G1A"] == (None, None)
    assert rows["G1B"] == (0, None)
    assert rows["G2"] == (2, Decimal("18"))

    _reset(db_conn)
    # Clean up raw.retrosheet_* tables created in this test file
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()


def test_compute_starter_workload_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert starter_workload.compute(db_conn) == 0


def test_health_check_runs_cleanly_against_empty_database():
    checks = starter_workload.health_check()
    assert len(checks) == 3
    assert all(c.ok for c in checks)


def test_health_check_flags_negative_values(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_win, home_starter_rest_days, home_starter_outs_7d) VALUES "
            "('mlb:999001', '999001', 2020, '2020-05-15', %(atl)s, %(nya)s, true, -1, -5)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    checks = starter_workload.health_check()
    neg_rest_check = next(c for c in checks if c.name == "starter workload: non-negative rest days")
    neg_outs_check = next(
        c for c in checks if c.name == "starter workload: non-negative workload outs"
    )
    assert not neg_rest_check.ok
    assert not neg_outs_check.ok

    _reset(db_conn)

