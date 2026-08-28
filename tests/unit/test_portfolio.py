"""Unit tests for Kelly Criterion Portfolio Allocator (PORT-01, ADR-113)."""

import pytest

from mlb_baseball.model.portfolio import (
    BetOpportunity,
    KellyAllocator,
    PositionType,
    american_to_decimal_odds,
    probability_to_decimal_odds,
)


def test_american_and_probability_to_decimal_odds():
    """Verify exact odds conversions for American, implied probability, and decimal formats."""
    # Positive American odds (+150 -> 2.50)
    assert american_to_decimal_odds(150) == pytest.approx(2.50)
    # Negative American odds (-200 -> 1.50)
    assert american_to_decimal_odds(-200) == pytest.approx(1.50)
    # Even American odds (+100 -> 2.00)
    assert american_to_decimal_odds(100) == pytest.approx(2.00)

    # Implied probability (0.50 -> 2.00, 0.25 -> 4.00)
    assert probability_to_decimal_odds(0.50) == pytest.approx(2.00)
    assert probability_to_decimal_odds(0.25) == pytest.approx(4.00)

    with pytest.raises(ValueError):
        probability_to_decimal_odds(0.0)
    with pytest.raises(ValueError):
        probability_to_decimal_odds(1.0)


def test_calculate_single_kelly_fraction_hand_calculated():
    """Verify deterministic hand-calculated Kelly fractions."""
    allocator = KellyAllocator(fraction=0.25)

    # 1. 60% win prob at even money (decimal 2.0, b = 1.0)
    # Full Kelly = (0.60 * 1.0 - 0.40) / 1.0 = 0.20
    full_k = allocator.calculate_single_kelly_fraction(model_prob=0.60, decimal_odds=2.0)
    assert full_k == pytest.approx(0.20, abs=1e-5)

    # 2. 50% win prob at even money -> 0.0
    zero_k = allocator.calculate_single_kelly_fraction(model_prob=0.50, decimal_odds=2.0)
    assert zero_k == 0.0

    # 3. 40% win prob at even money -> 0.0 (negative edge)
    neg_k = allocator.calculate_single_kelly_fraction(model_prob=0.40, decimal_odds=2.0)
    assert neg_k == 0.0


def test_kelly_allocator_portfolio_caps():
    """Verify portfolio constraints: single bet cap, total exposure cap, proportional scaling."""
    # Allocator with 2.5% max single bet, 10% max total exposure, quarter-Kelly (0.25)
    allocator = KellyAllocator(
        fraction=0.25,
        max_single_bet_pct=0.025,
        max_total_exposure_pct=0.100,
        min_edge_pct=0.02,
    )

    # Create 8 strong opportunities (+EV)
    opportunities = [
        BetOpportunity(
            opportunity_id=f"opp_{i}",
            game_instance_key=f"game_{i}",
            market_source="polymarket",
            position_type=PositionType.MONEYLINE,
            description=f"Matchup {i} Home Win",
            model_probability=0.65,
            market_implied_probability=0.50,
            decimal_odds=2.0,
        )
        for i in range(8)
    ]

    plan = allocator.allocate(opportunities=opportunities, total_bankroll=10000.0)

    assert plan.total_bankroll_usd == 10000.0
    assert len(plan.recommendations) == 8

    # 1. Total exposure must not exceed 10.0% ($1,000)
    assert plan.total_allocated_usd <= 1000.01
    assert plan.total_exposure_pct <= 0.1001

    # 2. Individual bets must all be positive and bounded
    for rec in plan.recommendations:
        assert rec.wager_amount_usd > 0
        assert rec.wager_amount_usd <= 250.01  # <= 2.5% of $10,000
        assert rec.expected_value_pct > 0
        assert rec.expected_growth_rate > 0
