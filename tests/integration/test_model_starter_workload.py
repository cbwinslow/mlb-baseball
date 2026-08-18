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
    # DROPs (not DELETEs) every stub table this file creates on demand --
    # see test_model_offense.py's identical _reset for the full explanation
    # (issue #7): each test_model_*.py file creates its own minimal schema
    # for these tables, and a stale stub from an earlier file's run breaks
    # later files' schema expectations. All five tables here are created
    # ad-hoc by this file's own fixtures, never by a migration, so dropping
    # them is always safe.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in (
            "raw.retrosheet_event",
            "raw.retrosheet_gameinfo",
            "raw.mlb_schedule",
            "raw.mlb_probable",
            "raw.mlb_playbyplay",
        ):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
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

    _reset(db_conn)


def test_compute_starter_workload_returns_zero_without_retrosheet_gameinfo_table(db_conn):
    # Issue #9 item 2: compute()'s own SQL joins raw.retrosheet_gameinfo
    # too, but only retrosheet_event was gated -- see
    # test_model_offense.py's identical regression for the full explanation
    # (retrosheet_event/retrosheet_gameinfo are landed by two different
    # connectors).
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, bat_event_fl text, event_cd text, "
            "event_outs_ct text, _season text)"
        )
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()

    assert starter_workload.compute(db_conn) == 0

    _reset(db_conn)


def test_health_check_runs_cleanly_against_empty_database():
    checks = starter_workload.health_check()
    assert len(checks) == 4
    assert all(c.ok for c in checks)


def test_health_check_reports_coverage_when_healthy(db_conn):
    # Issue #9 item 3 fix surfaced a real, separate pre-existing bug: the
    # old inline logic only ever appended a "May+ rest days coverage"
    # check when coverage was BELOW 0.90 (or when there were zero May+
    # starts at all) -- when coverage was fine (the common, healthy case),
    # nothing was appended at all, so `mlb doctor` silently omitted this
    # check exactly when it was passing. One populated May+ row (100%
    # coverage) proves the refactored _coverage_checks() now reports an
    # explicit passing check in that case, for both home and away.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('startp1', 'Start', 'PitcherOne'), "
            "('startp2', 'Start', 'PitcherTwo') "
            "RETURNING id, retro_id"
        )
        players = {retro_id: player_id for player_id, retro_id in cur.fetchall()}
        home_starter, away_starter = players["startp1"], players["startp2"]
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_win, home_starter_id, home_starter_rest_days, "
            "away_starter_id, away_starter_rest_days) VALUES "
            "('mlb:999002', '999002', 2020, '2020-05-15', %(atl)s, %(nya)s, true, "
            "%(home_starter)s, 5, %(away_starter)s, 4)",
            {
                "atl": atl,
                "nya": nya,
                "home_starter": home_starter,
                "away_starter": away_starter,
            },
        )
    db_conn.commit()

    checks = starter_workload.health_check()
    home_check = next(
        c
        for c in checks
        if c.name == "starter workload: May+ rest days coverage for resolved home starters"
    )
    away_check = next(
        c
        for c in checks
        if c.name == "starter workload: May+ rest days coverage for resolved away starters"
    )
    assert home_check.ok
    assert "100.0%" in home_check.detail
    assert away_check.ok
    assert "100.0%" in away_check.detail

    _reset(db_conn)


def test_health_check_reports_coverage_independently_per_side(db_conn):
    # PR #31 review (kilo-code-bot, coderabbitai): the previous test only
    # ever populated both sides identically (100% coverage each), so it
    # couldn't catch a real, plausible bug -- the away aggregate
    # accidentally reading home_starter_id/home_starter_rest_days instead
    # of its own away_* columns -- since both checks would still report
    # 100.0% either way. This fixture deliberately makes the two sides
    # DIFFER: a resolved home starter with missing rest days (0% coverage,
    # below the 90% threshold -> fails) and a resolved away starter with
    # populated rest days (100% coverage -> passes). If the away
    # aggregate ever silently reused the home columns, this test would
    # see away_check.ok == False (wrongly inheriting home's failure) and
    # fail loudly.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('startp1', 'Start', 'PitcherOne'), "
            "('startp2', 'Start', 'PitcherTwo') "
            "RETURNING id, retro_id"
        )
        players = {retro_id: player_id for player_id, retro_id in cur.fetchall()}
        home_starter, away_starter = players["startp1"], players["startp2"]
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_win, home_starter_id, home_starter_rest_days, "
            "away_starter_id, away_starter_rest_days) VALUES "
            "('mlb:999003', '999003', 2020, '2020-05-15', %(atl)s, %(nya)s, true, "
            "%(home_starter)s, NULL, %(away_starter)s, 4)",
            {
                "atl": atl,
                "nya": nya,
                "home_starter": home_starter,
                "away_starter": away_starter,
            },
        )
    db_conn.commit()

    checks = starter_workload.health_check()
    home_check = next(
        c
        for c in checks
        if c.name == "starter workload: May+ rest days coverage for resolved home starters"
    )
    away_check = next(
        c
        for c in checks
        if c.name == "starter workload: May+ rest days coverage for resolved away starters"
    )
    assert not home_check.ok
    assert "0.0%" in home_check.detail
    assert away_check.ok
    assert "100.0%" in away_check.detail

    _reset(db_conn)


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


def _ensure_playbyplay_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_playbyplay ("
                "game_pk text, at_bat_index text, inning text, half_inning text, "
                "pitcher_id text, event_type text, outs text, _season text)"
            )
    db_conn.commit()


def _ensure_mlb_schedule_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule ("
                "game_id text, _season text, game_date text, game_type text, "
                "status text, home_id text, away_id text, game_num text, "
                "venue_id text)"
            )
    db_conn.commit()


def _ensure_probable_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_probable')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_probable "
                "(game_pk text, side text, pitcher_id text, pitcher_name text, "
                "_loaded_at timestamptz NOT NULL DEFAULT now())"
            )
    db_conn.commit()


def _extend_team_range_to_2026(db_conn, *team_ids):
    with db_conn.cursor() as cur:
        cur.execute("UPDATE core.team SET last_year = 2026 WHERE id = ANY(%s)", (list(team_ids),))
    db_conn.commit()


def test_compute_live_starter_workload_matches_hand_calculation(db_conn):
    # 2026 completed games via raw.mlb_playbyplay:
    # G1 (2026-04-01, game_pk='900001'):
    #   ATL starts livep001 (pitcher_id='5001', top half inning, home starter)
    #   NYA starts livep002 (pitcher_id='5002', bottom half inning, away starter)
    #   livep001 pitches 3 outs (outs 0->1, 1->2, 2->3).
    #   livep002 pitches 3 outs (outs 0->1, 1->2, 2->3).
    #   Entering G1: both pitchers have no prior starts -> rest_days = NULL, outs_7d = NULL.
    #
    # G1_MID (2026-04-04, game_pk='900002'):
    #   NYA uses livep002 in relief (top half inning, inning 2, at_bat_index 4, outs 0->2).
    #   livep002 pitches 2 relief outs.
    #   Starter for NYA is otherp (5003, top half, inning 1, 3 outs).
    #   Starter for ATL is otherp2 (5004, bottom half, inning 1, 3 outs).
    #
    # G2 (2026-04-06, game_pk='900003', 5 days after G1):
    #   ATL starts livep001 (top half), NYA starts livep002 (bottom half).
    #   livep001 entering G2:
    #     prior start: G1 (2026-04-01) -> rest_days = 2026-04-06 - 2026-04-01 = 5
    #     trailing 7d workload [2026-03-30 to 2026-04-05]: G1 (3 outs) -> outs_7d = 3
    #   livep002 entering G2:
    #     prior start: G1 (2026-04-01) -> rest_days = 2026-04-06 - 2026-04-01 = 5
    #     trailing 7d workload [2026-03-30 to 2026-04-05]:
    #       G1 start (3 outs) + G1_MID relief (2 outs) -> outs_7d = 5
    #   In G2, livep001 pitches 3 outs, livep002 pitches 3 outs.
    #
    # G3 (2026-04-20, game_pk='900004', 14 days after G2):
    #   ATL starts livep001 (top half), NYA starts livep002 (bottom half).
    #   livep001 entering G3:
    #     prior start: G2 (2026-04-06) -> rest_days = 2026-04-20 - 2026-04-06 = 14
    #     trailing 7d workload [2026-04-13 to 2026-04-19]:
    #       no appearances in window -> outs_7d = NULL
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('MLB900001', '900001', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('MLB900002', '900002', 2026, '2026-04-04', %(nya)s, %(atl)s, 4, 2, 'regular'), "
            "('MLB900003', '900003', 2026, '2026-04-06', %(atl)s, %(nya)s, 2, 1, 'regular'), "
            "('MLB900004', '900004', 2026, '2026-04-20', %(atl)s, %(nya)s, 3, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            # G1: livep001 (ATL starter, top) 3 outs; livep002 (NYA starter, bottom) 3 outs
            "('900001', '0', '1', 'top', '5001', 'strikeout', '1', '2026'), "
            "('900001', '1', '1', 'top', '5001', 'field_out', '2', '2026'), "
            "('900001', '2', '1', 'top', '5001', 'field_out', '3', '2026'), "
            "('900001', '3', '1', 'bottom', '5002', 'strikeout', '1', '2026'), "
            "('900001', '4', '1', 'bottom', '5002', 'field_out', '2', '2026'), "
            "('900001', '5', '1', 'bottom', '5002', 'field_out', '3', '2026'), "
            # G1_MID: otherp starts for NYA (top, 3 outs), livep002 relief (top, 2 outs)
            "('900002', '0', '1', 'top', '5003', 'strikeout', '1', '2026'), "
            "('900002', '1', '1', 'top', '5003', 'field_out', '2', '2026'), "
            "('900002', '2', '1', 'top', '5003', 'field_out', '3', '2026'), "
            "('900002', '3', '1', 'bottom', '5004', 'field_out', '1', '2026'), "
            "('900002', '4', '2', 'top', '5002', 'field_out', '2', '2026'), "
            # G2: livep001 (top) 3 outs, livep002 (bottom) 3 outs
            "('900003', '0', '1', 'top', '5001', 'strikeout', '1', '2026'), "
            "('900003', '1', '1', 'top', '5001', 'field_out', '2', '2026'), "
            "('900003', '2', '1', 'top', '5001', 'field_out', '3', '2026'), "
            "('900003', '3', '1', 'bottom', '5002', 'strikeout', '1', '2026'), "
            "('900003', '4', '1', 'bottom', '5002', 'field_out', '2', '2026'), "
            "('900003', '5', '1', 'bottom', '5002', 'field_out', '3', '2026'), "
            # G3: livep001 (top) 3 outs, livep002 (bottom) 3 outs
            "('900004', '0', '1', 'top', '5001', 'strikeout', '1', '2026'), "
            "('900004', '1', '1', 'top', '5001', 'field_out', '2', '2026'), "
            "('900004', '2', '1', 'top', '5001', 'field_out', '3', '2026'), "
            "('900004', '3', '1', 'bottom', '5002', 'strikeout', '1', '2026')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = starter_workload.compute_live(db_conn)
    db_conn.commit()

    assert updated == 4
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, "
            "f.home_starter_rest_days, f.home_starter_outs_7d, "
            "f.away_starter_rest_days, f.away_starter_outs_7d "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.game_date, g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: first start for both -> all NULL
    assert rows["MLB900001"] == (None, None, None, None)

    # G2: 5 days rest for both; livep001 had 3 outs; livep002 had 3 start + 2 relief = 5 outs
    g2 = rows["MLB900003"]
    assert g2[0] == 5
    assert g2[1] == Decimal("3")
    assert g2[2] == 5
    assert g2[3] == Decimal("5")

    # G3: 14 days rest for livep001; no appearances in trailing 7 days -> outs_7d = NULL
    g3 = rows["MLB900004"]
    assert g3[0] == 14
    assert g3[1] is None

    _reset(db_conn)


def test_compute_live_returns_zero_without_playbyplay_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert starter_workload.compute_live(db_conn) == 0


def test_compute_live_does_not_overwrite_retrosheet_derived_values(db_conn):
    # compute_live() must only fill the NULL gap compute() leaves --
    # a game already resolved via compute() must never be touched by the live path.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('MLB900003', '900003', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_starter_rest_days = 6, home_starter_outs_7d = 15 "
            "WHERE mlb_game_pk = '900003'"
        )
    db_conn.commit()

    starter_workload.compute_live(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_rest_days, home_starter_outs_7d "
            "FROM gold.game_feature WHERE mlb_game_pk = '900003'"
        )
        rest_days, outs_7d = cur.fetchone()
    assert rest_days == 6
    assert outs_7d == Decimal("15")

    _reset(db_conn)


def test_compute_probable_populates_upcoming_game_from_latest_announced_probable(db_conn):
    # Home probable (pitcher_id 7001) has a prior start on 2026-04-01 (6 outs)
    # and a relief outing on 2026-04-04 (3 outs).
    # Entering upcoming scheduled start on 2026-04-08:
    #   rest_days = 2026-04-08 - 2026-04-01 = 7 days
    #   trailing 7d workload [2026-04-01 to 2026-04-07]: 6 + 3 = 9 outs.
    # Away probable (pitcher_id 7002) has zero prior history (debut):
    #   rest_days = NULL, outs_7d = NULL.
    # Stale scratched announcement for home (pitcher_id 555555, loaded 1 day earlier)
    # must lose to 7001.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    _ensure_probable_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _extend_team_range_to_2026(db_conn, atl, nya)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id) VALUES "
            "('900030', '2026', '2026-04-01', 'R', 'Final', '144', '147'), "
            "('900032', '2026', '2026-04-04', 'R', 'Final', '147', '144'), "
            "('900031', '2026', '2026-04-08', 'R', 'Scheduled', '144', '147')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            # 900030: 7001 starts (top half) and pitches 6 outs (2 innings of 3 outs)
            "('900030', '0', '1', 'top', '7001', 'strikeout', '1', '2026'), "
            "('900030', '1', '1', 'top', '7001', 'field_out', '2', '2026'), "
            "('900030', '2', '1', 'top', '7001', 'field_out', '3', '2026'), "
            "('900030', '3', '2', 'top', '7001', 'strikeout', '1', '2026'), "
            "('900030', '4', '2', 'top', '7001', 'field_out', '2', '2026'), "
            "('900030', '5', '2', 'top', '7001', 'field_out', '3', '2026'), "
            # 900032: 5003 starts, 7001 relieves for 3 outs (bottom half)
            "('900032', '0', '1', 'bottom', '5003', 'field_out', '1', '2026'), "
            "('900032', '1', '2', 'bottom', '7001', 'strikeout', '1', '2026'), "
            "('900032', '2', '2', 'bottom', '7001', 'field_out', '2', '2026'), "
            "('900032', '3', '2', 'bottom', '7001', 'field_out', '3', '2026')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_probable (game_pk, side, pitcher_id, pitcher_name, _loaded_at) "
            "VALUES "
            "('900031', 'home', '555555', 'Scratched Pitcher', now() - interval '1 day'), "
            "('900031', 'home', '7001', 'Real Starter', now()), "
            "('900031', 'away', '7002', 'Rookie Debut', now())"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = starter_workload.compute_probable(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_rest_days, home_starter_outs_7d, "
            "away_starter_rest_days, away_starter_outs_7d "
            "FROM gold.game_feature WHERE mlb_game_pk = '900031'"
        )
        home_rest, home_outs, away_rest, away_outs = cur.fetchone()

    # Home probable 7001: 7 days rest, 6 start outs + 3 relief outs = 9 outs
    assert home_rest == 7
    assert home_outs == Decimal("9")
    # Away probable 7002: debut with zero history -> NULL
    assert away_rest is None
    assert away_outs is None

    # Idempotence: re-running does not corrupt or alter values
    updated_again = starter_workload.compute_probable(db_conn)
    db_conn.commit()
    assert updated_again == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_rest_days, home_starter_outs_7d "
            "FROM gold.game_feature WHERE mlb_game_pk = '900031'"
        )
        assert cur.fetchone() == (7, Decimal("9"))

    _reset(db_conn)


def test_compute_probable_only_uses_history_strictly_before_target_game_date(db_conn):
    # Leakage-safety proof: rest-days and trailing workload calculations for a
    # probable (not-yet-played) game must only ever look at appearances
    # strictly before THAT target game's own date, never 'as of today'.
    #
    # Specifically tests a probable announced days ahead of an intervening start:
    # Pitcher probp1 (7001) is announced as probable for Game A on 2026-04-15 (900041)
    # and also for Game B on 2026-04-08 (900044).
    #
    # Pitcher 7001's history across 2026 contains:
    # 1. 2026-04-01 (900040): Start, pitches 15 outs.
    # 2. 2026-04-08 (900042): Start, pitches 18 outs. (Intervening start between 900040 and 900041).
    # 3. 2026-04-20 (900043): Start, pitches 20 outs. (Future start strictly after 900041).
    #
    # Expected entering Game B (900044 on 2026-04-08):
    #   - Appearances strictly before 2026-04-08: 900040 (2026-04-01) only.
    #   - Prior start: 2026-04-01 -> rest_days = 2026-04-08 - 2026-04-01 = 7.
    #   - Trailing 7d workload [2026-04-01 to 2026-04-07]: 900040 (15 outs) -> outs_7d = 15.
    #   - 900042 (on 2026-04-08 itself) and 900043 (on 2026-04-20) MUST NOT leak into 900044.
    #
    # Expected entering Game A (900041 on 2026-04-15):
    #   - Appearances strictly before 2026-04-15: 900040 (2026-04-01) and 900042 (2026-04-08).
    #   - Prior start: 900042 (2026-04-08) -> rest_days = 2026-04-15 - 2026-04-08 = 7.
    #     (If the intervening start 900042 was missed, rest_days would be 14 from 900040.
    #      If future 900043 leaked, rest_days would be negative: 2026-04-15 - 2026-04-20 = -5).
    #   - Trailing 7d workload [2026-04-08 to 2026-04-14]: 900042 (18 outs) is within window.
    #     900040 (2026-04-01, 14 days ago) is outside window.
    #     900043 (2026-04-20, in future) is strictly excluded.
    #     -> outs_7d = 18.
    #     (If 900040 leaked into the 7d sum, outs_7d would be 15 + 18 = 33.
    #      If 900043 leaked into the 7d sum, outs_7d would be 18 + 20 = 38).
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    _ensure_probable_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _extend_team_range_to_2026(db_conn, atl, nya)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id) VALUES "
            "('900040', '2026', '2026-04-01', 'R', 'Final', '144', '147'), "
            "('900042', '2026', '2026-04-08', 'R', 'Final', '144', '147'), "
            "('900044', '2026', '2026-04-08', 'R', 'Scheduled', '144', '147'), "
            "('900041', '2026', '2026-04-15', 'R', 'Scheduled', '144', '147'), "
            "('900043', '2026', '2026-04-20', 'R', 'Final', '144', '147')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            # 900040 (2026-04-01): 7001 starts (top half) and pitches 15 outs
            "('900040', '0', '1', 'top', '7001', 'field_out', '3', '2026'), "
            "('900040', '1', '2', 'top', '7001', 'field_out', '3', '2026'), "
            "('900040', '2', '3', 'top', '7001', 'field_out', '3', '2026'), "
            "('900040', '3', '4', 'top', '7001', 'field_out', '3', '2026'), "
            "('900040', '4', '5', 'top', '7001', 'field_out', '3', '2026'), "
            # 900042 (2026-04-08): 7001 starts (top half) and pitches 18 outs
            "('900042', '0', '1', 'top', '7001', 'field_out', '3', '2026'), "
            "('900042', '1', '2', 'top', '7001', 'field_out', '3', '2026'), "
            "('900042', '2', '3', 'top', '7001', 'field_out', '3', '2026'), "
            "('900042', '3', '4', 'top', '7001', 'field_out', '3', '2026'), "
            "('900042', '4', '5', 'top', '7001', 'field_out', '3', '2026'), "
            "('900042', '5', '6', 'top', '7001', 'field_out', '3', '2026'), "
            # 900043 (2026-04-20): 7001 starts (top half) and pitches 20 outs
            "('900043', '0', '1', 'top', '7001', 'field_out', '3', '2026'), "
            "('900043', '1', '2', 'top', '7001', 'field_out', '3', '2026'), "
            "('900043', '2', '3', 'top', '7001', 'field_out', '3', '2026'), "
            "('900043', '3', '4', 'top', '7001', 'field_out', '3', '2026'), "
            "('900043', '4', '5', 'top', '7001', 'field_out', '3', '2026'), "
            "('900043', '5', '6', 'top', '7001', 'field_out', '3', '2026'), "
            "('900043', '6', '7', 'top', '7001', 'field_out', '2', '2026')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_probable (game_pk, side, pitcher_id, pitcher_name) "
            "VALUES "
            "('900044', 'home', '7001', 'Real Starter'), "
            "('900041', 'home', '7001', 'Real Starter')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    starter_workload.compute_probable(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_rest_days, home_starter_outs_7d "
            "FROM gold.game_feature WHERE mlb_game_pk = '900044'"
        )
        g_tgt2_rest, g_tgt2_outs = cur.fetchone()

        cur.execute(
            "SELECT home_starter_rest_days, home_starter_outs_7d "
            "FROM gold.game_feature WHERE mlb_game_pk = '900041'"
        )
        g_tgt1_rest, g_tgt1_outs = cur.fetchone()

    # Game B (900044 on 2026-04-08): only sees 900040 (2026-04-01)
    assert g_tgt2_rest == 7
    assert g_tgt2_outs == Decimal("15")

    # Game A (900041 on 2026-04-15): sees intervening start 900042 (2026-04-08) as prior start
    assert g_tgt1_rest == 7
    assert g_tgt1_outs == Decimal("18")

    _reset(db_conn)


def test_compute_probable_returns_zero_without_probable_or_playbyplay_table(db_conn):
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_probable")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert starter_workload.compute_probable(db_conn) == 0

    _ensure_probable_table(db_conn)
    assert starter_workload.compute_probable(db_conn) == 0  # playbyplay still missing

    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_probable")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
    db_conn.commit()
