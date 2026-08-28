"""Batter Pull-Side / Opposite-Field Spray Power Engine (SPRAY-01, ADR-163).

Provides directional batted ball spray analysis and pull-power concentration modeling:
1. Directional Spray Decomposition (Pull%, Center%, Oppo% across GB/FB trajectories).
2. Pull Power Concentration (PPC) and Home Run Spray Distribution.
3. Spray Neutrality Index (SNI) quantifying all-fields contact dispersion.
4. Hitter Spray Archetypes (Dead Pull Slugger, All-Fields Gap Hitter, Opposite Field Spray).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterSprayMetrics:
    """Observed directional spray distribution and home run counts."""

    batter_id: str
    batter_name: str
    bats_hand: str = "R"  # "L", "R", "S"
    pull_pct: float = 0.42  # 42% pull
    center_pct: float = 0.34
    oppo_pct: float = 0.24
    hr_pull: int = 18
    hr_total: int = 22
    gb_pull_pct: float = 0.58


@dataclasses.dataclass(frozen=True)
class SprayEvaluationResult:
    """Evaluated directional spray power profile and archetype classification."""

    batter_name: str
    bats_hand: str
    pull_power_concentration_pct: float  # HR_pull / HR_total * 100
    spray_neutrality_index: float  # 0.0 to 1.0 (1.0 = perfect 33/33/33 dispersion)
    spray_archetype: str  # "DEAD_PULL_SLUGGER", "ALL_FIELDS_GAP_HITTER", "OPPO_SPRAY", "BALANCED"
    is_dead_pull_liability: bool


class BaseSprayEngine(Protocol):
    """Polymorphic protocol for batter spray direction engines."""

    def evaluate_spray(
        self,
        metrics: BatterSprayMetrics,
    ) -> SprayEvaluationResult:
        """Calculate spray power concentration and neutrality index."""
        ...


class SprayDirectionEngine:
    """Calculates directional spray dispersion, pull power, and hitter archetype (SPRAY-01)."""

    def evaluate_spray(
        self,
        metrics: BatterSprayMetrics,
    ) -> SprayEvaluationResult:
        """Compute pull power concentration and spray neutrality index."""
        # 1. Pull Power Concentration: % of HRs hit to pull side
        total_hr = max(1, metrics.hr_total)
        ppc = round((metrics.hr_pull / total_hr) * 100.0, 1)

        # 2. Spray Neutrality Index (SNI): Euclidean distance from uniform (1/3, 1/3, 1/3)
        u = 1.0 / 3.0
        dist = math.sqrt(
            (metrics.pull_pct - u) ** 2
            + (metrics.center_pct - u) ** 2
            + (metrics.oppo_pct - u) ** 2
        )
        sni = round(float(np.clip(1.0 - (dist * 2.2), 0.0, 1.0)), 2)

        # 3. Dead-pull liability flag (heavy pull GBs + high pull%)
        is_dead_pull = metrics.pull_pct >= 0.48 or (
            metrics.gb_pull_pct >= 0.65 and metrics.pull_pct >= 0.44
        )

        # 4. Spray Archetype
        if metrics.pull_pct >= 0.46 and ppc >= 75.0:
            archetype = "DEAD_PULL_SLUGGER"
        elif sni >= 0.82:
            archetype = "ALL_FIELDS_GAP_HITTER"
        elif metrics.oppo_pct >= 0.32:
            archetype = "OPPO_SPRAY"
        else:
            archetype = "BALANCED"

        return SprayEvaluationResult(
            batter_name=metrics.batter_name,
            bats_hand=metrics.bats_hand,
            pull_power_concentration_pct=ppc,
            spray_neutrality_index=sni,
            spray_archetype=archetype,
            is_dead_pull_liability=is_dead_pull,
        )


def health_check() -> list[Check]:
    """Operational health check for the Spray Direction Engine (SPRAY-01)."""
    checks: list[Check] = []
    try:
        engine = SprayDirectionEngine()
        pull_slugger = BatterSprayMetrics(
            "b1",
            "Pull Slugger",
            bats_hand="L",
            pull_pct=0.50,
            center_pct=0.30,
            oppo_pct=0.20,
            hr_pull=28,
            hr_total=30,
        )
        all_fields = BatterSprayMetrics(
            "b2",
            "Contact Sprayer",
            bats_hand="R",
            pull_pct=0.34,
            center_pct=0.34,
            oppo_pct=0.32,
            hr_pull=5,
            hr_total=12,
        )

        r_pull = engine.evaluate_spray(pull_slugger)
        r_all = engine.evaluate_spray(all_fields)

        if (
            r_pull.spray_archetype == "DEAD_PULL_SLUGGER"
            and r_all.spray_archetype == "ALL_FIELDS_GAP_HITTER"
        ):
            checks.append(
                Check(
                    "spray direction engine",
                    True,
                    f"Spray verified (PPC: {r_pull.pull_power_concentration_pct:.1f}%)",
                )
            )
        else:
            checks.append(
                Check(
                    "spray direction engine", False, f"Unexpected spray output: {r_pull}, {r_all}"
                )
            )
    except Exception as exc:
        checks.append(Check("spray direction engine", False, str(exc)))
    return checks
