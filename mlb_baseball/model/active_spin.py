"""Pitcher Spin Axis Gyro Efficiency & Active Spin Engine (ACTIVE-SPIN-01, ADR-224).

Provides Hawkeye spin decomposition, transverse Magnus conversion, and gyro angle modeling:
1. Active Spin Efficiency Percentage (active_spin_pct = inferred_active_rpm / total_rpm * 100).
2. Gyro Angle Estimation (gyro_angle in degrees = arccos(active_pct) * 180 / pi).
3. Active Spin Magnus Index (ASMI score measuring true aerodynamic movement efficiency).
4. Spin Archetypes (Pure Transverse Magnus Rider, Pure Bullet Gyro Spinner, Sloppy Spin Leak).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherActiveSpinMetrics:
    """Observed pitcher total spin rate, trajectory-inferred active spin, and pitch type."""

    pitcher_id: str
    pitcher_name: str
    pitch_type: str = "4-Seam"
    total_spin_rpm: float = 2300.0
    inferred_active_spin_rpm: float = 2000.0
    observed_ivb_in: float = 16.5
    observed_hb_in: float = 8.0
    pitch_count_evaluated: int = 200


@dataclasses.dataclass(frozen=True)
class ActiveSpinEvaluationResult:
    """Evaluated active spin efficiency percentage, gyro angle, ASMI score, and tier."""

    pitcher_name: str
    pitch_type: str
    active_spin_pct: float  # Fraction of spin converted to aerodynamic movement (0-100%)
    gyro_angle_deg: float  # Estimated 3D gyro tilt angle (0 to 90 deg)
    asmi_score: float  # Active Spin Magnus Index (0 to 160)
    spin_tier: str  # e.g. "PURE_TRANSVERSE_MAGNUS_RIDER", "PURE_BULLET_GYRO_SPINNER"
    is_pure_magnus: bool


class BaseActiveSpinEngine(Protocol):
    """Polymorphic protocol for active spin efficiency engines."""

    def evaluate_active_spin(
        self,
        metrics: PitcherActiveSpinMetrics,
    ) -> ActiveSpinEvaluationResult:
        """Calculate active spin %, gyro angle, and ASMI score."""
        ...


class PitcherActiveSpinEngine:
    """Calculates active spin efficiency, gyro angle, and ASMI rating (ACTIVE-SPIN-01)."""

    def evaluate_active_spin(
        self,
        metrics: PitcherActiveSpinMetrics,
    ) -> ActiveSpinEvaluationResult:
        """Compute active spin percentage, 3D gyro angle, and ASMI score."""
        total_rpm = max(100.0, metrics.total_spin_rpm)
        active_ratio = min(1.0, max(0.0, metrics.inferred_active_spin_rpm / total_rpm))
        active_pct = round(active_ratio * 100.0, 1)

        # Gyro Angle in degrees: arccos(active_ratio)
        gyro_rad = math.acos(active_ratio)
        gyro_deg = round(math.degrees(gyro_rad), 1)

        # ASMI Score: benchmark 85.0% active spin, 2250 total RPM
        active_bonus = (active_pct - 85.0) * 1.8
        rpm_bonus = ((metrics.total_spin_rpm - 2250.0) / 100.0) * 2.5
        asmi = round(max(0.0, 100.0 + active_bonus + rpm_bonus), 1)

        is_magnus = active_pct >= 93.0 and asmi >= 116.0 and metrics.total_spin_rpm >= 2350.0

        # Tiers
        if is_magnus:
            tier = "PURE_TRANSVERSE_MAGNUS_RIDER"
        elif active_pct <= 35.0:
            tier = "PURE_BULLET_GYRO_SPINNER"
        elif metrics.pitch_type in ("4-Seam", "FF") and active_pct <= 72.0:
            tier = "SUB_OPTIMAL_SLOPPY_SPIN_LEAK"
        elif active_pct >= 88.0:
            tier = "HIGH_EFFICIENCY_MAGNUS_PROFILE"
        else:
            tier = "AVERAGE_ACTIVE_SPIN"

        return ActiveSpinEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            pitch_type=metrics.pitch_type,
            active_spin_pct=active_pct,
            gyro_angle_deg=gyro_deg,
            asmi_score=asmi,
            spin_tier=tier,
            is_pure_magnus=is_magnus,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Active Spin Engine (ACTIVE-SPIN-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherActiveSpinEngine()
        magnus = PitcherActiveSpinMetrics(
            "p1", "Paul Skenes", "4-Seam", 2480.0, 2430.0, 19.5, 9.0, 250
        )
        gyro = PitcherActiveSpinMetrics(
            "p2", "Bullet Slider", "Slider", 2400.0, 600.0, 1.0, -2.0, 180
        )

        r_mag = engine.evaluate_active_spin(magnus)
        r_gyr = engine.evaluate_active_spin(gyro)

        if (
            r_mag.spin_tier == "PURE_TRANSVERSE_MAGNUS_RIDER"
            and r_gyr.spin_tier == "PURE_BULLET_GYRO_SPINNER"
        ):
            checks.append(
                Check(
                    "active spin engine",
                    True,
                    f"Active Spin verified (Skenes Active%: {r_mag.active_spin_pct:.1f}%)",
                )
            )
        else:
            checks.append(
                Check(
                    "active spin engine", False, f"Unexpected active spin output: {r_mag}, {r_gyr}"
                )
            )
    except Exception as exc:
        checks.append(Check("active spin engine", False, str(exc)))
    return checks
