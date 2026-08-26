"""Bullpen Bridge Sequencing & High-Leverage Handoff Engine (BULLPEN-BRIDGE-01, ADR-256).

Provides bullpen arm sequencing quality, late-inning handoff efficiency, and
chain-of-command run prevention:
1. Bridge Sequencing Efficiency Index (BSEI) scoring overall 7th-8th-9th
   inning arm transition quality.
2. High-Leverage Handoff Runs Saved (HLHRS) estimating runs prevented by
   proper bridge sequencing vs chaotic bullpen usage.
3. Bullpen chain tiers classifying sequencing quality.

Mathematical foundation:
    Effective bullpen usage chains arms in leverage-appropriate order, preserving
    the best reliever for the highest-leverage situation. Chaotic usage wastes
    elite arms in low-leverage spots or exposes weak arms in high-leverage ones.

    BSEI = max(0, 100 + (hold_pct - 65.0) * 1.5
               + (leverage_match_rate - 50.0) * 1.0
               + (30.0 - inherited_score_pct) * 0.8)

    HLHRS_runs = (BSEI - 100.0) * (high_lev_innings * 0.0045)

References:
    - Tango, Lichtman, Dolphin (2007). The Book: Playing the Percentages in
      Baseball. Ch. 10 "Relief Pitchers."
    - Carleton, Russell A. (2014). "The Leverage-Adjusted Bullpen Usage
      Inefficiency." Baseball Prospectus.
    - Lichtman, Mitchel (2018). "Optimal Bullpen Strategy and Reliever
      Sequencing." The Hardball Times.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BullpenBridgeMetrics:
    """Observed bullpen sequencing and handoff efficiency metrics."""

    team_id: str
    team_name: str
    hold_pct: float = 65.0
    leverage_match_rate: float = 50.0
    inherited_score_pct: float = 30.0
    high_leverage_innings: float = 80.0
    clean_inning_pct: float = 55.0


@dataclasses.dataclass(frozen=True)
class BridgeEvaluationResult:
    """Output of bullpen bridge sequencing evaluation."""

    team_name: str
    bsei_score: float
    hlhrs_runs_saved: float
    bridge_tier: str
    is_elite_bridge: bool


class BridgeEvaluator(Protocol):
    """Protocol for bullpen bridge sequencing evaluators."""

    def evaluate_bridge(
        self,
        metrics: BullpenBridgeMetrics,
    ) -> BridgeEvaluationResult:
        """Calculate BSEI rating, HLHRS runs, and bridge tier."""
        ...


class BullpenBridgeEngine:
    """Calculates bullpen bridge sequencing and handoff efficiency (BULLPEN-BRIDGE-01)."""

    def evaluate_bridge(
        self,
        metrics: BullpenBridgeMetrics,
    ) -> BridgeEvaluationResult:
        """Compute BSEI score and high-leverage handoff runs saved.

        BSEI (Bridge Sequencing Efficiency Index):
            BSEI = max(0, 100 + (hold_pct - 65.0) * 1.5
                       + (leverage_match_rate - 50.0) * 1.0
                       + (30.0 - inherited_score_pct) * 0.8)

        HLHRS (High-Leverage Handoff Runs Saved):
            HLHRS_runs = (BSEI - 100.0) * (high_lev_innings * 0.0045)
        """
        hold_bonus = (metrics.hold_pct - 65.0) * 1.5
        lev_bonus = (metrics.leverage_match_rate - 50.0) * 1.0
        inherit_bonus = (30.0 - metrics.inherited_score_pct) * 0.8
        bsei = round(max(0.0, 100.0 + hold_bonus + lev_bonus + inherit_bonus), 1)

        innings = max(1.0, metrics.high_leverage_innings)
        runs = round((bsei - 100.0) * (innings * 0.0045), 2)

        is_elite = (
            bsei >= 118.0 and metrics.hold_pct >= 78.0 and metrics.leverage_match_rate >= 62.0
        )

        if is_elite:
            tier = "DOMINANT_LOCKDOWN_BRIDGE_CHAIN"
        elif metrics.hold_pct <= 52.0 or metrics.inherited_score_pct >= 42.0:
            tier = "LEAKING_BRIDGE_HANDOFF_LIABILITY"
        elif bsei >= 105.0 and metrics.hold_pct >= 68.0:
            tier = "SOLID_BRIDGE_SEQUENCING"
        else:
            tier = "AVERAGE_BRIDGE_SEQUENCING"

        return BridgeEvaluationResult(
            team_name=metrics.team_name,
            bsei_score=bsei,
            hlhrs_runs_saved=runs,
            bridge_tier=tier,
            is_elite_bridge=is_elite,
        )


def health_check() -> list[Check]:
    """Verify bullpen bridge engine produces expected outputs."""
    engine = BullpenBridgeEngine()

    elite = BullpenBridgeMetrics(
        team_id="t1",
        team_name="Elite Pen",
        hold_pct=82.0,
        leverage_match_rate=68.0,
        inherited_score_pct=18.0,
        high_leverage_innings=95.0,
        clean_inning_pct=72.0,
    )
    leaking = BullpenBridgeMetrics(
        team_id="t2",
        team_name="Leaking Pen",
        hold_pct=48.0,
        leverage_match_rate=35.0,
        inherited_score_pct=45.0,
        high_leverage_innings=85.0,
    )

    r_e = engine.evaluate_bridge(elite)
    r_l = engine.evaluate_bridge(leaking)

    ok = (
        r_e.bsei_score > 118.0
        and r_e.hlhrs_runs_saved > 5.0
        and r_e.bridge_tier == "DOMINANT_LOCKDOWN_BRIDGE_CHAIN"
        and r_e.is_elite_bridge is True
        and r_l.bridge_tier == "LEAKING_BRIDGE_HANDOFF_LIABILITY"
        and r_l.hlhrs_runs_saved < 0.0
    )

    return [
        Check(
            name="bullpen bridge engine",
            ok=ok,
            detail=(
                f"Expected outputs: {r_e}, {r_l}"
                if ok
                else f"Unexpected bridge output: {r_e}, {r_l}"
            ),
        )
    ]
