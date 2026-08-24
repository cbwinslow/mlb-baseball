"""Batter Eye Tracking & Plate Discipline Swing Decision Engine (DECISION-01, ADR-151).

Provides Statcast 4-zone swing decision value modeling and hitter archetype classification:
1. Statcast 4-Attack-Zone Run Value Weights (Heart, Shadow, Chase, Waste).
2. Swing Decision Value (SDV) per 100 Pitches & Season Net Run Production.
3. Hitter Plate Discipline Archetype Classifier (Slugger, Walker, Free Swinger, Chaser).
4. Zone Selectivity and Called Strike Vulnerability Profiling.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Protocol

from mlb_baseball.health import Check


class DisciplineArchetype(enum.Enum):
    """Plate discipline batter classifications."""

    DISCIPLINED_SLUGGER = "disciplined_slugger"  # High heart swing, low chase (Elite)
    PASSIVE_WALKER = (
        "passive_walker"  # Low chase, low heart swing (Takes lots of walks/called strikes)
    )
    FREE_SWINGER = "free_swinger"  # High heart swing, moderate-high chase (Aggressive contact)
    VULNERABLE_CHASER = (
        "vulnerable_chaser"  # High chase (>=35%), poor decision run value (Exploitable)
    )


@dataclasses.dataclass(frozen=True)
class BatterZoneRates:
    """Batter swing frequencies across the 4 Statcast attack zones."""

    batter_id: str
    batter_name: str
    heart_swing_pct: float = 0.72  # MLB avg ~72%
    shadow_swing_pct: float = 0.52  # MLB avg ~52%
    chase_swing_pct: float = 0.28  # MLB avg ~28%
    waste_swing_pct: float = 0.08  # MLB avg ~8%


@dataclasses.dataclass(frozen=True)
class SwingDecisionEvaluation:
    """Evaluated Swing Decision Value and discipline classification."""

    batter_name: str
    swing_decision_val_per_100: float  # Net runs added per 100 pitches
    season_run_value_added: float  # Net runs added across ~2500 pitches in a season
    archetype: DisciplineArchetype
    discipline_grade: str  # "ELITE", "ABOVE_AVERAGE", "AVERAGE", "POOR"


class BaseDecisionEngine(Protocol):
    """Polymorphic protocol for swing decision engines."""

    def evaluate_batter_discipline(
        self,
        rates: BatterZoneRates,
        season_pitches: int = 2500,
    ) -> SwingDecisionEvaluation:
        """Evaluate batter swing decision efficiency and net run value."""
        ...


class BatterSwingDecisionEngine:
    """Calculates swing decision values and player discipline archetypes (DECISION-01)."""

    def evaluate_batter_discipline(
        self,
        rates: BatterZoneRates,
        season_pitches: int = 2500,
    ) -> SwingDecisionEvaluation:
        """Compute run value of swing/take decisions across 4 attack zones."""
        # 1. Run Value Weights per pitch in each zone:
        rv_heart = (rates.heart_swing_pct - 0.72) * 0.28 * 0.22
        rv_shadow = (rates.shadow_swing_pct - 0.52) * 0.42 * 0.02
        rv_chase = (0.28 - rates.chase_swing_pct) * 0.22 * 0.28
        rv_waste = (0.08 - rates.waste_swing_pct) * 0.08 * 0.32

        net_rv_per_pitch = rv_heart + rv_shadow + rv_chase + rv_waste
        sdv_per_100 = round(net_rv_per_pitch * 100.0, 2)
        season_rv = round(net_rv_per_pitch * season_pitches, 1)

        # 2. Archetype classification
        if rates.chase_swing_pct >= 0.35:
            archetype = DisciplineArchetype.VULNERABLE_CHASER
            grade = "POOR"
        elif rates.heart_swing_pct >= 0.75 and rates.chase_swing_pct <= 0.22:
            archetype = DisciplineArchetype.DISCIPLINED_SLUGGER
            grade = "ELITE"
        elif rates.chase_swing_pct <= 0.20 and rates.heart_swing_pct < 0.68:
            archetype = DisciplineArchetype.PASSIVE_WALKER
            grade = "ABOVE_AVERAGE"
        elif rates.heart_swing_pct >= 0.78 and rates.chase_swing_pct >= 0.28:
            archetype = DisciplineArchetype.FREE_SWINGER
            grade = "AVERAGE"
        else:
            archetype = (
                DisciplineArchetype.DISCIPLINED_SLUGGER
                if sdv_per_100 >= 0.5
                else DisciplineArchetype.FREE_SWINGER
            )
            grade = "ABOVE_AVERAGE" if sdv_per_100 >= 0.0 else "AVERAGE"

        return SwingDecisionEvaluation(
            batter_name=rates.batter_name,
            swing_decision_val_per_100=sdv_per_100,
            season_run_value_added=season_rv,
            archetype=archetype,
            discipline_grade=grade,
        )


def health_check() -> list[Check]:
    """Operational health check for the Batter Swing Decision Engine (DECISION-01)."""
    checks: list[Check] = []
    try:
        engine = BatterSwingDecisionEngine()
        elite_eye = BatterZoneRates("b1", "Elite Eye", heart_swing_pct=0.80, chase_swing_pct=0.16)
        free_swinger = BatterZoneRates(
            "b2", "Free Swinger", heart_swing_pct=0.74, chase_swing_pct=0.38
        )

        r_elite = engine.evaluate_batter_discipline(elite_eye)
        r_free = engine.evaluate_batter_discipline(free_swinger)

        if r_elite.swing_decision_val_per_100 > 0.8 and r_free.swing_decision_val_per_100 < 0.0:
            checks.append(
                Check(
                    "batter swing decision engine",
                    True,
                    f"Decision verified (Elite: {r_elite.swing_decision_val_per_100:+.2f})",
                )
            )
        else:
            checks.append(
                Check(
                    "batter swing decision engine",
                    False,
                    f"Unexpected swing decision evaluations: {r_elite}, {r_free}",
                )
            )
    except Exception as exc:
        checks.append(Check("batter swing decision engine", False, str(exc)))
    return checks
