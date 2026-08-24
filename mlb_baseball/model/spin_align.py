"""Pitcher Release Point Spin Angle Stability Engine (SPIN-ALIGN-01, ADR-240).

Provides release height uniformity, multi-pitch spin axis alignment, and ASARCI index:
1. Arsenal Spin Alignment & Release Consistency Index (ASARCI score measuring tunnel deception).
2. Deception Whiff Synergy Multiplier (DWSM factor boosting swing-and-miss rates).
3. Alignment Archetypes (Mirrored Spin Tunnel Illusionist, Telegraphed Arm Slot Tipper).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherSpinAlignMetrics:
    """Observed pitcher spin axis std dev mins, release Z std dev in, and release X std dev in."""

    pitcher_id: str
    pitcher_name: str
    spin_axis_std_dev_mins: float = 28.0  # Std dev of spin tilt across repertoire (benchmark ~28m)
    release_height_std_dev_in: float = 1.5  # Std dev of Z release in inches (benchmark ~1.5 in)
    release_side_std_dev_in: float = 1.8  # Std dev of X release in inches (benchmark ~1.8 in)
    pitch_arsenal_size: int = 4


@dataclasses.dataclass(frozen=True)
class SpinAlignEvaluationResult:
    """Evaluated spin alignment score, deception multiplier, and illusion tier."""

    pitcher_name: str
    asarci_score: float  # Arsenal Spin Alignment & Release Consistency Index (0 to 160)
    deception_multiplier: float  # Deception whiff synergy boost multiplier
    alignment_tier: str  # e.g. "MIRRORED_SPIN_TUNNEL_ILLUSIONIST", "TELEGRAPHED_ARM_SLOT_TIPPER"
    is_illusionist: bool


class BaseSpinAlignEngine(Protocol):
    """Polymorphic protocol for arsenal spin alignment engines."""

    def evaluate_spin_align(
        self,
        metrics: PitcherSpinAlignMetrics,
    ) -> SpinAlignEvaluationResult:
        """Calculate ASARCI score, deception multiplier, and tier."""
        ...


class PitcherSpinAlignEngine:
    """Calculates release point consistency, spin tilt stability, and ASARCI (SPIN-ALIGN-01)."""

    def evaluate_spin_align(
        self,
        metrics: PitcherSpinAlignMetrics,
    ) -> SpinAlignEvaluationResult:
        """Compute ASARCI rating and deception synergy multiplier."""
        # ASARCI Score: benchmark 28m axis SD, 1.5 in Z SD, 1.8 in X SD
        axis_saving = (28.0 - metrics.spin_axis_std_dev_mins) * 1.4
        z_saving = (1.5 - metrics.release_height_std_dev_in) * 15.0
        x_saving = (1.8 - metrics.release_side_std_dev_in) * 12.0
        asarci = round(max(0.0, 100.0 + axis_saving + z_saving + x_saving), 1)

        # DWSM Multiplier
        mult = round(1.0 + (asarci - 100.0) * 0.0035, 3)

        is_illusionist = (
            asarci >= 116.0
            and metrics.spin_axis_std_dev_mins <= 18.0
            and metrics.release_height_std_dev_in <= 0.8
        )

        # Tiers
        if is_illusionist:
            tier = "MIRRORED_SPIN_TUNNEL_ILLUSIONIST"
        elif metrics.spin_axis_std_dev_mins >= 40.0 or metrics.release_height_std_dev_in >= 2.5:
            tier = "TELEGRAPHED_ARM_SLOT_TIPPER"
        elif metrics.release_height_std_dev_in <= 1.0:
            tier = "SOLID_REPEATED_RELEASE_DELIVERY"
        else:
            tier = "AVERAGE_ARSENAL_ALIGNMENT"

        return SpinAlignEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            asarci_score=asarci,
            deception_multiplier=mult,
            alignment_tier=tier,
            is_illusionist=is_illusionist,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Spin Align Engine (SPIN-ALIGN-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherSpinAlignEngine()
        illusionist = PitcherSpinAlignMetrics("p1", "Spencer Strider", 12.0, 0.5, 0.6, 3)
        tipper = PitcherSpinAlignMetrics("p2", "Tipping Pitcher", 44.0, 2.8, 2.6, 4)

        r_ill = engine.evaluate_spin_align(illusionist)
        r_tip = engine.evaluate_spin_align(tipper)

        if (
            r_ill.alignment_tier == "MIRRORED_SPIN_TUNNEL_ILLUSIONIST"
            and r_tip.alignment_tier == "TELEGRAPHED_ARM_SLOT_TIPPER"
        ):
            checks.append(
                Check(
                    "spin align engine",
                    True,
                    f"Spin Align verified (Strider ASARCI: {r_ill.asarci_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("spin align engine", False, f"Unexpected spin align output: {r_ill}, {r_tip}")
            )
    except Exception as exc:
        checks.append(Check("spin align engine", False, str(exc)))
    return checks
