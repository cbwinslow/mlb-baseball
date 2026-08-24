"""Pitcher Two-Strike Put-Away & Whiff Conversion Engine (PUTAWAY-01, ADR-176).

Provides 2-strike count conversion, terminal strikeout efficiency, and whiff modeling:
1. Two-Strike Put-Away Rate (PutAway%) vs League Baseline (19.5%).
2. Two-Strike Whiff Rate on Secondary pitches (Sliders, Sweepers, Splitters).
3. Put-Away Surplus Index (PASI_runs saved from converting counts to terminal outs).
4. Finisher Pitcher Tiers (Elite Strikeout Closer, Above Average Finisher, Foul Ball Extender).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherPutAwayMetrics:
    """Observed two-strike count pitch outcomes for a pitcher."""

    pitcher_id: str
    pitcher_name: str
    putaway_pct: float = 0.20  # % of 2-strike pitches resulting in strikeout
    two_strike_pitches: int = 600
    whiff_2strike_pct: float = 0.14
    secondary_putaway_pct: float = 0.22


@dataclasses.dataclass(frozen=True)
class PutAwayEvaluationResult:
    """Evaluated two-strike put-away surplus value and finisher classification."""

    pitcher_name: str
    putaway_pct: float
    putaway_delta_league: float  # PutAway% - League Baseline (0.195)
    pasi_runs_saved: float  # Put-Away Surplus Index in runs saved
    finisher_tier: (
        str  # "ELITE_STRIKEOUT_CLOSER", "ABOVE_AVERAGE_FINISHER", "FOUL_BALL_EXTENDER", "AVERAGE"
    )
    is_elite_putaway_arm: bool


class BasePutAwayEngine(Protocol):
    """Polymorphic protocol for pitcher put-away engines."""

    def evaluate_putaway(
        self,
        metrics: PitcherPutAwayMetrics,
        league_putaway_baseline: float = 0.195,
    ) -> PutAwayEvaluationResult:
        """Calculate put-away delta and seasonal PASI runs."""
        ...


class PitcherPutAwayEngine:
    """Calculates two-strike put-away efficiency and PASI runs (PUTAWAY-01)."""

    def evaluate_putaway(
        self,
        metrics: PitcherPutAwayMetrics,
        league_putaway_baseline: float = 0.195,
    ) -> PutAwayEvaluationResult:
        """Compute PASI runs saved and finisher tier."""
        delta_pa = round(metrics.putaway_pct - league_putaway_baseline, 3)

        # Converting a 2-strike count into immediate strikeout saves ~ 0.11 runs vs foul/ball
        pasi_runs = round(delta_pa * metrics.two_strike_pitches * 0.11, 2)

        # Elite Finisher Flag
        is_elite = metrics.putaway_pct >= 0.240 or pasi_runs >= 3.0

        # Finisher Tier
        if is_elite:
            tier = "ELITE_STRIKEOUT_CLOSER"
        elif metrics.putaway_pct >= 0.210 or pasi_runs >= 1.0:
            tier = "ABOVE_AVERAGE_FINISHER"
        elif metrics.putaway_pct <= 0.165 or pasi_runs <= -2.0:
            tier = "FOUL_BALL_EXTENDER"
        else:
            tier = "AVERAGE"

        return PutAwayEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            putaway_pct=metrics.putaway_pct,
            putaway_delta_league=delta_pa,
            pasi_runs_saved=pasi_runs,
            finisher_tier=tier,
            is_elite_putaway_arm=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Put-Away Engine (PUTAWAY-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherPutAwayEngine()
        closer = PitcherPutAwayMetrics(
            "p1", "Elite Closer", putaway_pct=0.265, two_strike_pitches=500
        )
        extender = PitcherPutAwayMetrics(
            "p2", "Foul Ball Extender", putaway_pct=0.150, two_strike_pitches=500
        )

        r_clo = engine.evaluate_putaway(closer)
        r_ext = engine.evaluate_putaway(extender)

        if (
            r_clo.finisher_tier == "ELITE_STRIKEOUT_CLOSER"
            and r_ext.finisher_tier == "FOUL_BALL_EXTENDER"
        ):
            checks.append(
                Check(
                    "putaway engine",
                    True,
                    f"Put-away verified (Closer PASI: {r_clo.pasi_runs_saved:>+4.1f} runs)",
                )
            )
        else:
            checks.append(
                Check("putaway engine", False, f"Unexpected putaway output: {r_clo}, {r_ext}")
            )
    except Exception as exc:
        checks.append(Check("putaway engine", False, str(exc)))
    return checks
