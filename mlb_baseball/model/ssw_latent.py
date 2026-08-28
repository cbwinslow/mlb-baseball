"""Pitcher Seam-Shifted Wake Latent Movement Engine (SSW-LATENT-01, ADR-232).

Provides optical vs inferred spin axis deviation, non-Magnus boundary layer break, and SSWLMR:
1. Seam-Shifted Wake Latent Movement Rating (SSWLMR score measuring aerodynamic seam boost).
2. Latent SSW Break Delta (extra horizontal/vertical movement created by boundary layer separation).
3. SSW Archetypes (Elite Seam-Shifted Wake Manipulator, Pure Symmetrical Magnus Delivery).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherSswLatentMetrics:
    """Observed pitcher optical spin axis, trajectory inferred axis, and break components."""

    pitcher_id: str
    pitcher_name: str
    pitch_type: str = "Sinker"
    optical_axis_minutes: int = 75  # 1:15 clock tilt at release (minutes)
    inferred_axis_minutes: int = 110  # 1:50 inferred trajectory tilt (minutes)
    observed_break_in: float = 17.5  # Total observed trajectory movement in inches
    pure_magnus_break_in: float = 14.0  # Predicted movement from spin alone in inches
    pitch_count_evaluated: int = 220


@dataclasses.dataclass(frozen=True)
class SswLatentEvaluationResult:
    """Evaluated seam-shifted wake deviation, latent break inches, SSWLMR rating, and tier."""

    pitcher_name: str
    pitch_type: str
    axis_deviation_mins: int  # Minutes difference between optical and inferred axes
    latent_ssw_break_in: float  # Extra non-Magnus movement created by seam wake (in)
    sswlmr_score: float  # Seam-Shifted Wake Latent Movement Rating (0 to 160)
    ssw_tier: str  # e.g. "ELITE_SEAM_SHIFTED_WAKE_MANIPULATOR", "PURE_SYMMETRICAL_MAGNUS"
    is_elite_manipulator: bool


class BaseSswLatentEngine(Protocol):
    """Polymorphic protocol for seam-shifted wake evaluation engines."""

    def evaluate_ssw(
        self,
        metrics: PitcherSswLatentMetrics,
    ) -> SswLatentEvaluationResult:
        """Calculate axis deviation, latent break, and SSWLMR score."""
        ...


class PitcherSswLatentEngine:
    """Calculates non-Magnus seam aerodynamic break, axis tilt gap, and SSWLMR (SSW-LATENT-01)."""

    def evaluate_ssw(
        self,
        metrics: PitcherSswLatentMetrics,
    ) -> SswLatentEvaluationResult:
        """Compute SSWLMR rating and latent boundary layer break inches."""
        axis_gap = abs(metrics.inferred_axis_minutes - metrics.optical_axis_minutes)
        latent_break = round(max(0.0, metrics.observed_break_in - metrics.pure_magnus_break_in), 1)

        # SSWLMR Score: benchmark 35 mins deviation, 3.5 in latent break (this
        # class's own defaults: |110-75|=35 mins, 17.5-14.0=3.5 in)
        axis_bonus = (axis_gap - 35.0) * 0.9
        break_bonus = (latent_break - 3.5) * 8.0
        sswlmr = round(max(0.0, 100.0 + axis_bonus + break_bonus), 1)

        is_manipulator = sswlmr >= 116.0 and latent_break >= 3.8 and axis_gap >= 38

        # Tiers
        if is_manipulator:
            tier = "ELITE_SEAM_SHIFTED_WAKE_MANIPULATOR"
        elif latent_break <= 0.6 and axis_gap <= 12:
            tier = "PURE_SYMMETRICAL_MAGNUS_DELIVERY"
        elif latent_break >= 2.8:
            tier = "SOLID_SEAM_ORIENTED_ARSENAL"
        else:
            tier = "AVERAGE_SSW_EFFECT"

        return SswLatentEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            pitch_type=metrics.pitch_type,
            axis_deviation_mins=axis_gap,
            latent_ssw_break_in=latent_break,
            sswlmr_score=sswlmr,
            ssw_tier=tier,
            is_elite_manipulator=is_manipulator,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher SSW Latent Engine (SSW-LATENT-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherSswLatentEngine()
        manipulator = PitcherSswLatentMetrics(
            "p1", "Logan Webb", "Sinker", 75, 125, 19.5, 14.2, 260
        )
        symmetrical = PitcherSswLatentMetrics(
            "p2", "Four Seam Pure", "4-Seam", 65, 70, 16.0, 15.6, 200
        )

        r_man = engine.evaluate_ssw(manipulator)
        r_sym = engine.evaluate_ssw(symmetrical)

        if (
            r_man.ssw_tier == "ELITE_SEAM_SHIFTED_WAKE_MANIPULATOR"
            and r_sym.ssw_tier == "PURE_SYMMETRICAL_MAGNUS_DELIVERY"
        ):
            checks.append(
                Check(
                    "ssw latent engine",
                    True,
                    f"SSW Latent verified (Webb SSWLMR: {r_man.sswlmr_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("ssw latent engine", False, f"Unexpected ssw latent output: {r_man}, {r_sym}")
            )
    except Exception as exc:
        checks.append(Check("ssw latent engine", False, str(exc)))
    return checks
