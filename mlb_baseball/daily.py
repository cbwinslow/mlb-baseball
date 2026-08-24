"""Unified Daily Quantitative Research, Forecasting, and Wagering Pipeline (PIPE-01, ADR-116).

Orchestrates all platform capabilities into a single daily briefing pipeline:
1. Operational preflight verification (doctor health checks)
2. Daily betting grid & multi-model win probabilities (GBM-v2, Log5, Elo)
3. Two-phase Markov Monte Carlo game & First-5 (F5) simulations
4. Starting pitcher proposition market forecasts (Poisson strikeout PMFs)
5. +EV prediction market screening (Polymarket / Kalshi alpha)
6. Kelly Criterion risk-managed portfolio allocation plan

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time pricing without lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import datetime

import psycopg

from mlb_baseball import doctor, serve
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check
from mlb_baseball.model.portfolio import (
    BetOpportunity,
    KellyAllocator,
    PortfolioAllocationPlan,
    PositionType,
    probability_to_decimal_odds,
)
from mlb_baseball.model.props import predict_pitcher_strikeouts


@dataclasses.dataclass(frozen=True)
class DailyMatchupForecast:
    """Consolidated quantitative forecast for a single scheduled matchup."""

    game_instance_key: str
    game_date: str
    away_team: str
    home_team: str
    model_home_win_prob: float
    model_away_win_prob: float
    expected_total_runs: float | None
    home_starter: str | None
    away_starter: str | None


@dataclasses.dataclass(frozen=True)
class DailyPitcherPropCard:
    """Consolidated starting pitcher proposition forecast."""

    pitcher_name: str
    team: str
    opp_team: str
    projected_k_pct: float
    expected_k: float
    prob_over_5_5_k: float
    prob_over_6_5_k: float


@dataclasses.dataclass(frozen=True)
class DailyBriefingReport:
    """Master quantitative research, simulation, and wagering briefing."""

    target_date: str
    health_status: list[Check]
    matchups: list[DailyMatchupForecast]
    pitcher_props: list[DailyPitcherPropCard]
    portfolio_plan: PortfolioAllocationPlan
    generated_at: str


def generate_daily_briefing(
    target_date: datetime.date | str | None = None,
    bankroll: float = 10000.0,
    min_edge: float = 0.020,
    conn: psycopg.Connection | None = None,
) -> DailyBriefingReport:
    """Execute complete end-to-end quantitative daily research briefing pipeline (PIPE-01)."""
    date_str = str(target_date) if target_date is not None else str(datetime.date.today())

    def _execute(c: psycopg.Connection) -> DailyBriefingReport:
        # 1. Operational Preflight
        health_checks = doctor.run()

        # 2. Daily Betting Grid & Matchup Forecasts
        grid_rows = serve.fetch_daily_betting_grid(game_date=date_str, conn=c)
        matchups: list[DailyMatchupForecast] = []
        for r in grid_rows:
            h_prob = float(r.get("home_win_prob") or 0.50)
            matchups.append(
                DailyMatchupForecast(
                    game_instance_key=str(r.get("game_instance_key", "")),
                    game_date=date_str,
                    away_team=str(r.get("away_team", "AWAY")),
                    home_team=str(r.get("home_team", "HOME")),
                    model_home_win_prob=round(h_prob, 4),
                    model_away_win_prob=round(1.0 - h_prob, 4),
                    expected_total_runs=float(r["projected_total_runs"])
                    if r.get("projected_total_runs") is not None
                    else None,
                    home_starter=str(r.get("home_starter_name"))
                    if r.get("home_starter_name")
                    else None,
                    away_starter=str(r.get("away_starter_name"))
                    if r.get("away_starter_name")
                    else None,
                )
            )

        # 3. Starting Pitcher Props
        prop_rows = serve.fetch_pitcher_prop_market(conn=c)
        props: list[DailyPitcherPropCard] = []
        for pr in prop_rows[:10]:
            p_k = float(pr.get("projected_k_pct") or 0.22)
            opp_k = float(pr.get("opponent_k_pct") or 0.22)
            name = str(pr.get("pitcher_name") or "Starting Pitcher")
            team = str(pr.get("team") or "MLB")
            res = predict_pitcher_strikeouts(
                player_id=int(pr.get("player_id") or 0),
                player_name=name,
                mlb_game_pk=str(pr.get("mlb_game_pk", "0")),
                pitcher_k_pct=p_k,
                opponent_k_pct=opp_k,
            )
            props.append(
                DailyPitcherPropCard(
                    pitcher_name=name,
                    team=team,
                    opp_team="OPP",
                    projected_k_pct=round(res.projected_k_pct, 4),
                    expected_k=round(res.expected_k, 2),
                    prob_over_5_5_k=round(res.over_under_probs.get(5.5, 0.50), 4),
                    prob_over_6_5_k=round(res.over_under_probs.get(6.5, 0.35), 4),
                )
            )

        # 4. Market Alpha & Kelly Allocation
        raw_alphas = serve.fetch_prediction_market_alpha(
            min_edge=min_edge, game_date=date_str, limit=50, conn=c
        )
        opportunities: list[BetOpportunity] = []
        for i, a in enumerate(raw_alphas):
            m_prob = float(a.get("model_home_win_prob") or 0.50)
            mkt_prob = float(a.get("market_home_prob") or 0.50)
            if mkt_prob <= 0.0 or mkt_prob >= 1.0:
                continue
            opportunities.append(
                BetOpportunity(
                    opportunity_id=f"daily_alpha_{i}",
                    game_instance_key=str(a.get("game_instance_key", "")),
                    market_source=str(a.get("market_source", "market")),
                    position_type=PositionType.MONEYLINE,
                    description=(
                        f"{a.get('away_team', 'AWAY')} @ "
                        f"{a.get('home_team', 'HOME')} "
                        f"({a.get('recommendation', 'Win')})"
                    ),
                    model_probability=m_prob,
                    market_implied_probability=mkt_prob,
                    decimal_odds=probability_to_decimal_odds(mkt_prob),
                )
            )

        allocator = KellyAllocator(
            fraction=0.25,
            max_single_bet_pct=0.025,
            max_total_exposure_pct=0.150,
            min_edge_pct=min_edge,
        )
        portfolio_plan = allocator.allocate(opportunities, total_bankroll=bankroll)

        return DailyBriefingReport(
            target_date=date_str,
            health_status=health_checks,
            matchups=matchups,
            pitcher_props=props,
            portfolio_plan=portfolio_plan,
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    if conn is not None:
        return _execute(conn)
    with get_connection() as c:
        return _execute(c)


def format_daily_briefing_terminal(report: DailyBriefingReport) -> str:
    """Format master daily briefing into a clean terminal report."""
    lines: list[str] = []
    lines.append(
        "\n================================================================================"
    )
    lines.append("          MLB QUANTITATIVE RESEARCH & WAGERING DAILY BRIEFING")
    lines.append(f"                     Date: {report.target_date} (Generated UTC)")
    lines.append(
        "================================================================================\n"
    )

    # 1. Operational Health
    passed_health = sum(1 for c in report.health_status if c.ok)
    total_health = len(report.health_status)
    health_indicator = (
        "🟢 ALL CHECKS PASSING"
        if passed_health == total_health
        else f"🟡 {passed_health}/{total_health} PASSING"
    )
    lines.append(f"OPERATIONAL HEALTH STATUS: {health_indicator}\n")

    # 2. Matchup Slate Forecast
    lines.append("--- TODAY'S MATCHUP FORECASTS (GBM-v2 + Log5 Ensembled) ---")
    if not report.matchups:
        lines.append("No active scheduled matchups found for this date in gold.game_feature.\n")
    else:
        m_hdr = (
            f"{'Matchup':<16} {'Home Win%':<11} {'Away Win%':<11} "
            f"{'Home Starter':<20} {'Away Starter':<20}"
        )
        lines.append(m_hdr)
        lines.append("-" * len(m_hdr))
        for m in report.matchups:
            lines.append(
                f"{m.away_team + ' @ ' + m.home_team:<16} "
                f"{m.model_home_win_prob * 100:>8.1f}%   "
                f"{m.model_away_win_prob * 100:>8.1f}%   "
                f"{str(m.home_starter or 'TBD'):<20} "
                f"{str(m.away_starter or 'TBD'):<20}"
            )
        lines.append("")

    # 3. Starting Pitcher Props
    lines.append("--- STARTING PITCHER PROPOSITION FORECASTS (Poisson Count PMF) ---")
    if not report.pitcher_props:
        lines.append("No starting pitcher prop projections available.\n")
    else:
        p_hdr = (
            f"{'Pitcher':<24} {'Team':<6} {'Proj K%':<10} "
            f"{'Exp K':<8} {'O/U 5.5 K':<12} {'O/U 6.5 K':<12}"
        )
        lines.append(p_hdr)
        lines.append("-" * len(p_hdr))
        for p in report.pitcher_props:
            lines.append(
                f"{p.pitcher_name:<24} "
                f"{p.team:<6} "
                f"{p.projected_k_pct * 100:>7.1f}%   "
                f"{p.expected_k:>6.2f}  "
                f"{p.prob_over_5_5_k * 100:>9.1f}%   "
                f"{p.prob_over_6_5_k * 100:>9.1f}%"
            )
        lines.append("")

    # 4. Kelly Allocation Plan
    lines.append(
        f"--- KELLY CRITERION CAPITAL ALLOCATION "
        f"(Bankroll: ${report.portfolio_plan.total_bankroll_usd:,.2f}) ---"
    )
    lines.append(
        f"Total Allocated: ${report.portfolio_plan.total_allocated_usd:,.2f} "
        f"({report.portfolio_plan.total_exposure_pct * 100:.2f}% Exposure) | "
        f"Exp Growth Rate: {report.portfolio_plan.expected_portfolio_growth_rate * 100:.4f}%\n"
    )
    if not report.portfolio_plan.recommendations:
        lines.append("No +EV prediction market positions meeting the edge threshold today.\n")
    else:
        k_hdr = (
            f"{'Market / Matchup':<32} {'Model%':<8} {'Mkt%':<8} "
            f"{'Edge%':<8} {'Kelly%':<8} {'Wager ($)':<10} {'+EV%':<8}"
        )
        lines.append(k_hdr)
        lines.append("-" * len(k_hdr))
        for r in report.portfolio_plan.recommendations[:10]:
            lines.append(
                f"{r.opportunity.description:<32} "
                f"{r.opportunity.model_probability * 100:>6.1f}%  "
                f"{r.opportunity.market_implied_probability * 100:>6.1f}%  "
                f"{r.opportunity.edge * 100:>+6.1f}%  "
                f"{r.kelly_fraction * 100:>6.2f}%  "
                f"${r.wager_amount_usd:>8.2f}  "
                f"{r.expected_value_pct * 100:>+6.1f}%"
            )
        lines.append("")

    return "\n".join(lines)
