"""Batter First-Pitch Aggressiveness & Early-Count Ambush Engine (AMBUSH-01, ADR-205).

Provides 0-0 count decision making, first-pitch damage, and ambush surplus modeling:
1. First-Pitch Swing & Zone Selectivity (in-zone aggression vs chase discipline).
2. First-Pitch Ambush Value Index (FPAV score combining 0-0 SLG and selectivity).
3. First-Pitch Surplus Value (FPSV net runs produced from early-count damage).
4. Ambush Archetypes (Lethal Ambush Crusher, Passive First-Pitch Taker, Wild Hacker).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterAmbushMetrics:
    """Observed batter 0-0 count swing decisions, contact quality, and power production."""

    batter_id: str
    batter_name: str
    first_pitch_swing_pct: float = 32.0  # League average ~30.0%
    first_pitch_zone_swing_pct: float = 52.0
    first_pitch_chase_pct: float = 16.0
    first_pitch_hard_hit_pct: float = 44.0
    first_pitch_slugging: float = 0.580  # League average ~0.520
    first_pitch_pa_count: int = 500


@dataclasses.dataclass(frozen=True)
class AmbushEvaluationResult:
    """Evaluated early-count aggression, FPAV score, and ambush run production."""

    batter_name: str
    fpav_score: float  # First-Pitch Ambush Value Index (0 to 160)
    fpsv_runs_saved: float  # Net run production from early-count damage
    ambush_tier: str  # e.g. "LETHAL_FIRST_PITCH_AMBUSHER", "PASSIVE_FIRST_PITCH_TAKER"
    is_lethal_ambusher: bool


class BaseAmbushEngine(Protocol):
    """Polymorphic protocol for batter first-pitch ambush engines."""

    def evaluate_ambush(
        self,
        metrics: BatterAmbushMetrics,
    ) -> AmbushEvaluationResult:
        """Calculate FPAV index, FPSV runs, and ambush tier."""
        ...


class BatterAmbushEngine:
    """Calculates first-pitch damage, in-zone ambush efficiency, and run value (AMBUSH-01)."""

    def evaluate_ambush(
        self,
        metrics: BatterAmbushMetrics,
    ) -> AmbushEvaluationResult:
        """Compute FPAV score and early-count surplus run production."""
        # FPAV Score: benchmark is 0.520 SLG, 35.0% selectivity delta, 40.0% HardHit
        slg_bonus = (metrics.first_pitch_slugging - 0.520) * 58.0
        selectivity_delta = metrics.first_pitch_zone_swing_pct - metrics.first_pitch_chase_pct
        sel_bonus = (selectivity_delta - 35.0) * 1.2
        hh_bonus = (metrics.first_pitch_hard_hit_pct - 40.0) * 0.8
        fpav = round(max(0.0, 100.0 + slg_bonus + sel_bonus + hh_bonus), 1)

        # FPSV Runs Saved / Produced
        pas = max(1, metrics.first_pitch_pa_count)
        slg_surplus = metrics.first_pitch_slugging - 0.520
        # ~12% of PAs end on 0-0 contact or are heavily impacted
        fpsv = round(slg_surplus * (pas * 0.12) * 0.44, 2)

        is_lethal = (
            fpav >= 118.0
            and metrics.first_pitch_slugging >= 0.700
            and metrics.first_pitch_swing_pct >= 34.0
        )

        # Tiers
        if is_lethal:
            tier = "LETHAL_FIRST_PITCH_AMBUSHER"
        elif metrics.first_pitch_chase_pct >= 26.0:
            tier = "WILD_EARLY_COUNT_HACKER"
        elif metrics.first_pitch_swing_pct <= 18.0:
            tier = "PASSIVE_FIRST_PITCH_TAKER"
        else:
            tier = "AVERAGE_EARLY_COUNT_APPROACH"

        return AmbushEvaluationResult(
            batter_name=metrics.batter_name,
            fpav_score=fpav,
            fpsv_runs_saved=fpsv,
            ambush_tier=tier,
            is_lethal_ambusher=is_lethal,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Ambush Engine (AMBUSH-01)."""
    checks: list[Check] = []
    try:
        engine = BatterAmbushEngine()
        ambusher = BatterAmbushMetrics("b1", "Corey Seager", 44.0, 68.0, 12.0, 58.0, 0.850, 550)
        passive = BatterAmbushMetrics("b2", "Passive Taker", 14.0, 30.0, 8.0, 35.0, 0.460, 480)

        r_amb = engine.evaluate_ambush(ambusher)
        r_pas = engine.evaluate_ambush(passive)

        if (
            r_amb.ambush_tier == "LETHAL_FIRST_PITCH_AMBUSHER"
            and r_pas.ambush_tier == "PASSIVE_FIRST_PITCH_TAKER"
        ):
            checks.append(
                Check(
                    "ambush engine",
                    True,
                    f"Ambush verified (Seager FPAV: {r_amb.fpav_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("ambush engine", False, f"Unexpected ambush output: {r_amb}, {r_pas}")
            )
    except Exception as exc:
        checks.append(Check("ambush engine", False, str(exc)))
    return checks
