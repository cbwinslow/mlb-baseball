from decimal import Decimal

import psycopg

from mlb_baseball.model import features, pitcher_estimators


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
    assert pitcher_estimators.compute(db_conn) == 0


def test_compute_populates_pitcher_estimators_and_platoons(db_conn):
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
        # LHB (20 events):
        # 6 Ks (event_cd=3, outs=1), 2 BB (event_cd=14, outs=0), 1 HBP (event_cd=16, outs=0),
        # 3 1B (event_cd=20, outs=0), 1 2B (event_cd=21, outs=0), 1 HR (event_cd=23, outs=0),
        # 4 FBs (battedball_cd='F', outs=1), 2 GBs (battedball_cd='G', outs=1),
        # 1 PU (battedball_cd='P', outs=1)
        lhb_events = [
            ("3", None, "1", "L"),
            ("3", None, "1", "L"),
            ("3", None, "1", "L"),
            ("3", None, "1", "L"),
            ("3", None, "1", "L"),
            ("3", None, "1", "L"),
            ("14", None, "0", "L"),
            ("14", None, "0", "L"),
            ("16", None, "0", "L"),
            ("20", None, "0", "L"),
            ("20", None, "0", "L"),
            ("20", None, "0", "L"),
            ("21", None, "0", "L"),
            ("23", None, "0", "L"),  # HR is also a flyball
            ("2", "F", "1", "L"),
            ("2", "F", "1", "L"),
            ("2", "F", "1", "L"),
            ("2", "F", "1", "L"),
            ("2", "G", "1", "L"),
            ("2", "P", "1", "L"),
        ]

        # RHB (20 events):
        # 4 Ks (event_cd=3, outs=1), 2 BB (event_cd=14, outs=0),
        # 2 1B (event_cd=20, outs=0), 1 2B (event_cd=21, outs=0), 1 3B (event_cd=22, outs=0),
        # 5 FBs (battedball_cd='F', 1 out, 4 non-outs), 10 GBs (battedball_cd='G', 0 outs),
        # 1 PU (battedball_cd='P', 1 out)
        # Total RHB outs = 4 + 1 + 1 = 6 outs. Total game outs = 12 + 6 = 18 outs (6.0 IP).
        rhb_events = [
            ("3", None, "1", "R"),
            ("3", None, "1", "R"),
            ("3", None, "1", "R"),
            ("3", None, "1", "R"),
            ("14", None, "0", "R"),
            ("14", None, "0", "R"),
            ("20", None, "0", "R"),
            ("20", None, "0", "R"),
            ("21", None, "0", "R"),
            ("22", None, "0", "R"),
            ("2", "F", "1", "R"),
            ("2", "F", "0", "R"),
            ("2", "F", "0", "R"),
            ("2", "F", "0", "R"),
            ("2", "F", "0", "R"),
            ("2", "G", "0", "R"),
            ("2", "G", "0", "R"),
            ("2", "G", "0", "R"),
            ("2", "G", "0", "R"),
            ("2", "P", "1", "R"),
        ]

        event_id = 1
        for e_cd, bb_cd, outs, hand in lhb_events + rhb_events:
            cur.execute(
                "INSERT INTO raw.retrosheet_event ("
                "game_id, inn_ct, bat_home_id, resp_pit_id, resp_pit_start_fl, event_id, "
                "event_outs_ct, event_runs_ct, bat_event_fl, event_cd, battedball_cd, "
                "bat_hand_cd, _season) "
                "VALUES ('ATL202405010', 1, '0', 'degro001', 'T', %s, %s, '0', 'T', %s, "
                "%s, %s, '2024')",
                (event_id, outs, e_cd, bb_cd, hand),
            )
            event_id += 1

        # Seed G2 event for starter degro001
        cur.execute(
            "INSERT INTO raw.retrosheet_event ("
            "game_id, inn_ct, bat_home_id, resp_pit_id, resp_pit_start_fl, event_id, "
            "event_outs_ct, event_runs_ct, bat_event_fl, event_cd, battedball_cd, "
            "bat_hand_cd, _season) "
            "VALUES ('ATL202405080', 1, '0', 'degro001', 'T', 1, '1', '0', 'T', '3', "
            "NULL, 'R', '2024')"
        )

        db_conn.commit()

    updated = pitcher_estimators.compute(db_conn)
    assert updated >= 2

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_xfip, home_starter_siera, home_starter_vs_lhb_woba, "
            "       home_starter_vs_rhb_woba, home_starter_vs_lhb_k_pct, home_starter_vs_rhb_k_pct "
            "FROM gold.game_feature WHERE game_id = %s",
            (g1_id,),
        )
        row_g1 = cur.fetchone()
        # Zero lookahead: Game 1 has no preceding games, so rates should be NULL
        assert all(v is None for v in row_g1)

        cur.execute(
            "SELECT home_starter_xfip, home_starter_siera, home_starter_vs_lhb_woba, "
            "       home_starter_vs_rhb_woba, home_starter_vs_lhb_k_pct, home_starter_vs_rhb_k_pct "
            "FROM gold.game_feature WHERE game_id = %s",
            (g2_id,),
        )
        row_g2 = cur.fetchone()
        xfip, siera, vs_lhb_woba, vs_rhb_woba, vs_lhb_k_pct, vs_rhb_k_pct = row_g2

        # Verify against hand-calculated fixtures
        assert xfip == Decimal("4.5417")
        # SIERA tied out against the published formula (Swartz & Seidman,
        # "Introducing SIERA," Baseball Prospectus, 2010,
        # https://www.baseballprospectus.com/news/article/10045/introducing-siera-part-5/):
        #   SIERA = 6.145 - 16.986*(K/PA) + 11.434*(BB/PA) - 1.858*(netGB/PA)
        #           + 7.653*(K/PA)^2 +/- 6.664*(netGB/PA)^2
        #           + 10.130*(K/PA)*(netGB/PA) - 5.195*(BB/PA)*(netGB/PA)
        #   where netGB = GB - FB - PU, and the +/- on the squared netGB term
        #   is negative when netGB/PA > 0, positive when netGB/PA < 0.
        # This fixture: PA=40, K=10, BB=4, GB=5, FB=10, PU=2 -> netGB/PA=-0.175.
        # Plan 06 tie-out (2026-08-25) found the formula as originally shipped
        # (ADR-090) used the wrong coefficients on both interaction terms
        # (-9.096/-3.037 instead of +10.130/-5.195) and the wrong variable
        # (raw GB%, not net GB%) in the squared and both interaction terms —
        # confirmed by fetching the primary BP source directly, independently
        # cross-checked against a second source. Fixed in
        # mlb_baseball/sql/team_pitcher_estimators_retrosheet_update.sql; this
        # feeds gbm.py's FEATURE_COLUMNS (starter_siera_diff/bullpen_siera_diff)
        # in production, so the champion model needs retraining to reflect it
        # — see docs/PACKAGE_VALIDATION_STATUS.md.
        assert siera == Decimal("3.6972")
        assert vs_lhb_k_pct == Decimal("0.3000")  # 6/20
        assert vs_rhb_k_pct == Decimal("0.2000")  # 4/20
        assert vs_lhb_woba == Decimal(
            "0.4070"
        )  # (0.69*2 + 0.72*1 + 0.89*3 + 1.27*1 + 2.10*1) / 20 = 8.14 / 20 = 0.4070
        assert vs_rhb_woba == Decimal(
            "0.3025"
        )  # (0.69*2 + 0.89*2 + 1.27*1 + 1.62*1) / 20 = 6.05 / 20 = 0.3025


def test_health_check_passes():
    checks = pitcher_estimators.health_check()
    assert len(checks) == 2
    domain_check = next(c for c in checks if c.name == "model.pitcher_estimators.domain")
    assert domain_check.ok is True
