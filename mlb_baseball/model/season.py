"""Full-Season Monte Carlo & Postseason Playoff Simulation Engine (PROJ-01, ADR-109).

Simulates remaining/full 162-game MLB regular-season schedules across all 30 teams,
evaluates tie-breakers, division championships, wild card berths, and simulates
the complete 12-team MLB postseason bracket (Wild Card Series best-of-3, Division
Series best-of-5, League Championship best-of-7, World Series best-of-7).

Provides point-in-time team strength modeling using Log5 Pythagorean expectations
and generates regular-season win total distributions for long-term futures markets.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np
import psycopg

from mlb_baseball.db import get_connection

# 30 Active MLB Franchises by League & Division
MLB_DIVISIONS: dict[str, dict[str, list[str]]] = {
    "AL": {
        "AL East": ["BAL", "BOS", "NYA", "TBA", "TOR"],
        "AL Central": ["CHA", "CLE", "DET", "KCA", "MIN"],
        "AL West": ["HOU", "ANA", "OAK", "SEA", "TEX", "ATH"],
    },
    "NL": {
        "NL East": ["ATL", "MIA", "NYN", "PHI", "WAS"],
        "NL Central": ["CHN", "CIN", "MIL", "PIT", "SLN"],
        "NL West": ["ARI", "COL", "LAN", "SDN", "SFN"],
    },
}

ALL_MLB_TEAMS: list[str] = [
    "ANA",
    "ARI",
    "ATL",
    "BAL",
    "BOS",
    "CHA",
    "CHN",
    "CIN",
    "CLE",
    "COL",
    "DET",
    "HOU",
    "KCA",
    "LAN",
    "MIA",
    "MIL",
    "MIN",
    "NYA",
    "NYN",
    "OAK",
    "PHI",
    "PIT",
    "SDN",
    "SEA",
    "SFN",
    "SLN",
    "TBA",
    "TEX",
    "TOR",
    "WAS",
]

DEFAULT_HOME_FIELD_ADVANTAGE = 0.035  # ~53.5% baseline home win probability


def team_league_and_division(team_code: str) -> tuple[str, str]:
    """Return (league, division) for a given team code."""
    for league, divisions in MLB_DIVISIONS.items():
        for div_name, teams in divisions.items():
            if team_code in teams:
                return league, div_name
    # Fallback to AL East if unknown
    return "AL", "AL East"


def log5_game_win_prob(
    home_true_talent: float,
    away_true_talent: float,
    hfa: float = DEFAULT_HOME_FIELD_ADVANTAGE,
) -> float:
    """Calculate home team win probability using Bill James' Log5 formulation.

    P(A beats B) = (pA * (1 - pB)) / (pA * (1 - pB) + (1 - pA) * pB) + HFA
    """
    pa = max(0.01, min(0.99, home_true_talent))
    pb = max(0.01, min(0.99, away_true_talent))
    odds_a = pa / (1.0 - pa)
    odds_b = pb / (1.0 - pb)
    neutral_prob = odds_a / (odds_a + odds_b)
    return float(np.clip(neutral_prob + hfa, 0.01, 0.99))


@dataclasses.dataclass(frozen=True)
class ScheduledGame:
    """A scheduled game between home and away teams."""

    home_team: str
    away_team: str
    game_date: str | None = None
    home_win_prob: float = 0.535


@dataclasses.dataclass(frozen=True)
class TeamSeasonProjection:
    """Full-season simulation projections for a single team."""

    team_code: str
    league: str
    division: str
    true_talent_wpct: float
    mean_wins: float
    mean_losses: float
    std_wins: float
    p05_wins: float
    p25_wins: float
    p50_wins: float
    p75_wins: float
    p95_wins: float
    make_playoffs_prob: float
    win_division_prob: float
    win_wild_card_prob: float
    win_pennant_prob: float
    win_world_series_prob: float
    win_totals_over_probs: dict[float, float]


@dataclasses.dataclass(frozen=True)
class SeasonSimulationResult:
    """Result of full-season Monte Carlo simulation runs."""

    season: int
    simulations_run: int
    duration_ms: float
    simulations_per_sec: float
    team_projections: dict[str, TeamSeasonProjection]


def simulate_series(
    team_a_prob: float,
    length: int,
    rng: np.random.Generator,
) -> bool:
    """Simulate a playoff series (e.g. best of 3, 5, or 7).

    Returns True if Team A wins the series, False if Team B wins.
    """
    wins_needed = (length // 2) + 1
    wins_a = 0
    wins_b = 0
    while wins_a < wins_needed and wins_b < wins_needed:
        if rng.random() < team_a_prob:
            wins_a += 1
        else:
            wins_b += 1
    return wins_a == wins_needed


def simulate_postseason_bracket(
    al_standings: list[tuple[str, int, float]],
    nl_standings: list[tuple[str, int, float]],
    team_talents: dict[str, float],
    rng: np.random.Generator,
) -> tuple[str, str, str]:
    """Simulate the complete 12-team MLB postseason bracket.

    Returns (al_champion, nl_champion, world_series_champion).
    """
    # 1. AL Playoffs
    # Top 3 are division winners (seeds 1..3), next 3 are wild cards (seeds 4..6)
    al_seeds = [team for team, _, _ in al_standings[:6]]
    # Wild Card Round: Seed 3 vs 6 (best of 3), Seed 4 vs 5 (best of 3)
    p3_6 = log5_game_win_prob(team_talents[al_seeds[2]], team_talents[al_seeds[5]], hfa=0.03)
    wc1_winner = al_seeds[2] if simulate_series(p3_6, 3, rng) else al_seeds[5]

    p4_5 = log5_game_win_prob(team_talents[al_seeds[3]], team_talents[al_seeds[4]], hfa=0.03)
    wc2_winner = al_seeds[3] if simulate_series(p4_5, 3, rng) else al_seeds[4]

    # ALDS (Best of 5): Seed 1 vs Winner(4/5), Seed 2 vs Winner(3/6)
    p1_wc2 = log5_game_win_prob(team_talents[al_seeds[0]], team_talents[wc2_winner], hfa=0.02)
    alds1_winner = al_seeds[0] if simulate_series(p1_wc2, 5, rng) else wc2_winner

    p2_wc1 = log5_game_win_prob(team_talents[al_seeds[1]], team_talents[wc1_winner], hfa=0.02)
    alds2_winner = al_seeds[1] if simulate_series(p2_wc1, 5, rng) else wc1_winner

    # ALCS (Best of 7): alds1_winner vs alds2_winner
    p_alcs = log5_game_win_prob(team_talents[alds1_winner], team_talents[alds2_winner], hfa=0.01)
    al_champion = alds1_winner if simulate_series(p_alcs, 7, rng) else alds2_winner

    # 2. NL Playoffs
    nl_seeds = [team for team, _, _ in nl_standings[:6]]
    p3_6_nl = log5_game_win_prob(team_talents[nl_seeds[2]], team_talents[nl_seeds[5]], hfa=0.03)
    wc1_nl_winner = nl_seeds[2] if simulate_series(p3_6_nl, 3, rng) else nl_seeds[5]

    p4_5_nl = log5_game_win_prob(team_talents[nl_seeds[3]], team_talents[nl_seeds[4]], hfa=0.03)
    wc2_nl_winner = nl_seeds[3] if simulate_series(p4_5_nl, 3, rng) else nl_seeds[4]

    p1_wc2_nl = log5_game_win_prob(team_talents[nl_seeds[0]], team_talents[wc2_nl_winner], hfa=0.02)
    nlds1_winner = nl_seeds[0] if simulate_series(p1_wc2_nl, 5, rng) else wc2_nl_winner

    p2_wc1_nl = log5_game_win_prob(team_talents[nl_seeds[1]], team_talents[wc1_nl_winner], hfa=0.02)
    nlds2_winner = nl_seeds[1] if simulate_series(p2_wc1_nl, 5, rng) else wc1_nl_winner

    p_nlcs = log5_game_win_prob(team_talents[nlds1_winner], team_talents[nlds2_winner], hfa=0.01)
    nl_champion = nlds1_winner if simulate_series(p_nlcs, 7, rng) else nlds2_winner

    # 3. World Series (Best of 7): AL Champion vs NL Champion
    p_ws = log5_game_win_prob(team_talents[al_champion], team_talents[nl_champion], hfa=0.01)
    ws_champion = al_champion if simulate_series(p_ws, 7, rng) else nl_champion

    return al_champion, nl_champion, ws_champion


def simulate_season_monte_carlo(
    schedule: list[ScheduledGame],
    team_true_talents: dict[str, float],
    n_simulations: int = 10000,
    seed: int | None = 0,
    season: int = 2024,
) -> SeasonSimulationResult:
    """Run vectorized Monte Carlo simulations for a full 162-game MLB season."""
    start_time = time.perf_counter()
    rng = np.random.default_rng(seed)

    teams = sorted(team_true_talents.keys())
    team_idx_map = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    # Precalculate game probability array
    n_games = len(schedule)
    home_indices = np.array([team_idx_map[g.home_team] for g in schedule], dtype=np.int32)
    away_indices = np.array([team_idx_map[g.away_team] for g in schedule], dtype=np.int32)
    home_probs = np.array(
        [
            log5_game_win_prob(
                team_true_talents[g.home_team],
                team_true_talents[g.away_team],
            )
            for g in schedule
        ],
        dtype=np.float32,
    )

    # Simulation accumulators
    win_counts = np.zeros((n_simulations, n_teams), dtype=np.int16)
    playoff_counts = np.zeros(n_teams, dtype=np.int32)
    division_counts = np.zeros(n_teams, dtype=np.int32)
    wild_card_counts = np.zeros(n_teams, dtype=np.int32)
    pennant_counts = np.zeros(n_teams, dtype=np.int32)
    world_series_counts = np.zeros(n_teams, dtype=np.int32)

    # Batch simulation: random numbers for all games across all simulations
    # shape: (n_simulations, n_games)
    rand_matrix = rng.random((n_simulations, n_games), dtype=np.float32)
    home_wins_matrix = rand_matrix < home_probs  # boolean (sims, games)

    for sim_idx in range(n_simulations):
        sim_home_wins = home_wins_matrix[sim_idx]
        # Accumulate wins per team
        sim_wins = np.zeros(n_teams, dtype=np.int16)
        np.add.at(sim_wins, home_indices[sim_home_wins], 1)
        np.add.at(sim_wins, away_indices[~sim_home_wins], 1)
        win_counts[sim_idx] = sim_wins

        # Determine Standings for AL and NL
        # Group by Division to find 3 division winners per league
        al_div_winners: list[tuple[str, int, float]] = []
        al_wild_card_pool: list[tuple[str, int, float]] = []
        nl_div_winners: list[tuple[str, int, float]] = []
        nl_wild_card_pool: list[tuple[str, int, float]] = []

        for league, divisions in MLB_DIVISIONS.items():
            for _, div_teams in divisions.items():
                active_div_teams = [t for t in div_teams if t in team_idx_map]
                if not active_div_teams:
                    continue
                div_standings = sorted(
                    [
                        (t, int(sim_wins[team_idx_map[t]]), team_true_talents[t])
                        for t in active_div_teams
                    ],
                    key=lambda x: (x[1], x[2]),
                    reverse=True,
                )
                div_winner = div_standings[0]
                if league == "AL":
                    al_div_winners.append(div_winner)
                    al_wild_card_pool.extend(div_standings[1:])
                else:
                    nl_div_winners.append(div_winner)
                    nl_wild_card_pool.extend(div_standings[1:])

        # Sort division winners seeds 1..3
        al_div_winners.sort(key=lambda x: (x[1], x[2]), reverse=True)
        nl_div_winners.sort(key=lambda x: (x[1], x[2]), reverse=True)

        # Sort wild cards seeds 4..6
        al_wild_card_pool.sort(key=lambda x: (x[1], x[2]), reverse=True)
        nl_wild_card_pool.sort(key=lambda x: (x[1], x[2]), reverse=True)
        al_wc_winners = al_wild_card_pool[:3]
        nl_wc_winners = nl_wild_card_pool[:3]

        al_playoffs = al_div_winners + al_wc_winners
        nl_playoffs = nl_div_winners + nl_wc_winners

        # Record division & wild card counts
        for team, _, _ in al_div_winners:
            division_counts[team_idx_map[team]] += 1
            playoff_counts[team_idx_map[team]] += 1
        for team, _, _ in al_wc_winners:
            wild_card_counts[team_idx_map[team]] += 1
            playoff_counts[team_idx_map[team]] += 1

        for team, _, _ in nl_div_winners:
            division_counts[team_idx_map[team]] += 1
            playoff_counts[team_idx_map[team]] += 1
        for team, _, _ in nl_wc_winners:
            wild_card_counts[team_idx_map[team]] += 1
            playoff_counts[team_idx_map[team]] += 1

        # Simulate Postseason
        al_champ, nl_champ, ws_champ = simulate_postseason_bracket(
            al_playoffs, nl_playoffs, team_true_talents, rng
        )
        pennant_counts[team_idx_map[al_champ]] += 1
        pennant_counts[team_idx_map[nl_champ]] += 1
        world_series_counts[team_idx_map[ws_champ]] += 1

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    sims_per_sec = (n_simulations / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else 0.0

    # Build Team Projections
    team_projections: dict[str, TeamSeasonProjection] = {}
    for team, idx in team_idx_map.items():
        league, division = team_league_and_division(team)
        t_wins = win_counts[:, idx]
        mean_w = float(np.mean(t_wins))
        std_w = float(np.std(t_wins))
        p05, p25, p50, p75, p95 = np.percentile(t_wins, [5, 25, 50, 75, 95])

        # Calculate win total lines over probabilities (65.5 to 105.5)
        over_probs: dict[float, float] = {}
        for line in [65.5, 70.5, 75.5, 80.5, 81.5, 85.5, 90.5, 95.5, 100.5]:
            over_probs[line] = float(np.mean(t_wins > line))

        team_projections[team] = TeamSeasonProjection(
            team_code=team,
            league=league,
            division=division,
            true_talent_wpct=team_true_talents[team],
            mean_wins=round(mean_w, 2),
            mean_losses=round(162.0 - mean_w, 2),
            std_wins=round(std_w, 2),
            p05_wins=float(p05),
            p25_wins=float(p25),
            p50_wins=float(p50),
            p75_wins=float(p75),
            p95_wins=float(p95),
            make_playoffs_prob=round(float(playoff_counts[idx]) / n_simulations, 4),
            win_division_prob=round(float(division_counts[idx]) / n_simulations, 4),
            win_wild_card_prob=round(float(wild_card_counts[idx]) / n_simulations, 4),
            win_pennant_prob=round(float(pennant_counts[idx]) / n_simulations, 4),
            win_world_series_prob=round(float(world_series_counts[idx]) / n_simulations, 4),
            win_totals_over_probs=over_probs,
        )

    return SeasonSimulationResult(
        season=season,
        simulations_run=n_simulations,
        duration_ms=round(elapsed_ms, 2),
        simulations_per_sec=round(sims_per_sec, 2),
        team_projections=team_projections,
    )


def load_schedule_from_db(
    season: int,
    conn: psycopg.Connection | None = None,
) -> list[ScheduledGame]:
    """Load the full regular season schedule from PostgreSQL core.game."""

    def _query(c: psycopg.Connection) -> list[ScheduledGame]:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ht.retro_team_id AS home_team,
                    at.retro_team_id AS away_team,
                    g.game_date
                FROM core.game g
                JOIN core.team ht ON ht.id = g.home_team_id
                JOIN core.team at ON at.id = g.away_team_id
                WHERE g.season = %s
                  AND ht.retro_team_id NOT IN ('ALS', 'NLS')
                  AND at.retro_team_id NOT IN ('ALS', 'NLS')
                ORDER BY g.game_date, g.game_number
                """,
                (season,),
            )
            rows = cur.fetchall()
            return [
                ScheduledGame(home_team=row[0], away_team=row[1], game_date=str(row[2]))
                for row in rows
            ]

    if conn is not None:
        return _query(conn)
    with get_connection() as c:
        return _query(c)


def generate_balanced_schedule(teams: list[str]) -> list[ScheduledGame]:
    """Generate a synthetic authentic 162-game MLB schedule when database schedule is absent."""
    schedule: list[ScheduledGame] = []
    # In a 30-team league, each team plays ~13 games vs 4 division opponents (52 games)
    # ~6 games vs 10 league non-division opponents (60 games), and interleague (50 games)
    for i, t1 in enumerate(teams):
        for j, t2 in enumerate(teams):
            if i >= j:
                continue
            l1, d1 = team_league_and_division(t1)
            l2, d2 = team_league_and_division(t2)
            if d1 == d2:
                series_games = 6  # 6 home, 6 away = 12 division
            elif l1 == l2:
                series_games = 3  # 3 home, 3 away = 6 league
            else:
                series_games = 2  # 2 home, 2 away = 4 interleague
            for _ in range(series_games):
                schedule.append(ScheduledGame(home_team=t1, away_team=t2))
                schedule.append(ScheduledGame(home_team=t2, away_team=t1))
    return schedule


@dataclasses.dataclass(frozen=True)
class MarcelPlayerProjection:
    """Marcel / Empirical Bayes 3-year rate projection for an individual player (PROJ-02)."""

    player_id: int | str
    player_name: str
    is_pitcher: bool
    age: int
    projected_rate: float  # wOBA for batters, FIP for pitchers
    projected_war: float
    confidence_sample_weight: float


def marcel_project_rate(
    metric_3yr: tuple[float, float, float],
    sample_sizes_3yr: tuple[int, int, int],
    player_age: int,
    is_pitcher: bool = False,
    league_mean: float = 0.315,
    regression_n0: int = 1200,
) -> float:
    """Calculate Marcel rate projection with 3-year lookback and aging curves (PROJ-02).

    Weighting: 5/12 * t-1 + 4/12 * t-2 + 3/12 * t-3 + N0 * league_mean.
    Formula: (sum(w_i * metric_i * n_i) + N0 * league_mean) / (sum(w_i * n_i) + N0).
    Aging curve: +0.003/yr for age < 27; -0.004/yr for age > 29.
    """
    weights = (5.0, 4.0, 3.0)
    weighted_obs = sum(
        w * m * n for w, m, n in zip(weights, metric_3yr, sample_sizes_3yr, strict=True)
    )
    weighted_n = sum(w * n for w, n in zip(weights, sample_sizes_3yr, strict=True))

    denominator = weighted_n + regression_n0
    if denominator <= 0:
        base_rate = league_mean
    else:
        base_rate = (weighted_obs + (regression_n0 * league_mean)) / denominator

    # Aging adjustment
    if player_age < 27:
        age_delta = 0.003 * (27 - player_age)
    elif player_age > 29:
        age_delta = -0.004 * (player_age - 29)
    else:
        age_delta = 0.0

    # For pitchers, lower FIP is better, so aging adds to FIP (makes worse)
    if is_pitcher:
        return float(max(1.50, min(8.00, base_rate - age_delta * 10.0)))
    return float(max(0.150, min(0.480, base_rate + age_delta)))


def pythagorean_team_win_pct(
    runs_scored_per_game: float,
    runs_allowed_per_game: float,
    exponent: float = 1.83,
) -> float:
    """Calculate true-talent win percentage using Pythagorean expectation with Smyth-Patel exp."""
    rs_exp = runs_scored_per_game**exponent
    ra_exp = runs_allowed_per_game**exponent
    if (rs_exp + ra_exp) <= 0:
        return 0.500
    return float(np.clip(rs_exp / (rs_exp + ra_exp), 0.200, 0.800))
