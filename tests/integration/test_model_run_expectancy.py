from __future__ import annotations

from mlb_baseball.model import features, run_expectancy


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player WHERE retro_id IN ('degrj001', 'scher001')")
        cur.execute("DELETE FROM core.team WHERE retro_team_id IN ('ATL', 'NYA')")
        cur.execute("DELETE FROM core.venue WHERE name = 'Truist Park'")
        cur.execute("DELETE FROM gold.run_expectancy_24")
        cur.execute("DELETE FROM gold.leverage_index")
    db_conn.commit()


def test_compute_populates_re24_and_li(db_conn):
    # Plan 06 / ADR-262: avg_li now comes from a real join to
    # gold.leverage_index, not a hand-typed table -- seed one exact,
    # hand-picked fixture row for the state this test's events land in
    # (inning=1, top, 0 outs, bases empty, margin=0) so the resulting
    # avg_li is still a clean, fully hand-verifiable number.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, inn_ct integer, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, event_id integer, outs_ct text, event_outs_ct text, "
            "event_runs_ct text, base1_run_id text, base2_run_id text, base3_run_id text, "
            "start_bat_score_ct text, start_fld_score_ct text, "
            "bat_event_fl text, _season text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, gametype text, visteam text, hometeam text, _season text)"
        )
        cur.execute(
            "INSERT INTO gold.leverage_index "
            "(inning_bucket, is_bottom, outs_before, base_state, margin_bucket, "
            "leverage_index, sample_size) VALUES "
            "(1, false, 0, '000', 0, 1.2000, 1000)"
        )

        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, city, state) "
            "VALUES ('ATL01', 'Truist Park', 'Atlanta', 'GA') RETURNING id"
        )
        (venue_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year, "
            "mlb_team_id) VALUES "
            "('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {r[1]: r[0] for r in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]

        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name, birth_date) "
            "VALUES ('degrj001', 'Jacob', 'deGrom', '1988-06-19'), "
            "       ('scher001', 'Max', 'Scherzer', '1984-07-27')"
        )

        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, away_team_id, "
            " home_score, away_score, game_type, venue_id) VALUES "
            "('G1', 2021, '2021-04-01', 0, %(atl)s, %(nya)s, 5, 3, 'regular', %(v)s), "
            "('G2', 2021, '2021-04-08', 0, %(atl)s, %(nya)s, 4, 2, 'regular', %(v)s), "
            "('G3', 2022, '2022-04-01', 0, %(atl)s, %(nya)s, 6, 1, 'regular', %(v)s)",
            {"atl": atl, "nya": nya, "v": venue_id},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular'), ('G3', 'regular')"
        )

        # Seed G1 events for Jacob deGrom (ATL starter):
        # 30 PA, all inning=1/top/0 outs/bases empty/margin=0 (LI = 1.2000
        # each, per the fixture row above) -> Total LI = 36.00 -> avg = 1.2000
        for i in range(30):
            cur.execute(
                "INSERT INTO raw.retrosheet_event "
                "(game_id, inn_ct, bat_home_id, resp_pit_id, resp_pit_start_fl, "
                "event_id, outs_ct, event_outs_ct, event_runs_ct, "
                "base1_run_id, base2_run_id, base3_run_id, "
                "start_bat_score_ct, start_fld_score_ct, bat_event_fl, _season) "
                "VALUES ('G1', 1, '0', 'degrj001', 'T', %(i)s, '0', '1', '0', "
                "NULL, NULL, NULL, '0', '0', 'T', '2021')",
                {"i": i + 1},
            )

        # Seed G2 events
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "event_id, outs_ct, event_outs_ct, event_runs_ct, "
            "base1_run_id, base2_run_id, base3_run_id, "
            "start_bat_score_ct, start_fld_score_ct, bat_event_fl, _season) "
            "VALUES ('G2', 1, '0', 'degrj001', 'T', 1, '0', '1', '0', "
            "NULL, NULL, NULL, '0', '0', 'T', '2021')"
        )
    db_conn.commit()

    features.build(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature f "
            "SET home_starter_id = p.id "
            "FROM core.game g "
            "JOIN core.player p ON p.retro_id = 'degrj001' "
            "WHERE f.game_id = g.id AND g.retro_game_id IN ('G1', 'G2', 'G3')"
        )
    db_conn.commit()

    rows = run_expectancy.compute(db_conn)
    assert rows > 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_avg_li "
            "FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        res = {r[0]: r[1] for r in cur.fetchall()}

    # G1: first game of 2021 -> NULL
    assert res["G1"] is None

    # G2: entering avg LI = 36.00 / 30 = 1.2000
    assert float(res["G2"]) == 1.2000

    # G3: first game of 2022 -> NULL (season partition reset)
    assert res["G3"] is None

    _reset(db_conn)


def test_compute_is_idempotent(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, inn_ct integer, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, event_id integer, outs_ct text, event_outs_ct text, "
            "event_runs_ct text, base1_run_id text, base2_run_id text, base3_run_id text, "
            "start_bat_score_ct text, start_fld_score_ct text, "
            "bat_event_fl text, _season text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, gametype text, visteam text, hometeam text, _season text)"
        )
    db_conn.commit()

    features.build(db_conn)
    first_pass = run_expectancy.compute(db_conn)
    second_pass = run_expectancy.compute(db_conn)
    assert first_pass == second_pass
    _reset(db_conn)


def test_compute_missing_table_gate(db_conn):
    _reset(db_conn)
    assert run_expectancy.compute(db_conn) == 0


def test_health_check_passes(db_conn):
    checks = run_expectancy.health_check()
    assert len(checks) == 1
    assert checks[0].ok
