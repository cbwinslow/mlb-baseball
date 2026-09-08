"""Rest-of-season sim reads core.game directly -- it must count regular-season
games only (incl. Game 163), never postseason. ADR-282 / separate-postseason-stats.
"""

from mlb_baseball.model.ros import RestOfSeasonSimulator


def _seed(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('NYA','NYA','Yanks',1901,2030),('BOS','BOS','Sox',1901,2030) "
            "RETURNING id, retro_team_id"
        )
        ids = {r[1]: r[0] for r in cur.fetchall()}
        # 3 completed regular-season games: NYA wins all 3.
        for n in range(1, 4):
            cur.execute(
                "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, game_number, "
                "home_team_id, away_team_id, home_score, away_score, game_type) "
                "VALUES (%s,%s,2024,'2024-05-01',%s,%s,%s,5,2,'regular')",
                (f"NYA20240501{n}", f"70{n}", n, ids["NYA"], ids["BOS"]),
            )
        # A completed World Series game (Oct) NYA also "wins" -- must be ignored.
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, game_number, "
            "home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('NYA20241026WS','70ws',2024,'2024-10-26',1,%s,%s,8,1,'worldseries')",
            (ids["NYA"], ids["BOS"]),
        )
    db_conn.commit()
    return ids


def test_simulate_ros_excludes_postseason_from_current_standings(db_conn):
    _seed(db_conn)
    report = RestOfSeasonSimulator(random_seed=1).simulate_ros(
        season=2024, as_of_date="2024-11-01", n_sims=20, conn=db_conn
    )
    nya = next(p for p in report.team_projections if p.retro_team_id == "NYA")
    bos = next(p for p in report.team_projections if p.retro_team_id == "BOS")
    # 3 regular-season games, not 4 -- the World Series game is not counted.
    assert (nya.current_wins, nya.current_losses) == (3, 0)
    assert (bos.current_wins, bos.current_losses) == (0, 3)
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()
