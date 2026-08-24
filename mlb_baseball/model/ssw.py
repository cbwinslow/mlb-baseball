"""Seam-Shifted Wake (SSW) & Aerodynamic Non-Magnus Spin Deviation Engine (SSW-01, ADR-147).

Provides pitch aerodynamics, seam orientation tracking, and non-Magnus force modeling:
1. Spin-Based Magnus Deflection Expectation (IVB and HB from pure spin axis & velocity).
2. Seam-Shifted Wake Deviation Vector (quantifies non-Magnus lateral/vertical movement).
3. SSW Archetype Classification (Sinkers, Sweepers, Changeups with heavy seam effects).
4. Batter Perception Deception & Whiff/Hard-Hit Quality Lift.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitchSpinKinematics:
    """Pitch release velocity, spin rate, and observed trajectory flight numbers."""

    pitch_id: str
    pitch_type: str  # "FF", "SI", "SL", "ST", "CH", "CU"
    velocity_mph: float
    spin_rate_rpm: float
    observed_ivb_in: float  # Observed Induced Vertical Break (inches)
    observed_hb_in: float  # Observed Horizontal Break (inches, positive = arm side)
    spin_axis_deg: float  # 0 to 360 degrees (tilt clock angle)


@dataclasses.dataclass(frozen=True)
class SSWAnalysisResult:
    """Evaluated Seam-Shifted Wake movement deviations and deception metrics."""

    pitch_type: str
    magnus_ivb_in: float
    magnus_hb_in: float
    ssw_ivb_delta_in: float
    ssw_hb_delta_in: float
    ssw_total_magnitude_in: float
    whiff_boost_pct: float
    hard_hit_suppression_pct: float
    has_pronounced_ssw: bool


class BaseSSWEngine(Protocol):
    """Polymorphic protocol for seam-shifted wake engines."""

    def evaluate_pitch_ssw(
        self,
        kinematics: PitchSpinKinematics,
    ) -> SSWAnalysisResult:
        """Calculate seam-shifted wake deviation and deception metrics."""
        ...


class SeamShiftedWakeEngine:
    """Calculates non-Magnus aerodynamics and seam-shifted wake movement (SSW-01)."""

    def evaluate_pitch_ssw(
        self,
        kinematics: PitchSpinKinematics,
    ) -> SSWAnalysisResult:
        """Compute expected Magnus movement vs observed deflection to isolate SSW force."""
        # 1. Theoretical pure Magnus movement estimation from spin axis & spin rate
        # Velo and spin factor:
        spin_factor = (kinematics.spin_rate_rpm / 2200.0) * (kinematics.velocity_mph / 93.0)
        rad_axis = math.radians(kinematics.spin_axis_deg)

        # Baseline Magnus component projections:
        if kinematics.pitch_type in ("FF", "SI"):
            base_mag_ivb = 16.0 * math.cos(rad_axis) * spin_factor
            base_mag_hb = 14.0 * math.sin(rad_axis) * spin_factor
        elif kinematics.pitch_type in ("SL", "ST"):
            base_mag_ivb = 2.0 * math.cos(rad_axis) * spin_factor
            base_mag_hb = -10.0 * math.sin(rad_axis) * spin_factor
        elif kinematics.pitch_type == "CH":
            base_mag_ivb = 8.0 * math.cos(rad_axis) * spin_factor
            base_mag_hb = 12.0 * math.sin(rad_axis) * spin_factor
        else:  # CU / other
            base_mag_ivb = -10.0 * math.cos(rad_axis) * spin_factor
            base_mag_hb = -6.0 * math.sin(rad_axis) * spin_factor

        # 2. Seam-shifted wake deviation: Observed - Magnus
        delta_ivb = kinematics.observed_ivb_in - base_mag_ivb
        delta_hb = kinematics.observed_hb_in - base_mag_hb

        # SSW vector magnitude
        ssw_mag = float(math.sqrt(delta_ivb**2 + delta_hb**2))

        # 3. Deception metrics: SSW breaks batter optical tracking
        # Every 1.0 inch of SSW yields ~ +1.4% whiff boost and -1.6% hard hit rate
        whiff_boost = round(ssw_mag * 1.4, 2)
        hh_suppression = round(ssw_mag * 1.6, 2)

        has_ssw = ssw_mag >= 2.0  # Pronounced SSW if > 2.0 inches of non-Magnus movement

        return SSWAnalysisResult(
            pitch_type=kinematics.pitch_type,
            magnus_ivb_in=round(base_mag_ivb, 2),
            magnus_hb_in=round(base_mag_hb, 2),
            ssw_ivb_delta_in=round(delta_ivb, 2),
            ssw_hb_delta_in=round(delta_hb, 2),
            ssw_total_magnitude_in=round(ssw_mag, 2),
            whiff_boost_pct=whiff_boost,
            hard_hit_suppression_pct=hh_suppression,
            has_pronounced_ssw=has_ssw,
        )


def health_check() -> list[Check]:
    """Operational health check for the Seam-Shifted Wake Aerodynamics Engine (SSW-01)."""
    checks: list[Check] = []
    try:
        engine = SeamShiftedWakeEngine()
        # Sinker with heavy arm-side seam shift
        sinker = PitchSpinKinematics(
            "p1",
            "SI",
            velocity_mph=94.5,
            spin_rate_rpm=2150,
            observed_ivb_in=6.5,
            observed_hb_in=17.5,
            spin_axis_deg=45.0,
        )

        res = engine.evaluate_pitch_ssw(sinker)

        if res.ssw_total_magnitude_in > 2.0 and res.has_pronounced_ssw:
            checks.append(
                Check(
                    "seam shifted wake engine",
                    True,
                    f"SSW verified (Mag: {res.ssw_total_magnitude_in:.1f}in)",
                )
            )
        else:
            checks.append(Check("seam shifted wake engine", False, f"Unexpected SSW output: {res}"))
    except Exception as exc:
        checks.append(Check("seam shifted wake engine", False, str(exc)))
    return checks
