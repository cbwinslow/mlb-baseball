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
        cur.execute("DELETE FROM core.game")
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


def test_serve_pitcher_props_and_live_game_tracker(db_conn):
    _reset(db_conn)


def test_serve_daily_betting_grid_uses_latest_prediction_snapshot_only(db_conn):
    # Regression test for the 0087 fix: gold.prediction intentionally keeps
    # every prediction snapshot ever generated for a game/model (see
    # mlb_baseball/model/evaluation.py's docstring) -- a still-upcoming game
    # accumulates one new row per daily `mlb predict` cron cycle. Before
    # 0087, serve.daily_betting_grid joined gold.prediction directly on
    # (game_instance_key, model_version), so two snapshots for the same
    # game/model fanned the underlying gold.game_feature row out into two
    # grid rows -- one per historical snapshot, not one per game.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    bos_id = teams["BOS"]
    nya_id = teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature ("
            "game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id) "
            "VALUES ('SRV-G3', 999003, 2024, '2024-06-03', %(home_id)s, %(away_id)s)",
            {"home_id": bos_id, "away_id": nya_id},
        )
        cur.execute(
            "INSERT INTO gold.prediction ("
            "mlb_game_pk, game_instance_key, model_version, generated_at, home_win_prob) VALUES "
            "(999003, 'SRV-G3', 'gbm-v1', '2024-06-02 12:00:00+00', 0.44), "
            "(999003, 'SRV-G3', 'gbm-v1', '2024-06-02 18:00:00+00', 0.66)"
        )
    db_conn.commit()

    grid = serve.fetch_daily_betting_grid(game_date="2024-06-03", conn=db_conn)

    assert len(grid) == 1
    assert float(grid[0]["gbm_home_win_prob"]) == 0.66

    _reset(db_conn)


def test_serve_prediction_market_alpha_uses_latest_prediction_snapshot_only(db_conn):
    # Same regression as above, for serve.prediction_market_alpha -- also
    # fixed by 0087, also previously joined gold.prediction directly.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    bos_id = teams["BOS"]
    nya_id = teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('SRVG4', '999004', 2024, '2024-06-04', %(home_id)s, %(away_id)s, "
            "5, 3, 'regular') RETURNING id",
            {"home_id": bos_id, "away_id": nya_id},
        )
        (game_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature ("
            "game_id, game_instance_key, mlb_game_pk, season, game_date, "
            "home_team_id, away_team_id) VALUES "
            "(%s, 'SRV-G4', 999004, 2024, '2024-06-04', %s, %s)",
            (game_id, bos_id, nya_id),
        )
        cur.execute(
            "INSERT INTO core.market "
            "(game_id, source, market_ref, team_id, implied_probability, volume, status) "
            "VALUES (%s, 'kalshi', 'KXMLBGAME-BOS', %s, 0.55, 1000, 'closed')",
            (game_id, bos_id),
        )
        cur.execute(
            "INSERT INTO gold.prediction ("
            "mlb_game_pk, game_instance_key, model_version, generated_at, home_win_prob) VALUES "
            "(999004, 'SRV-G4', 'gbm-v1', '2024-06-03 12:00:00+00', 0.40), "
            "(999004, 'SRV-G4', 'gbm-v1', '2024-06-03 18:00:00+00', 0.70)"
        )
    db_conn.commit()

    alpha = serve.fetch_prediction_market_alpha(min_edge=0.0, game_date="2024-06-04", conn=db_conn)

    assert len(alpha) == 1
    assert float(alpha[0]["model_home_win_prob"]) == 0.70

    _reset(db_conn)


def test_serve_sgp_grid_uses_latest_predictions_and_actual_pitcher_hand(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (id, retro_id, mlbam_id, first_name, last_name) VALUES "
            "(101, 'p1_retro', '101', 'Chris', 'Sale') "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO gold.game_feature ("
            "game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_starter_id, home_starter_throws, home_starter_fastball_velo) VALUES ("
            "'SRV-G2', 999002, 2024, '2024-06-02', %(home_id)s, %(away_id)s, "
            "101, 'L', 94.5)",
            {"home_id": teams["BOS"], "away_id": teams["NYA"]},
        )
        cur.execute(
            "INSERT INTO gold.prediction ("
            "mlb_game_pk, game_instance_key, model_version, generated_at, home_win_prob) VALUES "
            "(999002, 'SRV-G2', 'gbm-v2', '2024-06-01 12:00:00+00', 0.410), "
            "(999002, 'SRV-G2', 'gbm-v2', '2024-06-01 13:00:00+00', 0.610)"
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT home_win_prob FROM serve.sgp_matchup_grid WHERE mlb_game_pk = '999002'")
        probabilities = cur.fetchall()
        cur.execute("SELECT throws FROM serve.pitcher_arsenal WHERE pitcher_id = 101")
        throws = cur.fetchall()

    assert len(probabilities) == 1
    assert float(probabilities[0][0]) == 0.610
    assert throws == [("L",)]

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
            "INSERT INTO core.game (id, retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score) VALUES "
            "(999, 'BOS202406010', '999001', 2024, '2024-06-01', 1, "
            "%(home_id)s, %(away_id)s, 5, 3)",
            {"home_id": bos_id, "away_id": nya_id},
        )
        cur.execute(
            "INSERT INTO gold.game_feature ("
            "game_id, game_instance_key, mlb_game_pk, season, game_date, "
            "home_team_id, away_team_id, home_starter_id, away_starter_id, "
            "home_starter_k_pct, away_starter_k_pct, "
            "home_k_pct, away_k_pct, home_starter_siera, away_starter_siera, home_win) VALUES ("
            "999, 'SRV-G1', 999001, 2024, '2024-06-01', %(home_id)s, %(away_id)s, "
            "101, 102, 0.315, 0.290, 0.210, 0.240, 3.10, 3.35, true)",
            {"home_id": bos_id, "away_id": nya_id},
        )
    db_conn.commit()

    props = serve.fetch_pitcher_prop_market(game_date="2024-06-01", conn=db_conn)
    assert len(props) == 1
    p = props[0]
    assert p["home_starter_name"] == "Chris Sale"
    assert p["away_starter_name"] == "Gerrit Cole"
    assert float(p["home_starter_projected_k_pct"]) > 0.30

    live_games = serve.fetch_live_game_tracker(game_date="2024-06-01", conn=db_conn)
    assert len(live_games) == 1
    lg = live_games[0]
    assert lg["home_team"] == "BOS"
    assert lg["away_team"] == "NYA"
    assert lg["current_home_score"] == 5
    assert lg["current_away_score"] == 3
    assert lg["actual_home_win"] is True

    _reset(db_conn)
