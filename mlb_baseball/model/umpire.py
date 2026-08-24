"""Individual Umpire Strike Zone & Run Bias Modeler (UMP-01, ADR-136)."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class UmpireProfile:
    """Historical strike zone tendencies and run scoring impact for a home plate umpire."""

    umpire_id: str
    umpire_name: str
    games_behind_plate: int
    zone_horizontal_expansion_in: float  # +0.8 in = wide zone (pitcher friendly), -0.5 in = tight
    zone_vertical_expansion_in: float  # +0.5 in = tall zone
    called_strike_accuracy_pct: float  # e.g. 93.5%
    run_impact_per_game: float  # Expected run delta on game total (e.g. -0.35 runs)
    k_rate_multiplier: float  # e.g. 1.04x strikeout boost
    bb_rate_multiplier: float  # e.g. 0.94x walk reduction


@dataclasses.dataclass(frozen=True)
class UmpireGameAdjustment:
    """Calculated betting and modeling adjustments for a specific game matchup."""

    umpire_name: str
    baseline_total_runs: float
    adjusted_total_runs: float
    run_adjustment_delta: float
    home_starter_k_line_adjustment: float
    away_starter_k_line_adjustment: float
    zone_classification: str  # "pitcher_friendly", "hitter_friendly", "neutral"


class BaseUmpireEngine(Protocol):
    """Polymorphic protocol for umpire evaluation engines."""

    def evaluate_game_adjustment(
        self,
        umpire: UmpireProfile,
        baseline_total: float,
        home_starter_base_ks: float = 6.0,
        away_starter_base_ks: float = 5.5,
    ) -> UmpireGameAdjustment:
        """Calculate run total and strikeout prop adjustments."""
        ...


class UmpireBiasEngine:
    """Evaluates individual umpire strike zone dimensions and market total adjustments (UMP-01)."""

    def evaluate_game_adjustment(
        self,
        umpire: UmpireProfile,
        baseline_total: float,
        home_starter_base_ks: float = 6.0,
        away_starter_base_ks: float = 5.5,
    ) -> UmpireGameAdjustment:
        """Calculate run total and strikeout prop adjustments for an assigned umpire."""
        # 1. Total runs adjustment: directly apply empirical run impact
        adj_total = round(baseline_total + umpire.run_impact_per_game, 2)
        delta_run = round(umpire.run_impact_per_game, 2)

        # 2. Strikeout adjustments
        h_ks_adj = round(home_starter_base_ks * umpire.k_rate_multiplier, 2)
        a_ks_adj = round(away_starter_base_ks * umpire.k_rate_multiplier, 2)

        # 3. Zone classification
        if umpire.zone_horizontal_expansion_in >= 0.40 or umpire.run_impact_per_game <= -0.25:
            classification = "pitcher_friendly"
        elif umpire.zone_horizontal_expansion_in <= -0.30 or umpire.run_impact_per_game >= 0.25:
            classification = "hitter_friendly"
        else:
            classification = "neutral"

        return UmpireGameAdjustment(
            umpire_name=umpire.umpire_name,
            baseline_total_runs=baseline_total,
            adjusted_total_runs=adj_total,
            run_adjustment_delta=delta_run,
            home_starter_k_line_adjustment=h_ks_adj,
            away_starter_k_line_adjustment=a_ks_adj,
            zone_classification=classification,
        )


def health_check() -> list[Check]:
    """Operational health check for the Umpire Bias Modeler (UMP-01)."""
    checks: list[Check] = []
    try:
        engine = UmpireBiasEngine()
        pitcher_ump = UmpireProfile(
            umpire_id="u1",
            umpire_name="Wide Zone Ump",
            games_behind_plate=120,
            zone_horizontal_expansion_in=0.75,
            zone_vertical_expansion_in=0.20,
            called_strike_accuracy_pct=92.5,
            run_impact_per_game=-0.42,
            k_rate_multiplier=1.06,
            bb_rate_multiplier=0.92,
        )

        adj = engine.evaluate_game_adjustment(
            pitcher_ump, baseline_total=8.5, home_starter_base_ks=6.0
        )

        if (
            adj.adjusted_total_runs < 8.5
            and adj.zone_classification == "pitcher_friendly"
            and adj.home_starter_k_line_adjustment > 6.0
        ):
            checks.append(
                Check(
                    "umpire bias modeler",
                    True,
                    f"Umpire adjustments verified ({adj.adjusted_total_runs})",
                )
            )
        else:
            checks.append(
                Check(
                    "umpire bias modeler",
                    False,
                    f"Unexpected adjustment: {adj.adjusted_total_runs}",
                )
            )
    except Exception as exc:
        checks.append(Check("umpire bias modeler", False, str(exc)))
    return checks
