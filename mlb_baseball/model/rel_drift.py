"""Pitcher Release Point Variance & Mechanical Tell Engine (REL-DRIFT-01, ADR-207).

Provides 3D spatial release point dispersion, mechanical repeat consistency, and fatigue alerts:
1. Spatial Release Dispersion (sqrt(std_x^2 + std_z^2) in inches).
2. Mechanical Consistency Score (MCS index measuring repeat stability).
3. Late-Game Arm Slot Collapse Warning (detecting mechanical tells and fatigue).
4. Release Archetypes (Metronomic Repeater, Fatigue Collapse Alert, Scattered Release).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherReleaseDispersionMetrics:
    """Observed pitcher spatial release point dispersion and late-game fatigue metrics."""

    pitcher_id: str
    pitcher_name: str
    mean_rel_x_ft: float = -2.10
    mean_rel_z_ft: float = 5.85
    std_rel_x_in: float = 1.8  # Standard deviation of horizontal release in inches
    std_rel_z_in: float = 1.6  # Standard deviation of vertical release in inches
    late_game_rel_drop_in: float = 0.8  # Arm slot drop in pitches 75+
    pitch_count_evaluated: int = 90


@dataclasses.dataclass(frozen=True)
class ReleaseDriftEvaluationResult:
    """Evaluated release dispersion, MCS score, and mechanical fatigue flags."""

    pitcher_name: str
    spatial_dispersion_in: float  # Euclidean 2D dispersion in inches
    mcs_score: float  # Mechanical Consistency Score (0 to 160)
    release_tier: str  # e.g. "METRONOMIC_MECHANICAL_REPEATER", "FATIGUE_ARM_SLOT_COLLAPSE_ALERT"
    is_metronomic_repeater: bool
    fatigue_collapse_warning: bool


class BaseReleaseDriftEngine(Protocol):
    """Polymorphic protocol for pitcher release point drift engines."""

    def evaluate_release_drift(
        self,
        metrics: PitcherReleaseDispersionMetrics,
    ) -> ReleaseDriftEvaluationResult:
        """Calculate spatial dispersion, MCS score, and fatigue warnings."""
        ...


class PitcherReleaseDriftEngine:
    """Calculates spatial release consistency, repeatability, and fatigue tells (REL-DRIFT-01)."""

    def evaluate_release_drift(
        self,
        metrics: PitcherReleaseDispersionMetrics,
    ) -> ReleaseDriftEvaluationResult:
        """Compute Euclidean release dispersion and MCS consistency index."""
        # 2D spatial dispersion in inches: sqrt(std_x^2 + std_z^2)
        spatial_disp = math.sqrt(metrics.std_rel_x_in**2 + metrics.std_rel_z_in**2)
        spatial_disp = round(spatial_disp, 2)

        # MCS Score: benchmark 2.6 in dispersion, 0.8 in late-game drop
        disp_bonus = (2.6 - spatial_disp) * 16.0
        drop_penalty = max(0.0, metrics.late_game_rel_drop_in - 0.8) * 11.0
        mcs = round(max(0.0, 100.0 + disp_bonus - drop_penalty), 1)

        is_metronomic = (
            mcs >= 112.0 and spatial_disp <= 2.10 and metrics.late_game_rel_drop_in <= 1.0
        )
        is_collapse = metrics.late_game_rel_drop_in >= 2.4

        # Tiers
        if is_metronomic:
            tier = "METRONOMIC_MECHANICAL_REPEATER"
        elif is_collapse:
            tier = "FATIGUE_ARM_SLOT_COLLAPSE_ALERT"
        elif spatial_disp >= 3.60:
            tier = "ERRATIC_SCATTERED_RELEASE_POINT"
        else:
            tier = "AVERAGE_RELEASE_CONSISTENCY"

        return ReleaseDriftEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            spatial_dispersion_in=spatial_disp,
            mcs_score=mcs,
            release_tier=tier,
            is_metronomic_repeater=is_metronomic,
            fatigue_collapse_warning=is_collapse,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Release Drift Engine (REL-DRIFT-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherReleaseDriftEngine()
        metronomic = PitcherReleaseDispersionMetrics(
            "p1", "Zack Greinke", -2.1, 5.8, 1.2, 1.1, 0.5, 95
        )
        fatigued = PitcherReleaseDispersionMetrics(
            "p2", "Fatigued Arm", -2.1, 5.8, 2.2, 2.1, 2.8, 88
        )

        r_met = engine.evaluate_release_drift(metronomic)
        r_fat = engine.evaluate_release_drift(fatigued)

        if (
            r_met.release_tier == "METRONOMIC_MECHANICAL_REPEATER"
            and r_fat.release_tier == "FATIGUE_ARM_SLOT_COLLAPSE_ALERT"
        ):
            checks.append(
                Check(
                    "rel drift engine",
                    True,
                    f"Release Drift verified (Greinke MCS: {r_met.mcs_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "rel drift engine", False, f"Unexpected release drift output: {r_met}, {r_fat}"
                )
            )
    except Exception as exc:
        checks.append(Check("rel drift engine", False, str(exc)))
    return checks
