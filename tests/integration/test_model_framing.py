"""Regression coverage for mlb_baseball.model.framing -- prior-season
team catcher-framing value via Statcast and in-season starting catcher CSAE% (CAT-02, ADR-045).
"""

from decimal import Decimal

from mlb_baseball.model import features, framing


def _ensure_framing_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_framing')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_framing "
                "(id text, name text, pitches text, rv_tot text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, inn_ct integer, bat_home_id text, event_cd text, "
                "event_tx text, pos2_fld_id text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_gameinfo ("
                "gid text, gametype text, visteam text, hometeam text, _season text)"
            )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for t in ("raw.statcast_framing", "raw.retrosheet_event", "raw.retrosheet_gameinfo"):
            cur.execute(f"SELECT to_regclass('{t}')")
            if cur.fetchone()[0]:
                cur.execute(f"DELETE FROM {t}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player_war")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_sums_multiple_catchers_and_resolves_bref_team_codes(db_conn):
    _reset(db_conn)
    _ensure_framing_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('LAN', 'Los Angeles', 'Dodgers', 1958, 9999, 119), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        lan, nya = teams["LAN"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('catcp001', '1001', 'Primary', 'Catcher'), "
            "('catcp002', '1002', 'Backup', 'Catcher') "
            "RETURNING id, mlbam_id"
        )
        players = {mlbam_id: player_id for player_id, mlbam_id in cur.fetchall()}
        p1, p2 = players["1001"], players["1002"]
        cur.execute(
            "INSERT INTO core.player_war (player_id, season, is_pitcher, team_code, war) VALUES "
            "(%s, 2023, false, 'LAD', 3.0), "
            "(%s, 2023, false, 'LAD', 0.5), "
            "(%s, 2024, false, 'LAD', 3.5)",
            (p1, p2, p1),
        )
        cur.execute(
            "INSERT INTO raw.statcast_framing (id, name, pitches, rv_tot, _season) VALUES "
            "('1001', 'Primary Catcher', '5000', '6.5', '2023'), "
            "('1002', 'Backup Catcher', '800', '-1.2', '2023'), "
            "('1001', 'Primary Catcher', '5200', '9.0', '2024')"
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (lan, nya),
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = framing.compute(db_conn)
    db_conn.commit()

    assert updated >= 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_framing_prior, away_framing_prior FROM gold.game_feature")
        (home_prior, away_prior) = cur.fetchone()

    assert home_prior == Decimal("5.3")
    assert away_prior is None

    _reset(db_conn)


def test_compute_in_season_catcher_framing_matches_hand_calculation(db_conn):
    # In G1: LAN home fielding (bat_home_id='0', pos2_fld_id='catcp001').
    # 15 called strikes ('3' / 'C'), 15 balls ('14' / 'B') -> 30 takes.
    # Entering G2:
    #   called strike rate = 15/30 = 0.5000
    #   csae_pct = 0.5000 - 0.3300 = +0.1700
    #   framing_runs = (15 - 9.90) * 0.125 = 5.10 * 0.125 = 0.64
    _reset(db_conn)
    _ensure_framing_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('LAN', 'Los Angeles', 'Dodgers', 1958, 9999, 119), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        lan, nya = teams["LAN"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(lan)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-08', %(lan)s, %(nya)s, 4, 2, 'regular')",
            {"lan": lan, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        # 15 called strikes + 15 balls for catcp001 in G1
        events = []
        for _ in range(15):
            events.append("('G1', 1, '0', '3', 'C', 'catcp001', '2024')")
            events.append("('G1', 1, '0', '14', 'B', 'catcp001', '2024')")
        # G2 minimal event
        events.append("('G2', 1, '0', '3', 'C', 'catcp001', '2024')")
        events.append("('G2', 1, '1', '3', 'C', 'catcp002', '2024')")

        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, event_cd, event_tx, pos2_fld_id, _season) "
            f"VALUES {', '.join(events)}"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = framing.compute(db_conn)
    db_conn.commit()

    assert updated >= 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_catcher_csae_pct, f.home_catcher_framing_runs "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'G2'"
        )
        (retro_id, csae, runs) = cur.fetchone()

    assert csae == Decimal("0.1700")
    assert runs == Decimal("0.64")

    _reset(db_conn)


def test_health_check_returns_ok_on_clean_data(db_conn):
    _reset(db_conn)
    _ensure_framing_tables(db_conn)
    checks = framing.health_check()
    assert all(c.ok for c in checks)
    _reset(db_conn)
