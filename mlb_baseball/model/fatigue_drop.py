"""Pitcher Arm Fatigue Velocity Decay & Release Height Drop Engine (FATIGUE-DROP-01, ADR-236).

Provides pitch-count velocity cliff decay, vertical arm slot collapse, and PAFII rating:
1. Pitcher Arm Fatigue Inefficiency Index (PAFII score measuring endurance maintenance).
2. High-Fatigue Vulnerability Runs Saved (HFVRS runs saved in late innings).
3. Fatigue Archetypes (Steel Arm Workhorse Endurer, Severe Fatigue Arm Collapser).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherFatigueDropMetrics:
    """Observed pitcher velocity drop mph, release height drop in, and strike % past pitch 75."""

    pitcher_id: str
    pitcher_name: str
    late_game_velo_drop_mph: float = 1.5  # Velo decay in pitches 75+ (benchmark ~1.5 mph)
    late_game_rel_drop_in: float = 1.8  # Release Z drop in inches (benchmark ~1.8 in)
    late_game_strike_pct: float = 61.0  # Strike % in pitches 75+ (benchmark ~61.0%)
    pitches_thrown_over_75: int = 150


@dataclasses.dataclass(frozen=True)
class FatigueDropEvaluationResult:
    """Evaluated arm fatigue score, late-inning runs saved, and endurance tier."""

    pitcher_name: str
    pafii_score: float  # Pitcher Arm Fatigue Inefficiency Index (0 to 160)
    hfvrs_runs_saved: float  # Net defensive runs saved by sustaining late velocity & arm slot
    fatigue_tier: str  # e.g. "STEEL_ARM_WORKHORSE_ENDURER", "SEVERE_FATIGUE_ARM_COLLAPSER"
    is_steel_arm_workhorse: bool


class BaseFatigueDropEngine(Protocol):
    """Polymorphic protocol for pitcher arm fatigue engines."""

    def evaluate_fatigue_drop(
        self,
        metrics: PitcherFatigueDropMetrics,
    ) -> FatigueDropEvaluationResult:
        """Calculate PAFII score, HFVRS runs, and endurance tier."""
        ...


class PitcherFatigueDropEngine:
    """Calculates late velocity preservation, arm slot maintenance, and PAFII (FATIGUE-DROP-01)."""

    def evaluate_fatigue_drop(
        self,
        metrics: PitcherFatigueDropMetrics,
    ) -> FatigueDropEvaluationResult:
        """Compute PAFII rating and high-fatigue runs saved."""
        # PAFII Score: benchmark 1.5 mph drop, 1.8 in rel drop, 61.0% strike
        velo_saving = (1.5 - metrics.late_game_velo_drop_mph) * 12.0
        rel_saving = (1.8 - metrics.late_game_rel_drop_in) * 8.0
        strike_bonus = (metrics.late_game_strike_pct - 61.0) * 1.5
        pafii = round(max(0.0, 100.0 + velo_saving + rel_saving + strike_bonus), 1)

        # HFVRS Runs (~0.0028 runs per pitch 75+ per point above 100)
        pitches = max(1, metrics.pitches_thrown_over_75)
        runs = round((pafii - 100.0) * (pitches * 0.0028), 2)

        is_workhorse = (
            pafii >= 116.0
            and metrics.late_game_velo_drop_mph <= 0.8
            and metrics.late_game_rel_drop_in <= 0.8
        )

        # Tiers
        if is_workhorse:
            tier = "STEEL_ARM_WORKHORSE_ENDURER"
        elif metrics.late_game_velo_drop_mph >= 2.4 or metrics.late_game_rel_drop_in >= 2.8:
            tier = "SEVERE_FATIGUE_ARM_COLLAPSER"
        elif metrics.late_game_velo_drop_mph <= 1.1:
            tier = "SOLID_DEEP_GAME_ENDURER"
        else:
            tier = "AVERAGE_FATIGUE_PROFILE"

        return FatigueDropEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            pafii_score=pafii,
            hfvrs_runs_saved=runs,
            fatigue_tier=tier,
            is_steel_arm_workhorse=is_workhorse,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Fatigue Drop Engine (FATIGUE-DROP-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherFatigueDropEngine()
        workhorse = PitcherFatigueDropMetrics("p1", "Zack Wheeler", 0.5, 0.4, 66.5, 200)
        collapser = PitcherFatigueDropMetrics("p2", "Fatigued Pitcher", 2.8, 3.2, 54.0, 120)

        r_wor = engine.evaluate_fatigue_drop(workhorse)
        r_col = engine.evaluate_fatigue_drop(collapser)

        if (
            r_wor.fatigue_tier == "STEEL_ARM_WORKHORSE_ENDURER"
            and r_col.fatigue_tier == "SEVERE_FATIGUE_ARM_COLLAPSER"
        ):
            checks.append(
                Check(
                    "fatigue drop engine",
                    True,
                    f"Fatigue Drop verified (Wheeler PAFII: {r_wor.pafii_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "fatigue drop engine",
                    False,
                    f"Unexpected fatigue drop output: {r_wor}, {r_col}",
                )
            )
    except Exception as exc:
        checks.append(Check("fatigue drop engine", False, str(exc)))
    return checks
