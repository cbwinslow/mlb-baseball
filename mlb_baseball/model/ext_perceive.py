"""Pitcher Release Extension vs Effective Velocity Engine (EXT-PERCEIVE-01, ADR-215).

Provides release extension kinematics, perceived velocity boost, and reaction time compression:
1. Effective Perceived Velocity (v_eff = v_radar + (ext - 6.0) * 0.72 mph).
2. Batter Reaction Time Compression (delta_t in milliseconds from shortened ball flight).
3. Effective Velocity Extension Rating (EVER score & perceived whiff boost multiplier).
4. Extension Archetypes (Elite Long Extension Deceiver, Compact Short Extension Penalized).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherExtensionKinematicsMetrics:
    """Observed pitcher release extension depth, radar velocity, and release height."""

    pitcher_id: str
    pitcher_name: str
    extension_ft: float = 6.4  # Release distance from rubber (benchmark ~6.4 ft)
    radar_velocity_mph: float = 94.0
    induced_vert_break_in: float = 16.5
    release_z_ft: float = 5.85
    pitch_count_evaluated: int = 200


@dataclasses.dataclass(frozen=True)
class ExtPerceiveEvaluationResult:
    """Evaluated effective velocity, reaction time compression, EVER score, and whiff boost."""

    pitcher_name: str
    effective_velocity_mph: float  # Radar velo + extension boost
    reaction_time_compression_ms: float  # Reaction time shortened in ms
    ever_score: float  # Effective Velocity Extension Rating (0 to 160)
    whiff_boost_multiplier: float  # Perceived velocity whiff boost (1.00x to 1.35x)
    extension_tier: str  # e.g. "ELITE_LONG_EXTENSION_DECEIVER", "COMPACT_SHORT_EXTENSION"
    is_elite_deceiver: bool


class BaseExtPerceiveEngine(Protocol):
    """Polymorphic protocol for extension perceived velocity engines."""

    def evaluate_extension(
        self,
        metrics: PitcherExtensionKinematicsMetrics,
    ) -> ExtPerceiveEvaluationResult:
        """Calculate effective velocity, reaction compression, and EVER score."""
        ...


class PitcherExtPerceiveEngine:
    """Calculates release extension velocity boosts and EVER rating (EXT-PERCEIVE-01)."""

    def evaluate_extension(
        self,
        metrics: PitcherExtensionKinematicsMetrics,
    ) -> ExtPerceiveEvaluationResult:
        """Compute effective velocity and reaction window compression."""
        # Effective Velocity: 0.72 mph added per foot of extension above 6.0 ft baseline
        v_eff = round(metrics.radar_velocity_mph + (metrics.extension_ft - 6.0) * 0.72, 2)

        # Reaction time compression: flight time reduction in ms
        fps = metrics.radar_velocity_mph * 1.467
        # Distance shortened relative to 6.4 ft benchmark
        dt_ms = round(((metrics.extension_ft - 6.4) / fps) * 1000.0, 1)

        # EVER Score: benchmark 6.4 ft ext, 93.5 mph v_eff, 16.0 in IVB
        ext_bonus = (metrics.extension_ft - 6.4) * 28.0
        veff_bonus = (v_eff - 93.5) * 2.2
        ivb_bonus = (metrics.induced_vert_break_in - 16.0) * 1.4
        ever = round(max(0.0, 100.0 + ext_bonus + veff_bonus + ivb_bonus), 1)

        whiff_mult = round(1.0 + max(0.0, ever - 100.0) / 260.0, 3)

        is_deceiver = (
            metrics.extension_ft >= 7.05
            and ever >= 116.0
            and (v_eff - metrics.radar_velocity_mph) >= 0.75
        )

        # Tiers
        if is_deceiver:
            tier = "ELITE_LONG_EXTENSION_DECEIVER"
        elif metrics.extension_ft <= 5.75:
            tier = "COMPACT_SHORT_EXTENSION_PENALIZED"
        elif metrics.radar_velocity_mph >= 97.0:
            tier = "POWER_VELO_AVERAGE_EXTENSION"
        else:
            tier = "AVERAGE_EXTENSION_DELIVERY"

        return ExtPerceiveEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            effective_velocity_mph=v_eff,
            reaction_time_compression_ms=dt_ms,
            ever_score=ever,
            whiff_boost_multiplier=whiff_mult,
            extension_tier=tier,
            is_elite_deceiver=is_deceiver,
        )


def health_check() -> list[Check]:
    """Operational health check for Extension Perceived Velocity Engine (EXT-PERCEIVE-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherExtPerceiveEngine()
        deceiver = PitcherExtensionKinematicsMetrics(
            "p1", "Logan Gilbert", 7.4, 96.0, 18.0, 5.8, 220
        )
        compact = PitcherExtensionKinematicsMetrics(
            "p2", "Compact Delivery", 5.5, 93.0, 15.0, 5.9, 180
        )

        r_dec = engine.evaluate_extension(deceiver)
        r_com = engine.evaluate_extension(compact)

        if (
            r_dec.extension_tier == "ELITE_LONG_EXTENSION_DECEIVER"
            and r_com.extension_tier == "COMPACT_SHORT_EXTENSION_PENALIZED"
        ):
            checks.append(
                Check(
                    "ext perceive engine",
                    True,
                    f"Ext Perceive verified (Gilbert v_eff: {r_dec.effective_velocity_mph:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "ext perceive engine",
                    False,
                    f"Unexpected ext perceive output: {r_dec}, {r_com}",
                )
            )
    except Exception as exc:
        checks.append(Check("ext perceive engine", False, str(exc)))
    return checks
