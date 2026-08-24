"""Starting Pitcher First-Pitch Strike Surplus Valuation Engine (FSTRIKE-01, ADR-172).

Provides first-pitch count leverage and run expectancy surplus modeling:
1. First-Pitch Strike Rate (F-Strike%) vs League Baseline (60.5%).
2. Count Delta Leverage (0-1 Count wOBA ~ 0.270 vs 1-0 Count wOBA ~ 0.355).
3. First-Pitch Strike Surplus Value (FPSV_runs per season and per 100 BF).
4. Pitcher Command Tiers (Elite Zone Pounder, Above Average, Passive Behind Count).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherFStrikeMetrics:
    """Observed first-pitch strike metrics and sample volume for a pitcher."""

    pitcher_id: str
    pitcher_name: str
    fstrike_pct: float = 0.65  # First pitch strike percentage
    batters_faced: int = 700
    woba_after_0_1: float = 0.275
    woba_after_1_0: float = 0.350


@dataclasses.dataclass(frozen=True)
class FStrikeEvaluationResult:
    """Evaluated first-pitch strike surplus run value and command rating."""

    pitcher_name: str
    fstrike_pct: float
    fps_delta_league: float  # F-Strike% - League Baseline (0.605)
    fpsv_runs_seasonal: float  # Net runs saved over league average starter
    fpsv_per_100_bf: float  # Surplus runs saved per 100 batters faced
    command_tier: str  # "ELITE_ZONE_POUNDER", "ABOVE_AVERAGE", "AVERAGE", "PASSIVE_BEHIND_COUNT"


class BaseFStrikeEngine(Protocol):
    """Polymorphic protocol for first-pitch strike surplus engines."""

    def evaluate_fstrike(
        self,
        metrics: PitcherFStrikeMetrics,
        league_fstrike_baseline: float = 0.605,
    ) -> FStrikeEvaluationResult:
        """Calculate first-pitch strike surplus value and tier."""
        ...


class FirstPitchStrikeEngine:
    """Calculates first-pitch strike run value surplus (FSTRIKE-01)."""

    def evaluate_fstrike(
        self,
        metrics: PitcherFStrikeMetrics,
        league_fstrike_baseline: float = 0.605,
    ) -> FStrikeEvaluationResult:
        """Compute seasonal FPSV runs and command classification."""
        delta_fps = round(metrics.fstrike_pct - league_fstrike_baseline, 3)

        # Average Run Expectancy swing between 0-1 and 1-0 counts is ~ 0.068 runs/PA
        fpsv_season = round(delta_fps * metrics.batters_faced * 0.068, 2)
        fpsv_100 = round(delta_fps * 100.0 * 0.068, 2)

        # Command Tiers
        if metrics.fstrike_pct >= 0.660 or fpsv_100 >= 0.35:
            tier = "ELITE_ZONE_POUNDER"
        elif metrics.fstrike_pct >= 0.625 or fpsv_100 >= 0.12:
            tier = "ABOVE_AVERAGE"
        elif metrics.fstrike_pct <= 0.560 or fpsv_100 <= -0.30:
            tier = "PASSIVE_BEHIND_COUNT"
        else:
            tier = "AVERAGE"

        return FStrikeEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            fstrike_pct=metrics.fstrike_pct,
            fps_delta_league=delta_fps,
            fpsv_runs_seasonal=fpsv_season,
            fpsv_per_100_bf=fpsv_100,
            command_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for First-Pitch Strike Engine (FSTRIKE-01)."""
    checks: list[Check] = []
    try:
        engine = FirstPitchStrikeEngine()
        pounder = PitcherFStrikeMetrics("p1", "Zone Pounder", fstrike_pct=0.68, batters_faced=750)
        passive = PitcherFStrikeMetrics("p2", "Wild Reliever", fstrike_pct=0.53, batters_faced=250)

        r_pnd = engine.evaluate_fstrike(pounder)
        r_pas = engine.evaluate_fstrike(passive)

        if (
            r_pnd.command_tier == "ELITE_ZONE_POUNDER"
            and r_pas.command_tier == "PASSIVE_BEHIND_COUNT"
        ):
            checks.append(
                Check(
                    "first pitch strike engine",
                    True,
                    f"F-Strike verified (Pounder FPSV: {r_pnd.fpsv_runs_seasonal:>+4.1f} runs)",
                )
            )
        else:
            checks.append(
                Check(
                    "first pitch strike engine", False, f"Unexpected FPS output: {r_pnd}, {r_pas}"
                )
            )
    except Exception as exc:
        checks.append(Check("first pitch strike engine", False, str(exc)))
    return checks
