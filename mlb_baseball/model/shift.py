"""Defensive Alignment & Batted Ball Spray Suppression Engine (SHIFT-01, ADR-140).

Provides defensive positioning evaluation, spray-angle filtering, and BABIP suppression modeling:
1. Defensive Alignments (Standard, Shaded Pull, Infield In, Outfield Deep).
2. Batter Ground Ball Pull-Rate & Spray Distribution Interaction.
3. Team Outs Above Average (OAA) & Infield Range Defensive Conversion.
4. Expected BABIP & Run Suppression per Game.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


class AlignmentType(enum.Enum):
    """Defensive positioning alignments."""

    STANDARD = "standard"  # Straight up, neutral positioning
    SHADED_PULL = "shaded_pull"  # Shaded to pull side (legal 2 on each side of 2B)
    INFIELD_IN = "infield_in"  # Infield drawn in (prevents run from 3B, increases hit probability)
    OUTFIELD_DEEP = "outfield_deep"  # Outfield playing deep (prevents XBH, concedes bloop singles)


@dataclasses.dataclass(frozen=True)
class BatterBattedBallTendencies:
    """Batter directional spray and speed characteristics."""

    batter_id: str
    batter_name: str
    pull_pct_ground_balls: float = 0.45  # e.g. 52% pulled ground balls
    hard_hit_pct: float = 0.38
    sprint_speed_ft_s: float = 27.0  # 27.0 ft/s is MLB average


@dataclasses.dataclass(frozen=True)
class DefensiveAlignmentProfile:
    """Defensive scheme and team defensive fielding skill."""

    team_id: str
    alignment: AlignmentType
    infield_oaa_season: float = 0.0  # Infield Outs Above Average
    outfield_oaa_season: float = 0.0


@dataclasses.dataclass(frozen=True)
class DefensiveSuppressionResult:
    """Evaluated BABIP and run prevention under current defensive alignment."""

    batter_name: str
    alignment: AlignmentType
    expected_babip: float  # e.g. 0.285
    babip_delta_vs_league: float  # e.g. -0.015 (suppression)
    ground_ball_out_rate: float  # e.g. 0.76 (76% of GBs turned into outs)
    expected_run_prevention_per_game: float  # e.g. -0.22 runs


class BaseDefensiveEngine(Protocol):
    """Polymorphic protocol for defensive alignment evaluators."""

    def evaluate_defensive_matchup(
        self,
        defense: DefensiveAlignmentProfile,
        batter: BatterBattedBallTendencies,
        league_avg_babip: float = 0.295,
    ) -> DefensiveSuppressionResult:
        """Calculate expected BABIP and run suppression against batter spray profile."""
        ...


class DefensiveAlignmentEngine:
    """Evaluates defensive positioning and team OAA impact on batted balls (SHIFT-01)."""

    def evaluate_defensive_matchup(
        self,
        defense: DefensiveAlignmentProfile,
        batter: BatterBattedBallTendencies,
        league_avg_babip: float = 0.295,
    ) -> DefensiveSuppressionResult:
        """Compute expected BABIP and out conversions given alignment and batter tendencies."""
        # 1. Base BABIP from batter contact quality and speed
        # Fast runners get +BABIP (+0.010 per ft/s above 27.0)
        speed_delta = (batter.sprint_speed_ft_s - 27.0) * 0.010
        # Hard hit boost
        hard_hit_delta = (batter.hard_hit_pct - 0.38) * 0.15
        base_babip = league_avg_babip + speed_delta + hard_hit_delta

        # 2. Alignment effect
        if defense.alignment == AlignmentType.SHADED_PULL:
            # If batter is heavy pull hitter, shaded pull suppresses ground balls
            if batter.pull_pct_ground_balls >= 0.48:
                align_delta = -0.022
                gb_out_boost = +0.05
            else:
                align_delta = -0.005
                gb_out_boost = +0.01
        elif defense.alignment == AlignmentType.INFIELD_IN:
            # Infield in increases hit through infield (+0.045 BABIP)
            align_delta = +0.045
            gb_out_boost = -0.10
        elif defense.alignment == AlignmentType.OUTFIELD_DEEP:
            # Concedes bloopers (+0.015), prevents gap extra base hits
            align_delta = +0.012
            gb_out_boost = 0.00
        else:  # STANDARD
            align_delta = 0.000
            gb_out_boost = 0.00

        # 3. Team OAA Conversion Range (every +10 OAA suppresses ~0.012 BABIP)
        oaa_total = defense.infield_oaa_season + defense.outfield_oaa_season
        oaa_delta = -(oaa_total / 10.0) * 0.012

        final_babip = float(np.clip(base_babip + align_delta + oaa_delta, 0.210, 0.400))
        babip_diff = final_babip - league_avg_babip

        # Baseline ground ball out rate ~73%
        gb_out_rate = float(
            np.clip(0.73 + gb_out_boost + (defense.infield_oaa_season * 0.004), 0.55, 0.90)
        )

        # Run prevention: ~14 BIP per game * BABIP delta * 0.78 runs per hit
        run_prev = round(14.0 * babip_diff * 0.78, 2)

        return DefensiveSuppressionResult(
            batter_name=batter.batter_name,
            alignment=defense.alignment,
            expected_babip=round(final_babip, 3),
            babip_delta_vs_league=round(babip_diff, 3),
            ground_ball_out_rate=round(gb_out_rate, 3),
            expected_run_prevention_per_game=run_prev,
        )


def health_check() -> list[Check]:
    """Operational health check for the Defensive Alignment Engine (SHIFT-01)."""
    checks: list[Check] = []
    try:
        engine = DefensiveAlignmentEngine()
        defense = DefensiveAlignmentProfile(
            "lad", AlignmentType.SHADED_PULL, infield_oaa_season=8.0
        )
        pull_slugger = BatterBattedBallTendencies("b1", "Pull Slugger", pull_pct_ground_balls=0.54)

        res = engine.evaluate_defensive_matchup(defense, pull_slugger)

        # Shaded pull against 54% pull slugger + elite defense should suppress BABIP < 0.280
        if res.expected_babip < 0.280 and res.ground_ball_out_rate > 0.76:
            checks.append(
                Check(
                    "defensive alignment engine",
                    True,
                    f"Defensive shift verified (BABIP: {res.expected_babip:.3f})",
                )
            )
        else:
            checks.append(
                Check("defensive alignment engine", False, f"Unexpected suppression result: {res}")
            )
    except Exception as exc:
        checks.append(Check("defensive alignment engine", False, str(exc)))
    return checks
