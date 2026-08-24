"""Player-Game Props Prediction System (PROP-01, ADR-106).

Provides probabilistic forecast models for individual player proposition markets
(starting pitcher strikeouts, outs recorded/IP, batter hits, total bases, anytime HR)
using point-in-time sabermetrics, Log5 odds composition, and Poisson/Negative Binomial
distributions.

Formula citations:
- Pitcher & Batter Log5 Odds Ratio: Bill James / Tom Tango, The Book (2007)
- Strikeout Poisson / NegBin count distribution: Albert & Bennett, Curve Ball (2001)
- Park & component multipliers: FanGraphs Sabermetric Library
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from mlb_baseball.db import get_connection

DEFAULT_LEAGUE_K_PCT = 0.225
DEFAULT_LEAGUE_HR_PCT = 0.030
DEFAULT_LEAGUE_HIT_PCT = 0.245
DEFAULT_STARTER_BATTERS_FACED = 22.5
DEFAULT_BATTER_PLATE_APPEARANCES = 4.15


def log5_matchup_rate(rate_a: float, rate_b: float, league_rate: float) -> float:
    """Combine two individual rates against league average using Bill James Log5 odds ratio."""
    p_a = max(0.01, min(0.99, rate_a))
    p_b = max(0.01, min(0.99, rate_b))
    lg = max(0.01, min(0.99, league_rate))

    odds_a = p_a / (1.0 - p_a)
    odds_b = p_b / (1.0 - p_b)
    odds_lg = lg / (1.0 - lg)

    odds_matchup = (odds_a * odds_b) / odds_lg
    return odds_matchup / (1.0 + odds_matchup)


def poisson_pmf(k: int, mu: float) -> float:
    """Compute Poisson probability mass function P(X = k) given mean mu."""
    if mu <= 0.0:
        return 1.0 if k == 0 else 0.0
    if k < 0:
        return 0.0
    return (math.exp(-mu) * (mu**k)) / math.factorial(k)


def poisson_cdf(k: int, mu: float) -> float:
    """Compute Poisson cumulative distribution function P(X <= k) given mean mu."""
    if k < 0:
        return 0.0
    if mu <= 0.0:
        return 1.0
    prob_sum = 0.0
    for i in range(k + 1):
        prob_sum += poisson_pmf(i, mu)
    return min(1.0, prob_sum)


def poisson_over_prob(line: float, mu: float) -> float:
    """Compute probability that outcome strictly exceeds line (P(X > line))."""
    floor_k = math.floor(line)
    return 1.0 - poisson_cdf(floor_k, mu)


@dataclass(frozen=True)
class PitcherKProp:
    """Starting pitcher strikeout prop prediction and distribution."""

    player_id: int
    player_name: str
    mlb_game_pk: str
    expected_k: float
    expected_bf: float
    projected_k_pct: float
    over_under_probs: dict[float, float]
    k_distribution: dict[int, float]


@dataclass(frozen=True)
class PitcherOutsProp:
    """Starting pitcher outs recorded / innings pitched prop prediction."""

    player_id: int
    player_name: str
    mlb_game_pk: str
    expected_outs: float
    expected_ip: float
    over_under_probs: dict[float, float]


@dataclass(frozen=True)
class BatterGameProp:
    """Individual batter game performance prop prediction."""

    player_id: int
    player_name: str
    mlb_game_pk: str
    expected_hits: float
    expected_total_bases: float
    anytime_hr_prob: float
    over_0_5_hits_prob: float
    over_1_5_hits_prob: float
    over_0_5_tb_prob: float
    over_1_5_tb_prob: float


def predict_pitcher_strikeouts(
    player_id: int,
    player_name: str,
    mlb_game_pk: str,
    pitcher_k_pct: float,
    opponent_k_pct: float,
    pitcher_rest_days: int | None = None,
    pitcher_outs_7d: float | None = None,
    lines: Sequence[float] = (3.5, 4.5, 5.5, 6.5, 7.5, 8.5),
) -> PitcherKProp:
    """Predict strikeout distribution and over/under line probabilities for a starting pitcher."""
    proj_k_pct = log5_matchup_rate(pitcher_k_pct, opponent_k_pct, DEFAULT_LEAGUE_K_PCT)

    # Rest and workload adjustment on expected batters faced
    expected_bf = DEFAULT_STARTER_BATTERS_FACED
    if pitcher_rest_days is not None:
        if pitcher_rest_days >= 5:
            expected_bf += 1.0
        elif pitcher_rest_days <= 3:
            expected_bf -= 2.0

    if pitcher_outs_7d is not None and pitcher_outs_7d > 18.0:
        expected_bf -= 1.5

    expected_k = expected_bf * proj_k_pct

    # Over/under probabilities across requested lines
    ou_probs = {line: poisson_over_prob(line, expected_k) for line in lines}

    # PMF distribution for k = 0..15
    k_dist = {k: poisson_pmf(k, expected_k) for k in range(21)}

    return PitcherKProp(
        player_id=player_id,
        player_name=player_name,
        mlb_game_pk=str(mlb_game_pk),
        expected_k=expected_k,
        expected_bf=expected_bf,
        projected_k_pct=proj_k_pct,
        over_under_probs=ou_probs,
        k_distribution=k_dist,
    )


def predict_pitcher_outs(
    player_id: int,
    player_name: str,
    mlb_game_pk: str,
    pitcher_fip: float,
    opponent_wrc_plus: float,
    pitcher_rest_days: int | None = None,
    lines: Sequence[float] = (14.5, 15.5, 16.5, 17.5, 18.5),
) -> PitcherOutsProp:
    """Predict outs recorded distribution and over/under probabilities for a starting pitcher."""
    # Baseline ~16.2 outs (~5.1 IP)
    base_outs = 16.2

    # Quality adjustment: lower FIP = pitches deeper into game
    fip_adj = (4.00 - max(2.0, min(6.5, pitcher_fip))) * 0.8
    # Opponent adjustment: weaker offense = more outs recorded
    wrc_adj = (100.0 - max(60.0, min(140.0, opponent_wrc_plus))) * 0.03

    expected_outs = max(6.0, min(24.0, base_outs + fip_adj + wrc_adj))

    if pitcher_rest_days is not None and pitcher_rest_days <= 3:
        expected_outs -= 2.0

    expected_ip = expected_outs / 3.0
    ou_probs = {line: poisson_over_prob(line, expected_outs) for line in lines}

    return PitcherOutsProp(
        player_id=player_id,
        player_name=player_name,
        mlb_game_pk=str(mlb_game_pk),
        expected_outs=expected_outs,
        expected_ip=expected_ip,
        over_under_probs=ou_probs,
    )


def predict_batter_props(
    player_id: int,
    player_name: str,
    mlb_game_pk: str,
    batter_obp: float,
    batter_slg: float,
    batter_iso: float,
    pitcher_fip: float,
    park_hr_factor: float = 100.0,
    expected_pa: float = DEFAULT_BATTER_PLATE_APPEARANCES,
) -> BatterGameProp:
    """Predict batter hit, total bases, and home run probabilities for a game."""
    # Hit rate estimation
    approx_hit_rate = max(0.10, min(0.40, batter_obp * 0.72))
    # Adjust for opposing pitcher quality
    pitcher_factor = math.sqrt(max(2.0, min(6.0, pitcher_fip)) / 4.00)
    proj_hit_rate_per_pa = approx_hit_rate * pitcher_factor

    expected_hits = expected_pa * proj_hit_rate_per_pa

    # Total bases per PA based on SLG
    proj_tb_per_pa = max(0.15, min(0.80, (batter_slg * 0.85) * pitcher_factor))
    expected_tb = expected_pa * proj_tb_per_pa

    # Home run probability per PA
    base_hr_rate = max(0.005, min(0.12, (batter_iso * 0.25) * (park_hr_factor / 100.0)))
    proj_hr_rate = base_hr_rate * pitcher_factor

    # Anytime HR: 1 - (1 - p_hr)^PA
    anytime_hr_prob = 1.0 - ((1.0 - proj_hr_rate) ** expected_pa)

    # Over 0.5 and 1.5 hits / total bases probabilities
    p_hit_per_pa = proj_hit_rate_per_pa
    p_zero_hits = (1.0 - p_hit_per_pa) ** expected_pa
    over_0_5_hits = 1.0 - p_zero_hits

    # Binomial / Poisson approximation for 2+ hits
    p_one_hit = expected_pa * p_hit_per_pa * ((1.0 - p_hit_per_pa) ** (expected_pa - 1))
    over_1_5_hits = max(0.0, 1.0 - (p_zero_hits + p_one_hit))

    over_0_5_tb = poisson_over_prob(0.5, expected_tb)
    over_1_5_tb = poisson_over_prob(1.5, expected_tb)

    return BatterGameProp(
        player_id=player_id,
        player_name=player_name,
        mlb_game_pk=str(mlb_game_pk),
        expected_hits=expected_hits,
        expected_total_bases=expected_tb,
        anytime_hr_prob=anytime_hr_prob,
        over_0_5_hits_prob=over_0_5_hits,
        over_1_5_hits_prob=over_1_5_hits,
        over_0_5_tb_prob=over_0_5_tb,
        over_1_5_tb_prob=over_1_5_tb,
    )


def fetch_game_pitcher_props(
    mlb_game_pk: str,
    conn: psycopg.Connection | None = None,
) -> list[PitcherKProp]:
    """Fetch and calculate starting pitcher strikeout props for a specific game."""

    def _query(c: psycopg.Connection) -> list[PitcherKProp]:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    f.mlb_game_pk,
                    f.home_starter_id,
                    COALESCE(hp.first_name || ' ' || hp.last_name,
                        hp.last_name, hp.retro_id) AS home_starter_name,
                    f.home_starter_k_pct,
                    f.home_starter_rest_days,
                    f.home_starter_outs_7d,
                    f.away_k_pct AS away_team_k_pct,
                    f.away_starter_id,
                    COALESCE(ap.first_name || ' ' || ap.last_name,
                        ap.last_name, ap.retro_id) AS away_starter_name,
                    f.away_starter_k_pct,
                    f.away_starter_rest_days,
                    f.away_starter_outs_7d,
                    f.home_k_pct AS home_team_k_pct
                FROM gold.game_feature f
                LEFT JOIN core.player hp ON hp.id = f.home_starter_id
                LEFT JOIN core.player ap ON ap.id = f.away_starter_id
                WHERE f.mlb_game_pk = %s
                ORDER BY f.feature_cutoff_at DESC
                LIMIT 1
                """,
                (str(mlb_game_pk),),
            )
            row = cur.fetchone()
            if not row:
                return []

            props = []
            # Home starter facing away offense
            if row.get("home_starter_id") and row.get("home_starter_k_pct") is not None:
                h_k_pct = float(row["home_starter_k_pct"])
                a_team_k = float(row.get("away_team_k_pct") or DEFAULT_LEAGUE_K_PCT)
                props.append(
                    predict_pitcher_strikeouts(
                        player_id=int(row["home_starter_id"]),
                        player_name=str(row.get("home_starter_name") or "Home Starter"),
                        mlb_game_pk=str(mlb_game_pk),
                        pitcher_k_pct=h_k_pct,
                        opponent_k_pct=a_team_k,
                        pitcher_rest_days=row.get("home_starter_rest_days"),
                        pitcher_outs_7d=float(row["home_starter_outs_7d"])
                        if row.get("home_starter_outs_7d") is not None
                        else None,
                    )
                )

            # Away starter facing home offense
            if row.get("away_starter_id") and row.get("away_starter_k_pct") is not None:
                a_k_pct = float(row["away_starter_k_pct"])
                h_team_k = float(row.get("home_team_k_pct") or DEFAULT_LEAGUE_K_PCT)
                props.append(
                    predict_pitcher_strikeouts(
                        player_id=int(row["away_starter_id"]),
                        player_name=str(row.get("away_starter_name") or "Away Starter"),
                        mlb_game_pk=str(mlb_game_pk),
                        pitcher_k_pct=a_k_pct,
                        opponent_k_pct=h_team_k,
                        pitcher_rest_days=row.get("away_starter_rest_days"),
                        pitcher_outs_7d=float(row["away_starter_outs_7d"])
                        if row.get("away_starter_outs_7d") is not None
                        else None,
                    )
                )
            return props

    if conn is not None:
        return _query(conn)
    with get_connection() as c:
        return _query(c)
