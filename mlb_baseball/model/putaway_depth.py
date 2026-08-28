"""Pitcher Secondary Pitch Whiff Escalation Engine (PUTAWAY-DEPTH-01, ADR-244).

Provides 2-strike secondary whiff surge, chase expansion, and PWEI index:
1. Putaway Whiff Escalation Index (PWEI score measuring 2-strike execution).
2. Two-Strike Strikeouts Above Average (TSSAA extra punchouts from secondary sharpening).
3. Putaway Archetypes (Lethal Two Strike Executioner, Blunt Weapon No Escalation).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherPutawayDepthMetrics:
    """Observed pitcher early whiff %, 2-strike whiff %, and 2-strike chase %."""

    pitcher_id: str
    pitcher_name: str
    early_count_whiff_pct: float = 28.0  # Whiff % in non-2-strike counts (benchmark ~28.0%)
    two_strike_whiff_pct: float = 38.0  # Whiff % in 2-strike counts (benchmark ~38.0%)
    two_strike_chase_pct: float = 34.0  # O-Swing % in 2-strike counts (benchmark ~34.0%)
    two_strike_secondaries_count: int = 150


@dataclasses.dataclass(frozen=True)
class PutawayDepthEvaluationResult:
    """Evaluated putaway escalation score, strikeout surplus, and tier."""

    pitcher_name: str
    pwei_score: float  # Putaway Whiff Escalation Index (0 to 160)
    whiff_delta_pct: float  # Whiff % increase from early to 2-strike counts
    tssaa_strikeouts: float  # Two-Strike Strikeouts Above Average
    tssrv_runs_saved: float  # Net defensive runs saved from surplus strikeouts
    putaway_tier: str  # e.g. "LETHAL_TWO_STRIKE_EXECUTIONER", "BLUNT_WEAPON_NO_ESCALATION"
    is_executioner: bool


class BasePutawayDepthEngine(Protocol):
    """Polymorphic protocol for putaway whiff escalation engines."""

    def evaluate_putaway_depth(
        self,
        metrics: PitcherPutawayDepthMetrics,
    ) -> PutawayDepthEvaluationResult:
        """Calculate PWEI rating, TSSAA strikeouts, and tier."""
        ...


class PitcherPutawayDepthEngine:
    """Calculates 2-strike secondary whiff surge, chase expansion, and PWEI (PUTAWAY-DEPTH-01)."""

    def evaluate_putaway_depth(
        self,
        metrics: PitcherPutawayDepthMetrics,
    ) -> PutawayDepthEvaluationResult:
        """Compute PWEI score, TSSAA strikeouts, and defensive run value."""
        delta_whiff = round(metrics.two_strike_whiff_pct - metrics.early_count_whiff_pct, 1)

        # PWEI Score: benchmark 38.0% 2S whiff, 10.0% delta, 34.0% 2S chase
        whiff_bonus = (metrics.two_strike_whiff_pct - 38.0) * 1.8
        surge_bonus = (delta_whiff - 10.0) * 1.4
        chase_bonus = (metrics.two_strike_chase_pct - 34.0) * 1.2
        pwei = round(max(0.0, 100.0 + whiff_bonus + surge_bonus + chase_bonus), 1)

        # TSSAA Strikeouts & TSSRV Runs (~0.28 runs per surplus strikeout)
        pitches = max(1, metrics.two_strike_secondaries_count)
        tssaa = round(((metrics.two_strike_whiff_pct - 38.0) / 100.0) * pitches * 0.60, 1)
        runs = round(tssaa * 0.28, 2)

        is_exec = pwei >= 116.0 and metrics.two_strike_whiff_pct >= 45.0 and delta_whiff >= 13.0

        # Tiers
        if is_exec:
            tier = "LETHAL_TWO_STRIKE_EXECUTIONER"
        elif delta_whiff <= 4.0 or metrics.two_strike_whiff_pct <= 30.0:
            tier = "BLUNT_WEAPON_NO_ESCALATION"
        elif metrics.two_strike_whiff_pct >= 42.0:
            tier = "SOLID_PUTAWAY_FINISHER"
        else:
            tier = "AVERAGE_PUTAWAY_ESCALATION"

        return PutawayDepthEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            pwei_score=pwei,
            whiff_delta_pct=delta_whiff,
            tssaa_strikeouts=tssaa,
            tssrv_runs_saved=runs,
            putaway_tier=tier,
            is_executioner=is_exec,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Putaway Depth Engine (PUTAWAY-DEPTH-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherPutawayDepthEngine()
        exec_p = PitcherPutawayDepthMetrics("p1", "Tarik Skubal", 32.0, 50.0, 46.0, 180)
        blunt_p = PitcherPutawayDepthMetrics("p2", "Blunt Reliever", 26.0, 28.0, 26.0, 100)

        r_exe = engine.evaluate_putaway_depth(exec_p)
        r_blu = engine.evaluate_putaway_depth(blunt_p)

        if (
            r_exe.putaway_tier == "LETHAL_TWO_STRIKE_EXECUTIONER"
            and r_blu.putaway_tier == "BLUNT_WEAPON_NO_ESCALATION"
        ):
            checks.append(
                Check(
                    "putaway depth engine",
                    True,
                    f"Putaway Depth verified (Skubal PWEI: {r_exe.pwei_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "putaway depth engine",
                    False,
                    f"Unexpected putaway depth output: {r_exe}, {r_blu}",
                )
            )
    except Exception as exc:
        checks.append(Check("putaway depth engine", False, str(exc)))
    return checks
