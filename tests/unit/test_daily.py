"""Unit tests for Unified Daily Quantitative Briefing Pipeline (PIPE-01, ADR-116)."""

from mlb_baseball.daily import (
    DailyBriefingReport,
    DailyMatchupForecast,
    DailyPitcherPropCard,
    format_daily_briefing_terminal,
)
from mlb_baseball.health import Check
from mlb_baseball.model.portfolio import (
    AllocationRecommendation,
    BetOpportunity,
    PortfolioAllocationPlan,
    PositionType,
)


def test_format_daily_briefing_terminal():
    """Verify daily briefing terminal formatting produces clean, comprehensive sections."""
    opp = BetOpportunity(
        opportunity_id="opp_1",
        game_instance_key="mlb:123",
        market_source="polymarket",
        position_type=PositionType.MONEYLINE,
        description="BAL @ NYA (BUY_HOME_YES)",
        model_probability=0.62,
        market_implied_probability=0.45,
        decimal_odds=2.22,
    )
    rec = AllocationRecommendation(
        opportunity=opp,
        kelly_fraction=0.025,
        wager_amount_usd=250.0,
        expected_value_pct=0.3764,
        expected_growth_rate=0.0125,
    )
    plan = PortfolioAllocationPlan(
        total_bankroll_usd=10000.0,
        total_allocated_usd=250.0,
        total_exposure_pct=0.025,
        expected_portfolio_growth_rate=0.0125,
        recommendations=[rec],
    )

    report = DailyBriefingReport(
        target_date="2026-08-24",
        health_status=[Check("database reachable", True, "connected")],
        matchups=[
            DailyMatchupForecast(
                game_instance_key="mlb:123",
                game_date="2026-08-24",
                away_team="BAL",
                home_team="NYA",
                model_home_win_prob=0.6200,
                model_away_win_prob=0.3800,
                expected_total_runs=8.5,
                home_starter="Cole, G",
                away_starter="Burnes, C",
            )
        ],
        pitcher_props=[
            DailyPitcherPropCard(
                pitcher_name="Gerrit Cole",
                team="NYA",
                opp_team="BAL",
                projected_k_pct=0.2950,
                expected_k=7.25,
                prob_over_5_5_k=0.7450,
                prob_over_6_5_k=0.5820,
            )
        ],
        portfolio_plan=plan,
        generated_at="2026-08-24T04:55:00Z",
    )

    output = format_daily_briefing_terminal(report)

    # Verify sections exist in output
    assert "MLB QUANTITATIVE RESEARCH & WAGERING DAILY BRIEFING" in output
    assert "OPERATIONAL HEALTH STATUS: 🟢 ALL CHECKS PASSING" in output
    assert "BAL @ NYA" in output
    assert "Cole, G" in output
    assert "Gerrit Cole" in output
    assert "KELLY CRITERION CAPITAL ALLOCATION" in output
    assert "$250.00" in output
    assert "+37.6%" in output
