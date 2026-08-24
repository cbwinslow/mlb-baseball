"""Batter Pulled-Air (FB/LD) Power Polarization Engine (PULL-AIR-01, ADR-183).

Provides pulled fly ball and line drive power optimization modeling:
1. Pulled-Air Contact Rate (PullAir% = Pulled FB & LD / Total FB & LD).
2. Pulled-Air Damage Multiplier (PADM scaling power output and HR efficiency).
3. Pull-Side HR Hunter Identification (maximizing short porch and fence geometry).
4. Strategy Archetypes (Elite Pull-Air Punisher, Above Average Pull-Air, All-Fields Air Spray).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterPullAirMetrics:
    """Observed airborne batted ball trajectory and directional distribution."""

    batter_id: str
    batter_name: str
    pulled_air_count: int = 35  # Pulled FB + LD
    total_air_count: int = 110  # Total FB + LD
    pulled_air_hr: int = 18
    total_hr: int = 22


@dataclasses.dataclass(frozen=True)
class PullAirEvaluationResult:
    """Evaluated pulled air frequency, damage multiplier, and strategy classification."""

    batter_name: str
    pull_air_pct: float  # % of air balls hit to pull field
    pulled_air_delta_league: float  # PullAir% - League Baseline (28.5%)
    padm_multiplier: float  # Pulled-Air Damage Multiplier (>= 1.0)
    strategy_archetype: str  # "ELITE_PULL_AIR_PUNISHER", "ABOVE_AVERAGE_PULL_AIR", etc.
    is_elite_pull_air_hitter: bool


class BasePullAirEngine(Protocol):
    """Polymorphic protocol for pulled-air power engines."""

    def evaluate_pull_air(
        self,
        metrics: BatterPullAirMetrics,
        league_pull_air_baseline: float = 28.5,
    ) -> PullAirEvaluationResult:
        """Calculate pull-air frequency and PADM multiplier."""
        ...


class PullAirPowerEngine:
    """Calculates batter pulled-air rate and power damage multiplier (PULL-AIR-01)."""

    def evaluate_pull_air(
        self,
        metrics: BatterPullAirMetrics,
        league_pull_air_baseline: float = 28.5,
    ) -> PullAirEvaluationResult:
        """Compute pulled-air frequency and damage multiplier."""
        air_tot = max(1, metrics.total_air_count)
        pull_air_pct = round((metrics.pulled_air_count / air_tot) * 100.0, 1)
        delta_pct = round(pull_air_pct - league_pull_air_baseline, 1)

        # Pulled-Air Damage Multiplier (PADM)
        # Pulling air balls converts exit velocity into HRs ~ 3x more effectively
        hr_pull_share = metrics.pulled_air_hr / max(1, metrics.total_hr)
        padm = round((pull_air_pct / league_pull_air_baseline) * (1.0 + hr_pull_share * 0.5), 2)

        # Elite Pull-Air Punisher Flag
        is_elite = pull_air_pct >= 38.0 and padm >= 1.60

        # Strategy Archetype
        if is_elite:
            archetype = "ELITE_PULL_AIR_PUNISHER"
        elif pull_air_pct >= 33.0 or padm >= 1.30:
            archetype = "ABOVE_AVERAGE_PULL_AIR"
        elif pull_air_pct <= 22.0:
            archetype = "ALL_FIELDS_AIR_SPRAY"
        else:
            archetype = "AVERAGE"

        return PullAirEvaluationResult(
            batter_name=metrics.batter_name,
            pull_air_pct=pull_air_pct,
            pulled_air_delta_league=delta_pct,
            padm_multiplier=padm,
            strategy_archetype=archetype,
            is_elite_pull_air_hitter=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Pull-Air Power Engine (PULL-AIR-01)."""
    checks: list[Check] = []
    try:
        engine = PullAirPowerEngine()
        paredes = BatterPullAirMetrics("b1", "Isaac Paredes Archetype", 46, 110, 24, 26)
        all_fields = BatterPullAirMetrics("b2", "All Fields Hitter", 22, 110, 5, 15)

        r_par = engine.evaluate_pull_air(paredes)
        r_all = engine.evaluate_pull_air(all_fields)

        if (
            r_par.strategy_archetype == "ELITE_PULL_AIR_PUNISHER"
            and r_all.strategy_archetype == "ALL_FIELDS_AIR_SPRAY"
        ):
            checks.append(
                Check(
                    "pull-air power engine",
                    True,
                    f"Pull-air verified (PADM: {r_par.padm_multiplier:.2f}x)",
                )
            )
        else:
            checks.append(
                Check(
                    "pull-air power engine", False, f"Unexpected pull-air output: {r_par}, {r_all}"
                )
            )
    except Exception as exc:
        checks.append(Check("pull-air power engine", False, str(exc)))
    return checks
