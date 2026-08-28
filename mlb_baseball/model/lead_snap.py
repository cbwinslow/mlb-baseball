"""Baserunner Secondary Lead Distance vs Pickoff Threat Engine (LEAD-SNAP-01, ADR-229).

Provides primary lead extension, secondary jump distance, and extra-base advance modeling:
1. Aggressive Secondary Lead Index (ASLI score measuring first-to-third jump efficiency).
2. Extra-Base Advance Probability Boost (delta_P_advance on balls in play).
3. Lead Archetypes (Aggressive Terror on Basepaths, Cautious Anchored, Overextended Pickoff Risk).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class RunnerLeadSnapMetrics:
    """Observed baserunner primary lead ft, secondary lead ft, and pitcher move time."""

    runner_id: str
    runner_name: str
    primary_lead_distance_ft: float = 10.5  # Primary lead ft (benchmark ~10.5 ft)
    secondary_jump_distance_ft: float = (
        20.5  # Secondary lead at plate crossing (benchmark ~20.5 ft)
    )
    pitcher_move_time_sec: float = 1.35  # Pitcher delivery time to plate (benchmark ~1.35 s)
    pickoff_throw_rate_pct: float = 10.0  # Pickoff throw frequency % (benchmark ~10.0%)
    baserunning_opportunities: int = 75


@dataclasses.dataclass(frozen=True)
class LeadSnapEvaluationResult:
    """Evaluated secondary lead score, advance probability boost, and baserunning runs."""

    runner_name: str
    asli_score: float  # Aggressive Secondary Lead Index (0 to 160)
    advance_prob_boost_pct: float  # Extra-base advance probability boost %
    aslrv_runs_produced: float  # Net offensive runs produced from secondary leads
    lead_tier: str  # e.g. "AGGRESSIVE_TERROR_ON_BASEPATHS", "CAUTIOUS_ANCHORED_STATIONARY_RUNNER"
    is_aggressive_terror: bool


class BaseLeadSnapEngine(Protocol):
    """Polymorphic protocol for baserunner lead snap engines."""

    def evaluate_lead_snap(
        self,
        metrics: RunnerLeadSnapMetrics,
    ) -> LeadSnapEvaluationResult:
        """Calculate ASLI rating, advance boost, and run production."""
        ...


class RunnerLeadSnapEngine:
    """Calculates secondary lead distance, pickoff risk, and ASLI rating (LEAD-SNAP-01)."""

    def evaluate_lead_snap(
        self,
        metrics: RunnerLeadSnapMetrics,
    ) -> LeadSnapEvaluationResult:
        """Compute ASLI score, extra-base boost, and offensive runs produced."""
        # ASLI Score: benchmark 20.5 ft secondary, 10.5 ft primary, 1.35 s move time
        sec_bonus = (metrics.secondary_jump_distance_ft - 20.5) * 4.2
        prim_bonus = (metrics.primary_lead_distance_ft - 10.5) * 3.0
        move_bonus = (metrics.pitcher_move_time_sec - 1.35) * 25.0
        asli = round(max(0.0, 100.0 + sec_bonus + prim_bonus + move_bonus), 1)

        # Advance boost % & ASLRV Runs Produced
        adv_boost = round(max(0.0, (metrics.secondary_jump_distance_ft - 20.5) * 3.5), 1)
        opps = max(1, metrics.baserunning_opportunities)
        runs = round((asli - 100.0) * (opps * 0.0018), 2)

        is_terror = (
            asli >= 116.0
            and metrics.secondary_jump_distance_ft >= 23.0
            and metrics.primary_lead_distance_ft >= 11.5
        )

        # Tiers
        if is_terror:
            tier = "AGGRESSIVE_TERROR_ON_BASEPATHS"
        elif metrics.primary_lead_distance_ft >= 13.5 and metrics.pitcher_move_time_sec <= 1.22:
            tier = "OVEREXTENDED_PICKOFF_RISK"
        elif metrics.secondary_jump_distance_ft <= 18.0 and metrics.primary_lead_distance_ft <= 9.2:
            tier = "CAUTIOUS_ANCHORED_STATIONARY_RUNNER"
        elif metrics.secondary_jump_distance_ft >= 21.8:
            tier = "SOLID_AGGRESSIVE_BASERUNNER"
        else:
            tier = "AVERAGE_BASE_LEAD_PROFILE"

        return LeadSnapEvaluationResult(
            runner_name=metrics.runner_name,
            asli_score=asli,
            advance_prob_boost_pct=adv_boost,
            aslrv_runs_produced=runs,
            lead_tier=tier,
            is_aggressive_terror=is_terror,
        )


def health_check() -> list[Check]:
    """Operational health check for Runner Lead Snap Engine (LEAD-SNAP-01)."""
    checks: list[Check] = []
    try:
        engine = RunnerLeadSnapEngine()
        terror = RunnerLeadSnapMetrics("r1", "Elly De La Cruz", 12.8, 25.2, 1.38, 12.0, 85)
        cautious = RunnerLeadSnapMetrics("r2", "Stationary Runner", 8.8, 17.5, 1.30, 8.0, 60)

        r_ter = engine.evaluate_lead_snap(terror)
        r_cau = engine.evaluate_lead_snap(cautious)

        if (
            r_ter.lead_tier == "AGGRESSIVE_TERROR_ON_BASEPATHS"
            and r_cau.lead_tier == "CAUTIOUS_ANCHORED_STATIONARY_RUNNER"
        ):
            checks.append(
                Check(
                    "lead snap engine",
                    True,
                    f"Lead Snap verified (Elly ASLI: {r_ter.asli_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("lead snap engine", False, f"Unexpected lead snap output: {r_ter}, {r_cau}")
            )
    except Exception as exc:
        checks.append(Check("lead snap engine", False, str(exc)))
    return checks
