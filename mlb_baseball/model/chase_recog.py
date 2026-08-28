"""Batter Breaking Ball Chase Recognition Engine (CHASE-RECOG-01, ADR-247).

Provides breaking ball out-of-zone take discipline, chase avoidance, and BBCRI index:
1. Breaking Ball Chase Recognition Index (BBCRI score measuring chase discipline).
2. Chase Discipline Runs (CDRA net offensive runs produced through pitch selection).
3. Discipline Archetypes (Elite Breaking Ball Hawk, Free Swinging Slider Bait).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterChaseRecogMetrics:
    """Observed out-of-zone breaking ball chase %, take %, and waste whiff %."""

    batter_id: str
    batter_name: str
    breaking_ball_chase_pct: float = 32.0  # O-Swing % on breaking pitches (benchmark ~32.0%)
    breaking_ball_take_correct_pct: float = 68.0  # Correct ball take % (benchmark ~68.0%)
    breaking_ball_waste_whiff_pct: float = 58.0  # Whiff % on chase swings (benchmark ~58.0%)
    out_of_zone_breaking_pitches: int = 200


@dataclasses.dataclass(frozen=True)
class ChaseRecogEvaluationResult:
    """Evaluated breaking ball recognition score, run value, and discipline tier."""

    batter_name: str
    bbcri_score: float  # Breaking Ball Chase Recognition Index (0 to 160)
    cdra_runs_produced: float  # Net offensive runs produced via chase discipline
    recognition_tier: (
        str  # e.g. "ELITE_BREAKING_BALL_DISCIPLINE_HAWK", "FREE_SWINGING_SLIDER_BAIT_LIABILITY"
    )
    is_discipline_hawk: bool


class BaseChaseRecogEngine(Protocol):
    """Polymorphic protocol for breaking ball chase recognition engines."""

    def evaluate_chase_recog(
        self,
        metrics: BatterChaseRecogMetrics,
    ) -> ChaseRecogEvaluationResult:
        """Calculate BBCRI rating, CDRA runs, and tier."""
        ...


class BatterChaseRecogEngine:
    """Calculates out-of-zone breaking ball chase discipline, take %, and BBCRI (CHASE-RECOG-01)."""

    def evaluate_chase_recog(
        self,
        metrics: BatterChaseRecogMetrics,
    ) -> ChaseRecogEvaluationResult:
        """Compute BBCRI score and net offensive runs produced."""
        # BBCRI Score: benchmark 32.0% chase, 68.0% take, 58.0% whiff
        chase_saving = (32.0 - metrics.breaking_ball_chase_pct) * 2.2
        take_bonus = (metrics.breaking_ball_take_correct_pct - 68.0) * 1.6
        whiff_saving = (58.0 - metrics.breaking_ball_waste_whiff_pct) * 0.8
        bbcri = round(max(0.0, 100.0 + chase_saving + take_bonus + whiff_saving), 1)

        # CDRA Runs (~0.0022 runs per pitch per point above 100)
        pitches = max(1, metrics.out_of_zone_breaking_pitches)
        runs = round((bbcri - 100.0) * (pitches * 0.0022), 2)

        is_hawk = (
            bbcri >= 116.0
            and metrics.breaking_ball_chase_pct <= 22.0
            and metrics.breaking_ball_take_correct_pct >= 78.0
        )

        # Tiers
        if is_hawk:
            tier = "ELITE_BREAKING_BALL_DISCIPLINE_HAWK"
        elif (
            metrics.breaking_ball_chase_pct >= 42.0
            or metrics.breaking_ball_take_correct_pct <= 58.0
        ):
            tier = "FREE_SWINGING_SLIDER_BAIT_LIABILITY"
        elif metrics.breaking_ball_chase_pct <= 27.0:
            tier = "SOLID_DISCIPLINED_TAKER"
        else:
            tier = "AVERAGE_CHASE_RECOGNITION"

        return ChaseRecogEvaluationResult(
            batter_name=metrics.batter_name,
            bbcri_score=bbcri,
            cdra_runs_produced=runs,
            recognition_tier=tier,
            is_discipline_hawk=is_hawk,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Chase Recog Engine (CHASE-RECOG-01)."""
    checks: list[Check] = []
    try:
        engine = BatterChaseRecogEngine()
        hawk = BatterChaseRecogMetrics("b1", "Juan Soto", 16.0, 84.0, 36.0, 300)
        bait = BatterChaseRecogMetrics("b2", "Slider Bait", 46.0, 54.0, 68.0, 200)

        r_hwk = engine.evaluate_chase_recog(hawk)
        r_bai = engine.evaluate_chase_recog(bait)

        if (
            r_hwk.recognition_tier == "ELITE_BREAKING_BALL_DISCIPLINE_HAWK"
            and r_bai.recognition_tier == "FREE_SWINGING_SLIDER_BAIT_LIABILITY"
        ):
            checks.append(
                Check(
                    "chase recog engine",
                    True,
                    f"Chase Recog verified (Soto BBCRI: {r_hwk.bbcri_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "chase recog engine",
                    False,
                    f"Unexpected chase recog output: {r_hwk}, {r_bai}",
                )
            )
    except Exception as exc:
        checks.append(Check("chase recog engine", False, str(exc)))
    return checks
