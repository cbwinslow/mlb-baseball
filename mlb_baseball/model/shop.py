"""Multi-Book Odds Line Shopping & Value Scanner (SHOP-01, ADR-146).

Provides cross-sportsbook line comparison, best-price discovery, and synthetic hold calculation:
1. Multi-Book Price Aggregation (DraftKings, FanDuel, Pinnacle, BetMGM, Kalshi/Polymarket).
2. Best-Available Odds Extraction (maximizes return on both home and away outcomes).
3. Synthetic Two-Way Market Hold & Pure Arbitrage Detection (S_synth < 1.00).
4. Edge & Expected Value (+EV) Quantification against Model True Probabilities.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class SportsbookQuote:
    """Individual sportsbook price quote for a matchup."""

    sportsbook_name: str
    home_decimal_odds: float
    away_decimal_odds: float
    vig_pct: float


@dataclasses.dataclass(frozen=True)
class LineShoppingComparison:
    """Aggregated best prices, synthetic hold, and model expected value."""

    game_id: str
    home_team: str
    away_team: str
    model_home_prob: float
    best_home_sportsbook: str
    best_home_odds: float
    best_away_sportsbook: str
    best_away_odds: float
    synthetic_market_hold_pct: float  # e.g. 0.8% (much lower than single book 4.5%)
    is_pure_arbitrage: bool
    home_ev_pct: float  # e.g. +4.2% EV
    away_ev_pct: float
    best_value_side: str | None  # "HOME", "AWAY", or None


class BaseLineShoppingEngine(Protocol):
    """Polymorphic protocol for line shopping engines."""

    def find_best_lines(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        quotes: Sequence[SportsbookQuote],
        model_home_prob: float,
    ) -> LineShoppingComparison:
        """Scan sportsbook quotes to find optimal execution prices and EV."""
        ...


class OddsLineShoppingEngine:
    """Scans multi-book market offerings to isolate maximum expected value (SHOP-01)."""

    def find_best_lines(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        quotes: Sequence[SportsbookQuote],
        model_home_prob: float,
    ) -> LineShoppingComparison:
        """Find best execution prices across quotes and calculate model EV."""
        if not quotes:
            # Fallback neutral quote
            quotes = [SportsbookQuote("Consensus", 1.91, 1.91, 4.7)]

        best_h_quote = max(quotes, key=lambda q: q.home_decimal_odds)
        best_a_quote = max(quotes, key=lambda q: q.away_decimal_odds)

        best_h_odds = best_h_quote.home_decimal_odds
        best_a_odds = best_a_quote.away_decimal_odds

        # Synthetic hold = (1 / best_h) + (1 / best_a) - 1.0
        synthetic_prob_sum = (1.0 / best_h_odds) + (1.0 / best_a_odds)
        synthetic_hold = (synthetic_prob_sum - 1.0) * 100.0

        is_arb = synthetic_prob_sum < 1.000

        # Model Expected Value: EV = p * odds - 1.0
        model_a_prob = 1.0 - model_home_prob
        home_ev = (model_home_prob * best_h_odds) - 1.0
        away_ev = (model_a_prob * best_a_odds) - 1.0

        best_side: str | None = None
        if home_ev > 0.015 and home_ev >= away_ev:
            best_side = "HOME"
        elif away_ev > 0.015 and away_ev > home_ev:
            best_side = "AWAY"

        return LineShoppingComparison(
            game_id=game_id,
            home_team=home_team,
            away_team=away_team,
            model_home_prob=round(model_home_prob, 3),
            best_home_sportsbook=best_h_quote.sportsbook_name,
            best_home_odds=round(best_h_odds, 3),
            best_away_sportsbook=best_a_quote.sportsbook_name,
            best_away_odds=round(best_a_odds, 3),
            synthetic_market_hold_pct=round(synthetic_hold, 2),
            is_pure_arbitrage=is_arb,
            home_ev_pct=round(home_ev * 100.0, 2),
            away_ev_pct=round(away_ev * 100.0, 2),
            best_value_side=best_side,
        )


def health_check() -> list[Check]:
    """Operational health check for the Odds Line Shopping Engine (SHOP-01)."""
    checks: list[Check] = []
    try:
        engine = OddsLineShoppingEngine()
        quotes = [
            SportsbookQuote(
                "DraftKings", home_decimal_odds=2.25, away_decimal_odds=1.70, vig_pct=4.2
            ),
            SportsbookQuote("FanDuel", home_decimal_odds=2.10, away_decimal_odds=1.80, vig_pct=4.1),
            SportsbookQuote(
                "Pinnacle", home_decimal_odds=2.18, away_decimal_odds=1.77, vig_pct=2.4
            ),
        ]

        res = engine.find_best_lines("g1", "LAD", "SF", quotes, model_home_prob=0.50)

        # Best home: DK (2.25), Best away: FD (1.80) -> synthetic hold 0.0%
        if (
            res.best_home_sportsbook == "DraftKings"
            and res.best_away_sportsbook == "FanDuel"
            and res.home_ev_pct > 10.0
        ):
            checks.append(
                Check(
                    "odds line shopping engine",
                    True,
                    f"Line shopping verified (Best: {res.best_home_sportsbook})",
                )
            )
        else:
            checks.append(
                Check("odds line shopping engine", False, f"Unexpected shopping output: {res}")
            )
    except Exception as exc:
        checks.append(Check("odds line shopping engine", False, str(exc)))
    return checks
