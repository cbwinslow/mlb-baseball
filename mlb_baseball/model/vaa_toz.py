"""Pitcher Vertical Approach Angle vs Top-of-Zone Whiff Engine (VAA-TOZ-01, ADR-204).

Provides top-of-strike-zone entry angle trigonometry, flatness indexing, and whiff prediction:
1. Top-of-Zone VAA (VAA_TOZ in degrees, benchmark -5.0° to -4.5°).
2. Top-of-Zone Flatness Index (TOZ-FI score measuring the "rising" optical illusion).
3. Upper-Third Whiff Multiplier (scaling in-zone swing-and-miss rates).
4. VAA Archetypes (Deadly Flat Rising Heater, Above Average, Steep Downhill Fastball).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherTOZVAAMetrics:
    """Observed pitcher release kinematics, IVB, and upper-zone crossing parameters."""

    pitcher_id: str
    pitcher_name: str
    pitch_type: str = "FF"
    release_z_ft: float = 5.6  # Low release height aids flat VAA
    release_velo_mph: float = 96.0
    induced_vert_break_in: float = 18.5  # High IVB aids flat VAA
    plate_crossing_z_ft: float = 3.35  # Top third of strike zone
    extension_ft: float = 6.8


@dataclasses.dataclass(frozen=True)
class TOZVAAEvaluationResult:
    """Evaluated top-of-zone VAA angle, flatness index, and whiff multiplier."""

    pitcher_name: str
    pitch_type: str
    vaa_toz_deg: float  # Top-of-zone entry angle (e.g. -3.9° to -6.2°)
    toz_flatness_index: float  # TOZ-FI score (0 to 160)
    whiff_boost_multiplier: float  # Upper zone swing-and-miss boost (1.00x to 1.35x)
    vaa_tier: str  # e.g. "DEADLY_FLAT_RISING_HEATER", "STEEP_DOWNHILL_FASTBALL"
    is_deadly_flat_heater: bool


class BaseTOZVAAEngine(Protocol):
    """Polymorphic protocol for top-of-zone VAA engines."""

    def evaluate_toz_vaa(
        self,
        metrics: PitcherTOZVAAMetrics,
    ) -> TOZVAAEvaluationResult:
        """Calculate VAA_TOZ, flatness score, and whiff boost."""
        ...


class PitcherTOZVAAEngine:
    """Calculates top-of-zone vertical approach angle and whiff deception (VAA-TOZ-01)."""

    def evaluate_toz_vaa(
        self,
        metrics: PitcherTOZVAAMetrics,
    ) -> TOZVAAEvaluationResult:
        """Compute top-of-zone VAA and flatness multiplier."""
        # Top-of-zone VAA empirical kinematic model at z = 3.35 ft
        # Flat VAA is shallower/less negative (e.g. -3.8° vs steep -6.2°)
        vaa_base = -4.90
        rel_adj = (metrics.release_z_ft - 5.8) * -0.90  # Lower release -> flatter VAA
        ivb_adj = (metrics.induced_vert_break_in - 16.0) * 0.12  # Higher IVB -> flatter VAA
        velo_adj = (metrics.release_velo_mph - 93.5) * 0.04  # Higher velo -> flatter VAA

        vaa = round(vaa_base + rel_adj + ivb_adj + velo_adj, 2)

        # TOZ-FI Score: benchmark is -4.8° VAA, 16.0 in IVB, 94.0 mph
        vaa_bonus = (vaa - (-4.8)) * 18.0
        ivb_bonus = (metrics.induced_vert_break_in - 16.0) * 2.2
        velo_bonus = (metrics.release_velo_mph - 94.0) * 1.2
        toz_fi = round(max(0.0, 100.0 + vaa_bonus + ivb_bonus + velo_bonus), 1)

        whiff_mult = round(1.0 + max(0.0, toz_fi - 100.0) / 250.0, 3)

        is_deadly = vaa >= -4.20 and toz_fi >= 115.0

        # Tiers
        if is_deadly:
            tier = "DEADLY_FLAT_RISING_HEATER"
        elif vaa >= -4.75:
            tier = "ABOVE_AVERAGE_FLAT_PROFILE"
        elif vaa <= -5.80:
            tier = "STEEP_DOWNHILL_FASTBALL"
        else:
            tier = "AVERAGE_APPROACH_FASTBALL"

        return TOZVAAEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            pitch_type=metrics.pitch_type,
            vaa_toz_deg=vaa,
            toz_flatness_index=toz_fi,
            whiff_boost_multiplier=whiff_mult,
            vaa_tier=tier,
            is_deadly_flat_heater=is_deadly,
        )


def health_check() -> list[Check]:
    """Operational health check for Top-of-Zone VAA Engine (VAA-TOZ-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherTOZVAAEngine()
        flat_heater = PitcherTOZVAAMetrics("p1", "Spencer Strider", "FF", 5.4, 98.0, 20.0, 3.4, 7.0)
        steep_fastball = PitcherTOZVAAMetrics("p2", "Tall Pitcher", "FF", 6.6, 91.0, 13.0, 3.4, 6.0)

        r_fla = engine.evaluate_toz_vaa(flat_heater)
        r_ste = engine.evaluate_toz_vaa(steep_fastball)

        if (
            r_fla.vaa_tier == "DEADLY_FLAT_RISING_HEATER"
            and r_ste.vaa_tier == "STEEP_DOWNHILL_FASTBALL"
        ):
            checks.append(
                Check(
                    "vaa toz engine",
                    True,
                    f"VAA TOZ verified (Strider VAA: {r_fla.vaa_toz_deg:.2f}°)",
                )
            )
        else:
            checks.append(
                Check("vaa toz engine", False, f"Unexpected VAA TOZ output: {r_fla}, {r_ste}")
            )
    except Exception as exc:
        checks.append(Check("vaa toz engine", False, str(exc)))
    return checks
