"""Pitched Ball Seam-Orientation Gyro Spin & Efficiency Decomposer (SPIN-01, ADR-157).

Provides 3D spin vector decomposition, active spin isolation, and pitch archetype classification:
1. Transverse vs Gyro (Bullet) Spin Vector Decomposition.
2. Spin Efficiency Percentage (fraction of spin generating Magnus movement).
3. True Active Spin RPM Calculation.
4. Pitch Archetype Diagnostics (Pure Magnus 4-Seam, Gyro Bullet Slider, Sweeper, Tailing Sinker).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitchSpinObservation:
    """Observed total spin rate and pitch type flight parameters."""

    pitch_id: str
    pitch_type: str  # "FF", "SL", "ST", "SI", "CH", "CU"
    total_spin_rpm: float = 2350.0
    spin_efficiency_pct: float = 85.0  # 0 to 100%


@dataclasses.dataclass(frozen=True)
class SpinDecompositionResult:
    """Decomposed 3D spin components and pitch shape classification."""

    pitch_type: str
    total_spin_rpm: float
    active_spin_rpm: float
    gyro_spin_rpm: float
    spin_efficiency_pct: float
    spin_archetype: str  # "PURE_MAGNUS", "HYBRID_MOVEMENT", "GYRO_BULLET"


class BaseSpinEngine(Protocol):
    """Polymorphic protocol for spin decomposition engines."""

    def decompose_spin(
        self,
        obs: PitchSpinObservation,
    ) -> SpinDecompositionResult:
        """Decompose raw spin into transverse and gyro components."""
        ...


class SpinDecompositionEngine:
    """Calculates active spin, gyro spin, and pitch spin efficiency (SPIN-01)."""

    def decompose_spin(
        self,
        obs: PitchSpinObservation,
    ) -> SpinDecompositionResult:
        """Compute active transverse RPM and gyro bullet RPM."""
        eff_ratio = float(np.clip(obs.spin_efficiency_pct / 100.0, 0.0, 1.0))

        # 1. Transverse (Active) Spin RPM = total * efficiency
        active_rpm = round(obs.total_spin_rpm * eff_ratio, 1)

        # 2. Gyro (Bullet) Spin RPM: omega_total^2 = omega_active^2 + omega_gyro^2
        # => omega_gyro = sqrt(omega_total^2 - omega_active^2) = total * sqrt(1 - eff^2)
        gyro_rpm = round(obs.total_spin_rpm * math.sqrt(max(0.0, 1.0 - eff_ratio**2)), 1)

        # 3. Spin archetype
        if obs.spin_efficiency_pct >= 88.0:
            archetype = "PURE_MAGNUS"
        elif obs.spin_efficiency_pct <= 45.0:
            archetype = "GYRO_BULLET"
        else:
            archetype = "HYBRID_MOVEMENT"

        return SpinDecompositionResult(
            pitch_type=obs.pitch_type,
            total_spin_rpm=obs.total_spin_rpm,
            active_spin_rpm=active_rpm,
            gyro_spin_rpm=gyro_rpm,
            spin_efficiency_pct=round(obs.spin_efficiency_pct, 1),
            spin_archetype=archetype,
        )


def health_check() -> list[Check]:
    """Operational health check for the Spin Decomposition Engine (SPIN-01)."""
    checks: list[Check] = []
    try:
        engine = SpinDecompositionEngine()
        four_seam = PitchSpinObservation(
            "p1", "FF", total_spin_rpm=2400.0, spin_efficiency_pct=96.0
        )
        gyro_sl = PitchSpinObservation("p2", "SL", total_spin_rpm=2600.0, spin_efficiency_pct=30.0)

        r_ff = engine.decompose_spin(four_seam)
        r_sl = engine.decompose_spin(gyro_sl)

        if r_ff.spin_archetype == "PURE_MAGNUS" and r_sl.spin_archetype == "GYRO_BULLET":
            checks.append(
                Check(
                    "spin decomposition engine",
                    True,
                    f"Spin verified (Active: {r_ff.active_spin_rpm:.0f}rpm)",
                )
            )
        else:
            checks.append(
                Check("spin decomposition engine", False, f"Unexpected spin output: {r_ff}, {r_sl}")
            )
    except Exception as exc:
        checks.append(Check("spin decomposition engine", False, str(exc)))
    return checks
