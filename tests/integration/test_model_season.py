"""Integration tests for Full-Season Monte Carlo Simulation Engine (PROJ-01, ADR-109)."""

from mlb_baseball.model.season import (
    ALL_MLB_TEAMS,
    load_schedule_from_db,
    simulate_season_monte_carlo,
)


def _seed_teams_and_season_schedule(db_conn, season=2024):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
        # Insert all 30 teams
        for team in ALL_MLB_TEAMS:
            cur.execute(
                "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
                "VALUES (%s, %s, %s, 1901, 2030) RETURNING id",
                (team, team, "Team"),
            )
        cur.execute("SELECT id, retro_team_id FROM core.team")
        team_id_map = {row[1]: row[0] for row in cur.fetchall()}

        # Insert a sample schedule for 30 teams (e.g. 60 games)
        for i in range(0, len(ALL_MLB_TEAMS), 2):
            t1, t2 = ALL_MLB_TEAMS[i], ALL_MLB_TEAMS[i + 1]
            for game_num in range(1, 5):
                cur.execute(
                    "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
                    "game_number, home_team_id, away_team_id) "
                    "VALUES (%s, %s, %s, '2024-04-01', %s, %s, %s)",
                    (
                        f"{t1}{season}0401{game_num}",
                        f"99{i}{game_num}",
                        season,
                        game_num,
                        team_id_map[t1],
                        team_id_map[t2],
                    ),
                )
    db_conn.commit()


def test_load_schedule_from_db_and_simulate_season(db_conn):
    """Verify schedule retrieval from PostgreSQL and season Monte Carlo simulation."""
    _seed_teams_and_season_schedule(db_conn, season=2024)

    schedule = load_schedule_from_db(2024, conn=db_conn)
    assert len(schedule) == 60  # 15 matchups * 4 games

    talents = {t: 0.500 for t in ALL_MLB_TEAMS}
    result = simulate_season_monte_carlo(
        schedule=schedule,
        team_true_talents=talents,
        n_simulations=500,
        seed=42,
        season=2024,
    )

    assert result.season == 2024
    assert result.simulations_run == 500
    assert len(result.team_projections) == 30
    assert result.duration_ms > 0

    # Verify team projection structure
    nyy = result.team_projections["NYA"]
    assert nyy.league == "AL"
    assert nyy.division == "AL East"
    assert nyy.mean_wins >= 0
    assert 0.0 <= nyy.make_playoffs_prob <= 1.0
    assert 0.0 <= nyy.win_world_series_prob <= 1.0

    # Clean up
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()
