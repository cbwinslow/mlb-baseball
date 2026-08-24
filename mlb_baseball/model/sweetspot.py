"""Batter Sweet-Spot Concentration & Ideal Contact Rate Engine (SWEETSPOT-01, ADR-175).

Provides launch angle consistency, ideal contact rate, and ball flight geometry modeling:
1. Statcast Sweet-Spot% (Launch Angle 8° to 32°) and Launch Angle Tightness (Std Dev).
2. Ideal Contact Rate (ICR = Hard-Hit Exit Velocity >= 95 mph inside Sweet-Spot Launch Window).
3. Contact Quality Composite Index (ICR + Sweet-Spot Distribution).
4. Launch Path Archetypes (Line Drive Machine, Hard Hit Grounder, High Variance Flyball).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterContactGeometry:
    """Observed launch angle distribution and hard-hit intersection for a batter."""

    batter_id: str
    batter_name: str
    sweet_spot_pct: float = 0.35  # % of BBE between 8° and 32°
    hard_hit_pct: float = 0.42  # % of BBE with EV >= 95 mph
    ideal_contact_rate: float = 38.0  # % of BBE that are BOTH Hard-Hit and Sweet-Spot
    la_std_dev: float = 24.0  # Launch angle standard deviation in degrees


@dataclasses.dataclass(frozen=True)
class SweetSpotEvaluationResult:
    """Evaluated ball striking consistency, ICR, and launch path archetype."""

    batter_name: str
    ideal_contact_rate: float
    contact_quality_score: float  # Weighted score out of 100
    launch_path_archetype: (
        str  # "LINE_DRIVE_MACHINE", "HARD_HIT_GROUNDER", "HIGH_VARIANCE_FLYBALL", "AVERAGE"
    )
    is_elite_ball_striker: bool


class BaseSweetSpotEngine(Protocol):
    """Polymorphic protocol for sweet spot and ICR contact engines."""

    def evaluate_contact(
        self,
        geometry: BatterContactGeometry,
    ) -> SweetSpotEvaluationResult:
        """Calculate ideal contact rate and launch archetype."""
        ...


class SweetSpotEngine:
    """Evaluates launch angle distribution and Ideal Contact Rate (SWEETSPOT-01)."""

    def evaluate_contact(
        self,
        geometry: BatterContactGeometry,
    ) -> SweetSpotEvaluationResult:
        """Compute composite contact quality score and launch archetype."""
        # 1. Contact Quality Score (0 to 100)
        cqs = round(
            geometry.ideal_contact_rate * 0.70 + (geometry.sweet_spot_pct * 100.0) * 0.30, 1
        )

        # 2. Elite ball striker flag
        is_elite = geometry.ideal_contact_rate >= 42.0 or (
            geometry.sweet_spot_pct >= 0.40 and geometry.hard_hit_pct >= 0.45
        )

        # 3. Archetype Classification
        if geometry.ideal_contact_rate >= 40.0 and geometry.sweet_spot_pct >= 0.38:
            archetype = "LINE_DRIVE_MACHINE"
        elif geometry.hard_hit_pct >= 0.45 and geometry.sweet_spot_pct <= 0.28:
            archetype = "HARD_HIT_GROUNDER"
        elif geometry.la_std_dev >= 30.0:
            archetype = "HIGH_VARIANCE_FLYBALL"
        else:
            archetype = "AVERAGE"

        return SweetSpotEvaluationResult(
            batter_name=geometry.batter_name,
            ideal_contact_rate=geometry.ideal_contact_rate,
            contact_quality_score=cqs,
            launch_path_archetype=archetype,
            is_elite_ball_striker=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Sweet Spot Contact Engine (SWEETSPOT-01)."""
    checks: list[Check] = []
    try:
        engine = SweetSpotEngine()
        freeman = BatterContactGeometry(
            "b1",
            "Freddie Freeman Archetype",
            sweet_spot_pct=0.42,
            hard_hit_pct=0.48,
            ideal_contact_rate=45.0,
            la_std_dev=20.0,
        )
        grounder = BatterContactGeometry(
            "b2",
            "Hard Grounder Hitter",
            sweet_spot_pct=0.25,
            hard_hit_pct=0.48,
            ideal_contact_rate=24.0,
            la_std_dev=26.0,
        )

        r_fre = engine.evaluate_contact(freeman)
        r_gro = engine.evaluate_contact(grounder)

        if (
            r_fre.launch_path_archetype == "LINE_DRIVE_MACHINE"
            and r_gro.launch_path_archetype == "HARD_HIT_GROUNDER"
        ):
            checks.append(
                Check(
                    "sweet spot engine",
                    True,
                    f"Sweet-spot verified (ICR: {r_fre.ideal_contact_rate:.1f}%)",
                )
            )
        else:
            checks.append(
                Check("sweet spot engine", False, f"Unexpected sweetspot output: {r_fre}, {r_gro}")
            )
    except Exception as exc:
        checks.append(Check("sweet spot engine", False, str(exc)))
    return checks
