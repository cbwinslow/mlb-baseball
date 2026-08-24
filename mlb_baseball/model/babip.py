"""Batter BABIP Expected Luck Deficit & Regression Scanner (BABIP-LUCK-01, ADR-179).

Provides batted ball trajectory modeling, expected BABIP (xBABIP), and luck deficit evaluation:
1. Trajectory-Based Expected BABIP (xBABIP from Line Drive%, Hard-Hit%, Sprint Speed, and IFFB%).
2. BABIP Luck Deficit (Actual BABIP - Expected xBABIP).
3. Positive and Negative Regression Candidate Identification (Buy-Low vs Sell-High).
4. Regression Tiers (Severe Positive Regression, Fair Value Neutral, Severe Negative Regression).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterBABIPInputs:
    """Observed BABIP and trajectory distribution inputs for a batter."""

    batter_id: str
    batter_name: str
    actual_babip: float = 0.310
    ld_pct: float = 0.21  # Line drive rate
    gb_pct: float = 0.44  # Ground ball rate
    fb_pct: float = 0.35  # Fly ball rate
    hard_hit_pct: float = 0.40  # Exit velo >= 95 mph
    sprint_speed_fps: float = 27.2  # Statcast sprint speed in ft/s
    iffb_pct: float = 0.08  # Infield fly ball % of FB


@dataclasses.dataclass(frozen=True)
class BABIPEvaluationResult:
    """Evaluated expected xBABIP, luck delta, and regression classification."""

    batter_name: str
    actual_babip: float
    expected_xbabip: float
    babip_luck_delta: float  # Actual BABIP - Expected xBABIP
    regression_tier: str  # e.g. "SEVERE_POSITIVE_REGRESSION", "FAIR_VALUE_NEUTRAL"
    is_buy_low_candidate: bool


class BaseBABIPEngine(Protocol):
    """Polymorphic protocol for BABIP regression engines."""

    def evaluate_babip(
        self,
        inputs: BatterBABIPInputs,
    ) -> BABIPEvaluationResult:
        """Calculate expected xBABIP and luck delta."""
        ...


class BABIPRegressionEngine:
    """Calculates expected xBABIP and regression candidate tiers (BABIP-LUCK-01)."""

    def evaluate_babip(
        self,
        inputs: BatterBABIPInputs,
    ) -> BABIPEvaluationResult:
        """Compute trajectory xBABIP and luck deficit."""
        # 1. Expected xBABIP Model
        # Baseline ~ 0.220 + 0.380*LD + 0.120*HardHit + 0.006*(Speed - 27.0) - 0.140*IFFB + 0.040*GB
        speed_delta = inputs.sprint_speed_fps - 27.0
        xbabip = (
            0.220
            + 0.380 * inputs.ld_pct
            + 0.120 * inputs.hard_hit_pct
            + 0.006 * speed_delta
            - 0.140 * inputs.iffb_pct
            + 0.040 * inputs.gb_pct
        )
        xbabip = round(xbabip, 3)

        # 2. Luck Delta
        delta = round(inputs.actual_babip - xbabip, 3)

        # 3. Regression Tiers
        if delta <= -0.045:
            tier = "SEVERE_POSITIVE_REGRESSION"
            buy_low = True
        elif delta <= -0.020:
            tier = "MODERATE_UNDERPERFORMER"
            buy_low = True
        elif delta >= 0.045:
            tier = "SEVERE_NEGATIVE_REGRESSION"
            buy_low = False
        elif delta >= 0.020:
            tier = "MODERATE_OVERPERFORMER"
            buy_low = False
        else:
            tier = "FAIR_VALUE_NEUTRAL"
            buy_low = False

        return BABIPEvaluationResult(
            batter_name=inputs.batter_name,
            actual_babip=inputs.actual_babip,
            expected_xbabip=xbabip,
            babip_luck_delta=delta,
            regression_tier=tier,
            is_buy_low_candidate=buy_low,
        )


def health_check() -> list[Check]:
    """Operational health check for BABIP Regression Engine (BABIP-LUCK-01)."""
    checks: list[Check] = []
    try:
        engine = BABIPRegressionEngine()
        unlucky = BatterBABIPInputs(
            "b1",
            "Unlucky Slugger",
            actual_babip=0.235,
            ld_pct=0.24,
            hard_hit_pct=0.48,
            sprint_speed_fps=28.5,
            iffb_pct=0.04,
        )
        lucky = BatterBABIPInputs(
            "b2",
            "Lucky Blooper",
            actual_babip=0.385,
            ld_pct=0.16,
            hard_hit_pct=0.28,
            sprint_speed_fps=25.5,
            iffb_pct=0.14,
        )

        r_un = engine.evaluate_babip(unlucky)
        r_lu = engine.evaluate_babip(lucky)

        if (
            r_un.regression_tier == "SEVERE_POSITIVE_REGRESSION"
            and r_lu.regression_tier == "SEVERE_NEGATIVE_REGRESSION"
        ):
            checks.append(
                Check(
                    "babip luck engine",
                    True,
                    f"BABIP verified (Delta: {r_un.babip_luck_delta:>+5.3f})",
                )
            )
        else:
            checks.append(
                Check("babip luck engine", False, f"Unexpected BABIP output: {r_un}, {r_lu}")
            )
    except Exception as exc:
        checks.append(Check("babip luck engine", False, str(exc)))
    return checks
