"""Batter Two-Strike Approach Shortening & Choke-Up Engine (TWO-STRIKE-01, ADR-196).

Provides two-strike count swing adjustments, contact rate defense, and K suppression modeling:
1. Swing Length Shortening (Early Length - Two-Strike Length in feet).
2. Whiff Rate Reduction (Early Whiff% - Two-Strike Whiff%).
3. Two-Strike Battle Efficiency Index (TSBE score combining contact gain vs power sacrifice).
4. Approach Archetypes (Elite Two-Strike Battler, Tactical Choke-Up, Vulnerable Long Swing).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterTwoStrikeMetrics:
    """Observed early count vs two-strike swing mechanics and outcome metrics."""

    batter_id: str
    batter_name: str
    early_count_whiff_pct: float = 24.0
    two_strike_whiff_pct: float = 16.5
    early_count_swing_length_ft: float = 7.4
    two_strike_swing_length_ft: float = 6.6
    early_count_ev_mph: float = 92.5
    two_strike_ev_mph: float = 88.0
    two_strike_pa_count: int = 220
    two_strike_k_pct: float = 33.0  # League average ~40.0%


@dataclasses.dataclass(frozen=True)
class TwoStrikeEvaluationResult:
    """Evaluated two-strike adjustments, TSBE score, and approach tier."""

    batter_name: str
    whiff_reduction_pct: float  # Early Whiff - Two Strike Whiff
    swing_shortened_ft: float  # Early Length - Two Strike Length
    tsbe_score: float  # Two-Strike Battle Efficiency Index
    surplus_runs: float  # (40.0% - K%) * PAs * 0.32 runs
    approach_tier: str  # e.g. "ELITE_TWO_STRIKE_BATTLER", "TACTICAL_CHOKE_UP_SPECIALIST"
    is_elite_battler: bool


class BaseTwoStrikeEngine(Protocol):
    """Polymorphic protocol for two-strike approach engines."""

    def evaluate_two_strike(
        self,
        metrics: BatterTwoStrikeMetrics,
    ) -> TwoStrikeEvaluationResult:
        """Calculate two-strike adjustments, TSBE, and approach tier."""
        ...


class TwoStrikeApproachEngine:
    """Calculates two-strike swing shortening and contact battle efficiency (TWO-STRIKE-01)."""

    def evaluate_two_strike(
        self,
        metrics: BatterTwoStrikeMetrics,
    ) -> TwoStrikeEvaluationResult:
        """Compute swing delta, TSBE index, and surplus runs."""
        whiff_delta = round(metrics.early_count_whiff_pct - metrics.two_strike_whiff_pct, 1)
        length_delta = round(
            metrics.early_count_swing_length_ft - metrics.two_strike_swing_length_ft, 2
        )

        # TSBE Score calculation
        # Base 100 + whiff reduction bonus + length shortened bonus - excess K penalty
        k_delta = metrics.two_strike_k_pct - 40.0
        tsbe = 100.0 + (whiff_delta * 2.5) + (length_delta * 18.0) - (k_delta * 1.5)
        tsbe = round(max(0.0, tsbe), 1)

        # Surplus runs: saving a strikeout in a 2-strike count is worth ~0.32 runs
        pas = max(1, metrics.two_strike_pa_count)
        surplus = round(((40.0 - metrics.two_strike_k_pct) / 100.0) * pas * 0.32, 2)

        is_elite = tsbe >= 120.0 and surplus >= 3.5

        # Tiers
        if is_elite:
            tier = "ELITE_TWO_STRIKE_BATTLER"
        elif length_delta >= 0.50 and whiff_delta >= 4.0:
            tier = "TACTICAL_CHOKE_UP_SPECIALIST"
        elif length_delta <= 0.10 and metrics.two_strike_k_pct >= 45.0:
            tier = "VULNERABLE_LONG_SWING_PULLER"
        else:
            tier = "AVERAGE_TWO_STRIKE_APPROACH"

        return TwoStrikeEvaluationResult(
            batter_name=metrics.batter_name,
            whiff_reduction_pct=whiff_delta,
            swing_shortened_ft=length_delta,
            tsbe_score=tsbe,
            surplus_runs=surplus,
            approach_tier=tier,
            is_elite_battler=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Two-Strike Approach Engine (TWO-STRIKE-01)."""
    checks: list[Check] = []
    try:
        engine = TwoStrikeApproachEngine()
        battler = BatterTwoStrikeMetrics(
            "b1", "Steven Kwan Archetype", 18.0, 10.5, 6.8, 6.0, 88.0, 85.0, 240, 22.0
        )
        free_swinger = BatterTwoStrikeMetrics(
            "b2", "Free Swinger", 32.0, 31.0, 7.8, 7.8, 94.0, 93.0, 200, 48.0
        )

        r_bat = engine.evaluate_two_strike(battler)
        r_fre = engine.evaluate_two_strike(free_swinger)

        if (
            r_bat.approach_tier == "ELITE_TWO_STRIKE_BATTLER"
            and r_fre.approach_tier == "VULNERABLE_LONG_SWING_PULLER"
        ):
            checks.append(
                Check(
                    "two strike approach engine",
                    True,
                    f"Two-strike verified (Kwan TSBE: {r_bat.tsbe_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "two strike approach engine",
                    False,
                    f"Unexpected two-strike output: {r_bat}, {r_fre}",
                )
            )
    except Exception as exc:
        checks.append(Check("two strike approach engine", False, str(exc)))
    return checks
