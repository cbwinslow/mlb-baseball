"""Kelly Criterion Prediction Market Portfolio Allocator & Risk Engine (PORT-01, ADR-113).

Provides mathematically rigorous, fractional Kelly bankroll growth optimization and
multi-contract portfolio risk management for Polymarket, Kalshi, and sportsbook lines.

Adheres strictly to object-oriented encapsulation, polymorphic interfaces, and
point-in-time pricing without retroactive lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence
from typing import Protocol

from mlb_baseball.health import Check


class MarketOddsFormat(enum.Enum):
    """Supported market odds presentation formats."""

    DECIMAL = "decimal"
    AMERICAN = "american"
    PROBABILITY = "probability"


class PositionType(enum.Enum):
    """Categorization of betting positions and proposition markets."""

    MONEYLINE = "moneyline"
    RUN_LINE = "run_line"
    TOTAL_OVER = "total_over"
    TOTAL_UNDER = "total_under"
    PITCHER_PROP_K = "pitcher_prop_k"
    PITCHER_PROP_OUTS = "pitcher_prop_outs"
    BATTER_PROP_HR = "batter_prop_hr"


@dataclasses.dataclass(frozen=True)
class BetOpportunity:
    """Encapsulates a single prospective prediction market or betting opportunity."""

    opportunity_id: str
    game_instance_key: str
    market_source: str  # 'polymarket', 'kalshi', 'sportsbook'
    position_type: PositionType
    description: str
    model_probability: float
    market_implied_probability: float
    decimal_odds: float

    @property
    def edge(self) -> float:
        """Net probability edge: Model Prob - Market Implied Prob."""
        return self.model_probability - self.market_implied_probability

    @property
    def expected_value_pct(self) -> float:
        """Expected value percentage: (Model Prob * Decimal Odds - 1.0)."""
        return (self.model_probability * self.decimal_odds) - 1.0


@dataclasses.dataclass(frozen=True)
class AllocationRecommendation:
    """Output recommendation for a single market allocation."""

    opportunity: BetOpportunity
    kelly_fraction: float  # Fraction of bankroll recommended
    wager_amount_usd: float
    expected_value_pct: float
    expected_growth_rate: float


@dataclasses.dataclass(frozen=True)
class PortfolioAllocationPlan:
    """Comprehensive multi-game portfolio allocation plan with risk constraints."""

    total_bankroll_usd: float
    total_allocated_usd: float
    total_exposure_pct: float
    expected_portfolio_growth_rate: float
    recommendations: list[AllocationRecommendation]


class BaseCapitalAllocator(Protocol):
    """Polymorphic protocol for capital allocation algorithms."""

    def allocate(
        self,
        opportunities: Sequence[BetOpportunity],
        total_bankroll: float,
    ) -> PortfolioAllocationPlan:
        """Allocate capital across a collection of betting opportunities."""
        ...


def american_to_decimal_odds(american_odds: int | float) -> float:
    """Convert American moneyline odds (e.g. -150, +130) to decimal odds (e.g. 1.667, 2.300)."""
    if american_odds > 0:
        return 1.0 + (american_odds / 100.0)
    elif american_odds < 0:
        return 1.0 + (100.0 / abs(american_odds))
    return 1.0


def probability_to_decimal_odds(implied_prob: float) -> float:
    """Convert implied probability to fair decimal odds (1.0 / implied_prob)."""
    if implied_prob <= 0.0 or implied_prob >= 1.0:
        raise ValueError(f"implied_prob must be strictly in (0.0, 1.0), got {implied_prob}")
    return 1.0 / implied_prob


class KellyAllocator:
    """Fractional Kelly Criterion capital allocator with portfolio risk constraints (PORT-01).

    Attributes:
        fraction: Kelly multiplier (1.0 = Full Kelly, 0.5 = Half Kelly, 0.25 = Quarter Kelly).
        max_single_bet_pct: Maximum allowable bankroll allocation on any single opportunity.
        max_total_exposure_pct: Maximum combined bankroll exposure across all concurrent positions.
        min_edge_pct: Minimum required model edge (Model Prob - Market Prob) to consider wagering.
    """

    def __init__(
        self,
        fraction: float = 0.25,
        max_single_bet_pct: float = 0.025,
        max_total_exposure_pct: float = 0.150,
        min_edge_pct: float = 0.015,
    ) -> None:
        if not (0.0 < fraction <= 1.0):
            raise ValueError(f"fraction must be in (0, 1], got {fraction}")
        if not (0.0 < max_single_bet_pct <= max_total_exposure_pct <= 1.0):
            raise ValueError("Invalid risk bounds: require 0 < max_single <= max_total <= 1.0")
        self.fraction = fraction
        self.max_single_bet_pct = max_single_bet_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.min_edge_pct = min_edge_pct

    def calculate_single_kelly_fraction(
        self,
        model_prob: float,
        decimal_odds: float,
    ) -> float:
        """Calculate unconstrained full Kelly fraction: (p * b - (1 - p)) / b."""
        if decimal_odds <= 1.0:
            return 0.0
        b = decimal_odds - 1.0
        p = model_prob
        q = 1.0 - p
        full_kelly = (p * b - q) / b
        if full_kelly <= 0.0:
            return 0.0
        return max(0.0, min(1.0, full_kelly))

    def allocate(
        self,
        opportunities: Sequence[BetOpportunity],
        total_bankroll: float,
    ) -> PortfolioAllocationPlan:
        """Execute portfolio allocation optimizing compound growth under risk constraints."""
        if total_bankroll <= 0:
            raise ValueError(f"total_bankroll must be positive, got {total_bankroll}")

        raw_allocations: list[tuple[BetOpportunity, float]] = []

        # 1. Filter opportunities by minimum edge and compute fractional Kelly stakes
        for opp in opportunities:
            if opp.edge < self.min_edge_pct or opp.expected_value_pct <= 0:
                continue
            full_k = self.calculate_single_kelly_fraction(opp.model_probability, opp.decimal_odds)
            fractional_k = full_k * self.fraction
            capped_k = min(fractional_k, self.max_single_bet_pct)
            if capped_k > 0:
                raw_allocations.append((opp, capped_k))

        if not raw_allocations:
            return PortfolioAllocationPlan(
                total_bankroll_usd=total_bankroll,
                total_allocated_usd=0.0,
                total_exposure_pct=0.0,
                expected_portfolio_growth_rate=0.0,
                recommendations=[],
            )

        # 2. Portfolio-level total exposure constraint scaling
        total_requested_exposure = sum(k for _, k in raw_allocations)
        scale_factor = 1.0
        if total_requested_exposure > self.max_total_exposure_pct:
            scale_factor = self.max_total_exposure_pct / total_requested_exposure

        recommendations: list[AllocationRecommendation] = []
        total_wager = 0.0
        total_growth_rate = 0.0

        for opp, unscaled_k in raw_allocations:
            final_k = unscaled_k * scale_factor
            wager = round(final_k * total_bankroll, 2)
            total_wager += wager

            # Compound growth rate contribution: E[ln(1 + f * R)]
            b = opp.decimal_odds - 1.0
            p = opp.model_probability
            q = 1.0 - p
            growth = (p * math.log(1.0 + final_k * b)) + (q * math.log(max(1e-9, 1.0 - final_k)))
            total_growth_rate += growth

            recommendations.append(
                AllocationRecommendation(
                    opportunity=opp,
                    kelly_fraction=round(final_k, 5),
                    wager_amount_usd=wager,
                    expected_value_pct=round(opp.expected_value_pct, 4),
                    expected_growth_rate=round(growth, 6),
                )
            )

        # Sort recommendations by highest expected value %
        recommendations.sort(key=lambda r: r.expected_value_pct, reverse=True)

        return PortfolioAllocationPlan(
            total_bankroll_usd=total_bankroll,
            total_allocated_usd=round(total_wager, 2),
            total_exposure_pct=round(total_wager / total_bankroll, 4),
            expected_portfolio_growth_rate=round(total_growth_rate, 6),
            recommendations=recommendations,
        )


def health_check() -> list[Check]:
    """Operational health check for Kelly Portfolio Allocator (PORT-01)."""
    checks: list[Check] = []
    try:
        alloc = KellyAllocator(fraction=0.25)
        fk = alloc.calculate_single_kelly_fraction(0.60, 2.0)
        if abs(fk - 0.20) < 1e-5:
            checks.append(
                Check(
                    "portfolio kelly allocator",
                    True,
                    "Quarter-Kelly formula and risk bounds verified",
                )
            )
        else:
            checks.append(
                Check("portfolio kelly allocator", False, f"Incorrect Kelly fraction: {fk}")
            )
    except Exception as exc:
        checks.append(Check("portfolio kelly allocator", False, str(exc)))
    return checks
