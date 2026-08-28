"""Unit tests for Live In-Game Hedging & Middle Betting Engine (HEDGE-01, ADR-134)."""

from mlb_baseball.model.hedge import (
    HedgeStrategy,
    LiveHedgingEngine,
    health_check,
)


def test_equal_profit_live_hedge_calculation():
    """Verify equal profit hedging locks in exact guaranteed gain on favorable price move."""
    engine = LiveHedgingEngine()

    # Pre-game: $100 on Underdog at 2.60 (+160). Live 7th inning: Opponent moves to 2.40 (+140)
    plan = engine.calculate_hedge(
        initial_stake=100.0,
        initial_odds=2.60,
        hedge_odds=2.40,
        strategy=HedgeStrategy.EQUAL_PROFIT,
    )

    assert plan.recommended_hedge_stake_usd == 108.33
    assert plan.total_capital_committed_usd == 208.33
    assert abs(plan.net_profit_if_initial_wins_usd - 51.67) < 0.05
    assert abs(plan.net_profit_if_hedge_wins_usd - 51.66) < 0.05
    assert plan.is_arbitrage_guaranteed_profit is True
    assert plan.guaranteed_profit_margin_pct > 24.0


def test_free_roll_hedge_strategy():
    """Verify free roll hedge recovers original stake exactly."""
    engine = LiveHedgingEngine()

    plan = engine.calculate_hedge(
        initial_stake=100.0,
        initial_odds=3.00,
        hedge_odds=2.00,
        strategy=HedgeStrategy.RISK_FREE_FREE_ROLL,
    )

    assert plan.recommended_hedge_stake_usd == 100.0
    assert plan.total_capital_committed_usd == 200.0
    assert plan.net_profit_if_initial_wins_usd == 100.0
    assert plan.net_profit_if_hedge_wins_usd == 0.0  # Exactly break even if hedge wins


def test_middle_bet_corridor_evaluation():
    """Verify middle bet detects 8 and 9 run corridor on Over 7.5 / Under 9.5."""
    engine = LiveHedgingEngine()

    mid = engine.evaluate_middle(
        market_type="total",
        initial_line=7.5,
        initial_stake=100.0,
        initial_odds=1.90,
        opposite_line=9.5,
        opposite_stake=100.0,
        opposite_odds=1.90,
    )

    assert mid.is_positive_corridor is True
    assert mid.corridor_width == 2.0
    assert mid.corridor_outcomes == [8.0, 9.0]
    assert mid.double_win_payout_usd == 380.0  # Both bets pay out


def test_hedge_health_check():
    """Verify hedge health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Guaranteed profit verified" in checks[0].detail
