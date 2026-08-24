"""Middle Infield Double-Play Turn Speed & Footwork Engine (DP-FOOTWORK-01, ADR-241).

Provides middle infielder 2B/SS pivot speed, relay throw velocity, and DPTAA modeling:
1. Double-Play Footwork Turn Index (DPFTI score measuring pivot efficiency).
2. Double Plays Turned Above Average (DPTAA surplus double plays converted).
3. Footwork Archetypes (Lightning Acrobatic Pivot Master, Clunky Footwork DP Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class InfieldDpFootworkMetrics:
    """Observed middle infielder pivot time sec, throw velocity mph, and conversion %."""

    fielder_id: str
    fielder_name: str
    position: str = "2B"
    pivot_time_sec: float = 0.74  # Glove catch to release time (benchmark ~0.74 s)
    throw_velo_mph: float = 78.0  # Relay throw velocity (benchmark ~78.0 mph)
    dp_conversion_pct: float = 72.0  # Turnable double play conversion % (benchmark ~72.0%)
    dp_turn_opportunities: int = 60


@dataclasses.dataclass(frozen=True)
class DpFootworkEvaluationResult:
    """Evaluated double play footwork score, DPTAA turns, and defensive run value."""

    fielder_name: str
    position: str
    dpfti_score: float  # Double-Play Footwork Turn Index (0 to 160)
    dptaa_turns_saved: float  # Double Plays Turned Above Average
    dprv_runs_saved: float  # Net defensive runs saved from double play conversions
    footwork_tier: str  # e.g. "LIGHTNING_ACROBATIC_PIVOT_MASTER", "CLUNKY_FOOTWORK_DP_LIABILITY"
    is_lightning_master: bool


class BaseDpFootworkEngine(Protocol):
    """Polymorphic protocol for double-play footwork engines."""

    def evaluate_dp_footwork(
        self,
        metrics: InfieldDpFootworkMetrics,
    ) -> DpFootworkEvaluationResult:
        """Calculate DPFTI rating, DPTAA turns, and defensive runs."""
        ...


class InfieldDpFootworkEngine:
    """Calculates double play pivot time, relay velocity, and DPFTI (DP-FOOTWORK-01)."""

    def evaluate_dp_footwork(
        self,
        metrics: InfieldDpFootworkMetrics,
    ) -> DpFootworkEvaluationResult:
        """Compute DPFTI score, DPTAA double plays turned, and defensive run value."""
        # DPFTI Score: benchmark 72.0% conv, 0.74 s pivot, 78.0 mph throw
        conv_bonus = (metrics.dp_conversion_pct - 72.0) * 2.0
        time_saving = (0.74 - metrics.pivot_time_sec) * 55.0
        throw_bonus = (metrics.throw_velo_mph - 78.0) * 1.2
        dpfti = round(max(0.0, 100.0 + conv_bonus + time_saving + throw_bonus), 1)

        # DPTAA & DPRV Runs Saved (~0.45 runs per completed double play)
        opps = max(1, metrics.dp_turn_opportunities)
        dptaa = round(((metrics.dp_conversion_pct - 72.0) / 100.0) * opps, 1)
        runs = round(dptaa * 0.45, 2)

        is_master = (
            dpfti >= 116.0 and metrics.pivot_time_sec <= 0.62 and metrics.dp_conversion_pct >= 82.0
        )

        # Tiers
        if is_master:
            tier = "LIGHTNING_ACROBATIC_PIVOT_MASTER"
        elif metrics.pivot_time_sec >= 0.86 or metrics.dp_conversion_pct <= 60.0:
            tier = "CLUNKY_FOOTWORK_DP_LIABILITY"
        elif metrics.dp_conversion_pct >= 78.0:
            tier = "SOLID_DOUBLE_PLAY_PIVOTER"
        else:
            tier = "AVERAGE_MIDDLE_INFIELD_PIVOT"

        return DpFootworkEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            dpfti_score=dpfti,
            dptaa_turns_saved=dptaa,
            dprv_runs_saved=runs,
            footwork_tier=tier,
            is_lightning_master=is_master,
        )


def health_check() -> list[Check]:
    """Operational health check for Infield DP Footwork Engine (DP-FOOTWORK-01)."""
    checks: list[Check] = []
    try:
        engine = InfieldDpFootworkEngine()
        master = InfieldDpFootworkMetrics("f1", "Marcus Semien", "2B", 0.58, 86.0, 88.0, 70)
        clunky = InfieldDpFootworkMetrics("f2", "Clunky 2B", "2B", 0.88, 72.0, 56.0, 45)

        r_mas = engine.evaluate_dp_footwork(master)
        r_clu = engine.evaluate_dp_footwork(clunky)

        if (
            r_mas.footwork_tier == "LIGHTNING_ACROBATIC_PIVOT_MASTER"
            and r_clu.footwork_tier == "CLUNKY_FOOTWORK_DP_LIABILITY"
        ):
            checks.append(
                Check(
                    "dp footwork engine",
                    True,
                    f"DP Footwork verified (Semien DPFTI: {r_mas.dpfti_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "dp footwork engine", False, f"Unexpected dp footwork output: {r_mas}, {r_clu}"
                )
            )
    except Exception as exc:
        checks.append(Check("dp footwork engine", False, str(exc)))
    return checks
