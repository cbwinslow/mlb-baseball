"""Defensive Outfield Catch Probability & Distance/Opportunity Engine (CATCH-PROB-01, ADR-189).

Provides opportunity distance, hang time, directional difficulty, and 5-Star catch modeling:
1. Statcast 5-Star Catch Probability (Logistic function of distance, hang time, and chase angle).
2. Directional Angle Penalty (retreating over head vs charging straight in).
3. Outs Above Average (OAA added on each individual fielding opportunity).
4. Statcast Star Classifications (5-Star: <=25%, 4-Star: 26-50%, 3-Star: 51-75%, Routine: >95%).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfieldPlayOpportunity:
    """Flight and spatial positioning parameters for an outfield fly ball opportunity."""

    fielder_id: str
    fielder_name: str
    position: str = "CF"
    distance_needed_ft: float = 65.0
    hang_time_s: float = 4.2
    direction_angle_deg: float = 90.0  # 0° = charging in, 90° = lateral, 180° = back over head
    sprint_speed_fps: float = 28.5
    was_caught: bool = True


@dataclasses.dataclass(frozen=True)
class CatchProbEvaluationResult:
    """Evaluated catch probability, star rating, and OAA added for the play."""

    fielder_name: str
    catch_probability_pct: float
    star_rating: str  # "5_STAR", "4_STAR", "3_STAR", "2_STAR", "1_STAR", "ROUTINE"
    oaa_added: float  # (1.0 - CatchProb/100) if caught, else (-CatchProb/100)
    was_caught: bool
    is_highlight_catch: bool


class BaseCatchProbEngine(Protocol):
    """Polymorphic protocol for outfield catch probability engines."""

    def evaluate_opportunity(
        self,
        opportunity: OutfieldPlayOpportunity,
    ) -> CatchProbEvaluationResult:
        """Calculate catch probability and OAA impact."""
        ...


class OutfieldCatchProbEngine:
    """Calculates Statcast 5-Star catch probabilities and OAA fielding credit (CATCH-PROB-01)."""

    def evaluate_opportunity(
        self,
        opportunity: OutfieldPlayOpportunity,
    ) -> CatchProbEvaluationResult:
        """Compute logistic catch probability, star rating, and OAA."""
        hang_t = max(0.5, opportunity.hang_time_s)
        angle_pen = (opportunity.direction_angle_deg / 180.0) * 0.70
        eff_speed = max(15.0, opportunity.sprint_speed_fps * 0.92)
        time_needed = 0.60 + (opportunity.distance_needed_ft / eff_speed) + angle_pen
        delta_t = hang_t - time_needed

        # Logistic curve based on arrival margin delta_t
        z = delta_t * 6.5
        prob = 1.0 / (1.0 + math.exp(-z))
        prob_pct = round(prob * 100.0, 1)

        # Star Rating
        if prob_pct <= 25.0:
            star = "5_STAR"
        elif prob_pct <= 50.0:
            star = "4_STAR"
        elif prob_pct <= 75.0:
            star = "3_STAR"
        elif prob_pct <= 90.0:
            star = "2_STAR"
        elif prob_pct <= 95.0:
            star = "1_STAR"
        else:
            star = "ROUTINE"

        # OAA Added
        if opportunity.was_caught:
            oaa = round(1.0 - (prob_pct / 100.0), 3)
        else:
            oaa = round(-(prob_pct / 100.0), 3)

        highlight = opportunity.was_caught and star in ("5_STAR", "4_STAR")

        return CatchProbEvaluationResult(
            fielder_name=opportunity.fielder_name,
            catch_probability_pct=prob_pct,
            star_rating=star,
            oaa_added=oaa,
            was_caught=opportunity.was_caught,
            is_highlight_catch=highlight,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfield Catch Probability Engine (CATCH-PROB-01)."""
    checks: list[Check] = []
    try:
        engine = OutfieldCatchProbEngine()
        five_star = OutfieldPlayOpportunity(
            "f1", "Kevin Kiermaier", "CF", 82.0, 4.0, 160.0, 29.5, True
        )
        routine = OutfieldPlayOpportunity("f2", "Routine Play", "LF", 30.0, 4.8, 20.0, 27.0, True)

        r_5s = engine.evaluate_opportunity(five_star)
        r_ro = engine.evaluate_opportunity(routine)

        if r_5s.star_rating == "5_STAR" and r_ro.star_rating == "ROUTINE":
            checks.append(
                Check(
                    "catch probability engine",
                    True,
                    f"Catch prob verified (5-Star Prob: {r_5s.catch_probability_pct:.1f}%)",
                )
            )
        else:
            checks.append(
                Check(
                    "catch probability engine",
                    False,
                    f"Unexpected catch prob output: {r_5s}, {r_ro}",
                )
            )
    except Exception as exc:
        checks.append(Check("catch probability engine", False, str(exc)))
    return checks
