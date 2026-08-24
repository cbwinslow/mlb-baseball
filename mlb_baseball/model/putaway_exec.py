"""Pitcher Two-Strike Putaway Intent & Execution Engine (PUTAWAY-EXEC-01, ADR-212).

Provides two-strike zone command, chase inducement, and putaway execution modeling:
1. Two-Strike Putaway Execution Rating (TSPER score measuring shadow/chase targeting).
2. Putaway Surplus Value (PTSV net runs saved by avoiding heart mistakes and waste balls).
3. Command Archetypes (Surgical Two-Strike Sniper, Dangerous Heart Mistake, Waste Prone).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherPutawayExecutionMetrics:
    """Observed pitcher two-strike pitch location distribution across zone regions."""

    pitcher_id: str
    pitcher_name: str
    two_strike_shadow_pct: float = 38.0  # Borderline edge pitches (benchmark ~38.0%)
    two_strike_chase_pct: float = 28.0  # Competitive chase zone (benchmark ~28.0%)
    two_strike_heart_pct: float = 20.0  # Dangerous middle-zone pitches (benchmark ~20.0%)
    two_strike_waste_pct: float = 14.0  # Non-competitive waste pitches (benchmark ~14.0%)
    two_strike_pitch_count: int = 300


@dataclasses.dataclass(frozen=True)
class PutawayExecutionEvaluationResult:
    """Evaluated two-strike command execution, TSPER score, and run value."""

    pitcher_name: str
    tsper_score: float  # Two-Strike Putaway Execution Rating (0 to 160)
    ptsv_runs_saved: float  # Net defensive runs saved from optimal putaway targeting
    execution_tier: str  # e.g. "SURGICAL_TWO_STRIKE_SNIPER", "DANGEROUS_HEART_MISTAKE_PRONE"
    is_surgical_sniper: bool


class BasePutawayExecutionEngine(Protocol):
    """Polymorphic protocol for two-strike putaway execution engines."""

    def evaluate_putaway_execution(
        self,
        metrics: PitcherPutawayExecutionMetrics,
    ) -> PutawayExecutionEvaluationResult:
        """Calculate TSPER score, PTSV runs, and command tier."""
        ...


class PitcherPutawayExecutionEngine:
    """Calculates two-strike zone command, chase inducement, and run value (PUTAWAY-EXEC-01)."""

    def evaluate_putaway_execution(
        self,
        metrics: PitcherPutawayExecutionMetrics,
    ) -> PutawayExecutionEvaluationResult:
        """Compute TSPER rating and defensive run savings."""
        # Whiff intent = Shadow% + Chase% (benchmark 66.0%)
        whiff_intent = metrics.two_strike_shadow_pct + metrics.two_strike_chase_pct
        intent_bonus = (whiff_intent - 66.0) * 2.4

        # Penalties: Heart mistakes are heavily punished, waste pitches extend counts
        heart_penalty = (metrics.two_strike_heart_pct - 20.0) * 3.2
        waste_penalty = max(0.0, metrics.two_strike_waste_pct - 14.0) * 1.5

        tsper = round(max(0.0, 100.0 + intent_bonus - heart_penalty - waste_penalty), 1)

        # Runs saved: optimal command avoids damage and secures strikeouts (~0.0028 runs/pitch)
        pitches = max(1, metrics.two_strike_pitch_count)
        ptsv = round((tsper - 100.0) * (pitches * 0.0028), 2)

        is_sniper = (
            tsper >= 118.0
            and metrics.two_strike_heart_pct <= 15.0
            and metrics.two_strike_chase_pct >= 32.0
        )

        # Tiers
        if is_sniper:
            tier = "SURGICAL_TWO_STRIKE_SNIPER"
        elif metrics.two_strike_heart_pct >= 24.0:
            tier = "DANGEROUS_HEART_MISTAKE_PRONE"
        elif metrics.two_strike_waste_pct >= 20.0:
            tier = "WASTE_PRONE_COUNT_EXTENDER"
        else:
            tier = "AVERAGE_PUTAWAY_EXECUTION"

        return PutawayExecutionEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            tsper_score=tsper,
            ptsv_runs_saved=ptsv,
            execution_tier=tier,
            is_surgical_sniper=is_sniper,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Putaway Execution Engine (PUTAWAY-EXEC-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherPutawayExecutionEngine()
        sniper = PitcherPutawayExecutionMetrics("p1", "Gerrit Cole", 44.0, 36.0, 12.0, 8.0, 380)
        mistake = PitcherPutawayExecutionMetrics(
            "p2", "Mistake Pitcher", 32.0, 22.0, 28.0, 18.0, 250
        )

        r_sni = engine.evaluate_putaway_execution(sniper)
        r_mis = engine.evaluate_putaway_execution(mistake)

        if (
            r_sni.execution_tier == "SURGICAL_TWO_STRIKE_SNIPER"
            and r_mis.execution_tier == "DANGEROUS_HEART_MISTAKE_PRONE"
        ):
            checks.append(
                Check(
                    "putaway exec engine",
                    True,
                    f"Putaway Exec verified (Cole TSPER: {r_sni.tsper_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "putaway exec engine",
                    False,
                    f"Unexpected putaway exec output: {r_sni}, {r_mis}",
                )
            )
    except Exception as exc:
        checks.append(Check("putaway exec engine", False, str(exc)))
    return checks
