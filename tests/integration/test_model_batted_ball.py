"""Integration tests for mlb_baseball.model.batted_ball.

Validates point-in-time calculation of entering batted-ball profile metrics
(GB%, FB%, LD%, HR/FB) for starters, bullpens, and lineups.
"""

from decimal import Decimal

from mlb_baseball.model import batted_ball, features


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo", "raw.mlb_schedule"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player WHERE retro_id IN ('degrj001', 'scher001')")
        cur.execute("DELETE FROM core.team WHERE retro_team_id IN ('ATL', 'NYA')")
        cur.execute("DELETE FROM core.venue WHERE retro_park_id = 'ATL01'")
    db_conn.commit()


def test_compute_calculates_batted_ball_rates_with_zero_leakage(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, resp_pit_id text, resp_pit_start_fl text, "
            "event_cd text, ab_fl text, sf_fl text, bat_event_fl text, "
            "h_cd text, battedball_cd text, _season text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, gametype text, visteam text, hometeam text, _season text)"
        )
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, city, first_year, last_year) "
            "VALUES ('ATL01', 'Test Park', 'Atlanta', 1966, 2025) RETURNING id"
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
        # 15 GB, 10 FB (with 2 HR), 5 LD, 2 PU -> Total BBE = 32
        for _ in range(15):
            cur.execute(
                "INSERT INTO raw.retrosheet_event "
                "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
                "event_cd, ab_fl, sf_fl, bat_event_fl, h_cd, battedball_cd, _season) "
                "VALUES ('G1', '0', 'degrj001', 'T', '2', 'T', 'F', 'T', '0', 'G', '2021')"
            )
        for i in range(10):
            event_cd = "23" if i < 2 else "2"
            h_cd = "4" if i < 2 else "0"
            cur.execute(
                "INSERT INTO raw.retrosheet_event "
                "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
                "event_cd, ab_fl, sf_fl, bat_event_fl, h_cd, battedball_cd, _season) "
                "VALUES ('G1', '0', 'degrj001', 'T', %(e)s, 'T', 'F', 'T', %(h)s, 'F', '2021')",
                {"e": event_cd, "h": h_cd},
            )
        for _ in range(5):
            cur.execute(
                "INSERT INTO raw.retrosheet_event "
                "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
                "event_cd, ab_fl, sf_fl, bat_event_fl, h_cd, battedball_cd, _season) "
                "VALUES ('G1', '0', 'degrj001', 'T', '2', 'T', 'F', 'T', '0', 'L', '2021')"
            )
        for _ in range(2):
            cur.execute(
                "INSERT INTO raw.retrosheet_event "
                "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
                "event_cd, ab_fl, sf_fl, bat_event_fl, h_cd, battedball_cd, _season) "
                "VALUES ('G1', '0', 'degrj001', 'T', '2', 'T', 'F', 'T', '0', 'P', '2021')"
            )

        # Seed G2 events
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "event_cd, ab_fl, sf_fl, bat_event_fl, h_cd, battedball_cd, _season) "
            "VALUES ('G2', '0', 'degrj001', 'T', '2', 'T', 'F', 'T', '0', 'G', '2021')"
        )
    db_conn.commit()

    features.build(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature f SET home_starter_id = p.id "
            "FROM core.game g, core.player p "
            "WHERE g.id = f.game_id AND p.retro_id = 'degrj001'"
        )
    db_conn.commit()

    updated = batted_ball.compute(db_conn)
    assert updated > 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_gb_pct, f.home_starter_fb_pct, "
            "       f.home_starter_ld_pct, f.home_starter_hr_per_fb "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.game_date"
        )
        res = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: Entering G1, degrj001 has no prior 2021 games -> all rates NULL (zero leakage)
    assert res["G1"] == (None, None, None, None)

    # G2: Entering G2, degrj001 has G1's 32 BBE:
    # 15/32 = 0.4688, 10/32 = 0.3125, 5/32 = 0.1563, 2/10 = 0.2000
    assert abs(res["G2"][0] - Decimal("0.4688")) < Decimal("0.001")
    assert abs(res["G2"][1] - Decimal("0.3125")) < Decimal("0.001")
    assert abs(res["G2"][2] - Decimal("0.1563")) < Decimal("0.001")
    assert abs(res["G2"][3] - Decimal("0.2000")) < Decimal("0.001")

    # G3 (season 2022 fresh partition): zero leakage across seasons
    assert res["G3"] == (None, None, None, None)

    _reset(db_conn)


def test_compute_is_idempotent(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, event_cd text, ab_fl text, sf_fl text, bat_event_fl text, "
            "h_cd text, battedball_cd text, _season text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, gametype text, visteam text, hometeam text, _season text)"
        )
    db_conn.commit()

    features.build(db_conn)
    first_pass = batted_ball.compute(db_conn)
    second_pass = batted_ball.compute(db_conn)
    assert first_pass == second_pass
    _reset(db_conn)


def test_compute_missing_table_gate(db_conn):
    _reset(db_conn)
    assert batted_ball.compute(db_conn) == 0


def test_health_check_passes(db_conn):
    checks = batted_ball.health_check()
    assert len(checks) == 1
    assert checks[0].ok
