"""Infield Double Play Conversion Pivot Kinematics Engine (PIVOT-DP-01, ADR-197).

Provides middle infielder (2B/SS) pivot mechanics, turn time, and GDP conversion modeling:
1. Pivot Turn Time (bag touch to relay throw release in seconds).
2. Double Play Turn Index (DPTI score combining turn speed and relay velocity).
3. Double Play Turn Surplus Value (DPTS net runs saved over average fielder's choice).
4. Middle Infield Archetypes (Lightning Pivot Turner, Above Average, Slow Pivot Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class InfieldPivotMetrics:
    """Observed middle infield double play pivot and relay throw measurements."""

    fielder_id: str
    fielder_name: str
    position: str = "2B"  # "2B" or "SS"
    pivot_turn_time_s: float = 0.72  # Sample elite fielder value; DPTI formula's
    # own league-average benchmark (used below) is 0.78s
    relay_throw_velo_mph: float = 85.0
    double_plays_turned: int = 60
    double_play_opportunities: int = 80
    failed_pivot_turns: int = 15
    wild_relay_throws: int = 1


@dataclasses.dataclass(frozen=True)
class PivotDPEvaluationResult:
    """Evaluated double play conversion efficiency, DPTI score, and run savings."""

    fielder_name: str
    position: str
    dp_conversion_pct: float
    dpti_score: float  # Double Play Turn Index (0 to 150)
    dpts_runs_saved: float  # Net run savings over baseline GDP conversion
    pivot_tier: str  # e.g. "LIGHTNING_PIVOT_TURNER", "SLOW_PIVOT_LIABILITY"
    is_lightning_turner: bool


class BasePivotDPEngine(Protocol):
    """Polymorphic protocol for infield double play pivot engines."""

    def evaluate_pivot(
        self,
        metrics: InfieldPivotMetrics,
    ) -> PivotDPEvaluationResult:
        """Calculate pivot turn efficiency, DPTI, and DPTS runs."""
        ...


class InfieldPivotDPEngine:
    """Calculates middle infield pivot turn kinematics and GDP conversion (PIVOT-DP-01)."""

    def evaluate_pivot(
        self,
        metrics: InfieldPivotMetrics,
    ) -> PivotDPEvaluationResult:
        """Compute conversion rate, DPTI, and DPTS runs saved."""
        opps = max(1, metrics.double_play_opportunities)
        conv_pct = round((metrics.double_plays_turned / opps) * 100.0, 1)

        # DPTI Score: benchmark is 0.78s turn time and 82.0 mph relay throw
        time_bonus = (0.78 - metrics.pivot_turn_time_s) / 0.10 * 18.0
        velo_bonus = (metrics.relay_throw_velo_mph - 82.0) / 5.0 * 8.0
        dpti = round(max(0.0, 100.0 + time_bonus + velo_bonus), 1)

        # DPTS Runs Saved: average conversion baseline is 68.0%
        expected_turned = opps * 0.68
        surplus_turns = metrics.double_plays_turned - expected_turned
        dpts = round(surplus_turns * 0.48 - metrics.wild_relay_throws * 0.38, 2)

        is_lightning = dpti >= 115.0 and metrics.pivot_turn_time_s <= 0.72

        # Tiers
        if is_lightning:
            tier = "LIGHTNING_PIVOT_TURNER"
        elif dpti >= 104.0:
            tier = "ABOVE_AVERAGE_MIDDLE_INFIELDER"
        elif dpti <= 86.0 or metrics.pivot_turn_time_s >= 0.86:
            tier = "SLOW_PIVOT_LIABILITY"
        else:
            tier = "AVERAGE_PIVOT_DEFENDER"

        return PivotDPEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            dp_conversion_pct=conv_pct,
            dpti_score=dpti,
            dpts_runs_saved=dpts,
            pivot_tier=tier,
            is_lightning_turner=is_lightning,
        )


def health_check() -> list[Check]:
    """Operational health check for Infield Pivot DP Engine (PIVOT-DP-01)."""
    checks: list[Check] = []
    try:
        engine = InfieldPivotDPEngine()
        quick_2b = InfieldPivotMetrics("f1", "Elite 2B", "2B", 0.68, 86.5, 68, 80, 10, 0)
        slow_ss = InfieldPivotMetrics("f2", "Slow SS", "SS", 0.88, 79.0, 45, 80, 28, 3)

        r_qui = engine.evaluate_pivot(quick_2b)
        r_slo = engine.evaluate_pivot(slow_ss)

        if (
            r_qui.pivot_tier == "LIGHTNING_PIVOT_TURNER"
            and r_slo.pivot_tier == "SLOW_PIVOT_LIABILITY"
        ):
            checks.append(
                Check(
                    "pivot dp engine",
                    True,
                    f"Pivot DP verified (Quick 2B DPTI: {r_qui.dpti_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("pivot dp engine", False, f"Unexpected pivot DP output: {r_qui}, {r_slo}")
            )
    except Exception as exc:
        checks.append(Check("pivot dp engine", False, str(exc)))
    return checks
