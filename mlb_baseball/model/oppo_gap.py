"""Batter Opposite-Field Power & Alley Extra-Base Gap Engine (OPPO-GAP-01, ADR-239).

Provides opposite-field hard contact, power alley extra-base conversion, and run production:
1. Opposite-Field Gap Power Index (OFGPI score measuring oppo extra-base power).
2. Alley Extra-Base Runs (AEBR net offensive runs produced into the opposite field gap).
3. Oppo Archetypes (Elite All Fields Power Monster, Pull Dependent Oppo Slapper).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterOppoGapMetrics:
    """Observed batter opposite field contact %, hard hit %, and extra-base hit %."""

    batter_id: str
    batter_name: str
    oppo_contact_pct: float = 25.0  # Opposite field contact % (benchmark ~25.0%)
    oppo_hard_hit_pct: float = 34.0  # Hard-hit % on opposite field contact (benchmark ~34.0%)
    oppo_extra_base_hit_pct: float = 8.5  # Extra-base hit % on oppo contact (benchmark ~8.5%)
    oppo_batted_balls_count: int = 100


@dataclasses.dataclass(frozen=True)
class OppoGapEvaluationResult:
    """Evaluated opposite-field power score, extra-base runs, and power tier."""

    batter_name: str
    ofgpi_score: float  # Opposite-Field Gap Power Index (0 to 160)
    aebr_runs_produced: float  # Net offensive runs produced into the opposite gap
    oppo_tier: str  # e.g. "ELITE_ALL_FIELDS_POWER_MONSTER", "PULL_DEPENDENT_OPPO_SLAPPER"
    is_elite_monster: bool


class BaseOppoGapEngine(Protocol):
    """Polymorphic protocol for opposite field gap power engines."""

    def evaluate_oppo_gap(
        self,
        metrics: BatterOppoGapMetrics,
    ) -> OppoGapEvaluationResult:
        """Calculate OFGPI score, AEBR runs, and oppo tier."""
        ...


class BatterOppoGapEngine:
    """Calculates opposite-field hard contact, extra-base conversion, and OFGPI (OPPO-GAP-01)."""

    def evaluate_oppo_gap(
        self,
        metrics: BatterOppoGapMetrics,
    ) -> OppoGapEvaluationResult:
        """Compute OFGPI rating and alley extra-base runs produced."""
        # OFGPI Score: benchmark 8.5% XBH, 34.0% hard hit, 25.0% oppo contact
        xbh_bonus = (metrics.oppo_extra_base_hit_pct - 8.5) * 3.2
        hard_bonus = (metrics.oppo_hard_hit_pct - 34.0) * 1.8
        oppo_bonus = (metrics.oppo_contact_pct - 25.0) * 0.8
        ofgpi = round(max(0.0, 100.0 + xbh_bonus + hard_bonus + oppo_bonus), 1)

        # AEBR Runs (~0.0032 runs per oppo ball in play per point above 100)
        opps = max(1, metrics.oppo_batted_balls_count)
        runs = round((ofgpi - 100.0) * (opps * 0.0032), 2)

        is_monster = (
            ofgpi >= 116.0
            and metrics.oppo_extra_base_hit_pct >= 12.5
            and metrics.oppo_hard_hit_pct >= 42.0
        )

        # Tiers
        if is_monster:
            tier = "ELITE_ALL_FIELDS_POWER_MONSTER"
        elif metrics.oppo_extra_base_hit_pct <= 5.2 or metrics.oppo_hard_hit_pct <= 22.0:
            tier = "PULL_DEPENDENT_OPPO_SLAPPER"
        elif metrics.oppo_extra_base_hit_pct >= 10.0:
            tier = "SOLID_OPPO_GAP_HITTER"
        else:
            tier = "AVERAGE_OPPOSITE_FIELD_PROFILE"

        return OppoGapEvaluationResult(
            batter_name=metrics.batter_name,
            ofgpi_score=ofgpi,
            aebr_runs_produced=runs,
            oppo_tier=tier,
            is_elite_monster=is_monster,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Oppo Gap Engine (OPPO-GAP-01)."""
    checks: list[Check] = []
    try:
        engine = BatterOppoGapEngine()
        monster = BatterOppoGapMetrics("b1", "Aaron Judge", 33.0, 52.0, 16.0, 130)
        slapper = BatterOppoGapMetrics("b2", "Pull Only Batter", 20.0, 20.0, 4.0, 80)

        r_mon = engine.evaluate_oppo_gap(monster)
        r_sla = engine.evaluate_oppo_gap(slapper)

        if (
            r_mon.oppo_tier == "ELITE_ALL_FIELDS_POWER_MONSTER"
            and r_sla.oppo_tier == "PULL_DEPENDENT_OPPO_SLAPPER"
        ):
            checks.append(
                Check(
                    "oppo gap engine",
                    True,
                    f"Oppo Gap verified (Judge OFGPI: {r_mon.ofgpi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("oppo gap engine", False, f"Unexpected oppo gap output: {r_mon}, {r_sla}")
            )
    except Exception as exc:
        checks.append(Check("oppo gap engine", False, str(exc)))
    return checks
