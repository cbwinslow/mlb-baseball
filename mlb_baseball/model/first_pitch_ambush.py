"""Pitcher First-Pitch Strike Aggression vs Ambush Engine (FIRST-PITCH-AMBUSH-01, ADR-248).

Provides 0-0 strike command, ambush damage suppression, and FPCARI index:
1. First-Pitch Command & Ambush Resistance Index (FPCARI score measuring 0-0 leverage).
2. First-Pitch Count Leverage Runs Saved (FPLRS net defensive runs saved from 0-1 counts).
3. First-Pitch Archetypes (Surgical First Strike Commander, Meatball Ambush Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherFirstPitchAmbushMetrics:
    """Observed 0-0 strike %, 0-0 hard-hit %, and 0-0 slugging %."""

    pitcher_id: str
    pitcher_name: str
    first_pitch_strike_pct: float = 60.0  # 0-0 strike % (benchmark ~60.0%)
    first_pitch_opponent_hard_hit_pct: float = 44.0  # 0-0 hard-hit % (benchmark ~44.0%)
    first_pitch_opponent_slug_pct: float = 0.520  # 0-0 slugging % (benchmark ~0.520)
    total_batters_faced: int = 180


@dataclasses.dataclass(frozen=True)
class FirstPitchAmbushEvaluationResult:
    """Evaluated first-pitch command score, runs saved, and ambush tier."""

    pitcher_name: str
    fpcari_score: float  # First-Pitch Command & Ambush Resistance Index (0 to 160)
    fplrs_runs_saved: float  # Net defensive runs saved via count leverage
    ambush_tier: str  # e.g. "SURGICAL_FIRST_STRIKE_COMMANDER", "MEATBALL_AMBUSH_LIABILITY"
    is_commander: bool


class BaseFirstPitchAmbushEngine(Protocol):
    """Polymorphic protocol for first-pitch ambush engines."""

    def evaluate_first_pitch_ambush(
        self,
        metrics: PitcherFirstPitchAmbushMetrics,
    ) -> FirstPitchAmbushEvaluationResult:
        """Calculate FPCARI rating, FPLRS runs, and tier."""
        ...


class PitcherFirstPitchAmbushEngine:
    """Calculates 0-0 count strike rate, damage suppression, and FPCARI (FIRST-PITCH-AMBUSH-01)."""

    def evaluate_first_pitch_ambush(
        self,
        metrics: PitcherFirstPitchAmbushMetrics,
    ) -> FirstPitchAmbushEvaluationResult:
        """Compute FPCARI score and count leverage runs saved."""
        # FPCARI Score: benchmark 60.0% strike, 44.0% hard hit, 0.520 SLG
        strike_bonus = (metrics.first_pitch_strike_pct - 60.0) * 1.8
        hard_saving = (44.0 - metrics.first_pitch_opponent_hard_hit_pct) * 1.2
        slg_saving = (0.520 - metrics.first_pitch_opponent_slug_pct) * 45.0
        fpcari = round(max(0.0, 100.0 + strike_bonus + hard_saving + slg_saving), 1)

        # FPLRS Runs (~0.0025 runs per batter faced per point above 100)
        bf = max(1, metrics.total_batters_faced)
        runs = round((fpcari - 100.0) * (bf * 0.0025), 2)

        is_comm = (
            fpcari >= 116.0
            and metrics.first_pitch_strike_pct >= 66.0
            and metrics.first_pitch_opponent_hard_hit_pct <= 36.0
        )

        # Tiers
        if is_comm:
            tier = "SURGICAL_FIRST_STRIKE_COMMANDER"
        elif (
            metrics.first_pitch_strike_pct <= 52.0
            or metrics.first_pitch_opponent_hard_hit_pct >= 54.0
        ):
            tier = "MEATBALL_AMBUSH_LIABILITY"
        elif metrics.first_pitch_strike_pct >= 63.0:
            tier = "SOLID_FIRST_PITCH_STRIKER"
        else:
            tier = "AVERAGE_FIRST_PITCH_PROFILE"

        return FirstPitchAmbushEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            fpcari_score=fpcari,
            fplrs_runs_saved=runs,
            ambush_tier=tier,
            is_commander=is_comm,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher First Pitch Ambush Engine (FIRST-PITCH-AMBUSH-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherFirstPitchAmbushEngine()
        ace = PitcherFirstPitchAmbushMetrics("p1", "Logan Gilbert", 69.0, 32.0, 0.360, 220)
        ambushed = PitcherFirstPitchAmbushMetrics("p2", "Ambush Prone", 50.0, 56.0, 0.620, 150)

        r_ace = engine.evaluate_first_pitch_ambush(ace)
        r_amb = engine.evaluate_first_pitch_ambush(ambushed)

        if (
            r_ace.ambush_tier == "SURGICAL_FIRST_STRIKE_COMMANDER"
            and r_amb.ambush_tier == "MEATBALL_AMBUSH_LIABILITY"
        ):
            checks.append(
                Check(
                    "first pitch ambush engine",
                    True,
                    f"First Pitch Ambush verified (Gilbert FPCARI: {r_ace.fpcari_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "first pitch ambush engine",
                    False,
                    f"Unexpected first pitch ambush output: {r_ace}, {r_amb}",
                )
            )
    except Exception as exc:
        checks.append(Check("first pitch ambush engine", False, str(exc)))
    return checks
