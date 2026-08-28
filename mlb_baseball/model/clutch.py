"""Batter Clutch Context & High-Leverage Split Engine (CLUTCH-01, ADR-167).

Provides leverage-adjusted performance modeling and Empirical Bayes clutch regression:
1. Sabermetric Win Probability Added (WPA) vs Context-Neutral Value (WPA/pLI).
2. Empirical Bayes High-Leverage wOBA Shrinkage (M ~ 600 PA regression to mean).
3. Clutch Performance Index and High-Leverage Situational Delta.
4. Clutch Archetype Classification (Clutch Performer, Neutral Producer, Leverage Collapse).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterClutchRawStats:
    """Observed high-leverage and baseline context metrics for a hitter."""

    batter_id: str
    batter_name: str
    woba_overall: float = 0.330
    pa_high_li: int = 80  # Plate appearances with LI >= 1.50
    woba_high_li: float = 0.380
    wpa: float = 2.40  # Win Probability Added
    pli: float = 1.05  # Average leverage index faced


@dataclasses.dataclass(frozen=True)
class ClutchEvaluationResult:
    """Evaluated true-talent clutch performance and high-leverage value."""

    batter_name: str
    shrunk_high_li_woba: float
    clutch_woba_delta: float  # Shrunk High-LI wOBA - Overall wOBA
    clutch_index: float  # (WPA / pLI) - Context Neutral
    clutch_tier: str  # "CLUTCH_PERFORMER", "NEUTRAL_PRODUCER", "LEVERAGE_COLLAPSE"
    is_high_leverage_asset: bool


class BaseClutchEngine(Protocol):
    """Polymorphic protocol for batter clutch evaluation engines."""

    def evaluate_clutch(
        self,
        stats: BatterClutchRawStats,
        shrinkage_m: float = 600.0,
    ) -> ClutchEvaluationResult:
        """Calculate Empirical Bayes shrunk clutch splits."""
        ...


class BatterClutchEngine:
    """Calculates true-talent high-leverage performance with Empirical Bayes (CLUTCH-01)."""

    def evaluate_clutch(
        self,
        stats: BatterClutchRawStats,
        shrinkage_m: float = 600.0,
    ) -> ClutchEvaluationResult:
        """Compute shrunk high-leverage wOBA and sabermetric clutch score."""
        # 1. Empirical Bayes Shrinkage:
        # Shrunk = (PA_high * wOBA_high + M * wOBA_overall) / (PA_high + M)
        shrunk_woba = (stats.pa_high_li * stats.woba_high_li + shrinkage_m * stats.woba_overall) / (
            stats.pa_high_li + shrinkage_m
        )
        clutch_delta = round(shrunk_woba - stats.woba_overall, 3)

        # 2. Sabermetric Clutch Index (WPA / pLI - ContextNeutralWPA)
        # Context-neutral WPA is roughly ~ 0 for average player or (wOBA - 0.315)*PA/400
        context_neutral = round((stats.woba_overall - 0.315) * 5.0, 2)
        raw_clutch = round((stats.wpa / max(0.5, stats.pli)) - context_neutral, 2)

        # 3. Clutch Tier
        if clutch_delta >= 0.010 or raw_clutch >= 1.20:
            tier = "CLUTCH_PERFORMER"
            is_asset = True
        elif clutch_delta <= -0.010 or raw_clutch <= -1.20:
            tier = "LEVERAGE_COLLAPSE"
            is_asset = False
        else:
            tier = "NEUTRAL_PRODUCER"
            is_asset = False

        return ClutchEvaluationResult(
            batter_name=stats.batter_name,
            shrunk_high_li_woba=round(shrunk_woba, 3),
            clutch_woba_delta=clutch_delta,
            clutch_index=raw_clutch,
            clutch_tier=tier,
            is_high_leverage_asset=is_asset,
        )


def health_check() -> list[Check]:
    """Operational health check for the Batter Clutch Engine (CLUTCH-01)."""
    checks: list[Check] = []
    try:
        engine = BatterClutchEngine()
        clutch_slugger = BatterClutchRawStats(
            "b1",
            "Clutch Slugger",
            woba_overall=0.340,
            pa_high_li=120,
            woba_high_li=0.420,
            wpa=3.80,
            pli=1.15,
        )
        choker = BatterClutchRawStats(
            "b2",
            "Low Leverage Only",
            woba_overall=0.340,
            pa_high_li=100,
            woba_high_li=0.240,
            wpa=-1.20,
            pli=1.10,
        )

        r_clutch = engine.evaluate_clutch(clutch_slugger)
        r_choke = engine.evaluate_clutch(choker)

        if (
            r_clutch.clutch_tier == "CLUTCH_PERFORMER"
            and r_choke.clutch_tier == "LEVERAGE_COLLAPSE"
        ):
            checks.append(
                Check(
                    "batter clutch engine",
                    True,
                    f"Clutch verified (Delta: {r_clutch.clutch_woba_delta:>+5.3f})",
                )
            )
        else:
            checks.append(
                Check(
                    "batter clutch engine",
                    False,
                    f"Unexpected clutch output: {r_clutch}, {r_choke}",
                )
            )
    except Exception as exc:
        checks.append(Check("batter clutch engine", False, str(exc)))
    return checks
