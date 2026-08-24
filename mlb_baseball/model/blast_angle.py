"""Batter Contact Blast Angle & Launch Window Compression Engine (BLAST-ANGLE-01, ADR-199).

Provides launch angle consistency, power corridor compression, and damage optimization modeling:
1. Launch Angle Standard Deviation (sigma_LA measuring swing trajectory consistency).
2. Power Blast Window Rate (fraction of BBEs in the lethal 18°-28° home run corridor).
3. Launch Window Tightness Score (LWTS combining trajectory precision and hard-hit rate).
4. Launch Archetypes (Precision Power Blaster, Line Drive Artisan, Erratic Flyball Popup Risk).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterBlastAngleMetrics:
    """Observed launch angle distribution and contact quality metrics."""

    batter_id: str
    batter_name: str
    mean_launch_angle_deg: float = 14.5
    launch_angle_std_deg: float = 24.0  # League average ~28.0°
    sweet_spot_pct: float = 38.0  # 8° to 32°
    power_blast_window_pct: float = 22.0  # 18° to 28°
    hard_hit_pct: float = 42.0  # EV >= 95 mph
    bbe_count: int = 220


@dataclasses.dataclass(frozen=True)
class BlastAngleEvaluationResult:
    """Evaluated launch window consistency, LWTS score, and surplus run production."""

    batter_name: str
    lwts_score: float  # Launch Window Tightness Score (0 to 160)
    basd_runs_saved: float  # Net run production from optimal blast angle compression
    launch_tier: str  # e.g. "PRECISION_POWER_BLASTER", "ERRATIC_FLYBALL_POPUP_RISK"
    is_precision_blaster: bool


class BaseBlastAngleEngine(Protocol):
    """Polymorphic protocol for batter blast angle engines."""

    def evaluate_blast_angle(
        self,
        metrics: BatterBlastAngleMetrics,
    ) -> BlastAngleEvaluationResult:
        """Calculate launch window tightness, LWTS, and BASD runs."""
        ...


class BatterBlastAngleEngine:
    """Calculates launch angle distribution tightness and power corridor damage (BLAST-ANGLE-01)."""

    def evaluate_blast_angle(
        self,
        metrics: BatterBlastAngleMetrics,
    ) -> BlastAngleEvaluationResult:
        """Compute LWTS index, launch tier, and BASD run production."""
        # LWTS Score: benchmark is 28.0° std, 18.0% power blast, 38.0% hard hit
        std_bonus = (28.0 - metrics.launch_angle_std_deg) * 2.6
        blast_bonus = (metrics.power_blast_window_pct - 18.0) * 3.0
        hard_hit_bonus = (metrics.hard_hit_pct - 38.0) * 1.1
        lwts = round(max(0.0, 100.0 + std_bonus + blast_bonus + hard_hit_bonus), 1)

        # BASD Runs Saved / Produced
        bbes = max(1, metrics.bbe_count)
        blast_delta = (metrics.power_blast_window_pct - 18.0) / 100.0
        sweet_delta = (metrics.sweet_spot_pct - 34.0) / 100.0
        basd = round((blast_delta * bbes * 0.44) + (sweet_delta * bbes * 0.18), 2)

        is_precision = lwts >= 118.0 and metrics.launch_angle_std_deg <= 22.0

        # Tiers
        if is_precision and metrics.power_blast_window_pct >= 24.0:
            tier = "PRECISION_POWER_BLASTER"
        elif metrics.mean_launch_angle_deg <= 10.0 and metrics.launch_angle_std_deg <= 22.0:
            tier = "FLAT_TRAJECTORY_LINE_DRIVE_ARTISAN"
        elif metrics.launch_angle_std_deg >= 32.0 or lwts <= 85.0:
            tier = "ERRATIC_FLYBALL_POPUP_RISK"
        else:
            tier = "AVERAGE_LAUNCH_PROFILE"

        return BlastAngleEvaluationResult(
            batter_name=metrics.batter_name,
            lwts_score=lwts,
            basd_runs_saved=basd,
            launch_tier=tier,
            is_precision_blaster=is_precision,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Blast Angle Engine (BLAST-ANGLE-01)."""
    checks: list[Check] = []
    try:
        engine = BatterBlastAngleEngine()
        blaster = BatterBlastAngleMetrics("b1", "Yordan Alvarez", 16.0, 19.5, 45.0, 28.0, 56.0, 260)
        pop_risk = BatterBlastAngleMetrics("b2", "Popup Swinger", 26.0, 35.0, 28.0, 12.0, 32.0, 210)

        r_bla = engine.evaluate_blast_angle(blaster)
        r_pop = engine.evaluate_blast_angle(pop_risk)

        if (
            r_bla.launch_tier == "PRECISION_POWER_BLASTER"
            and r_pop.launch_tier == "ERRATIC_FLYBALL_POPUP_RISK"
        ):
            checks.append(
                Check(
                    "blast angle engine",
                    True,
                    f"Blast angle verified (Yordan LWTS: {r_bla.lwts_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "blast angle engine", False, f"Unexpected blast angle output: {r_bla}, {r_pop}"
                )
            )
    except Exception as exc:
        checks.append(Check("blast angle engine", False, str(exc)))
    return checks
