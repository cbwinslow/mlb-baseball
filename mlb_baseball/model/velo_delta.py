"""Pitcher Arsenals Separation & Velocity Delta Disruption Engine (VELO-DELTA-01, ADR-200).

Provides pitch velocity differentials, speed banding, and vertical drop disruption modeling:
1. Fastball-to-Changeup Velocity Delta (Delta v in mph, benchmark ~8.5 mph).
2. Fastball-to-Changeup Vertical Separation (Delta IVB in inches, benchmark ~10.5 in).
3. Velocity Delta Disruption Index (VDDI score measuring arsenal timing disruption).
4. Arsenal Archetypes (Elite Velo Disruptor, Tight Band Power Pitcher, Flat Arsenal).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherArsenalSeparationMetrics:
    """Observed pitcher multi-pitch velocities and movement coordinates."""

    pitcher_id: str
    pitcher_name: str
    fastball_velo_mph: float = 95.0
    changeup_velo_mph: float = 86.5
    slider_velo_mph: float = 87.0
    curveball_velo_mph: float = 79.5
    fastball_ivb_in: float = 16.5
    changeup_ivb_in: float = 6.0


@dataclasses.dataclass(frozen=True)
class VeloDeltaEvaluationResult:
    """Evaluated speed differentials, VDDI score, and whiff multiplier."""

    pitcher_name: str
    fb_ch_velo_delta_mph: float  # Fastball - Changeup velo
    fb_ch_ivb_delta_in: float  # Fastball - Changeup IVB
    vddi_score: float  # Velocity Delta Disruption Index (0 to 160)
    whiff_boost_multiplier: float  # 1.00x to 1.30x
    separation_tier: str  # e.g. "ELITE_VELO_BAND_DISRUPTOR", "DANGEROUS_FLAT_HOMOGENEOUS_ARSENAL"
    is_elite_disruptor: bool


class BaseVeloDeltaEngine(Protocol):
    """Polymorphic protocol for pitcher velo delta engines."""

    def evaluate_separation(
        self,
        metrics: PitcherArsenalSeparationMetrics,
    ) -> VeloDeltaEvaluationResult:
        """Calculate speed deltas, VDDI, and separation tier."""
        ...


class PitcherVeloDeltaEngine:
    """Calculates multi-pitch velocity deltas and off-speed disruption (VELO-DELTA-01)."""

    def evaluate_separation(
        self,
        metrics: PitcherArsenalSeparationMetrics,
    ) -> VeloDeltaEvaluationResult:
        """Compute velo differentials and disruption score."""
        v_delta = round(metrics.fastball_velo_mph - metrics.changeup_velo_mph, 1)
        ivb_delta = round(metrics.fastball_ivb_in - metrics.changeup_ivb_in, 1)

        # VDDI Score: benchmark is 8.5 mph velo delta, 10.0 in IVB delta, 93.5 mph FB
        v_bonus = (v_delta - 8.5) * 3.8
        ivb_bonus = (ivb_delta - 10.0) * 2.8
        fb_bonus = (metrics.fastball_velo_mph - 93.5) * 1.8
        vddi = round(max(0.0, 100.0 + v_bonus + ivb_bonus + fb_bonus), 1)

        whiff_mult = round(1.0 + max(0.0, vddi - 100.0) / 300.0, 3)

        is_elite = vddi >= 115.0 and v_delta >= 9.5

        # Tiers
        if is_elite:
            tier = "ELITE_VELO_BAND_DISRUPTOR"
        elif metrics.fastball_velo_mph >= 98.0 and v_delta <= 6.0:
            tier = "TIGHT_BAND_POWER_PITCHER"
        elif vddi <= 85.0 or v_delta <= 4.5:
            tier = "DANGEROUS_FLAT_HOMOGENEOUS_ARSENAL"
        else:
            tier = "AVERAGE_ARSENAL_SEPARATION"

        return VeloDeltaEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            fb_ch_velo_delta_mph=v_delta,
            fb_ch_ivb_delta_in=ivb_delta,
            vddi_score=vddi,
            whiff_boost_multiplier=whiff_mult,
            separation_tier=tier,
            is_elite_disruptor=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Velo Delta Engine (VELO-DELTA-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherVeloDeltaEngine()
        disruptor = PitcherArsenalSeparationMetrics(
            "p1", "Logan Webb", 93.5, 82.5, 84.0, 78.0, 14.0, 1.5
        )
        flat_pitcher = PitcherArsenalSeparationMetrics(
            "p2", "Flat Pitcher", 90.0, 86.5, 85.0, 83.0, 12.0, 8.0
        )

        r_dis = engine.evaluate_separation(disruptor)
        r_fla = engine.evaluate_separation(flat_pitcher)

        if (
            r_dis.separation_tier == "ELITE_VELO_BAND_DISRUPTOR"
            and r_fla.separation_tier == "DANGEROUS_FLAT_HOMOGENEOUS_ARSENAL"
        ):
            checks.append(
                Check(
                    "velo delta engine",
                    True,
                    f"Velo delta verified (Webb VDDI: {r_dis.vddi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("velo delta engine", False, f"Unexpected velo delta output: {r_dis}, {r_fla}")
            )
    except Exception as exc:
        checks.append(Check("velo delta engine", False, str(exc)))
    return checks
