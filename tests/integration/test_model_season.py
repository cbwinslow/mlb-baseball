"""Integration tests for Full-Season Monte Carlo Simulation Engine (PROJ-01, ADR-109)."""

from mlb_baseball.model.season import (
    ALL_MLB_TEAMS,
    load_schedule_from_db,
    simulate_season_monte_carlo,
    team_strength_asof,
    team_wins_asof,
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
                    "game_number, home_team_id, away_team_id, game_type) "
                    "VALUES (%s, %s, %s, '2024-04-01', %s, %s, %s, 'regular')",
                    (
                        f"{t1}{season}0401{game_num}",
                        f"99{i}{game_num}",
                        season,
                        game_num,
                        team_id_map[t1],
                        team_id_map[t2],
                    ),
                )
        # One postseason game between the first two teams -- load_schedule_from_db
        # must NOT return it (regular-season sim; ADR-282 / separate-postseason-stats).
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, game_type) "
            "VALUES (%s, %s, %s, '2024-10-26', 1, %s, %s, 'worldseries')",
            (
                f"{ALL_MLB_TEAMS[0]}{season}1026PS",
                "99postseason",
                season,
                team_id_map[ALL_MLB_TEAMS[0]],
                team_id_map[ALL_MLB_TEAMS[1]],
            ),
        )
    db_conn.commit()


def test_load_schedule_from_db_and_simulate_season(db_conn):
    """Verify schedule retrieval from PostgreSQL and season Monte Carlo simulation."""
    _seed_teams_and_season_schedule(db_conn, season=2024)

    schedule = load_schedule_from_db(2024, conn=db_conn)
    assert len(schedule) == 60  # 15 matchups * 4 games -- the World Series game is excluded
    assert all(g.game_date == "2024-04-01" for g in schedule)

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


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
        for team in ALL_MLB_TEAMS:
            cur.execute(
                "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
                "VALUES (%s, %s, %s, 1901, 2030) RETURNING id",
                (team, team, "Team"),
            )
        cur.execute("SELECT id, retro_team_id FROM core.team")
        team_id_map = {row[1]: row[0] for row in cur.fetchall()}
    db_conn.commit()
    return team_id_map


def test_team_strength_asof_real_runs_differentiate_teams_and_fallback_for_no_games(db_conn):
    """Verify real per-team Pythagorean strength from real runs, with a logged 0.500 fallback."""
    team_id_map = _seed_teams(db_conn)
    strong, weak, no_games_team = ALL_MLB_TEAMS[0], ALL_MLB_TEAMS[1], ALL_MLB_TEAMS[2]
    season = 2024

    with db_conn.cursor() as cur:
        # `strong` outscores opponents 6-2 in 5 real games before the cutoff.
        for i in range(5):
            cur.execute(
                "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
                "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
                "VALUES (%s, %s, %s, %s, 1, %s, %s, 6, 2, 'regular')",
                (
                    f"{strong}S{i}",
                    f"8{i}0",
                    season,
                    f"2024-04-0{i + 1}",
                    team_id_map[strong],
                    team_id_map[weak],
                ),
            )
        # 5 more games, same 6-2 result, on different dates/game_pks (`weak`
        # is the away side of every game above -- its real per-game runs
        # allowed/scored come from the same rows, no separate insert needed
        # for `weak` itself).
        for i in range(5):
            cur.execute(
                "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
                "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
                "VALUES (%s, %s, %s, %s, 1, %s, %s, 6, 2, 'regular')",
                (
                    f"{strong}W{i}",
                    f"8{i}1",
                    season,
                    f"2024-04-1{i}",
                    team_id_map[strong],
                    team_id_map[weak],
                ),
            )
    db_conn.commit()

    talents = team_strength_asof(season=season, as_of="2024-12-01", conn=db_conn)

    assert len(talents) == 30
    assert talents[strong] > 0.500
    assert talents[weak] < 0.500
    assert talents[strong] > talents[weak]
    # A team with zero games before the cutoff gets the explicit 0.500 fallback.
    assert talents[no_games_team] == 0.500

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_team_strength_asof_excludes_games_on_or_after_cutoff(db_conn):
    """No-lookahead: a game on or after `as_of` must not affect the computed strength."""
    team_id_map = _seed_teams(db_conn)
    team_a, team_b = ALL_MLB_TEAMS[0], ALL_MLB_TEAMS[1]
    season = 2024

    with db_conn.cursor() as cur:
        # One real game before the cutoff: team_a wins 3-1.
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('G1', '9001', %s, '2024-04-01', 1, %s, %s, 3, 1, 'regular')",
            (season, team_id_map[team_a], team_id_map[team_b]),
        )
        # One game ON the cutoff date and one AFTER it, both blowouts the other
        # way -- if either leaked in, team_a's strength would drop sharply.
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('G2', '9002', %s, '2024-04-10', 1, %s, %s, 0, 10, 'regular')",
            (season, team_id_map[team_a], team_id_map[team_b]),
        )
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('G3', '9003', %s, '2024-04-15', 1, %s, %s, 0, 10, 'regular')",
            (season, team_id_map[team_a], team_id_map[team_b]),
        )
    db_conn.commit()

    talents_before_cutoff_games = team_strength_asof(
        season=season, as_of="2024-04-10", conn=db_conn
    )

    # Only G1 (3-1 win) qualifies; the strong Pythagorean strength proves G2/G3
    # (the 0-10 losses on and after the cutoff) did not leak in.
    assert talents_before_cutoff_games[team_a] > 0.600

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_team_wins_asof_counts_real_wins_before_cutoff_only(db_conn):
    """Verify real win counting, with a strict cutoff (no-lookahead) and a 0-win default."""
    team_id_map = _seed_teams(db_conn)
    team_a, team_b, never_plays = ALL_MLB_TEAMS[0], ALL_MLB_TEAMS[1], ALL_MLB_TEAMS[2]
    season = 2024

    with db_conn.cursor() as cur:
        # team_a wins 2, loses 1, all before the cutoff.
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('W1', '9101', %s, '2024-04-01', 1, %s, %s, 5, 1, 'regular')",
            (season, team_id_map[team_a], team_id_map[team_b]),
        )
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('W2', '9102', %s, '2024-04-02', 1, %s, %s, 1, 4, 'regular')",
            (season, team_id_map[team_b], team_id_map[team_a]),
        )
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('L1', '9103', %s, '2024-04-03', 1, %s, %s, 6, 2, 'regular')",
            (season, team_id_map[team_b], team_id_map[team_a]),
        )
        # A win for team_a ON the cutoff date must not count (strict <).
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('W3', '9104', %s, '2024-04-10', 1, %s, %s, 9, 0, 'regular')",
            (season, team_id_map[team_a], team_id_map[team_b]),
        )
    db_conn.commit()

    wins = team_wins_asof(season=season, as_of="2024-04-10", conn=db_conn)

    assert len(wins) == 30
    assert wins[team_a] == 2
    assert wins[team_b] == 1
    assert wins[never_plays] == 0

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_ath_team_code_normalizes_to_oak(db_conn):
    """Real `core.team` rows key the Athletics as 'ATH' since their 2025 relocation, but
    ALL_MLB_TEAMS/MLB_DIVISIONS key the franchise as 'OAK'. load_schedule_from_db,
    team_strength_asof, and team_wins_asof must normalize 'ATH' -> 'OAK' or the
    Athletics' real games are either dropped or crash team_true_talents/team_idx_map
    lookups downstream (PR #242 CodeRabbit review).
    """
    season = 2025
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
        for team in ALL_MLB_TEAMS:
            retro_id = "ATH" if team == "OAK" else team
            cur.execute(
                "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
                "VALUES (%s, %s, %s, 1901, 2030) RETURNING id",
                (retro_id, team, "Team"),
            )
        cur.execute("SELECT id, retro_team_id FROM core.team")
        team_id_map = {row[1]: row[0] for row in cur.fetchall()}
        opponent = ALL_MLB_TEAMS[1] if ALL_MLB_TEAMS[1] != "OAK" else ALL_MLB_TEAMS[2]

        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, "
            "game_number, home_team_id, away_team_id, home_score, away_score, game_type) "
            "VALUES ('ATH1', '9201', %s, '2025-04-01', 1, %s, %s, 5, 1, 'regular')",
            (season, team_id_map["ATH"], team_id_map[opponent]),
        )
    db_conn.commit()

    schedule = load_schedule_from_db(season, conn=db_conn)
    assert any(g.home_team == "OAK" for g in schedule)
    assert not any(g.home_team == "ATH" or g.away_team == "ATH" for g in schedule)
    assert len(schedule) == 1
    assert schedule[0].home_team == "OAK"
    assert schedule[0].away_team == opponent

    talents = team_strength_asof(season=season, as_of="2025-12-01", conn=db_conn)
    assert "ATH" not in talents
    assert talents["OAK"] > 0.500  # OAK won 5-1; real runs must attribute to the 'OAK' key

    wins = team_wins_asof(season=season, as_of="2025-12-01", conn=db_conn)
    assert "ATH" not in wins
    assert wins["OAK"] == 1

    # End-to-end: the normalized schedule must not crash
    # simulate_season_monte_carlo with a KeyError on an unrecognized team.
    result = simulate_season_monte_carlo(
        schedule=schedule,
        team_true_talents={t: 0.500 for t in ALL_MLB_TEAMS},
        n_simulations=50,
        seed=1,
        season=season,
    )
    assert result.season == season

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()
