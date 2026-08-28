"""Integration tests for Player Props Prediction System (PROP-01, ADR-106)."""

# ruff: noqa: E501

from mlb_baseball.model.props import fetch_game_pitcher_props


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def _seed_game_with_starters(db_conn, game_pk="712999"):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('BOS', 'Boston', 'Red Sox', 1901, 2030), ('NYY', 'New York', 'Yankees', 1903, 2030) "
            "RETURNING id"
        )
        home_team_id, away_team_id = [row[0] for row in cur.fetchall()]

        cur.execute(
            "INSERT INTO core.player (retro_id, bbref_id, first_name, last_name) "
            "VALUES ('sale001', 'salech01', 'Chris', 'Sale'), ('cole001', 'coleg01', 'Gerrit', 'Cole') "
            "RETURNING id"
        )
        home_pitcher_id, away_pitcher_id = [row[0] for row in cur.fetchall()]

        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, game_number, home_team_id, away_team_id) "
            "VALUES ('BOS202405010', %s, 2024, '2024-05-01', 1, %s, %s) RETURNING id",
            (game_pk, home_team_id, away_team_id),
        )
        (game_id,) = cur.fetchone()

        cur.execute(
            """
            INSERT INTO gold.game_feature (
                game_id, mlb_game_pk, game_instance_key, season, game_date, game_number, feature_cutoff_at,
                home_team_id, away_team_id, home_starter_id, away_starter_id,
                home_starter_k_pct, away_starter_k_pct, home_starter_rest_days, away_starter_rest_days,
                home_starter_outs_7d, away_starter_outs_7d, home_k_pct, away_k_pct
            ) VALUES (
                %s, %s, %s, 2024, '2024-05-01', 1, '2024-05-01 19:00:00+00',
                %s, %s, %s, %s,
                0.315, 0.290, 5, 4,
                18.0, 0.0, 0.210, 0.240
            )
            """,
            (
                game_id,
                game_pk,
                f"mlb:{game_pk}",
                home_team_id,
                away_team_id,
                home_pitcher_id,
                away_pitcher_id,
            ),
        )
    db_conn.commit()


def test_fetch_game_pitcher_props_end_to_end(db_conn):
    """Verify end-to-end pitcher prop calculations from PostgreSQL game_feature table."""
    _reset(db_conn)
    _seed_game_with_starters(db_conn, game_pk="712999")

    props = fetch_game_pitcher_props("712999", conn=db_conn)
    assert len(props) == 2

    home_prop, away_prop = props
    assert home_prop.player_name == "Chris Sale"
    assert home_prop.expected_k > 5.0
    assert 0.0 < home_prop.over_under_probs[5.5] < 1.0

    assert away_prop.player_name == "Gerrit Cole"
    assert away_prop.expected_k > 5.0
    _reset(db_conn)


def test_fetch_game_pitcher_props_empty_when_not_found(db_conn):
    """Verify clean empty list when game_pk does not exist."""
    _reset(db_conn)
    props = fetch_game_pitcher_props("999999", conn=db_conn)
    assert props == []
    _reset(db_conn)
