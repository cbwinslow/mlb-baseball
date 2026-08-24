"""Pitcher Infield Fly Ball (IFFB) & Automatic Out Run Value Engine (IFFB-01, ADR-181).

Provides infield popup infliction, automatic out conversion, and run suppression modeling:
1. Infield Fly Ball Rate (IFFB% = Infield Popups / Total Fly Balls).
2. Automatic Out Value (BABIP <= .015, virtually zero run threat).
3. Pop-Up Surplus Runs Saved relative to league baseline (9.5% IFFB).
4. Induction Tiers (Elite Popup Inducer, Above Average Inducer, Warning Track Vulnerable).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherIFFBMetrics:
    """Observed popup and flyball distribution for a pitcher."""

    pitcher_id: str
    pitcher_name: str
    iffb_count: int = 16  # Infield fly ball popups
    fb_count: int = 160  # Total fly balls allowed
    pa_faced: int = 600


@dataclasses.dataclass(frozen=True)
class IFFBEvaluationResult:
    """Evaluated popup rate, surplus runs saved, and induction tier."""

    pitcher_name: str
    iffb_pct: float  # % of flyballs that are infield popups
    iffb_delta_league: float  # IFFB% - League Baseline (9.5%)
    popup_surplus_runs: float  # Seasonal runs saved by turning FBs into popups
    popup_tier: (
        str  # "ELITE_POPUP_INDUCER", "ABOVE_AVERAGE_INDUCER", "WARNING_TRACK_VULNERABLE", "AVERAGE"
    )
    is_elite_popup_artist: bool


class BaseIFFBEngine(Protocol):
    """Polymorphic protocol for infield fly ball engines."""

    def evaluate_iffb(
        self,
        metrics: PitcherIFFBMetrics,
        league_iffb_baseline: float = 9.5,
    ) -> IFFBEvaluationResult:
        """Calculate IFFB% and surplus runs saved."""
        ...


class InfieldFlyBallEngine:
    """Calculates pitcher IFFB induction and automatic out run savings (IFFB-01)."""

    def evaluate_iffb(
        self,
        metrics: PitcherIFFBMetrics,
        league_iffb_baseline: float = 9.5,
    ) -> IFFBEvaluationResult:
        """Compute popup rate and run suppression value."""
        fb_total = max(1, metrics.fb_count)
        iffb_pct = round((metrics.iffb_count / fb_total) * 100.0, 1)
        delta_pct = round(iffb_pct - league_iffb_baseline, 1)

        # Turning an outfield flyball into an infield popup saves ~ 0.22 runs
        surplus_runs = round((delta_pct / 100.0) * fb_total * 0.22, 2)

        # Elite Popup Artist Flag
        is_elite = iffb_pct >= 14.0 or surplus_runs >= 2.2

        # Induction Tier
        if is_elite:
            tier = "ELITE_POPUP_INDUCER"
        elif iffb_pct >= 11.5 or surplus_runs >= 0.8:
            tier = "ABOVE_AVERAGE_INDUCER"
        elif iffb_pct <= 6.0 or surplus_runs <= -1.5:
            tier = "WARNING_TRACK_VULNERABLE"
        else:
            tier = "AVERAGE"

        return IFFBEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            iffb_pct=iffb_pct,
            iffb_delta_league=delta_pct,
            popup_surplus_runs=surplus_runs,
            popup_tier=tier,
            is_elite_popup_artist=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Infield Fly Ball Engine (IFFB-01)."""
    checks: list[Check] = []
    try:
        engine = InfieldFlyBallEngine()
        popup_ace = PitcherIFFBMetrics("p1", "Elite Popup Inducer", iffb_count=28, fb_count=180)
        vulnerable = PitcherIFFBMetrics(
            "p2", "Warning Track Vulnerable", iffb_count=8, fb_count=180
        )

        r_ace = engine.evaluate_iffb(popup_ace)
        r_vul = engine.evaluate_iffb(vulnerable)

        if (
            r_ace.popup_tier == "ELITE_POPUP_INDUCER"
            and r_vul.popup_tier == "WARNING_TRACK_VULNERABLE"
        ):
            checks.append(
                Check(
                    "infield fly ball engine",
                    True,
                    f"IFFB verified (Ace Surplus: {r_ace.popup_surplus_runs:>+4.1f} runs)",
                )
            )
        else:
            checks.append(
                Check("infield fly ball engine", False, f"Unexpected IFFB output: {r_ace}, {r_vul}")
            )
    except Exception as exc:
        checks.append(Check("infield fly ball engine", False, str(exc)))
    return checks
