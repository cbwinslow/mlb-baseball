"""Pitcher Two-Strike Putaway Intent vs Heart Leakage Engine (INTENT-LEAK-01, ADR-228).

Provides two-strike chase zone expansion, middle-middle heart mistake leakage, and run value:
1. Two-Strike Putaway Intent Execution Index (TSPIEI score measuring waste precision).
2. Heart-Zone Putaway Catastrophe Runs (HPCR runs prevented by eliminating 2-strike meatballs).
3. Intent Archetypes (Surgical Putaway Command Sniper, Fatal Two-Strike Meatball Leaker).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherPutawayIntentMetrics:
    """Observed pitcher two-strike chase intent, heart mistake rate, and strikeout conversion."""

    pitcher_id: str
    pitcher_name: str
    chase_dirt_intent_pct: float = 52.0  # % in chase/dirt on 2 strikes (benchmark ~52.0%)
    heart_zone_leak_pct: float = 19.0  # % leaked into heart zone on 2 strikes (benchmark ~19.0%)
    two_strike_k_pct: float = 38.0  # 2-strike strikeout % (benchmark ~38.0%)
    two_strike_pitches_count: int = 400


@dataclasses.dataclass(frozen=True)
class IntentLeakEvaluationResult:
    """Evaluated putaway intent score, mistake runs prevented, and command tier."""

    pitcher_name: str
    tspiei_score: float  # Two-Strike Putaway Intent Execution Index (0 to 160)
    hpcr_runs_prevented: float  # Net defensive runs saved by avoiding heart mistakes
    intent_tier: str  # e.g. "SURGICAL_PUTAWAY_COMMAND_SNIPER", "FATAL_TWO_STRIKE_MEATBALL_LEAKER"
    is_surgical_sniper: bool


class BaseIntentLeakEngine(Protocol):
    """Polymorphic protocol for two-strike intent leakage engines."""

    def evaluate_intent_leak(
        self,
        metrics: PitcherPutawayIntentMetrics,
    ) -> IntentLeakEvaluationResult:
        """Calculate TSPIEI rating, HPCR runs, and intent tier."""
        ...


class PitcherIntentLeakEngine:
    """Calculates two-strike chase expansion and heart avoidance TSPIEI (INTENT-LEAK-01)."""

    def evaluate_intent_leak(
        self,
        metrics: PitcherPutawayIntentMetrics,
    ) -> IntentLeakEvaluationResult:
        """Compute TSPIEI score and heart leak catastrophe runs saved."""
        # TSPIEI Score: benchmark 52.0% chase, 19.0% heart, 38.0% K%
        chase_bonus = (metrics.chase_dirt_intent_pct - 52.0) * 1.8
        heart_saving = (19.0 - metrics.heart_zone_leak_pct) * 3.2
        k_bonus = (metrics.two_strike_k_pct - 38.0) * 1.4
        tspiei = round(max(0.0, 100.0 + chase_bonus + heart_saving + k_bonus), 1)

        # HPCR Runs Prevented (~0.28 runs saved per avoided 2-strike heart meatball)
        pitches = max(1, metrics.two_strike_pitches_count)
        mistake_delta = ((19.0 - metrics.heart_zone_leak_pct) / 100.0) * pitches
        hpcr_runs = round(mistake_delta * 0.28, 2)

        is_sniper = (
            tspiei >= 116.0
            and metrics.heart_zone_leak_pct <= 12.0
            and metrics.chase_dirt_intent_pct >= 58.0
        )

        # Tiers
        if is_sniper:
            tier = "SURGICAL_PUTAWAY_COMMAND_SNIPER"
        elif metrics.heart_zone_leak_pct >= 26.0 and metrics.two_strike_k_pct <= 32.0:
            tier = "FATAL_TWO_STRIKE_MEATBALL_LEAKER"
        elif metrics.chase_dirt_intent_pct >= 72.0 and metrics.two_strike_k_pct <= 32.0:
            tier = "ERRATIC_WILD_WASTER"
        elif metrics.heart_zone_leak_pct <= 14.0:
            tier = "SOLID_PUTAWAY_EXECUTOR"
        else:
            tier = "AVERAGE_PUTAWAY_COMMAND"

        return IntentLeakEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            tspiei_score=tspiei,
            hpcr_runs_prevented=hpcr_runs,
            intent_tier=tier,
            is_surgical_sniper=is_sniper,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Intent Leak Engine (INTENT-LEAK-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherIntentLeakEngine()
        sniper = PitcherPutawayIntentMetrics("p1", "Corbin Burnes", 66.0, 9.0, 48.0, 480)
        leaker = PitcherPutawayIntentMetrics("p2", "Meatball Pitcher", 42.0, 29.0, 26.0, 320)

        r_sni = engine.evaluate_intent_leak(sniper)
        r_lea = engine.evaluate_intent_leak(leaker)

        if (
            r_sni.intent_tier == "SURGICAL_PUTAWAY_COMMAND_SNIPER"
            and r_lea.intent_tier == "FATAL_TWO_STRIKE_MEATBALL_LEAKER"
        ):
            checks.append(
                Check(
                    "intent leak engine",
                    True,
                    f"Intent Leak verified (Burnes TSPIEI: {r_sni.tspiei_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "intent leak engine", False, f"Unexpected intent leak output: {r_sni}, {r_lea}"
                )
            )
    except Exception as exc:
        checks.append(Check("intent leak engine", False, str(exc)))
    return checks
