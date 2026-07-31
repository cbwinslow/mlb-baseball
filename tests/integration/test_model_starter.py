"""Regression coverage for mlb_baseball.model.starter -- true FIP and
K%/BB%/HR% computed from raw.retrosheet_event (ADR-034).

Every value in the fixture below is hand-computed and checked in the test
itself (see the comment above each assertion) -- same discipline as
features.py/elo.py's tests, and the same discipline this module's own
docstring documents against real production data (Jacob deGrom's 2018
season, and a full-scale reconciliation against raw.bref_pitching).
"""

from decimal import Decimal

from mlb_baseball.model import features, starter


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
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    db_conn.commit()


def _seed_teams_and_players(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('startp1', 'Start', 'PitcherOne'), "
            "('startp2', 'Start', 'PitcherTwo') "
            "RETURNING id, retro_id"
        )
        players = {retro_id: player_id for player_id, retro_id in cur.fetchall()}
    return teams, players


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_event")
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_gameinfo")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_rolling_fip_and_rates_match_hand_calculation(db_conn):
    # startp1 (ATL, home) pitches game G1: 1 K, 1 BB, 1 HR, 3 generic outs
    # (all batter events, 4 outs total) plus one non-batter-event out (a
    # caught stealing -- must still count toward outs, per this module's
    # own docstring finding from deGrom's real data) -- 5 outs total, 6
    # batters faced.
    #
    # Entering G2 (7 days later), startp1's rolling line is exactly:
    # BF=6, K=1, BB=1, HR=1, outs=5 -- so:
    #   k_pct = 1/6 = 0.16667, bb_pct = 1/6, hr_pct = 1/6
    #   fip = (13*1 + 3*(1+0) - 2*1) / (5/3) + 3.10 = 8.4 + 3.10 = 11.5
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams, players = _seed_teams_and_players(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            # startp1 (ATL's starter) pitching to the away team (bat_home_id=0)
            "('G1', '0', 'startp1', 'T', 'T', '3', '1', '2020'), "  # K
            "('G1', '0', 'startp1', 'T', 'T', '14', '0', '2020'), "  # BB
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "  # generic out
            "('G1', '0', 'startp1', 'T', 'T', '23', '0', '2020'), "  # HR
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "  # generic out
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "  # generic out
            "('G1', '0', 'startp1', 'T', 'F', '6', '1', '2020'), "  # caught stealing
            # startp2 (NYA's starter) pitching to the home team (bat_home_id=1)
            # -- minimal, just enough to be identifiable as the away starter.
            "('G1', '1', 'startp2', 'T', 'T', '2', '1', '2020'), "
            # G2: same two starters again, so we can check startp1's rolling
            # entering-G2 line without it needing any events of its own yet.
            "('G2', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G2', '1', 'startp2', 'T', 'T', '2', '1', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = starter.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_id, f.home_starter_era, "
            "f.home_starter_k_pct, f.home_starter_bb_pct, f.home_starter_hr_pct, "
            "f.home_starter_rest "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: startp1's first appearance -- nothing prior, everything NULL
    # except the identity itself.
    g1 = rows["G1"]
    assert g1[0] == players["startp1"]
    assert g1[1:5] == (None, None, None, None)

    # G2: entering it, startp1's rolling line from G1 alone.
    g2 = rows["G2"]
    assert g2[0] == players["startp1"]
    assert g2[1] == Decimal("11.5")
    assert abs(g2[2] - Decimal("1") / Decimal("6")) < Decimal("0.0001")
    assert abs(g2[3] - Decimal("1") / Decimal("6")) < Decimal("0.0001")
    assert abs(g2[4] - Decimal("1") / Decimal("6")) < Decimal("0.0001")
    assert g2[5] == 7  # 2020-04-08 minus 2020-04-01

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert starter.compute(db_conn) == 0


def test_health_check_runs_cleanly_against_an_empty_database():
    # Not asserting on the result -- just that it returns cleanly even
    # when raw.bref_pitching/raw.retrosheet_event don't exist yet (the
    # real, at-scale reconciliation only means something against
    # production data, see this module's own docstring).
    checks = starter.health_check()
    assert len(checks) == 2
    assert all(c.name for c in checks)
