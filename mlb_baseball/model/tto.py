"""Starting Pitcher Times-Through-the-Order (TTO) Degradation Engine (TTO-01, ADR-164).

Provides starter lineup turnover degradation modeling and third-time penalty optimization:
1. Multi-Pass Lineup wOBA and Strikeout Rate Degradation Tracking (1st, 2nd, 3rd TTO).
2. Third-Time Vulnerability Index (TTVI) quantifying familiarity and fatigue penalty.
3. Managerial Starter Hook Cutoff Rules (Strict 2-Time Hook, Moderate Leash, Workhorse Ace).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherTTOMetrics:
    """Observed times-through-the-order split metrics for a starting pitcher."""

    pitcher_id: str
    pitcher_name: str
    tto1_woba: float = 0.290  # Batters 1-9
    tto2_woba: float = 0.315  # Batters 10-18
    tto3_woba: float = 0.355  # Batters 19-27
    tto1_k_pct: float = 0.27
    tto3_k_pct: float = 0.19


@dataclasses.dataclass(frozen=True)
class TTOEvaluationResult:
    """Evaluated times-through-the-order penalty and managerial hook policy."""

    pitcher_name: str
    tto_woba_delta_3_1: float  # TTO3 wOBA - TTO1 wOBA
    tto_k_delta_3_1: float  # TTO3 K% - TTO1 K%
    third_time_vulnerability_index: float  # 0 to 100
    recommended_hook_policy: str  # "STRICT_2_TIME_HOOK", "MODERATE_LEASH", "WORKHORSE_ACE"


class BaseTTOEngine(Protocol):
    """Polymorphic protocol for times-through-the-order engines."""

    def evaluate_tto(
        self,
        metrics: PitcherTTOMetrics,
    ) -> TTOEvaluationResult:
        """Calculate TTO degradation deltas and hook recommendation."""
        ...


class TimesThroughOrderEngine:
    """Calculates starter familiarity degradation and optimal hook policy (TTO-01)."""

    def evaluate_tto(
        self,
        metrics: PitcherTTOMetrics,
    ) -> TTOEvaluationResult:
        """Compute TTO wOBA delta, K drop, and Third-Time Vulnerability Index."""
        delta_woba = round(metrics.tto3_woba - metrics.tto1_woba, 3)
        delta_k = round(metrics.tto3_k_pct - metrics.tto1_k_pct, 3)

        # 1. Third-Time Vulnerability Index (TTVI) (0 to 100):
        # League average delta_woba is ~ +0.040, delta_k is ~ -0.050
        woba_comp = max(0.0, delta_woba / 0.040) * 40.0
        k_comp = max(0.0, -delta_k) * 160.0
        ttvi = round(float(np.clip(woba_comp + k_comp, 0.0, 100.0)), 1)

        # 2. Hook Policy
        if ttvi >= 62.0 or delta_woba >= 0.060:
            hook = "STRICT_2_TIME_HOOK"
        elif ttvi >= 35.0:
            hook = "MODERATE_LEASH"
        else:
            hook = "WORKHORSE_ACE"

        return TTOEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            tto_woba_delta_3_1=delta_woba,
            tto_k_delta_3_1=delta_k,
            third_time_vulnerability_index=ttvi,
            recommended_hook_policy=hook,
        )


def health_check() -> list[Check]:
    """Operational health check for the TTO Degradation Engine (TTO-01)."""
    checks: list[Check] = []
    try:
        engine = TimesThroughOrderEngine()
        ace = PitcherTTOMetrics(
            "p1",
            "Ace Workhorse",
            tto1_woba=0.280,
            tto2_woba=0.290,
            tto3_woba=0.300,
            tto1_k_pct=0.30,
            tto3_k_pct=0.28,
        )
        two_time = PitcherTTOMetrics(
            "p2",
            "Two-Time Specialist",
            tto1_woba=0.270,
            tto2_woba=0.300,
            tto3_woba=0.365,
            tto1_k_pct=0.29,
            tto3_k_pct=0.17,
        )

        r_ace = engine.evaluate_tto(ace)
        r_two = engine.evaluate_tto(two_time)

        if (
            r_ace.recommended_hook_policy == "WORKHORSE_ACE"
            and r_two.recommended_hook_policy == "STRICT_2_TIME_HOOK"
        ):
            checks.append(
                Check(
                    "tto degradation engine",
                    True,
                    f"TTO verified (TTVI: {r_two.third_time_vulnerability_index:.1f})",
                )
            )
        else:
            checks.append(
                Check("tto degradation engine", False, f"Unexpected TTO output: {r_ace}, {r_two}")
            )
    except Exception as exc:
        checks.append(Check("tto degradation engine", False, str(exc)))
    return checks
