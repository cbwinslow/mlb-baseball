"""Batter In-Zone Whiff vs Contact Quality Tradeoff Engine (ZONE-WHIFF-01, ADR-223).

Provides in-zone swing aggressiveness, whiff avoidance, and barrel conversion modeling:
1. In-Zone Contact-Power Optimization Index (ZCPOI score measuring zone damage per swing).
2. In-Zone Production Surplus Runs (IZPSR net offensive runs produced).
3. Tradeoff Archetypes (Elite Zone Crusher Master, Empty Contact Slapper, All-or-Nothing).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterZoneWhiffMetrics:
    """Observed batter in-zone swing rate, in-zone whiff rate, and in-zone barrel rate."""

    batter_id: str
    batter_name: str
    zone_swing_rate_pct: float = 68.0  # In-zone swing % (benchmark ~68.0%)
    zone_whiff_rate_pct: float = 16.0  # In-zone whiff % (benchmark ~16.0%)
    zone_barrel_per_bbe_pct: float = 9.5  # Barrel % on in-zone BBEs (benchmark ~9.5%)
    zone_swings_count: int = 350


@dataclasses.dataclass(frozen=True)
class ZoneWhiffEvaluationResult:
    """Evaluated in-zone contact-power balance, ZCPOI rating, and offensive run surplus."""

    batter_name: str
    zcpoi_score: float  # In-Zone Contact-Power Optimization Index (0 to 160)
    izpsr_runs_saved: float  # In-Zone Production Surplus Runs
    tradeoff_tier: str  # e.g. "ELITE_ZONE_CRUSHER_MASTER", "EMPTY_CONTACT_ZONE_SLAPPER"
    is_elite_crusher: bool


class BaseZoneWhiffEngine(Protocol):
    """Polymorphic protocol for zone whiff tradeoff engines."""

    def evaluate_zone_whiff(
        self,
        metrics: BatterZoneWhiffMetrics,
    ) -> ZoneWhiffEvaluationResult:
        """Calculate ZCPOI score, IZPSR runs, and tradeoff tier."""
        ...


class BatterZoneWhiffEngine:
    """Calculates in-zone swing whiff, barrel conversion, and ZCPOI (ZONE-WHIFF-01)."""

    def evaluate_zone_whiff(
        self,
        metrics: BatterZoneWhiffMetrics,
    ) -> ZoneWhiffEvaluationResult:
        """Compute ZCPOI rating and in-zone offensive run production."""
        # ZCPOI Score: benchmark 16.0% Z-Whiff, 9.5% Z-Barrel, 68.0% Z-Swing
        whiff_bonus = (16.0 - metrics.zone_whiff_rate_pct) * 2.8
        barrel_bonus = (metrics.zone_barrel_per_bbe_pct - 9.5) * 3.2
        swing_bonus = (metrics.zone_swing_rate_pct - 68.0) * 0.9
        zcpoi = round(max(0.0, 100.0 + whiff_bonus + barrel_bonus + swing_bonus), 1)

        # IZPSR Runs Saved: ~0.0024 runs per swing per point above 100
        swings = max(1, metrics.zone_swings_count)
        runs = round((zcpoi - 100.0) * (swings * 0.0024), 2)

        is_crusher = (
            zcpoi >= 118.0
            and metrics.zone_barrel_per_bbe_pct >= 12.5
            and metrics.zone_whiff_rate_pct <= 14.0
        )

        # Tiers
        if is_crusher:
            tier = "ELITE_ZONE_CRUSHER_MASTER"
        elif metrics.zone_whiff_rate_pct <= 8.5 and metrics.zone_barrel_per_bbe_pct <= 4.5:
            tier = "EMPTY_CONTACT_ZONE_SLAPPER"
        elif metrics.zone_whiff_rate_pct >= 23.0 and metrics.zone_barrel_per_bbe_pct >= 13.5:
            tier = "ALL_OR_NOTHING_ZONE_WHIFFER"
        else:
            tier = "AVERAGE_ZONE_HITTER"

        return ZoneWhiffEvaluationResult(
            batter_name=metrics.batter_name,
            zcpoi_score=zcpoi,
            izpsr_runs_saved=runs,
            tradeoff_tier=tier,
            is_elite_crusher=is_crusher,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Zone Whiff Engine (ZONE-WHIFF-01)."""
    checks: list[Check] = []
    try:
        engine = BatterZoneWhiffEngine()
        crusher = BatterZoneWhiffMetrics("b1", "Yordan Alvarez", 74.0, 10.5, 18.0, 420)
        slapper = BatterZoneWhiffMetrics("b2", "Zero Power Contact", 66.0, 6.0, 3.0, 320)

        r_cru = engine.evaluate_zone_whiff(crusher)
        r_sla = engine.evaluate_zone_whiff(slapper)

        if (
            r_cru.tradeoff_tier == "ELITE_ZONE_CRUSHER_MASTER"
            and r_sla.tradeoff_tier == "EMPTY_CONTACT_ZONE_SLAPPER"
        ):
            checks.append(
                Check(
                    "zone whiff engine",
                    True,
                    f"Zone Whiff verified (Alvarez ZCPOI: {r_cru.zcpoi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("zone whiff engine", False, f"Unexpected zone whiff output: {r_cru}, {r_sla}")
            )
    except Exception as exc:
        checks.append(Check("zone whiff engine", False, str(exc)))
    return checks
