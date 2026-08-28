from decimal import Decimal

import psycopg

from mlb_baseball.model import features, statcast_expected


def _reset(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM gold.game_feature "
            "WHERE game_id IN (SELECT id FROM core.game WHERE season = 2024)"
        )
        cur.execute("DELETE FROM core.game WHERE season = 2024")
        cur.execute("DELETE FROM core.player WHERE retro_id IN ('degro001', 'scher001')")
        cur.execute("DELETE FROM core.team WHERE retro_team_id IN ('ATL', 'NYM')")
        cur.execute("DELETE FROM core.venue WHERE retro_park_id = 'ATL01'")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event CASCADE")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo CASCADE")


def test_compute_noop_when_raw_missing(db_conn):
    _reset(db_conn)
    assert statcast_expected.compute(db_conn) == 0


def test_compute_populates_statcast_expected_metrics(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, inn_ct integer, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, event_id integer, outs_ct text, event_outs_ct text, "
            "event_runs_ct text, base1_run_id text, base2_run_id text, base3_run_id text, "
            "bat_event_fl text, event_cd text, battedball_cd text, h_cd text, "
            "bat_hand_cd text, resp_bat_hand_cd text, _season text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, gametype text, visteam text, hometeam text, _season text)"
        )

        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, city, state) "
            "VALUES ('ATL01', 'Truist Park', 'Atlanta', 'GA') RETURNING id"
        )
        (venue_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025) RETURNING id"
        )
        (home_team_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('NYM', 'New York', 'Mets', 1962, 2025) RETURNING id"
        )
        (away_team_id,) = cur.fetchone()

        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('degro001', 'Jacob', 'deGrom') RETURNING id"
        )
        (home_sp_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('scher001', 'Max', 'Scherzer') RETURNING id"
        )
        (away_sp_id,) = cur.fetchone()

        # Insert 2 games
        cur.execute(
            "INSERT INTO core.game ("
            "retro_game_id, season, game_date, game_number, home_score, away_score, "
            "game_type, home_team_id, away_team_id, venue_id) "
            "VALUES ('ATL202405010', 2024, '2024-05-01', 0, 5, 3, 'regular', %s, %s, %s) "
            "RETURNING id",
            (home_team_id, away_team_id, venue_id),
        )
        (g1_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game ("
            "retro_game_id, season, game_date, game_number, home_score, away_score, "
            "game_type, home_team_id, away_team_id, venue_id) "
            "VALUES ('ATL202405080', 2024, '2024-05-08', 0, 4, 2, 'regular', %s, %s, %s) "
            "RETURNING id",
            (home_team_id, away_team_id, venue_id),
        )
        (g2_id,) = cur.fetchone()

        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, visteam, hometeam, _season) "
            "VALUES ('ATL202405010', 'regular', 'NYM', 'ATL', '2024'), "
            "       ('ATL202405080', 'regular', 'NYM', 'ATL', '2024')"
        )
    db_conn.commit()

    features.build(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature f SET home_starter_id = p.id "
            "FROM core.game g, core.player p "
            "WHERE g.id = f.game_id AND p.retro_id = 'degro001'"
        )
        cur.execute(
            "UPDATE gold.game_feature f SET away_starter_id = p.id "
            "FROM core.game g, core.player p "
            "WHERE g.id = f.game_id AND p.retro_id = 'scher001'"
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        # 50 events for starter degro001 in game 1:
        # 10 line drives (battedball_cd='L', event_cd='20')
        # 5 barrels / HRs (battedball_cd='L', event_cd='23', h_cd='4')
        # 10 fly balls (battedball_cd='F', event_cd='2')
        # 10 ground balls (battedball_cd='G', event_cd='2')
        # 5 popups (battedball_cd='P', event_cd='2')
        # 6 strikeouts (event_cd='3')
        # 3 walks (event_cd='14')
        # 1 HBP (event_cd='16')
        starter_events = (
            [("20", "L", "0", "0")] * 10
            + [("23", "L", "4", "0")] * 5
            + [("2", "F", "0", "1")] * 10
            + [("2", "G", "0", "1")] * 10
            + [("2", "P", "0", "1")] * 5
            + [("3", None, "0", "1")] * 6
            + [("14", None, "0", "0")] * 3
            + [("16", None, "0", "0")] * 1
        )

        event_id = 1
        for e_cd, bb_cd, h_cd, outs in starter_events:
            cur.execute(
                "INSERT INTO raw.retrosheet_event ("
                "game_id, inn_ct, bat_home_id, resp_pit_id, resp_pit_start_fl, event_id, "
                "event_outs_ct, event_runs_ct, bat_event_fl, event_cd, battedball_cd, h_cd, "
                "bat_hand_cd, _season) "
                "VALUES ('ATL202405010', 1, '0', 'degro001', 'T', %s, %s, '0', 'T', %s, "
                "%s, %s, 'R', '2024')",
                (event_id, outs, e_cd, bb_cd, h_cd),
            )
            event_id += 1

        # Seed G2 event for starter degro001
        cur.execute(
            "INSERT INTO raw.retrosheet_event ("
            "game_id, inn_ct, bat_home_id, resp_pit_id, resp_pit_start_fl, event_id, "
            "event_outs_ct, event_runs_ct, bat_event_fl, event_cd, battedball_cd, h_cd, "
            "bat_hand_cd, _season) "
            "VALUES ('ATL202405080', 1, '0', 'degro001', 'T', 1, '1', '0', 'T', '3', "
            "NULL, '0', 'R', '2024')"
        )

        db_conn.commit()

    updated = statcast_expected.compute(db_conn)
    assert updated >= 2

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_hard_hit_pct, home_starter_barrel_pct, home_starter_xba, "
            "       home_starter_xslg, home_starter_xwoba "
            "FROM gold.game_feature WHERE game_id = %s",
            (g1_id,),
        )
        row_g1 = cur.fetchone()
        # Zero lookahead: Game 1 has no preceding games, so rates should be NULL
        assert all(v is None for v in row_g1)

        cur.execute(
            "SELECT home_starter_hard_hit_pct, home_starter_barrel_pct, home_starter_xba, "
            "       home_starter_xslg, home_starter_xwoba "
            "FROM gold.game_feature WHERE game_id = %s",
            (g2_id,),
        )
        row_g2 = cur.fetchone()
        hard_hit_pct, barrel_pct, xba, xslg, xwoba = row_g2

        # Verify against hand-calculated fixtures
        assert hard_hit_pct == Decimal("0.3750")  # 15 / 40
        assert barrel_pct == Decimal("0.1250")  # 5 / 40
        assert xba == Decimal("0.3565")  # 16.40 / 46
        assert xslg == Decimal("0.8065")  # 37.10 / 46
        assert xwoba == Decimal("0.5058")  # 25.29 / 50


def test_health_check_passes():
    checks = statcast_expected.health_check()
    assert len(checks) == 2
    domain_check = next(c for c in checks if c.name == "model.statcast_expected.domain")
    assert domain_check.ok is True
