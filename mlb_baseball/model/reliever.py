"""Dynamic Bullpen Fatigue Decay & Manager Hierarchy Simulator (BULLPEN-01, ADR-138)."""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


class RelieverRole(enum.Enum):
    """Hierarchy ranking for bullpen arms."""

    CLOSER = "closer"
    SETUP = "setup"
    HIGH_LEVERAGE = "high_leverage"
    MIDDLE_RELIEF = "middle_relief"
    LONG_RELIEF = "long_relief"
    MOP_UP = "mop_up"


class AvailabilityStatus(enum.Enum):
    """Availability classification based on recent workload."""

    FRESH = "fresh"  # Available at 100% effectiveness
    FATIGUED = "fatigued"  # Available with penalty (diminished velo & command)
    UNAVAILABLE = "unavailable"  # Exceeded threshold (will not pitch unless emergency)


@dataclasses.dataclass(frozen=True)
class RelieverProfile:
    """Individual reliever season talent baseline and recent pitch logs."""

    player_id: str
    player_name: str
    role: RelieverRole
    true_talent_fip: float
    true_talent_k_pct: float
    pitches_yesterday: int = 0
    pitches_2d_ago: int = 0
    pitches_3d_ago: int = 0


@dataclasses.dataclass(frozen=True)
class RelieverFatigueState:
    """Evaluated workload and current day performance degradation."""

    player_id: str
    player_name: str
    role: RelieverRole
    fatigue_index: float
    status: AvailabilityStatus
    effective_fip: float
    effective_k_pct: float


@dataclasses.dataclass(frozen=True)
class BullpenDailyProjection:
    """Team-level composite bullpen availability and expected run suppression."""

    team_id: str
    team_abbrev: str
    total_bullpen_fatigue_score: float
    closer_status: AvailabilityStatus
    setup_status: AvailabilityStatus
    available_high_leverage_count: int
    expected_bullpen_fip_today: float
    fip_penalty_delta: float  # +0.35 = bullpen weakened today due to overuse


class BaseRelieverEngine(Protocol):
    """Polymorphic protocol for bullpen evaluation engines."""

    def evaluate_bullpen(
        self,
        team_id: str,
        team_abbrev: str,
        relievers: Sequence[RelieverProfile],
    ) -> tuple[BullpenDailyProjection, list[RelieverFatigueState]]:
        """Evaluate individual and composite bullpen readiness."""
        ...


class BullpenWorkloadHierarchyEngine:
    """Calculates bullpen fatigue degradation and manager usage hierarchies (BULLPEN-01)."""

    def evaluate_reliever(self, reliever: RelieverProfile) -> RelieverFatigueState:
        """Compute single reliever fatigue index and effective performance metrics."""
        # 3-day weighted fatigue index: (1.0 * yesterday) + (0.50 * 2d ago) + (0.25 * 3d ago)
        fatigue = (
            (1.00 * reliever.pitches_yesterday)
            + (0.50 * reliever.pitches_2d_ago)
            + (0.25 * reliever.pitches_3d_ago)
        )

        # Back-to-back penalty bonus (+10 if pitched both yesterday and 2d ago)
        if reliever.pitches_yesterday > 15 and reliever.pitches_2d_ago > 15:
            fatigue += 10.0

        if fatigue >= 45.0:
            status = AvailabilityStatus.UNAVAILABLE
            eff_fip = reliever.true_talent_fip + 1.25
            eff_k = reliever.true_talent_k_pct * 0.75
        elif fatigue >= 25.0:
            status = AvailabilityStatus.FATIGUED
            eff_fip = reliever.true_talent_fip + 0.45
            eff_k = reliever.true_talent_k_pct * 0.90
        else:
            status = AvailabilityStatus.FRESH
            eff_fip = reliever.true_talent_fip
            eff_k = reliever.true_talent_k_pct

        return RelieverFatigueState(
            player_id=reliever.player_id,
            player_name=reliever.player_name,
            role=reliever.role,
            fatigue_index=round(fatigue, 1),
            status=status,
            effective_fip=round(eff_fip, 2),
            effective_k_pct=round(eff_k, 3),
        )

    def evaluate_bullpen(
        self,
        team_id: str,
        team_abbrev: str,
        relievers: Sequence[RelieverProfile],
    ) -> tuple[BullpenDailyProjection, list[RelieverFatigueState]]:
        """Compute composite team bullpen projection based on reliever availability."""
        states = [self.evaluate_reliever(r) for r in relievers]

        total_fatigue = sum(s.fatigue_index for s in states)
        high_lev_roles = (RelieverRole.CLOSER, RelieverRole.SETUP, RelieverRole.HIGH_LEVERAGE)

        closer_st = AvailabilityStatus.UNAVAILABLE
        setup_st = AvailabilityStatus.UNAVAILABLE
        avail_hl_count = 0

        for s in states:
            if s.role == RelieverRole.CLOSER:
                closer_st = s.status
            elif s.role == RelieverRole.SETUP:
                setup_st = s.status

            if s.role in high_lev_roles and s.status != AvailabilityStatus.UNAVAILABLE:
                avail_hl_count += 1

        baseline_fip = float(np.mean([r.true_talent_fip for r in relievers])) if relievers else 4.00
        available_states = [s for s in states if s.status != AvailabilityStatus.UNAVAILABLE]
        if available_states:
            comp_fip = float(np.mean([s.effective_fip for s in available_states]))
        else:
            comp_fip = baseline_fip + 1.00

        fip_penalty = round(comp_fip - baseline_fip, 2)

        proj = BullpenDailyProjection(
            team_id=team_id,
            team_abbrev=team_abbrev,
            total_bullpen_fatigue_score=round(total_fatigue, 1),
            closer_status=closer_st,
            setup_status=setup_st,
            available_high_leverage_count=avail_hl_count,
            expected_bullpen_fip_today=round(comp_fip, 2),
            fip_penalty_delta=fip_penalty,
        )
        return proj, states


def health_check() -> list[Check]:
    """Operational health check for the Bullpen Workload Hierarchy Engine (BULLPEN-01)."""
    checks: list[Check] = []
    try:
        engine = BullpenWorkloadHierarchyEngine()
        arms = [
            RelieverProfile(
                "r1",
                "Closer",
                RelieverRole.CLOSER,
                true_talent_fip=2.80,
                true_talent_k_pct=0.34,
                pitches_yesterday=32,
                pitches_2d_ago=22,
            ),
            RelieverProfile(
                "r2",
                "Setup",
                RelieverRole.SETUP,
                true_talent_fip=3.20,
                true_talent_k_pct=0.30,
                pitches_yesterday=0,
                pitches_2d_ago=12,
            ),
            RelieverProfile(
                "r3",
                "Middle",
                RelieverRole.MIDDLE_RELIEF,
                true_talent_fip=3.80,
                true_talent_k_pct=0.24,
                pitches_yesterday=0,
                pitches_2d_ago=0,
            ),
        ]

        proj, states = engine.evaluate_bullpen("t1", "LAD", arms)

        if (
            states[0].status == AvailabilityStatus.UNAVAILABLE
            and states[1].status == AvailabilityStatus.FRESH
            and proj.available_high_leverage_count == 1
        ):
            checks.append(
                Check(
                    "bullpen workload hierarchy engine",
                    True,
                    f"Bullpen fatigue verified (Avail HL: {proj.available_high_leverage_count})",
                )
            )
        else:
            checks.append(
                Check(
                    "bullpen workload hierarchy engine", False, f"Unexpected bullpen state: {proj}"
                )
            )
    except Exception as exc:
        checks.append(Check("bullpen workload hierarchy engine", False, str(exc)))
    return checks
