"""Batter In-Zone Fastball Contact vs Whiff Engine (HEAT-CHECK-01, ADR-243).

Provides in-zone fastball contact %, hard contact rate, and IZHSMI score:
1. In-Zone Heat Vulnerability & Smash Index (IZHSMI score measuring fastball dominance).
2. In-Zone Fastball Production Runs (IZFPR net offensive runs against in-zone heaters).
3. Fastball Archetypes (Heat Seeking Fastball Punisher, High Velo Whiff Machine).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterHeatCheckMetrics:
    """Observed in-zone fastball contact %, hard-hit %, and whiff %."""

    batter_id: str
    batter_name: str
    in_zone_fb_contact_pct: float = 80.0  # Contact % on zone fastballs (benchmark ~80.0%)
    in_zone_fb_hard_hit_pct: float = 42.0  # Hard-hit % on zone fastballs (benchmark ~42.0%)
    in_zone_fb_whiff_pct: float = 20.0  # Whiff % on zone fastballs (benchmark ~20.0%)
    in_zone_fb_swings_count: int = 150


@dataclasses.dataclass(frozen=True)
class HeatCheckEvaluationResult:
    """Evaluated in-zone fastball smash score, run production, and tier."""

    batter_name: str
    izhsmi_score: float  # In-Zone Heat Vulnerability & Smash Index (0 to 160)
    izfpr_runs_produced: float  # Net offensive runs produced on in-zone fastballs
    smash_tier: str  # e.g. "HEAT_SEEKING_FASTBALL_PUNISHER", "HIGH_VELO_VULNERABLE_WHIFF_MACHINE"
    is_heat_punisher: bool


class BaseHeatCheckEngine(Protocol):
    """Polymorphic protocol for in-zone fastball contact engines."""

    def evaluate_heat_check(
        self,
        metrics: BatterHeatCheckMetrics,
    ) -> HeatCheckEvaluationResult:
        """Calculate IZHSMI score, IZFPR runs, and smash tier."""
        ...


class BatterHeatCheckEngine:
    """Calculates in-zone fastball contact, whiff avoidance, and IZHSMI (HEAT-CHECK-01)."""

    def evaluate_heat_check(
        self,
        metrics: BatterHeatCheckMetrics,
    ) -> HeatCheckEvaluationResult:
        """Compute IZHSMI rating and in-zone fastball runs produced."""
        # IZHSMI Score: benchmark 20.0% whiff, 42.0% hard hit, 80.0% contact
        whiff_saving = (20.0 - metrics.in_zone_fb_whiff_pct) * 2.4
        hard_bonus = (metrics.in_zone_fb_hard_hit_pct - 42.0) * 1.8
        contact_bonus = (metrics.in_zone_fb_contact_pct - 80.0) * 1.2
        izhsmi = round(max(0.0, 100.0 + whiff_saving + hard_bonus + contact_bonus), 1)

        # IZFPR Runs (~0.0028 runs per swing per point above 100)
        swings = max(1, metrics.in_zone_fb_swings_count)
        runs = round((izhsmi - 100.0) * (swings * 0.0028), 2)

        is_punisher = (
            izhsmi >= 116.0
            and metrics.in_zone_fb_whiff_pct <= 13.0
            and metrics.in_zone_fb_hard_hit_pct >= 48.0
        )

        # Tiers
        if is_punisher:
            tier = "HEAT_SEEKING_FASTBALL_PUNISHER"
        elif metrics.in_zone_fb_whiff_pct >= 28.0 or metrics.in_zone_fb_hard_hit_pct <= 30.0:
            tier = "HIGH_VELO_VULNERABLE_WHIFF_MACHINE"
        elif metrics.in_zone_fb_hard_hit_pct >= 46.0:
            tier = "SOLID_FASTBALL_CRUSHER"
        else:
            tier = "AVERAGE_IN_ZONE_FASTBALL_HIT"

        return HeatCheckEvaluationResult(
            batter_name=metrics.batter_name,
            izhsmi_score=izhsmi,
            izfpr_runs_produced=runs,
            smash_tier=tier,
            is_heat_punisher=is_punisher,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Heat Check Engine (HEAT-CHECK-01)."""
    checks: list[Check] = []
    try:
        engine = BatterHeatCheckEngine()
        punisher = BatterHeatCheckMetrics("b1", "Yordan Alvarez", 89.0, 58.0, 11.0, 200)
        vulnerable = BatterHeatCheckMetrics("b2", "Whiff Prone", 70.0, 28.0, 30.0, 120)

        r_pun = engine.evaluate_heat_check(punisher)
        r_vul = engine.evaluate_heat_check(vulnerable)

        if (
            r_pun.smash_tier == "HEAT_SEEKING_FASTBALL_PUNISHER"
            and r_vul.smash_tier == "HIGH_VELO_VULNERABLE_WHIFF_MACHINE"
        ):
            checks.append(
                Check(
                    "heat check engine",
                    True,
                    f"Heat Check verified (Alvarez IZHSMI: {r_pun.izhsmi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("heat check engine", False, f"Unexpected heat check output: {r_pun}, {r_vul}")
            )
    except Exception as exc:
        checks.append(Check("heat check engine", False, str(exc)))
    return checks
