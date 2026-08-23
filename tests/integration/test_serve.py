"""Integration tests for the Serving Layer (`serve.*`) (SRV-01, ADR-102)."""

from mlb_baseball import serve


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.team")
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('BOS', 'Boston', 'Red Sox', 1901, 2025, 111), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM core.market")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.player WHERE id IN (101, 102)")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_serve_daily_betting_grid_and_pitcher_card(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    bos_id = teams["BOS"]
    nya_id = teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (id, retro_id, mlbam_id, first_name, last_name) VALUES "
            "(101, 'p1_retro', '101', 'Chris', 'Sale'), "
            "(102, 'p2_retro', '102', 'Gerrit', 'Cole') "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO gold.game_feature ("
            "game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_starter_id, away_starter_id, home_starter_throws, home_starter_era, "
            "home_starter_siera, home_starter_csw_pct, home_starter_vert_separation_in, "
            "home_pyth_wpct, away_pyth_wpct, home_elo, away_elo) VALUES ("
            "'SRV-G1', 999001, 2024, '2024-06-01', %(home_id)s, %(away_id)s, "
            "101, 102, 'L', 2.85, 3.10, 0.325, 22.5, 0.580, 0.420, 1560, 1440)",
            {"home_id": bos_id, "away_id": nya_id},
        )
        cur.execute(
            "INSERT INTO gold.prediction ("
            "mlb_game_pk, game_instance_key, model_version, home_win_prob) VALUES "
            "(999001, 'SRV-G1', 'gbm-v1', 0.625), (999001, 'SRV-G1', 'elo-v1', 0.590)"
        )
    db_conn.commit()

    grid = serve.fetch_daily_betting_grid(game_date="2024-06-01", conn=db_conn)
    assert len(grid) == 1
    g = grid[0]
    assert g["home_team_code"] == "BOS"
    assert g["away_team_code"] == "NYA"
    assert g["home_starter_name"] == "Chris Sale"
    assert float(g["gbm_home_win_prob"]) == 0.625

    cards = serve.fetch_pitcher_card(player_id=101, conn=db_conn)
    assert len(cards) == 1
    c = cards[0]
    assert c["full_name"] == "Chris Sale"
    assert c["throws"] == "L"
    assert float(c["siera"]) == 3.10
    assert float(c["vert_separation_in"]) == 22.5

    _reset(db_conn)
